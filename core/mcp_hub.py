"""mcp_hub - MCP 服务器的主从分发：真源在 data/mcp.json，按各家原生格式写入。

写入 Codex 的 config.toml 时采用“最小文本编辑 + 回读校验 + 失败自动回滚”，
避免语法破坏导致 Codex 启动异常。"""
from __future__ import annotations
import json, os, re, shutil, tomllib
from fsutil import expand, USERPROFILE
import registry

FIELDS = ("type", "command", "args", "url", "headers", "env", "timeout", "description")


def load_master() -> dict:
    d = registry.read_json(registry.MCP_MASTER, None) if hasattr(registry, "read_json") else None
    if d is None:
        p = registry.MCP_MASTER
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    d = json.load(fh)
            except Exception:
                d = None
    if not d:
        d = dict(servers={})
    d.setdefault("servers", {})
    d.setdefault("disabled", [])
    return d


def save_master(d: dict):
    p = registry.MCP_MASTER
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def sanitize(name: str) -> dict:
    out = {}
    for k in FIELDS:
        v = name.get(k)
        if v not in (None, "", [], {}):
            out[k] = v
    return out


# ---------- TOML (Codex) ----------
def toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {toml_value(x)}" for k, x in v.items()) + " }"
    return json.dumps(v, ensure_ascii=False)


def _block_span(text: str, header: str):
    """返回 [mcp_servers.NAME] 块的**字符偏移**区间 (start, end, block)；不存在返回 None。"""
    NL = chr(10)
    lines = text.split(NL)
    offs, cur = [], 0
    for l in lines:
        offs.append(cur)
        cur += len(l) + 1
    starts = [i for i, l in enumerate(lines) if l.strip() == header]
    if not starts:
        return None
    s = starts[0]
    e = len(lines)
    for i in range(s + 1, len(lines)):
        st = lines[i].strip()
        if st.startswith("[") and st.endswith("]"):
            e = i
            break
    while e > s + 1 and not lines[e - 1].strip():
        e -= 1
    start = offs[s]
    end = offs[e] if e < len(offs) else len(text)
    return (start, end, NL.join(lines[s:e]))


def toml_read(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "rb") as fh:
            d = tomllib.load(fh)
    except Exception:
        return {}
    return dict(d.get("mcp_servers") or {})


def _toml_key_part(s: str) -> str:
    """表名片段：bare key 之外的一律加引号，避免被解析成嵌套表。"""
    safe = s and all(("a" <= c <= "z") or ("A" <= c <= "Z") or ("0" <= c <= "9") or c in "_-" for c in s)
    return s if safe else json.dumps(s, ensure_ascii=False)


def toml_upsert(path: str, name: str, cfg, enabled: bool | None = None) -> tuple[bool, str]:
    """[mcp_servers.NAME] 的增删改，保证块边界与空行不被破坏。"""
    NL = chr(10)
    if not os.path.isfile(path):
        return False, "config.toml 不存在"
    with open(path, encoding="utf-8") as fh:
        orig = fh.read()
    header = "[" + "mcp_servers." + _toml_key_part(name) + "]"
    span = _block_span(orig, header)
    if span is None and name != _toml_key_part(name):
        span = _block_span(orig, "[" + "mcp_servers." + name + "]")

    if cfg is None:
        if not span:
            return True, "无变化"
        start, end = span[0], span[1]
        # 连带吞掉块后面的空行，避免留下多余空白
        while end < len(orig) and orig[end] == NL:
            end += 1
        new = orig[:start] + orig[end:]
        if start == 0:
            new = new.lstrip(NL)
        new = new.rstrip(NL) + NL
    else:
        body = [header]
        seen = set()
        for k, v in cfg.items():
            if k == "enabled" and v is True:
                continue
            body.append(f"{k} = {toml_value(v)}")
            seen.add(k)
        if enabled is False and "enabled" not in seen:
            body.append("enabled = false")
        block = NL.join(body) + NL
        if span:
            start, end = span[0], span[1]
            # 保留块原有的尾随空行：先剥掉，再统一补一个
            tail = orig[end:]
            while tail.startswith(NL):
                tail = tail[1:]
            new = orig[:start] + block + NL + tail
        else:
            ins = NL + block + NL
            mm = re.search(r"^\[mcp_servers\]\s*$", orig, re.M)
            if mm:
                head = orig[:mm.end()].rstrip(NL)
                new = head + NL + NL + block + NL + orig[mm.end():].lstrip(NL)
            else:
                new = orig.rstrip(NL) + NL + NL + block
    if new == orig:
        return True, "无变化"
    bak = backup_file(path)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new)
    try:
        with open(path, "rb") as fh:
            tomllib.load(fh)
    except Exception as e:
        shutil.copy2(bak, path)
        return False, f"TOML 校验失败已回滚: {e}"
    return True, f"已写入（备份 {os.path.basename(bak)}）"


def toml_write(path: str, name: str, cfg: dict | None, enabled: bool | None = None) -> tuple[bool, str]:
    return toml_upsert(path, name, cfg, enabled)


