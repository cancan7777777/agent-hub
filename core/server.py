"""server - 本地 HTTP 服务：静态 UI + JSON API。仅监听 127.0.0.1，绝不对外。"""
from __future__ import annotations
import json, os, socket, sys, threading, traceback, time, uuid, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry, scan, consolidate, mcp_hub, plugin_hub, watcher, autostart
import fsutil
from fsutil import (dir_fingerprint, link_kind, make_junction, remove_path, read_target,
                    copy_tree, USERPROFILE)
from scan import list_skill_dirs
fsutil_backup = fsutil.backup_tree

UI = os.path.join(registry.ROOT, "ui")
fsutil.set_cache_file(registry.FPCACHE)
_LOCK = threading.RLock()
_CACHE: dict = {"scan": None, "ts": 0.0}
_JOBS: dict = {}
_PORT = [0]           # 实际监听端口，自启动状态要用它回显


def get_scan(force=False, max_age=6.0):
    with _LOCK:
        if force:
            fsutil.invalidate_tree()
        if force or _CACHE["scan"] is None or (time.time() - _CACHE["ts"]) > max_age:
            _CACHE["scan"] = scan.scan()
            _CACHE["ts"] = time.time()
        return _CACHE["scan"]


# ---------- 后台作业 ----------
def job_start(kind, fn):
    jid = uuid.uuid4().hex[:8]
    _JOBS[jid] = dict(id=jid, kind=kind, state="running", done=0, total=0,
                      log=[], started=time.time(), result=None)
    def run():
        try:
            res = fn(jid)
            _JOBS[jid].update(state="done", result=res)
        except Exception as e:
            _JOBS[jid].update(state="error", error=str(e),
                              tb=traceback.format_exc().splitlines()[-4:])
        _JOBS[jid]["finished"] = time.time()
    threading.Thread(target=run, daemon=True).start()
    return jid


def job_tick(jid, **kw):
    j = _JOBS.get(jid)
    if j:
        j.update(kw)


# ---------- 视图数据 ----------
def parse_skill_md(path: str) -> dict:
    md = os.path.join(path, "SKILL.md")
    out = dict(name="", desc="", has_md=False, bytes=0)
    if not os.path.isfile(md):
        return out
    try:
        with open(md, encoding="utf-8", errors="replace") as fh:
            txt = fh.read()
    except Exception:
        return out
    out["has_md"] = True
    out["bytes"] = len(txt.encode("utf-8", "replace"))
    if txt.lstrip().startswith("---"):
        body = txt.lstrip()[3:]
        end = body.find("\n---")
        head = body[:end] if end > 0 else ""
        for line in head.splitlines():
            if ":" in line and not line.startswith((" ", "\t", "-")):
                k, _, v = line.partition(":")
                k = k.strip().lower()
                v = v.strip().strip("\"'")
                if k == "name" and len(v) < 120:
                    out["name"] = v
                elif k == "description":
                    out["desc"] = v[:900]
    return out


