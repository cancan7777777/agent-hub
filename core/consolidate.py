"""consolidate - 把散落在各 agent 的副本收敛成 D 盘单一真源，其余位置换成目录联接。

安全原则
  1. 任何实体目录在删除前先压成 zip 存到 data/backups/
  2. 删除只针对“解析后仍在真源之外”的路径；指向真源的别名一律跳过
  3. 先出计划（dry-run），确认后再落盘
"""
from __future__ import annotations
import os
from fsutil import (dir_fingerprint, link_kind, make_junction, copy_tree, remove_path,
                    backup_tree, read_target, newest_mtime)
import registry
from scan import list_skill_dirs

AGENTS_HOME = registry.AGENTS_SKILLS   # ~/.agents/skills —— Codex 原生读取，整体指向真源
CANON_REAL = os.path.realpath(registry.CANONICAL)


def ensure_canonical_dir():
    os.makedirs(registry.CANONICAL, exist_ok=True)


def is_inside_canonical(path: str) -> bool:
    """路径经联接解析后是否落在真源内部（含真源自身）。"""
    try:
        rp = os.path.realpath(path)
    except OSError:
        return False
    return rp == CANON_REAL or rp.startswith(CANON_REAL + os.sep)


def choose_authoritative(cands: list) -> dict | None:
    real = [c for c in cands if c["kind"] == "real"]
    if not real:
        return None
    return sorted(real, key=lambda c: (-c["mtime"], -c["bytes"]))[0]


def collect_candidates() -> tuple[dict, dict]:
    """返回 (name -> 候选位置列表, (owner,base) -> 目录策略)"""
    out: dict = {}
    policy: dict = {}

    def add(owner, base, path, protect, mirror=True):
        name = os.path.basename(path)
        if name in protect or name.startswith("_"):
            return
        if is_inside_canonical(path):
            return  # 真源别名，绝不作为可删除副本
        out.setdefault(name, []).append(dict(
            owner=owner, base=os.path.abspath(base), name=name,
            path=os.path.abspath(path), kind=link_kind(path),
            target=read_target(path), mtime=newest_mtime(path),
            **dir_fingerprint(path)))

    for n, p in list_skill_dirs(registry.CANONICAL):
        add("canonical", registry.CANONICAL, p, [])

    hk = link_kind(AGENTS_HOME)
    if hk == "real":
        for n, p in list_skill_dirs(AGENTS_HOME):
            add("agents_home", AGENTS_HOME, p, [])

    for a in registry.AGENTS:
        for sd in a["skills"]:
            base = os.path.abspath(sd["path"])
            if base in (os.path.abspath(AGENTS_HOME), os.path.abspath(registry.CANONICAL)):
                continue
            mirror = sd.get("mirror", True)
            policy[(a["id"], base)] = dict(mirror=mirror, protect=sd.get("protect", []))
            for n, p in list_skill_dirs(base):
                add(a["id"], base, p, sd.get("protect", []), mirror=mirror)
    return out, policy


