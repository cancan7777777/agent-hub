"""plugin_hub - 只做盘点与跨 agent 对照展示（不跨工具启用，各家格式不兼容）。"""
from __future__ import annotations
import json, os, re, tomllib
from fsutil import USERPROFILE
import registry


def _toml_plugins(path: str) -> list:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as fh:
            d = tomllib.load(fh)
    except Exception:
        return []
    out = []
    for k, v in (d.get("plugins") or {}).items():
        mk = k.split("@")[-1] if "@" in k else ""
        out.append(dict(name=k, marketplace=mk, enabled=bool(v.get("enabled", True)),
                        version=v.get("version", ""), source="config.toml"))
    for k, v in (d.get("marketplaces") or {}).items():
        out.append(dict(name=k, marketplace=k, enabled=True, version="",
                        source="marketplace", path=v.get("source", "")))
    return out


def _claude_json(path: str) -> list:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        return []
    out = []
    for k, arr in (d.get("plugins") or {}).items():
        for inst in arr if isinstance(arr, list) else []:
            out.append(dict(name=k, marketplace=k.split("@")[-1], enabled=True,
                            version=inst.get("version", ""), install_path=inst.get("installPath", ""),
                            installed_at=inst.get("installedAt", ""), source="installed_plugins"))
    return out


def _dir_list(path: str) -> list:
    if not os.path.isdir(path):
        return []
    out = []
    try:
        skip = {"cache", "data", "marketplaces", "local", ".tmp", "tmp", "state", ".plugin-appserver"}
        for n in sorted(os.listdir(path)):
            p = os.path.join(path, n)
            if not os.path.isdir(p) or n.startswith(".") or n.lower() in skip:
                continue
            out.append(dict(name=n, enabled=True, version="", source="dir", path=p))
    except OSError:
        pass
    return out


def scan_plugins() -> dict:
    by_agent = {}
    names = {}
    for a in registry.AGENTS:
        items = []
        for spec in a.get("plugins") or []:
            p = spec["path"]
            if spec["kind"] == "toml_plugins":
                items += _toml_plugins(p)
            elif spec["kind"] == "claude_json":
                items += _claude_json(p)
            elif spec["kind"] == "dir":
                if os.path.isdir(p):
                    items += _dir_list(p)
        for it in items:
            it["agent"] = a["id"]
            key = re.split(r"@|[/\\]", it["name"])[0].lower()
            names.setdefault(key, set()).add(a["id"])
        by_agent[a["id"]] = items
    multi = {k: sorted(v) for k, v in names.items() if len(v) > 1}
    return dict(by_agent=by_agent, total=sum(len(v) for v in by_agent.values()),
                unique=len(names), shared=multi)