def build_state(force=False, since=0.0) -> dict:
    s = get_scan(force=force)
    st = registry.load_state()
    matrix = s["matrix"]
    view_by_agent: dict = {}
    for v in s["views"]:
        view_by_agent.setdefault(v["agent"], []).append(v)

    defaults = set(registry.default_install_ids())
    agent_meta = []
    for a in registry.ordered_agents():
        dirs = []
        for v in view_by_agent.get(a["id"], []):
            k = link_kind(os.path.abspath(v["dir"]))
            dirs.append(dict(path=os.path.abspath(v["dir"]), kind=k, exists=v["exists"],
                             role=v["role"], native_read=v["native_read"], retire=v.get("retire", False),
                             count=v["count"],
                             target=read_target(v["dir"]) if k in ("junction", "symlink") else None))
        mspec = a.get("mcp") or {}
        cnt = len({n for n, r in matrix.items()
                   if r.get("by_agent", {}).get(a["id"], {}).get("present")})
        agent_meta.append(dict(id=a["id"], name=a["name"], vendor=a["vendor"], color=a["color"],
                               icon=a.get("icon", ""),
                               default_install=a["id"] in defaults,
                               verified=a.get("verified", False), read_only=a.get("read_only", False),
                               note=a.get("note", ""), dirs=dirs, mcp_path=mspec.get("path"),
                               mcp_exists=os.path.isfile(mspec.get("path", "")) if mspec else False,
                               mcp_format=mspec.get("format"), skill_count=cnt))

    drift = [n for n, r in matrix.items() if r["drift"]]
    hosted = [n for n, r in matrix.items() if r["canonical"]]
    protected = [n for n, r in matrix.items()
                 if r.get("protected") and not r["canonical"] and not r["ignored"]]
    unhosted = [n for n, r in matrix.items()
                if not r["canonical"] and not r["ignored"] and not r.get("protected")]
    disabled = [n for n, r in matrix.items() if r["ignored"]]
    writable = lambda l: l["role"] != "source"
    linked = sum(1 for r in matrix.values() for l in r["locations"].values()
                 if l["kind"] in ("junction", "symlink") and writable(l))
    real_copies = sum(1 for r in matrix.values() for l in r["locations"].values()
                      if l["kind"] == "real" and writable(l))

    skills = []
    for n, r in sorted(matrix.items()):
        row = dict(r)
        row["meta"] = parse_skill_md(os.path.join(registry.CANONICAL, n)) if r["canonical"] else {}
        if not row["meta"].get("name"):
            for l in r["locations"].values():
                if os.path.isfile(os.path.join(l["path"], "SKILL.md")):
                    row["meta"] = parse_skill_md(l["path"])
                    break
        skills.append(row)

    bk = os.path.join(registry.BACKUPS)
    n_bk = len(os.listdir(bk)) if os.path.isdir(bk) else 0
    sz_bk = sum(os.path.getsize(os.path.join(bk, f)) for f in os.listdir(bk)
                if os.path.isfile(os.path.join(bk, f))) if os.path.isdir(bk) else 0

    return dict(agents=agent_meta, canonical_dir=registry.CANONICAL, root=registry.ROOT,
                canonical_info=dict(exists=os.path.isdir(registry.CANONICAL),
                                    kind=link_kind(registry.CANONICAL), count=len(s["canonical"])),
                agents_home=dict(path=registry.AGENTS_SKILLS, kind=link_kind(registry.AGENTS_SKILLS),
                                 target=read_target(registry.AGENTS_SKILLS)),
                hub_disabled_dir=os.path.join(registry.CANONICAL, "_hub_disabled"),
                default_install=sorted(defaults),
                skills=skills,
                stats=dict(skills=len(matrix), hosted=len(hosted), drift=len(drift),
                           unhosted=len(unhosted), disabled=len(disabled), linked=linked,
                           protected=len(protected),
                           real_copies=real_copies,
                           bytes_wasted=sum(r["bytes_total"] for r in matrix.values() if r["drift"]),
                           backups=n_bk, backup_bytes=sz_bk),
                last_apply=st.get("last_apply"), generated=s["generated"],
                watch=watcher.status(since),
                autostart=autostart.status(_PORT[0] or autostart.DEFAULT_PORT))


def mcp_view() -> dict:
    master = mcp_hub.load_master()
    disabled = set(master.get("disabled", []))
    agents = []
    for a in registry.ordered_agents():
        spec = a.get("mcp")
        if not spec:
            continue
        path, fmt, key = spec["path"], spec["format"], spec["key"]
        cur = mcp_hub.read_entries(path, fmt, key)
        agents.append(dict(id=a["id"], name=a["name"], color=a["color"],
                           icon=a.get("icon", ""), path=path,
                           exists=os.path.isfile(path), format=fmt,
                           can_off=mcp_hub.can_off(fmt, a["id"]),
                           present=sorted(cur), raw=cur))
    rows = []
    for name, cfg in sorted(master["servers"].items()):
        flags = {}
        for x in agents:
            entry = x["raw"].get(name)
            flags[x["id"]] = (not mcp_hub.entry_is_off(x["format"], entry)) if entry else None
        rows.append(dict(name=name, config=cfg, global_off=name in disabled,
                         origin=master.get("origin", {}).get(name),
                         agents={x["id"]: (name in x["present"]) for x in agents},
                         enabled_flags=flags))
    return dict(master=master, agents=agents, rows=rows)