def build_plan() -> dict:
    ensure_canonical_dir()
    cands, policy = collect_candidates()
    st = registry.load_state()
    ignored = set(st.get("ignored_skills", []))
    actions, notes = [], []

    for name, cs in sorted(cands.items()):
        if name in ignored or name.startswith("_"):
            continue
        canon_here = [c for c in cs if c["owner"] == "canonical"]
        best = canon_here[0] if canon_here else choose_authoritative(cs)
        if not best:
            notes.append(dict(name=name, kind="skip", why="没有可比对的实体副本"))
            continue

        canon_path = os.path.join(registry.CANONICAL, name)
        ck = link_kind(canon_path)
        chash = dir_fingerprint(canon_path)["hash"] if ck == "real" else None

        if ck != "real" or chash != best["hash"]:
            actions.append(dict(op="install", skill=name, src=best["path"], dst=canon_path,
                                src_owner=best["owner"], src_hash=best["hash"], size=best["bytes"],
                                overwrite=(ck == "real")))
        for c in cs:
            if c["owner"] == "canonical":
                continue
            if c["kind"] in ("junction", "symlink"):
                tgt = c.get("target")
                if tgt and os.path.abspath(tgt) != os.path.abspath(canon_path):
                    actions.append(dict(op="relink", skill=name, where=c["path"],
                                        old_target=tgt, dst=canon_path))
                continue
            if c["kind"] != "real":
                continue
            pol = policy.get((c["owner"], c["base"]), {})
            if pol.get("mirror") is False:
                # 该 agent 已经通过 ~/.agents 原生读到真源，重复镜像会造成二次注入
                actions.append(dict(op="purge", skill=name, where=c["path"], owner=c["owner"],
                                    hash=c["hash"], size=c["bytes"], backup=True,
                                    why="该 agent 经 ~/.agents 原生读取，移除重复副本",
                                    dst=canon_path))
                continue
            actions.append(dict(op="link", skill=name, where=c["path"], owner=c["owner"],
                                hash=c["hash"], size=c["bytes"], backup=True,
                                same_content=(chash is not None and c["hash"] == chash),
                                dst=canon_path))

    # ~/.agents/skills 与 .codex/skills 都被 Codex 读取，会造成同一技能注入两遍。
    # 收敛后把 ~/.agents/skills 清空，让 Codex 只认 .codex/skills，UI 每一列才能独立开关。
    hk = link_kind(AGENTS_HOME)
    if hk == "real":
        left = [n for n, _ in list_skill_dirs(AGENTS_HOME)]
        if left:
            actions.append(dict(op="agents_home_clear", skill="(目录级)", where=AGENTS_HOME,
                                dst=registry.CANONICAL, backup=True, pending=len(left)))
    elif hk in ("junction", "symlink"):
        actions.append(dict(op="agents_home_reset", skill="(目录级)", where=AGENTS_HOME,
                            old_target=read_target(AGENTS_HOME), backup=False))

    # E. 收敛后恢复可见性 + 补全缺失：为每个 agent 补全真源技能的联接。
    canon_names = set()
    for a in actions:
        if a["op"] == "install":
            canon_names.add(os.path.basename(a["dst"]))
        elif a["op"] == "link":
            canon_names.add(a["skill"])
    for a in registry.AGENTS:
        if a.get("read_only"):
            continue
        bases = [os.path.abspath(sd["path"]) for sd in a["skills"]]
        retired = [os.path.abspath(sd["path"]) for sd in a["skills"] if sd.get("retire")]
        if not retired:
            continue
        protect = set()
        for sd in a["skills"]:
            protect |= set(sd.get("protect", []))
        # 该 agent 的其他原生目录（如 .codex/skills）缺少哪些？
        others = [b for b in bases if b not in retired and b != os.path.abspath(registry.CANONICAL)]
        for base in others:
            have = {n for n,_ in list_skill_dirs(base)}
            for name in sorted(canon_names - protect - have):
                tgt = os.path.join(base, name)
                if link_kind(tgt) != "missing":
                    continue
                if not os.path.isdir(os.path.join(registry.CANONICAL, name)) and name not in canon_names:
                    continue
                actions.append(dict(op="restore", skill=name, owner=a["id"], where=tgt,
                                    dst=os.path.join(registry.CANONICAL, name), size=0))

    saved = sum(a.get("size", 0) or 0 for a in actions if a["op"] in ("link", "purge"))
    return dict(actions=actions, notes=notes,
                counts={op: sum(1 for a in actions if a["op"] == op)
                        for op in ("install", "link", "purge", "relink", "restore",
                                   "agents_home_clear", "agents_home_reset")},
                bytes_saved=saved, ignored=sorted(ignored))


