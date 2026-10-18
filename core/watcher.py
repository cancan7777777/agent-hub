"""watcher - 监听各 agent 的技能目录与 MCP 配置，外部新增时自动纳入管理器。

设计要点
  * 只做目录列举 + stat，不读文件内容，单轮约 0.05 秒
  * 发现变化才失效指纹缓存，界面按需增量刷新
  * 技能：auto_host 开启时自动收进真源并铺满各 agent
  * MCP ：始终吸收进 Hub 主列表（只写自己的文件，不碰 agent 配置）
"""
from __future__ import annotations
import hashlib, os, threading, time

import registry
from fsutil import link_kind, read_target
from scan import list_skill_dirs

REV = 0
NOTICES: list = []
_LOCK = threading.Lock()
_STOP = threading.Event()
_WATCHED_MCP: list = []
_WATCHED_PLUGINS: list = []
_DIRS: list = []
_LAST_SIG = ""
AUTO_HOST = True


def collect_watch_targets():
    dirs = [registry.CANONICAL, os.path.join(registry.CANONICAL, "_hub_disabled")]
    global _WATCHED_MCP, _WATCHED_PLUGINS
    _WATCHED_MCP, _WATCHED_PLUGINS = [], []
    for a in registry.AGENTS + [registry.SOURCE_ONLY]:
        for sd in a["skills"]:
            dirs.append(os.path.abspath(sd["path"]))
        spec = a.get("mcp") or {}
        if spec.get("path"):
            _WATCHED_MCP.append(os.path.abspath(spec["path"]))
        for pspec in a.get("plugins") or []:
            p = os.path.abspath(pspec["path"])
            if p not in _WATCHED_PLUGINS:
                _WATCHED_PLUGINS.append(p)
    _DIRS[:] = sorted(set(d for d in dirs if os.path.isdir(d)))


def _sig() -> str:
    h = hashlib.sha256()
    for base in _DIRS:
        h.update(base.encode("utf-8", "replace"))
        try:
            for name in sorted(os.listdir(base)):
                p = os.path.join(base, name)
                if not os.path.isdir(p):
                    continue
                try:
                    st = os.stat(p, follow_symlinks=False)
                    h.update(("%s|%d|%d" % (name, st.st_mtime_ns, st.st_size)).encode())
                except OSError:
                    h.update(name.encode())
        except OSError:
            h.update(b"<missing>")
    for path in _WATCHED_MCP + _WATCHED_PLUGINS:
        h.update(path.encode("utf-8", "replace"))
        try:
            st = os.stat(path)
            h.update(("%d|%d" % (st.st_mtime_ns, st.st_size)).encode())
        except OSError:
            h.update(b"<missing>")
    return h.hexdigest()[:24]


def notify(kind, text):
    with _LOCK:
        NOTICES.append(dict(kind=kind, text=text, ts=time.time()))
        del NOTICES[:-30]


def bump():
    global REV
    with _LOCK:
        REV += 1


def status(since=0.0):
    with _LOCK:
        return dict(rev=REV, auto_host=AUTO_HOST,
                    notices=[n for n in NOTICES if n["ts"] > since][-8:],
                    watched=len(_DIRS))


def set_auto_host(on):
    global AUTO_HOST
    AUTO_HOST = bool(on)
    st = registry.load_state()
    st["auto_host"] = AUTO_HOST
    registry.save_state(st)


def load_pref():
    set_auto_host(registry.load_state().get("auto_host", True))


# ---------------- 归集：MCP ----------------
def reconcile_mcp():
    """把各 agent 配置里有、Hub 主列表还没有的 MCP 服务器吸收进来。
    只写 Hub 自己的 data/mcp.json，不改任何 agent 配置。"""
    import mcp_hub
    master = mcp_hub.load_master()
    disabled = set(master.get("disabled", []))
    added = []
    for a in registry.AGENTS:
        spec = a.get("mcp")
        if not spec:
            continue
        path, fmt, key = spec["path"], spec["format"], spec["key"]
        if not os.path.isfile(path):
            continue
        try:
            cur = mcp_hub.read_entries(path, fmt, key)
        except Exception:
            continue
        for name, entry in cur.items():
            if name in master["servers"]:
                continue
            master["servers"][name] = mcp_hub.std_from_entry(fmt, entry)
            master.setdefault("origin", {})[name] = a["id"]
            if mcp_hub.entry_is_off(fmt, entry):
                disabled.add(name)
            added.append("%s（来自 %s）" % (name, a["name"]))
    if added:
        master["disabled"] = sorted(disabled)
        mcp_hub.save_master(master)
        notify("mcp", "发现新 MCP 服务器并已纳入管理：%s"
               % "、".join(added[:6]) + ("…" if len(added) > 6 else ""))
        bump()
    return added


# ---------------- 归集：技能 ----------------
def reconcile_skills(force=False):
    """发现各 agent 目录里尚未进真源的技能；force 或 auto_host 开启时自动托管。"""
    import consolidate
    st = registry.load_state()
    ignored = set(st.get("ignored_skills", []))
    present = {n for n, _ in list_skill_dirs(registry.CANONICAL)}
    present |= {n for n, _ in list_skill_dirs(os.path.join(registry.CANONICAL, "_hub_disabled"))}
    found = []
    for a in registry.AGENTS:
        if a.get("read_only"):
            continue
        for sd in a["skills"]:
            base = os.path.abspath(sd["path"])
            if base == os.path.abspath(registry.CANONICAL):
                continue
            for name, path in list_skill_dirs(base):
                if name in present or name in ignored or name.startswith(("_", ".")):
                    continue
                if name in sd.get("protect", []):
                    continue
                if link_kind(path) != "real":
                    continue
                present.add(name)
                found.append((name, a["name"]))
    if not found:
        return []
    if not (force or AUTO_HOST):
        notify("skill", "发现 %d 个未托管技能：%s"
               % (len(found), "、".join(n for n, _ in found[:5]) + ("…" if len(found) > 5 else "")))
        bump()
        return found
    ok = []
    for name, _ag in found:
        try:
            if consolidate.host_one(name).get("ok"):
                ok.append(name)
        except Exception:
            pass
    if ok:
        notify("host", "自动托管 %d 个新技能：%s"
               % (len(ok), "、".join(ok[:6]) + ("…" if len(ok) > 6 else "")))
        bump()
    return found


# ---------------- 主循环 ----------------
def loop(interval=2.0):
    global _LAST_SIG
    collect_watch_targets()
    load_pref()
    _LAST_SIG = _sig()
    while not _STOP.is_set():
        _STOP.wait(interval)
        if _STOP.is_set():
            break
        try:
            sig = _sig()
        except Exception:
            continue
        if sig == _LAST_SIG:
            continue
        _LAST_SIG = sig
        import fsutil
        fsutil.invalidate_tree()
        bump()
        try:
            reconcile_mcp()
        except Exception as e:
            notify("err", "MCP 归集失败：" + str(e)[:140])
        try:
            reconcile_skills()
        except Exception as e:
            notify("err", "技能归集失败：" + str(e)[:140])
        collect_watch_targets()
        _LAST_SIG = _sig()


def start(interval=2.0):
    t = threading.Thread(target=loop, args=(interval,), daemon=True)
    t.start()
    return t


def stop():
    _STOP.set()