# ---------- 写操作 ----------
def skill_row(name: str) -> dict:
    """只重算单个技能在各目录的分布，供前端局部更新，避免全量扫描。"""
    st = registry.load_state()
    ignored = set(st.get("ignored_skills", []))
    canon = os.path.join(registry.CANONICAL, name)
    ck = link_kind(canon)
    chash = dir_fingerprint(canon)["hash"] if ck == "real" and os.path.isdir(canon) else None
    locations, by_agent = {}, {}
    for a in registry.AGENTS + registry.SOURCES:
        for i, sd in enumerate(a["skills"]):
            base = os.path.abspath(sd["path"])
            tgt = os.path.join(base, name)
            k = link_kind(tgt)
            if k == "missing":
                continue
            if sd.get("retire"):
                continue
            fp = dir_fingerprint(tgt)
            locations[f"{a['id']}#{i}"] = dict(
                agent=a["id"], dir=base, role=sd["role"], path=tgt, kind=k,
                hash=fp["hash"], target=read_target(tgt) if k != "real" else None,
                files=fp["files"], bytes=fp["bytes"],
                matches_canonical=(chash is not None and fp["hash"] == chash))
            ag = by_agent.setdefault(a["id"], dict(present=True, kinds=[], hashes=[], dirs=[],
                                                   native_read=bool(sd.get("native_read")),
                                                   read_only=bool(a.get("read_only"))))
            ag["kinds"].append(k); ag["hashes"].append(fp["hash"]); ag["dirs"].append(base)
    protected_set = set()
    for a in registry.AGENTS + registry.SOURCES:
        for sd in a["skills"]:
            for pn in sd.get("protect", []):
                protected_set.add((a["id"], pn))
    loc_list = list(locations.values())
    is_builtin = bool(loc_list) and all((l["agent"], name) in protected_set for l in loc_list)
    is_source_only = bool(loc_list) and all(l["role"] == "source" for l in loc_list)
    is_protected = is_builtin or is_source_only
    hashes = {l["hash"] for l in locations.values()}
    if chash:
        hashes.add(chash)
    copies = sum(1 for l in locations.values() if l["kind"] == "real" and l["role"] != "source")
    total = (dir_fingerprint(canon)["bytes"] if chash else 0)
    present = sorted(a for a, x in by_agent.items() if x["present"])
    return dict(name=name, canonical=bool(chash), canonical_hash=chash,
                ignored=name in ignored, protected=is_protected,
                builtin=is_builtin, source_only=is_source_only,
                locations=locations, by_agent=by_agent,
                variant_count=len(hashes), drift=len(hashes) > 1, copies=copies,
                bytes_total=total, agents_present=present, agent_count=len(present),
                meta=parse_skill_md(canon) if chash else {})


def forget_paths(*paths):
    """只失效受影响路径的指纹缓存。不 bump watcher：
    UI 自己的写操作若触发 bump，会让随后的轮询整页重建、把滚动位置弹回顶部。"""
    for x in paths:
        try:
            fsutil.forget(x)
        except Exception:
            pass


def set_skill_for_agent(skill: str, agent_id: str, on: bool) -> dict:
    a = next((x for x in registry.AGENTS if x["id"] == agent_id), None)
    if not a:
        return dict(ok=False, msg="未知 agent")
    if a.get("read_only"):
        return dict(ok=False, msg="来源目录只读，不参与分发")
    promoted = False
    canon = os.path.join(registry.CANONICAL, skill)
    if on and not os.path.isdir(canon):
        # 只有「装上」才需要托管；「收回」绝不能顺手把技能吸进真源
        h = consolidate.host_one(skill, force=True)
        if not h.get("ok") or not os.path.isdir(canon):
            return dict(ok=False, msg=h.get("msg") or ("\u300c" + skill + "\u300d\u65e0\u6cd5\u6258\u7ba1"))
        promoted = True
    if not on and not os.path.isdir(canon):
        # 真源里没有：收回就等于把该 agent 下的实体副本移除（先备份）
        out = []
        for sd in a["skills"]:
            base = os.path.abspath(sd["path"])
            tgt = os.path.join(base, skill)
            k = link_kind(tgt)
            if k == "missing":
                continue
            if k == "real":
                b = fsutil_backup(tgt, registry.BACKUPS, "retract-%s-%s" % (agent_id, skill))
                out.append(dict(dir=base, ok=remove_path(tgt),
                                msg="移除实体副本" + ("（已备份）" if b else "（备份失败）")))
            else:
                out.append(dict(dir=base, ok=remove_path(tgt), msg="断开联接"))
        forget_paths(os.path.join(registry.CANONICAL, skill))
        return dict(ok=bool(out) and all(x["ok"] for x in out), detail=out,
                    msg="" if out else "该 agent 上没有这个技能")
    out, touched = [], []
    for sd in a["skills"]:
        base = os.path.abspath(sd["path"])
        if base == os.path.abspath(registry.AGENTS_SKILLS):
            continue
        tgt = os.path.join(base, skill)
        touched.append(tgt)
        if on:
            os.makedirs(base, exist_ok=True)
            k = link_kind(tgt)
            cur = read_target(tgt) if k in ("junction", "symlink") else None
            if cur and os.path.abspath(cur) == canon:
                out.append(dict(dir=base, ok=True, msg="已经是正确联接"))
                continue
            if k == "real":
                fsutil_backup(tgt, registry.BACKUPS, "cell-%s-%s" % (agent_id, skill))
                remove_path(tgt)
            ok = make_junction(canon, tgt)
            out.append(dict(dir=base, ok=ok, msg="建立联接" if ok else "联接失败"))
        else:
            k = link_kind(tgt)
            if k == "missing":
                out.append(dict(dir=base, ok=True, msg="本来就没有"))
            elif k == "real":
                # 实体副本可能含用户改动，删除前必须备份
                b = fsutil_backup(tgt, registry.BACKUPS, "retract-%s-%s" % (agent_id, skill))
                ok = remove_path(tgt)
                out.append(dict(dir=base, ok=ok,
                                msg="移除实体副本" + ("（已备份）" if b else "（备份失败）")))
            else:
                out.append(dict(dir=base, ok=remove_path(tgt), msg="断开联接"))
    forget_paths(*touched, os.path.join(registry.CANONICAL, skill))
    return dict(ok=all(x["ok"] for x in out) if out else False, detail=out,
                promoted=promoted, row=skill_row(skill),
                msg=("" if out else "该 agent 无可写入目录"))