def backup_file(path: str) -> str:
    import datetime
    os.makedirs(registry.BACKUPS, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(registry.BACKUPS, f"{stamp}-{os.path.basename(path)}.bak")
    shutil.copy2(path, dst)
    return dst


# ---------- JSON (Cursor / WorkBuddy / Gemini / Trae / Claude / Qoder / ZCode / dsh) ----------
def json_read(path: str, key: str) -> dict:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        return {}
    if key == "mcpServers" and "mcpServers" not in d:
        pass
    return dict(d.get(key) or {})


def json_write(path: str, key: str, name: str, cfg: dict | None) -> tuple[bool, str]:
    d = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            d = {}
    servers = d.get(key) or {}
    if cfg is None:
        if name not in servers:
            return True, "无变化"
        servers.pop(name, None)
    else:
        if servers.get(name) == cfg:
            return True, "无变化"
        servers[name] = cfg
    d[key] = servers
    bak = backup_file(path) if os.path.isfile(path) else None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    note = f"已写入（备份 {os.path.basename(bak)}）" if bak else "已新建文件"
    return True, note



# ---------- 统一分发：按 agent 的格式读写一条 MCP ----------
import mcp_format
import jsonc_patch as JP

NL = chr(10)


def read_entries(path: str, fmt: str, key: str) -> dict:
    """读某个 agent 配置里的全部 MCP，返回 {name: 原生条目}。"""
    if fmt == "toml":
        return toml_read(path)
    d = mcp_format.read_json_any(path)
    return dict(d.get(key) or {})


def can_off(fmt: str, agent_id: str = "") -> bool:
    """该格式能否表达停用（有 enabled / disabled 字段）。"""
    if fmt in ("toml", "opencode"):
        return True
    return agent_id == "workbuddy"


def std_from_entry(fmt: str, entry: dict) -> dict:
    return mcp_format.from_agent(fmt, entry)


def entry_is_off(fmt: str, entry: dict) -> bool:
    return mcp_format.is_off(fmt, entry)


def _atomic_write(path: str, text: str) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text if text.endswith(NL) else text + NL)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _jsonc_write(path: str, key: str, name: str, entry) -> tuple:
    """opencode.jsonc 走定点编辑，保留注释与原有排版。"""
    cur = mcp_format.read_json_any(path)
    servers = cur.get(key) or {}
    if entry is None:
        if name not in servers:
            return True, "无变化"
    elif servers.get(name) == entry:
        return True, "无变化"
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = "{" + NL + "}"
    if entry is None:
        new, ch = JP.remove_member(text, key, name)
        if not ch:
            return True, "无变化"
    else:
        new, ch = JP.add_member(text, key, name, entry)
        if not ch:
            return False, "配置结构无法解析，已跳过（未改动文件）"
    if new == text:
        return True, "无变化"
    bak = backup_file(path) if os.path.isfile(path) else None
    if not _atomic_write(path, new):
        return False, "写入失败"
    present = name in (mcp_format.read_json_any(path).get(key) or {})
    if present != (entry is not None):
        if bak:
            shutil.copy2(bak, path)
        return False, "写入后校验失败，已回滚"
    return True, ("已写入（保留注释，备份 %s）" % os.path.basename(bak)) if bak else "已新建文件"


def write_entry(path: str, fmt: str, key: str, name: str, std_cfg, on: bool = True,
                agent_id: str = "") -> tuple:
    """把 Hub 标准条目写入某个 agent。std_cfg=None 表示删除。"""
    if fmt == "toml":
        if std_cfg is None:
            return toml_write(path, name, None)
        entry = mcp_format.to_agent("toml", "", std_cfg, on)
        return toml_write(path, name, entry, enabled=on)
    entry = None if std_cfg is None else mcp_format.to_agent(fmt, agent_id, std_cfg, on)
    if fmt == "opencode":
        return _jsonc_write(path, key, name, entry)
    return _entry_write_generic(path, key, name, entry)


def _entry_write_generic(path: str, key: str, name: str, entry) -> tuple:
    d = mcp_format.read_json_any(path)
    servers = d.get(key) or {}
    if entry is None:
        if name not in servers:
            return True, "无变化"
        servers.pop(name, None)
    else:
        if servers.get(name) == entry:
            return True, "无变化"
        servers[name] = entry
    d[key] = servers
    bak = backup_file(path) if os.path.isfile(path) else None
    if not mcp_format.write_json_any(path, d):
        return False, "写入失败"
    return True, ("已写入（备份 %s）" % os.path.basename(bak)) if bak else "已新建文件"

def fanout(names: list | None = None, dry: bool = True) -> dict:
    m = load_master()
    disabled = set(m.get("disabled", []))
    targets = [n for n in (names or m["servers"]) if n in m["servers"]]
    results = []
    for a in registry.AGENTS:
        spec = a.get("mcp")
        if not spec:
            continue
        path, fmt, key = spec["path"], spec["format"], spec["key"]
        for n in targets:
            cfg = dict(sanitize(m["servers"][n]))
            off = n in disabled
            if fmt == "toml":
                if off:
                    cfg["enabled"] = False
                ok, msg = (True, "dry-run") if dry else toml_write(path, n, cfg)
            else:
                if a["id"] == "workbuddy" and off:
                    cfg["disabled"] = True
                elif a["id"] == "claude" and off:
                    continue
                ok, msg = (True, "dry-run") if dry else json_write(path, key, n, cfg)
            results.append(dict(agent=a["id"], server=n, path=path, ok=ok, msg=msg,
                                off=off, exists=os.path.isfile(path)))
        if not dry:
            pass
    return dict(dry=dry, servers=targets, results=results)


def seed_from_codex() -> dict:
    """首次运行：把 Codex 现有 mcp_servers 吸收为 Hub 主列表。"""
    m = load_master()
    if m["servers"]:
        return dict(added=0, total=len(m["servers"]))
    src = toml_read(os.path.join(USERPROFILE, ".codex", "config.toml"))
    added = 0
    for n, cfg in src.items():
        if n not in m["servers"]:
            m["servers"][n] = sanitize(cfg)
            if cfg.get("enabled") is False:
                m.setdefault("disabled", []).append(n)
            added += 1
    save_master(m)
    return dict(added=added, total=len(m["servers"]))
