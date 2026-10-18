"""mcp_format - MCP 条目在不同 agent 原生格式之间的双向转换。

Hub 内部统一用标准条目：
    {type, command, args, url, headers, env, timeout, description}
写盘时按各家格式翻译。
"""
from __future__ import annotations
import json, os, re

QUOTE = chr(34)          # 双引号
BS = chr(92)             # 反斜杠


def sanitize(cfg: dict) -> dict:
    keep = ("type", "command", "args", "url", "headers", "env", "timeout", "description")
    out = {}
    for k in keep:
        v = (cfg or {}).get(k)
        if v not in (None, "", [], {}):
            out[k] = v
    return out


def strip_jsonc(text: str) -> str:
    """去掉 // 与 /* */ 注释、尾逗号，让 JSONC 能被 json 解析。"""
    out = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == BS and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == QUOTE:
                in_str = False
            i += 1
            continue
        if c == QUOTE:
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    s = "".join(out)
    return re.sub(r"," + chr(92) + "s*([}" + chr(93) + chr(93) + chr(93) + "])", r"\1", s)


def read_json_any(path: str) -> dict:
    """读 .json / .jsonc，失败返回空。"""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.loads(strip_jsonc(fh.read()))
    except Exception:
        return {}


def write_json_any(path: str, obj: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def to_agent(fmt: str, agent_id: str, cfg: dict, on: bool = True) -> dict:
    """标准条目 -> 该 agent 的原生条目。"""
    c = sanitize(cfg)
    if fmt == "opencode":
        url = c.pop("url", None)
        headers = c.pop("headers", None)
        env = c.pop("env", None)
        args = c.pop("args", None)
        cmd = c.pop("command", None)
        c.pop("type", None)
        out = {"enabled": True}
        if url:
            out["type"] = "remote"
            out["url"] = url
            if headers:
                out["headers"] = headers
        else:
            out["type"] = "local"
            seq = ([cmd] if cmd else []) + (list(args) if args else [])
            out["command"] = [x for x in seq if x != ""]
            if env:
                out["environment"] = env
        if c.get("description"):
            out["description"] = c["description"]
        if c.get("timeout"):
            out["timeout"] = c["timeout"]
        if not on:
            out["enabled"] = False
        return out
    out = dict(c)
    out.pop("enabled", None)
    if not on:
        if fmt == "toml":
            out["enabled"] = False
        elif agent_id == "workbuddy":
            out["disabled"] = True
    return out


def from_agent(fmt: str, cfg: dict) -> dict:
    """该 agent 的原生条目 -> 标准条目。"""
    c = dict(cfg or {})
    if fmt == "opencode":
        out = {}
        cmd = c.get("command")
        if isinstance(cmd, list) and cmd:
            out["type"] = "local"
            out["command"] = cmd[0]
            if len(cmd) > 1:
                out["args"] = list(cmd[1:])
        elif isinstance(cmd, str) and cmd:
            out["type"] = "local"
            out["command"] = cmd
        if c.get("url"):
            out["type"] = "remote"
            out["url"] = c["url"]
            if c.get("headers"):
                out["headers"] = c["headers"]
        if c.get("environment"):
            out["env"] = c["environment"]
        for k in ("description", "timeout"):
            if c.get(k):
                out[k] = c[k]
        return out
    out = sanitize(c)
    if not out.get("type"):
        out["type"] = "stdio" if out.get("command") else "http"
    return out


def is_off(fmt: str, cfg: dict) -> bool:
    """该 agent 的配置里这条是否处于停用状态。"""
    c = cfg or {}
    if c.get("enabled") is False:
        return True
    if c.get("disabled") is True:
        return True
    return False