def set_global_enabled(items: list, on: bool) -> dict:
    off_dir = os.path.join(registry.CANONICAL, "_hub_disabled")
    st = registry.load_state()
    ignored = set(st.get("ignored_skills", []))
    changed = []
    for name in items:
        src = os.path.join(registry.CANONICAL, name)
        dst = os.path.join(off_dir, name)
        if on:
            if os.path.isdir(dst):
                if link_kind(src) != "real":
                    remove_path(src)
                    copy_tree_ok = make_junction(dst, src)
                changed.append(dict(name=name, ok=os.path.isdir(src)))
            ignored.discard(name)
        else:
            if os.path.isdir(src) and not os.path.isdir(dst):
                os.makedirs(off_dir, exist_ok=True)
                try:
                    os.rename(src, dst)
                    ok = True
                except OSError:
                    ok = False
                changed.append(dict(name=name, ok=ok))
            ignored.add(name)
    st["ignored_skills"] = sorted(ignored)
    registry.save_state(st)
    get_scan(force=True)
    return dict(ok=True, changed=changed, disabled=sorted(ignored))


def mcp_push(name: str) -> dict:
    """把主列表里的一台服务器推送到所有 agent。"""
    master = mcp_hub.load_master()
    if name not in master["servers"]:
        return dict(ok=False, msg="主列表没有这台服务器")
    cfg = master["servers"][name]
    off = name in set(master.get("disabled", []))
    res = []
    for a in registry.AGENTS:
        spec = a.get("mcp")
        if not spec:
            continue
        fmt = spec["format"]
        if off and not mcp_hub.can_off(fmt, a["id"]):
            res.append(dict(agent=a["id"], ok=True, skipped=True,
                            msg="该格式无停用字段，跳过（可直接移除）"))
            continue
        ok, msg = mcp_hub.write_entry(spec["path"], fmt, spec["key"], name, cfg, on=not off, agent_id=a["id"])
        res.append(dict(agent=a["id"], ok=ok, msg=msg, path=spec["path"]))
    return dict(ok=all(r["ok"] for r in res), results=res)


def mcp_set_one(agent_id: str, name: str, on: bool) -> dict:
    """只给某个 agent 写入 / 停用 / 启用一台服务器。"""
    a = next((x for x in registry.AGENTS if x["id"] == agent_id), None)
    if not a or not a.get("mcp"):
        return dict(ok=False, msg="该 agent 无 MCP 配置")
    master = mcp_hub.load_master()
    spec = a["mcp"]
    fmt = spec["format"]
    if not on and not mcp_hub.can_off(fmt, agent_id):
        return dict(ok=False, msg="%s 的配置无停用字段，请改用「移除」" % a["name"])
    if name not in master["servers"]:
        return dict(ok=False, msg="主列表没有这台服务器")
    ok, msg = mcp_hub.write_entry(spec["path"], fmt, spec["key"], name,
                                  master["servers"][name], on=on, agent_id=agent_id)
    return dict(ok=ok, msg=msg, agent=agent_id)


