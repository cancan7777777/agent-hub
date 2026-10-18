"""scan - 扫描所有 agent 的技能目录，产出“技能 × agent”矩阵与漂移报告。"""
from __future__ import annotations
import os, time
from fsutil import dir_fingerprint, link_kind, read_target, newest_mtime
import registry


def has_skill_md(d: str) -> bool:
    try:
        return any(f.lower() == "skill.md" for f in os.listdir(d))
    except OSError:
        return False


def list_skill_dirs(base: str) -> list:
    out = []
    if not os.path.isdir(base):
        return out
    try:
        for name in sorted(os.listdir(base)):
            fp = os.path.join(base, name)
            if os.path.isdir(fp) and not name.startswith(".") and has_skill_md(fp):
                out.append((name, fp))
    except OSError:
        pass
    return out


def entry_info(owner: str, path: str, fp: dict) -> dict:
    kind = link_kind(path)
    return dict(owner=owner, path=os.path.abspath(path), kind=kind, hash=fp["hash"],
                files=fp["files"], bytes=fp["bytes"], mtime=newest_mtime(path),
                target=read_target(path) if kind in ("junction", "symlink") else None)


def scan() -> dict:
    st = registry.load_state()
    ignored = set(st.get("ignored_skills", []))

    canon = {}
    for name, path in list_skill_dirs(registry.CANONICAL):
        canon[name] = entry_info("canonical", path, dir_fingerprint(path))

    registry.refresh_desktop_sources()   # 桌面端路径含会话 UUID，需每次重新发现
    views = []  # 每个 (agent, 目录) 一个视图
    for a in registry.AGENTS + registry.SOURCES:
        for i, sd in enumerate(a["skills"]):
            p = os.path.abspath(sd["path"])
            views.append(dict(
                vid=f"{a['id']}#{i}", agent=a["id"], dir=p, role=sd["role"],
                exists=os.path.isdir(p), native_read=sd.get("native_read", False),
                retire=sd.get("retire", False),
                protect=sd.get("protect", []),
                entries={n: entry_info(a["id"], ep, dir_fingerprint(ep))
                         for n, ep in list_skill_dirs(p) if n not in ignored}))

    names = set(canon)
    for v in views:
        names |= set(v["entries"])
    names |= {n for n in ignored}

    # 受保护条目（agent 内置技能）：(agent, name) -> True
    protected_set = set()
    for v in views:
        for n in v["protect"]:
            protected_set.add((v["agent"], n))

    matrix = {}
    for name in sorted(names):
        ch = canon[name]["hash"] if name in canon else None
        row = dict(name=name, canonical=name in canon, canonical_hash=ch,
                   ignored=name in ignored, locations={}, by_agent={}, variants={}, bytes_total=0)
        if name in canon:
            row["files"] = canon[name]["files"]
            row["bytes_total"] = canon[name]["bytes"]
        counted = set()
        for v in views:
            e = v["entries"].get(name)
            if not e:
                continue
            row["locations"][v["vid"]] = dict(
                agent=v["agent"], dir=v["dir"], role=v["role"], path=e["path"], kind=e["kind"],
                hash=e["hash"], target=e["target"], files=e["files"], bytes=e["bytes"],
                matches_canonical=(ch is not None and e["hash"] == ch))
            row["variants"].setdefault(e["hash"], []).append(v["agent"])
            if name not in canon and e["kind"] == "real" and v["role"] != "source" and e["hash"] not in counted:
                counted.add(e["hash"])
                row["bytes_total"] += e["bytes"]
            ag = row["by_agent"].setdefault(v["agent"], dict(
                present=False, kinds=[], hashes=[], dirs=[], native_read=False, read_only=(v["role"] == "source")))
            ag["present"] = True
            ag["kinds"].append(e["kind"])
            ag["hashes"].append(e["hash"])
            ag["dirs"].append(v["dir"])
            if v["native_read"]:
                ag["native_read"] = True
        writable = [l for l in row["locations"].values() if l["role"] != "source"]
        allh = {l["hash"] for l in writable}
        if ch:
            allh.add(ch)
        row["variant_count"] = len(allh)
        row["drift"] = row["variant_count"] > 1
        row["copies"] = sum(1 for l in row["locations"].values()
                            if l["kind"] == "real" and l["role"] != "source")
        row["agents_present"] = sorted([a for a, x in row["by_agent"].items() if x["present"]])
        row["agent_count"] = len(row["agents_present"])
        # 只出现在受保护目录 / 只读来源里的技能，属于 agent 内置，不算待托管
        locs = list(row["locations"].values())
        row["builtin"] = bool(locs) and all((l["agent"], name) in protected_set for l in locs)
        # 只出现在只读来源（CC Switch / Claude Cowork）里的技能可单向取用：允许托管，不计入待收敛
        row["source_only"] = bool(locs) and all(l["role"] == "source" for l in locs)
        row["protected"] = row["builtin"] or row["source_only"]
        row["ok"] = (name in canon and row["copies"] == 0) or (name not in canon and row["copies"] <= 1 and not row["drift"])
        matrix[name] = row

    return dict(canonical=canon, canonical_dir=registry.CANONICAL, matrix=matrix,
                views=[dict(vid=v["vid"], agent=v["agent"], dir=v["dir"], role=v["role"],
                            exists=v["exists"], native_read=v["native_read"],
                            retire=v.get("retire", False),
                            count=len(v["entries"]), protect=v["protect"]) for v in views],
                generated=time.time())