def apply_plan(plan: dict, progress=None) -> dict:
    ensure_canonical_dir()
    done, failed, backups = [], [], []
    acts = plan["actions"]
    total = len(acts)
    for i, a in enumerate(acts):
        if progress:
            progress(i + 1, total, a)
        try:
            if a["op"] == "install":
                dst = a["dst"]
                if os.path.lexists(dst):
                    if link_kind(dst) == "real":
                        if is_inside_canonical(dst):
                            raise RuntimeError("拒绝覆盖真源别名路径")
                        b = backup_tree(dst, registry.BACKUPS, "canonical-" + a["skill"])
                        if b:
                            backups.append(b)
                    remove_path(dst)
                if not copy_tree(a["src"], dst):
                    raise RuntimeError("copytree 失败")
            elif a["op"] in ("link", "purge"):
                where = a["where"]
                if link_kind(where) != "real":
                    done.append(a)
                    continue
                if is_inside_canonical(where):
                    raise RuntimeError("拒绝删除解析到真源内部的路径：" + where)
                b = backup_tree(where, registry.BACKUPS, f"{a['owner']}-{a['skill']}")
                if b:
                    backups.append(b)
                if not remove_path(where):
                    raise RuntimeError("删除实体副本失败")
                if a["op"] == "link":
                    if not make_junction(a["dst"], where):
                        raise RuntimeError("创建联接失败")
            elif a["op"] == "restore":
                os.makedirs(os.path.dirname(a["where"]), exist_ok=True)
                if not make_junction(a["dst"], a["where"]):
                    raise RuntimeError("补齐联接失败 " + a["where"])
            elif a["op"] == "relink":
                if not remove_path(a["where"]):
                    raise RuntimeError("删除旧联接失败")
                if not make_junction(a["dst"], a["where"]):
                    raise RuntimeError("创建联接失败")
            elif a["op"] == "agents_home_clear":
                # 逐个移除（内容已进真源），保留空目录本身
                for n, sub in list_skill_dirs(a["where"]):
                    if link_kind(sub) == "real":
                        b = backup_tree(sub, registry.BACKUPS, f"agents-home-{n}")
                        if b:
                            backups.append(b)
                    if not remove_path(sub):
                        raise RuntimeError("无法清空 " + sub)
            elif a["op"] == "agents_home_reset":
                if not remove_path(a["where"]):
                    raise RuntimeError("无法移除 ~/.agents/skills 联接")
                os.makedirs(a["where"], exist_ok=True)
            else:
                raise RuntimeError("未知操作 " + a["op"])
            done.append(a)
        except Exception as e:
            failed.append(dict(action=a, error=str(e)))
    st = registry.load_state()
    st["last_apply"] = dict(done=len(done), failed=len(failed), backups=len(backups))
    registry.save_state(st)
    return dict(done=done, failed=failed, backups=backups)