def mcp_drop(agent_id: str, name: str) -> dict:
    """从某个 agent 的配置里移除一台服务器。"""
    a = next((x for x in registry.AGENTS if x["id"] == agent_id), None)
    if not a or not a.get("mcp"):
        return dict(ok=False, msg="无配置")
    spec = a["mcp"]
    ok, msg = mcp_hub.write_entry(spec["path"], spec["format"], spec["key"], name, None)
    return dict(ok=ok, msg=msg, agent=agent_id)


def add_skill(src_path, host=True):
    """从外部目录或 zip 导入技能到真源；host=True 时顺手托管并铺满各 agent。"""
    import shutil, zipfile
    src = os.path.abspath(os.path.expandvars((src_path or "").strip().strip('"')))
    if not src or not os.path.exists(src):
        return dict(ok=False, msg="路径不存在：" + (src or "(空)"))
    consolidate.ensure_canonical_dir()
    tmp = None
    if zipfile.is_zipfile(src):
        tmp = os.path.join(registry.DATA, "_import_tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        with zipfile.ZipFile(src) as z:
            z.extractall(tmp)
        src = tmp
        if not os.path.isfile(os.path.join(src, "SKILL.md")):
            kids = [os.path.join(src, d) for d in sorted(os.listdir(src))
                    if os.path.isdir(os.path.join(src, d))]
            if len(kids) == 1 and os.path.isfile(os.path.join(kids[0], "SKILL.md")):
                src = kids[0]
    if not os.path.isdir(src):
        return dict(ok=False, msg="只接受技能目录或 zip 包")
    if os.path.isfile(os.path.join(src, "SKILL.md")):
        roots = [src]
    else:
        roots = [pth for _n, pth in list_skill_dirs(src)]
    if not roots:
        return dict(ok=False, msg="没找到含 SKILL.md 的技能目录")
    added, failed = [], []
    good = []
    for r in roots:
        name = os.path.basename(r.rstrip("\\/"))
        if not name or name.startswith((".", "_")):
            failed.append(name + ": 技能目录名不能以 . 或 _ 开头")
            continue
        good.append((name, r))
    if not good:
        return dict(ok=False, added=[], failed=failed or ["没有可用的技能目录"], host=host)
    for name, r in good:
        dst = os.path.join(registry.CANONICAL, name)
        if os.path.isdir(dst):
            fsutil_backup(dst, registry.BACKUPS, "overwrite-" + name)
            remove_path(dst)
        if not copy_tree(r, dst):
            failed.append(name)
            continue
        added.append(name)
        if host:
            res = consolidate.host_one(name)
            if not res.get("ok"):
                failed.append(name + ": " + str(res.get("msg")))
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    get_scan(force=True)
    watcher.bump()
    return dict(ok=not failed, added=added, failed=failed, host=host)


# ---------- HTTP ----------
CT = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
      ".css": "text/css; charset=utf-8", ".woff2": "font/woff2", ".woff": "font/woff",
      ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml",
      ".json": "application/json; charset=utf-8", ".ico": "image/x-icon"}


