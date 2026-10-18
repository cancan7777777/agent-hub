"""jsonc_patch - 保留注释与排版，定点增删 JSONC 里的一个成员。"""
from __future__ import annotations
import json

Q = chr(34)
BS = chr(92)
W = chr(32) + chr(9) + chr(10) + chr(13)
NL = chr(10)
SP = " "


def _scan(text):
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            yield i, c, True
            if c == BS:
                i += 2
                continue
            if c == Q:
                in_str = False
        else:
            yield i, c, False
            if c == Q:
                in_str = True
        i += 1


def _match_object(text, open_idx):
    depth = 0
    for i, c, in_str in _scan(text[open_idx:]):
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return open_idx + i
    return -1


def find_container(text, key):
    pat = Q + key + Q
    start = 0
    while True:
        j = text.find(pat, start)
        if j < 0:
            return None
        k = j + len(pat)
        while k < len(text) and text[k] in SP + chr(9) + NL + chr(13):
            k += 1
        if k < len(text) and text[k] == ":":
            k += 1
            while k < len(text) and text[k] in SP + chr(9) + NL + chr(13):
                k += 1
            if k < len(text) and text[k] == "{":
                e = _match_object(text, k)
                if e > k:
                    return (k + 1, e)
        start = j + len(pat)


def _members(text, s, e):
    out, depth, seg = [], 0, s
    ws = SP + chr(9) + NL + chr(13)
    for i, c, in_str in _scan(text[s:e]):
        if in_str:
            continue
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        elif c == "," and depth == 0:
            out.append((seg, s + i))
            seg = s + i + 1
    if text[seg:e].strip():
        out.append((seg, e))
    return out


def _member_name(text, a, b):
    ws = SP + chr(9) + NL + chr(13)
    j = a
    while j < b and text[j] in ws:
        j += 1
    if j >= b or text[j] != Q:
        return None
    k = j + 1
    while k < b:
        if text[k] == BS:
            k += 2
            continue
        if text[k] == Q:
            break
        k += 1
    try:
        return json.loads(text[j:k + 1])
    except Exception:
        return None


def has_container(text, key):
    return find_container(text, key) is not None


def remove_member(text, key, name):
    rng = find_container(text, key)
    if not rng:
        return text, False
    s, e = rng
    ws = SP + chr(9) + NL + chr(13)
    for a, b in _members(text, s, e):
        if _member_name(text, a, b) != name:
            continue
        tail = b
        while tail < e and text[tail] in ws:
            tail += 1
        if tail < e and text[tail] == ",":
            tail += 1
            while tail < e and text[tail] in ws:
                tail += 1
        if tail >= e:
            pa = text[:a].rstrip(ws)
            if pa.endswith(","):
                a = len(pa) - 1
        return text[:a] + text[tail:], True
    return text, False


def _line_indent(text, pos):
    """返回 pos 所在行的行首空白。"""
    a = text.rfind(NL, 0, pos)
    seg = text[a + 1:pos]
    return seg[:len(seg) - len(seg.lstrip(W))]


def _prev_line_indent(text, pos):
    """取 pos 之前最后一个非空行的行首空白，作为同级缩进参考。"""
    i = pos
    while i > 0:
        a = text.rfind(NL, 0, i)
        line = text[a + 1:i] if a >= 0 else text[:i]
        if line.strip():
            return line[:len(line) - len(line.lstrip(W))]
        if a <= 0:
            break
        i = a
    return ""


def _member_block(name, entry, indent):
    """生成一个成员的文本块（不含前导换行），成员起始列对齐 indent。

    json.dumps(indent=2) 已为内层自带 2 空格，因此这里只需再补 indent。"""
    inner = json.dumps(entry, ensure_ascii=False, indent=2).split(NL)
    body = NL.join((indent + l) if l.strip() else l for l in inner[1:-1])
    return Q + name + Q + ": {" + NL + body + NL + indent + "}"


def add_member(text, key, name, entry, indent=None):
    """在 "key": { ... } 里新增/覆盖一个成员，保留其余注释与排版。"""
    rng = find_container(text, key)
    if not rng:
        depth, close = 0, -1
        for i, c, in_str in _scan(text):
            if in_str:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    close = i
                    break
        if close < 0:
            return text, False
        base = _prev_line_indent(text, close)
        close_indent = _line_indent(text, close)
        inner_indent = (indent or (base + "  "))
        block = (base + Q + key + Q + ": {" + NL
                 + inner_indent + _member_block(name, entry, inner_indent)
                 + NL + base + "}")
        head = text[:close].rstrip(W)
        sep = "" if head.endswith("{") else ","
        tail = NL + close_indent + text[close:]
        return head + sep + NL + block + tail, True

    s, e = rng
    key_pos = text.rfind(Q + key + Q, 0, s)
    base = _line_indent(text, key_pos if key_pos >= 0 else s)
    member_indent = indent or (base + "  ")
    block = _member_block(name, entry, member_indent)

    # 覆盖同名成员：保住该行换行与缩进，并保留成员尾部空白
    for a, b in _members(text, s, e):
        if _member_name(text, a, b) != name:
            continue
        tok = a
        while tok < b and text[tok] in W:
            tok += 1
        ls = text.rfind(NL, 0, tok) + 1
        prefix = text[ls:tok]
        be = b
        while be > tok and text[be - 1] in W:
            be -= 1
        if prefix.strip() == "" and prefix != "":
            blk = prefix + _member_block(name, entry, prefix)
            return text[:ls] + blk + text[be:], True
        if prefix.strip() == "":
            return text[:ls] + block + text[be:], True
        return text[:a] + block + text[be:], True

    if not text[s:e].strip():
        return text[:s] + NL + member_indent + block + NL + base + text[e:], True

    back = text[e - 1::-1]
    pad = len(back) - len(back.lstrip(W))
    at = e - pad
    return text[:at] + "," + NL + member_indent + block + text[at:], True