def host_one(name: str, force: bool = False) -> dict:
    """单个技能一键托管：择优灌入真源，其余副本转联接（或按策略移除）。"""
    ensure_canonical_dir()
    name = os.path.basename(name)
    if not name or name.startswith((".", "_")):
        return dict(ok=False, msg="非法技能名")
    cands = []

    def consider(owner, base, path, mirror=True, keep=False):
        if not os.path.isdir(path) or is_inside_canonical(path):
            return
        cands.append(dict(owner=owner, base=os.path.abspath(base), path=os.path.abspath(path),
                          kind=link_kind(path), target=read_target(path), keep=keep,
                          mtime=newest_mtime(path), **dir_fingerprint(path)))

    if link_kind(AGENTS_HOME) == "real":
        consider("agents_home", AGENTS_HOME, os.path.join(AGENTS_HOME, name))
    for a in registry.AGENTS:
        for sd in a["skills"]:
            base = os.path.abspath(sd["path"])
            if base in (os.path.abspath(AGENTS_HOME), os.path.abspath(registry.CANONICAL)):
                continue
            protected = name in sd.get("protect", [])
            if protected and not force:
                continue
            consider(a["id"], base, os.path.join(base, name), sd.get("mirror", True),
                     keep=protected)

    canon_path = os.path.join(registry.CANONICAL, name)
    off_path = os.path.join(registry.CANONICAL, "_hub_disabled", name)
    real = [c for c in cands if c["kind"] == "real"]
    best = None
    if not os.path.isdir(canon_path):
        if os.path.isdir(off_path):
            # 之前被停用：直接原地恢复，不必再找副本
            try:
                os.rename(off_path, canon_path)
            except OSError as e:
                return dict(ok=False, msg="恢复失败：" + str(e))
        else:
            best = choose_authoritative(cands)
            if not best:
                return dict(ok=False, msg="找不到可托管的实体副本")
            if not copy_tree(best["path"], canon_path):
                return dict(ok=False, msg="复制到真源失败")

    backups, actions, errors = [], [], []
    for c in cands:
        if c.get("keep"):
            # agent 内置技能：内容收进真源用于分发，但原目录保持实体不动
            actions.append(dict(agent=c["owner"], dir=c["base"], msg="保留内置原目录（仅作为分发来源）"))
            continue
        if c["kind"] == "real":
            b = backup_tree(c["path"], registry.BACKUPS, f"host-{c['owner']}-{name}")
            if b:
                backups.append(b)
            if not remove_path(c["path"]):
                errors.append("删除副本失败 " + c["path"])
                continue
            pol = next((sd for a in registry.AGENTS for sd in a["skills"]
                        if os.path.abspath(sd["path"]) == c["base"]), {})
            if pol.get("mirror") is False:
                actions.append(dict(agent=c["owner"], dir=c["base"], msg="移除重复副本（该 agent 经 ~/.agents 原生读取）"))
            elif make_junction(canon_path, c["path"]):
                actions.append(dict(agent=c["owner"], dir=c["base"], msg="已转为联接"))
            else:
                errors.append("建联接失败 " + c["path"])
    # 装一次，处处可用：为所有可写 agent 铺好联接（不只是已有副本的那些）
    seen = {(c["owner"], c["base"]) for c in cands}
    for a in registry.AGENTS:
        if a.get("read_only"):
            continue
        for sd in a["skills"]:
            base = os.path.abspath(sd["path"])
            if base in (os.path.abspath(AGENTS_HOME), os.path.abspath(registry.CANONICAL)):
                continue
            if sd.get("retire") or name in sd.get("protect", []):
                continue
            if (a["id"], base) in seen:
                continue
            tgt = os.path.join(base, name)
            k = link_kind(tgt)
            if k == "real":
                b = backup_tree(tgt, registry.BACKUPS, f"host-{a['id']}-{name}")
                if b:
                    backups.append(b)
                remove_path(tgt)
            if link_kind(tgt) == "missing":
                os.makedirs(base, exist_ok=True)
                if make_junction(canon_path, tgt):
                    actions.append(dict(agent=a["id"], dir=base, msg="自动分发（新建联接）"))
                else:
                    errors.append("自动分发失败 " + tgt)

    st = registry.load_state()
    ig = set(st.get("ignored_skills", [])); ig.discard(name)
    st["ignored_skills"] = sorted(ig)
    registry.save_state(st)
    return dict(ok=not errors, name=name, hosted=True, actions=actions, errors=errors,
                backups=len(backups), src=(best or {}).get("path", "已存在真源"))


def unhost_one(name: str) -> dict:
    """把技能从真源移出到 _hub_disabled，并断开所有联接（内容保留，可恢复）。"""
    name = os.path.basename(name)
    src = os.path.join(registry.CANONICAL, name)
    off = os.path.join(registry.CANONICAL, "_hub_disabled", name)
    if not os.path.isdir(src):
        return dict(ok=False, msg="真源里没有这个技能")
    os.makedirs(os.path.dirname(off), exist_ok=True)
    removed = 0
    for a in registry.AGENTS:
        for sd in a["skills"]:
            tgt = os.path.join(os.path.abspath(sd["path"]), name)
            if link_kind(tgt) in ("junction", "symlink"):
                if remove_path(tgt):
                    removed += 1
    try:
        if os.path.isdir(off):
            remove_path(off)
        os.rename(src, off)
    except OSError as e:
        return dict(ok=False, msg="移动失败：" + str(e))
    st = registry.load_state()
    ig = set(st.get("ignored_skills", [])); ig.add(name)
    st["ignored_skills"] = sorted(ig)
    registry.save_state(st)
    return dict(ok=True, name=name, removed_links=removed, moved_to=off)

def import_all(only_missing: bool = True) -> dict:
    """一键导入：把所有还没进真源的技能全部收进真源并铺满各 agent。"""
    ensure_canonical_dir()
    st = registry.load_state()
    ignored = set(st.get("ignored_skills", []))
    present = {n for n, _ in list_skill_dirs(registry.CANONICAL)}
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
                found.append(name)
    ok, fail = [], []
    for name in sorted(set(found)):
        try:
            r = host_one(name)
            (ok if r.get("ok") else fail).append({"name": name, "msg": r.get("msg")})
        except Exception as e:
            fail.append({"name": name, "msg": str(e)[:120]})
    return dict(ok=not fail, hosted=[x["name"] for x in ok], failed=fail,
                scanned=len(set(found)))