class HubServer(ThreadingHTTPServer):
    """Windows 的 SO_REUSEADDR 语义是"允许抢占已监听端口"，两份实例会同时写配置。
    关掉它，端口被占就报错，由调用方决定是安静退出还是换端口。"""
    allow_reuse_address = False
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentHub/1.0"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        u = urlparse(self.path).path
        q = parse_qs(urlparse(self.path).query)
        try:
            if u == "/api/state":
                return self._send(200, build_state(force=q.get("fresh", ["0"])[0] == "1"))
            if u == "/api/mcp":
                return self._send(200, mcp_view())
            if u == "/api/plugins":
                return self._send(200, plugin_hub.scan_plugins())
            if u == "/api/autostart":
                return self._send(200, autostart.status(_PORT[0] or autostart.DEFAULT_PORT))
            if u == "/api/watch":
                return self._send(200, watcher.status(float(q.get("since", ["0"])[0] or 0)))
            if u == "/api/plan":
                return self._send(200, consolidate.build_plan())
            if u == "/api/job":
                return self._send(200, _JOBS.get(q.get("id", [""])[0], dict(state="unknown")))
            if u == "/api/skill/detail":
                name = q.get("name", [""])[0]
                if not name or name != os.path.basename(name):
                    return self._send(400, dict(error="非法技能名"))
                p = os.path.join(registry.CANONICAL, name)
                if not os.path.isdir(p):
                    # 未收敛时回落到任意一处实体副本，保证详情可读
                    st0 = get_scan()
                    row = st0["matrix"].get(name)
                    for l in (row or {}).get("locations", {}).values():
                        if l["kind"] == "real" and os.path.isdir(l["path"]):
                            p = l["path"]
                            break
                    else:
                        return self._send(404, dict(error="找不到该技能目录"))
                files = []
                for root, dirs, fs in os.walk(p):
                    dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")][:12]
                    for f in fs[:40]:
                        fp = os.path.join(root, f)
                        files.append(os.path.relpath(fp, p).replace("\\", "/"))
                    if len(files) > 160:
                        break
                md = os.path.join(p, "SKILL.md")
                txt = ""
                if os.path.isfile(md):
                    with open(md, encoding="utf-8", errors="replace") as fh:
                        txt = fh.read(60000)
                return self._send(200, dict(name=name, files=files[:200], skill_md=txt,
                                            meta=parse_skill_md(p)))
            if u in ("/", "/index.html"):
                u = "/index.html"
            fp = os.path.abspath(os.path.join(UI, u.lstrip("/")))
            if not fp.startswith(os.path.abspath(UI)) or not os.path.isfile(fp):
                return self._send(404, "not found")
            return self._send(200, open(fp, "rb").read(), CT.get(os.path.splitext(fp)[1].lower(), "application/octet-stream"))
        except Exception as e:
            return self._send(500, dict(error=str(e), tb=traceback.format_exc().splitlines()[-4:]))

    def do_POST(self):
        u = urlparse(self.path).path
        b = self._body()
        try:
            with _LOCK:
                if u == "/api/autohost":
                    watcher.set_auto_host(bool(b.get("on")))
                    return self._send(200, dict(ok=True, auto_host=watcher.AUTO_HOST))
                if u == "/api/autostart":
                    r = autostart.set_enabled(bool(b.get("on")),
                                              _PORT[0] or autostart.DEFAULT_PORT)
                    return self._send(200 if r.get("ok") else 500, r)
                if u == "/api/default_install":
                    ids = registry.set_default_install(b.get("agents"))
                    return self._send(200, dict(ok=True, default_install=ids))
                if u == "/api/skill/add":
                    return self._send(200, add_skill(b.get("path", ""), bool(b.get("host", True))))
                if u == "/api/consolidate/apply":
                    def work(jid):
                        job_tick(jid, stage="扫描并生成计划")
                        plan = consolidate.build_plan()
                        job_tick(jid, total=len(plan["actions"]), plan_counts=plan["counts"])
                        def prog(i, n, a):
                            job_tick(jid, done=i, current=f"{a['op']}:{a.get('skill','')}")
                        r = consolidate.apply_plan(plan, progress=prog)
                        get_scan(force=True)
                        return dict(done=len(r["done"]), failed=r["failed"], backups=r["backups"])
                    return self._send(200, dict(job=job_start("consolidate", work)))
                if u == "/api/import/all":
                    r = consolidate.import_all()
                    fsutil.invalidate_tree()
                    get_scan(force=True)
                    return self._send(200, r)
                if u == "/api/skill/host":
                    r = consolidate.host_one(b["skill"])
                    fsutil.invalidate_tree()
                    r["row"] = skill_row(b["skill"])
                    return self._send(200, r)
                if u == "/api/skill/unhost":
                    r = consolidate.unhost_one(b["skill"])
                    fsutil.invalidate_tree()
                    r["row"] = skill_row(b["skill"])
                    return self._send(200, r)
                if u == "/api/skill/agent":
                    return self._send(200, set_skill_for_agent(b["skill"], b["agent"], bool(b["on"])))
                if u == "/api/skill/global":
                    g = set_global_enabled(b.get("skills", []), bool(b["on"]))
                    fsutil.invalidate_tree()
                    g["rows"] = {n: skill_row(n) for n in b.get("skills", []) if n}
                    return self._send(200, g)
                if u == "/api/mcp/save":
                    m = mcp_hub.load_master()
                    old = b.get("old_name") or b.get("name")
                    if b.get("remove"):
                        m["servers"].pop(old, None)
                        m["disabled"] = [x for x in m.get("disabled", []) if x != old]
                    else:
                        if old != b.get("name"):
                            m["servers"].pop(old, None)
                        m["servers"][b["name"]] = b.get("config") or {}
                    mcp_hub.save_master(m)
                    return self._send(200, dict(ok=True, servers=list(m["servers"])))
                if u == "/api/mcp/global":
                    m = mcp_hub.load_master()
                    d = set(m.get("disabled", []))
                    (d.discard if b.get("on") else d.add)(b["name"])
                    m["disabled"] = sorted(d)
                    mcp_hub.save_master(m)
                    return self._send(200, dict(ok=True, disabled=m["disabled"]))
                if u == "/api/mcp/push":
                    return self._send(200, mcp_push(b["name"]))
                if u == "/api/mcp/one":
                    return self._send(200, mcp_set_one(b["agent"], b["name"], bool(b.get("on", True))))
                if u == "/api/mcp/drop":
                    return self._send(200, mcp_drop(b["agent"], b["name"]))
                if u == "/api/mcp/seed":
                    return self._send(200, mcp_hub.seed_from_codex())
            return self._send(404, dict(error="not found"))
        except Exception as e:
            return self._send(500, dict(error=str(e), tb=traceback.format_exc().splitlines()[-4:]))


def free_port(preferred=8765):
    for p in (preferred, 0):
        try:
            s = socket.socket()
            s.bind(("127.0.0.1", p))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            continue
    return 0


def _pin_console():
    """pythonw.exe 没有控制台，stdout/stderr 会是 None；补成日志文件，
    否则开机自启失败时什么都查不到。"""
    try:
        os.makedirs(registry.LOGS, exist_ok=True)
        if sys.stdout is None:
            sys.stdout = open(os.path.join(registry.LOGS, "hub.out.log"), "a",
                              encoding="utf-8", errors="replace", buffering=1)
        if sys.stderr is None:
            sys.stderr = open(os.path.join(registry.LOGS, "hub.err.log"), "a",
                              encoding="utf-8", errors="replace", buffering=1)
    except Exception:
        pass


def already_running(port: int) -> bool:
    """端口上是否已经有一份 hub 在服务。用接口探活，不误伤别的程序。"""
    import urllib.request
    if not port:
        return False
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/autostart",
                                    timeout=1.5) as r:
            return b'"supported"' in r.read(4096)
    except Exception:
        return False


def bind_server(port: int):
    """优先用给定端口；被别的程序占住则退回空闲端口。已有实例则返回 None。"""
    if already_running(port):
        print(f"已有一份实例在端口 {port} 运行，本次启动跳过。", flush=True)
        return None
    try:
        return HubServer(("127.0.0.1", port), Handler)
    except OSError as e:
        alt = free_port()
        if alt == port or already_running(alt):
            print(f"端口 {port} 不可用（{e}），且无可用端口，退出。", flush=True)
            return None
        print(f"端口 {port} 不可用（{e}），改用 {alt}。", flush=True)
        try:
            return HubServer(("127.0.0.1", alt), Handler)
        except OSError:
            return None


def parse_args(argv):
    """解析启动参数：端口（可省略）+ --no-browser（开机自启用，不弹浏览器）。"""
    port = None
    browser = True
    for a in argv:
        if a == "--no-browser":
            browser = False
        elif a in ("--browser", "-b"):
            browser = True
        else:
            try:
                port = int(a)
            except ValueError:
                print(f"忽略无法识别的参数：{a}", flush=True)
    return (port if port is not None else free_port()), browser


def main():
    _pin_console()
    port, open_browser = parse_args(sys.argv[1:])
    srv = bind_server(port)
    if srv is None:
        return
    _PORT[0] = srv.server_address[1]
    port = _PORT[0]                  # 可能已回退到别的端口，后面一律以实际值为准
    if os.environ.get("HUB_NO_WATCH") != "1":
        watcher.reconcile_mcp()      # 启动即吸收各 agent 已有配置
        watcher.reconcile_skills()   # 启动即吸收未托管的散落技能
        watcher.start(2.0)
    url = f"http://127.0.0.1:{port}/"
    print(f"AI Agent Hub  ->  {url}", flush=True)
    if open_browser and os.environ.get("HUB_NO_BROWSER") != "1":
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
