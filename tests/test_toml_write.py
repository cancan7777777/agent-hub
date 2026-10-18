"""toml_write 的回归测试：块定位必须用字符偏移，不能是行号。

曾经的缺陷：_block_span 返回行号，toml_write 却按字符偏移切片，
更新一个已存在的 [mcp_servers.x] 会把文件从第 N 个字符处截断。
"""
import atexit
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
import mcp_hub  # noqa: E402

import tomllib  # noqa: E402

NL = chr(10)
FAIL = []
TEMP_DIRS = []


def temp_dir(prefix):
    td = tempfile.TemporaryDirectory(prefix=prefix)
    TEMP_DIRS.append(td)
    return td.name


def cleanup_temp_dirs():
    while TEMP_DIRS:
        TEMP_DIRS.pop().cleanup()


atexit.register(cleanup_temp_dirs)


def check(cond, label):
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        FAIL.append(label)


BASE = NL.join([
    'model = "gpt-x"',
    'model_reasoning_effort = "high"',
    "",
    "[model_providers.custom]",
    'name = "custom"',
    'base_url = "http://127.0.0.1:15721/v1"',
    "",
    "[mcp_servers]",
    "",
    "[mcp_servers.alpha]",
    'type = "stdio"',
    'command = "alpha-cmd"',
    "",
    "[mcp_servers.beta]",
    'type = "stdio"',
    'command = "npx"',
    "args = [\"one\", \"two\"]",
    "",
    "[projects.'c:\\somewhere']",
    'trust_level = "trusted"',
    "",
])


def parse(path):
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def fresh():
    d = temp_dir("toml-")
    p = os.path.join(d, "config.toml")
    io.open(p, "w", encoding="utf-8").write(BASE)
    return p


print("1) 更新已存在的服务器（曾经的截断场景）")
p = fresh()
ok, msg = mcp_hub.toml_write(p, "alpha", {"type": "stdio", "command": "alpha-new"})
check(ok, "写入成功: " + msg)
d = parse(p)
check(d["mcp_servers"]["alpha"]["command"] == "alpha-new", "alpha 已更新")
check(d["model"] == "gpt-x", "顶部 model 未被截断")
check(d["model_providers"]["custom"]["base_url"] == "http://127.0.0.1:15721/v1", "model_providers 完好")
check("beta" in d["mcp_servers"], "beta 未被波及")
check(d["projects"]["c:\\somewhere"]["trust_level"] == "trusted", "projects 段完好")

print("2) 新增服务器（已有 [mcp_servers] 头）")
ok, msg = mcp_hub.toml_write(p, "gamma", {"type": "stdio", "command": "gamma-cmd"})
check(ok, "写入成功: " + msg)
d = parse(p)
check(sorted(d["mcp_servers"]) == ["alpha", "beta", "gamma"], "三个服务器都在")
check(d["model"] == "gpt-x", "文件头完好")

print("3) 停用（enabled = false）")
ok, msg = mcp_hub.toml_write(p, "gamma", {"type": "stdio", "command": "gamma-cmd"}, enabled=False)
check(ok, "写入成功: " + msg)
d = parse(p)
check(d["mcp_servers"]["gamma"]["enabled"] is False, "enabled=false 已写入")

print("4) 删除服务器")
ok, msg = mcp_hub.toml_write(p, "beta", None)
check(ok, "删除成功: " + msg)
d = parse(p)
check(sorted(d["mcp_servers"]) == ["alpha", "gamma"], "beta 已移除")
check(d["model"] == "gpt-x", "其余内容完好")

print("5) 删除不存在的服务器是 no-op")
before = io.open(p, encoding="utf-8").read()
ok, msg = mcp_hub.toml_write(p, "ghost", None)
check(ok and msg == "无变化", "返回无变化")
check(io.open(p, encoding="utf-8").read() == before, "文件字节不变")

print("6) 重复写入相同内容幂等")
before = io.open(p, encoding="utf-8").read()
ok, msg = mcp_hub.toml_write(p, "alpha", {"type": "stdio", "command": "alpha-new"})
check(ok and msg == "无变化", "幂等: " + msg)
check(io.open(p, encoding="utf-8").read() == before, "文件未变")

print("7) 没有 [mcp_servers] 头时自动补建")
d2 = temp_dir("toml2-")
p2 = os.path.join(d2, "config.toml")
io.open(p2, "w", encoding="utf-8").write('model = "m"' + NL + NL + '[desktop]' + NL + 'x = 1' + NL)
ok, msg = mcp_hub.toml_write(p2, "first", {"type": "stdio", "command": "c"})
check(ok, "写入成功: " + msg)
dd = parse(p2)
check(dd["mcp_servers"]["first"]["command"] == "c", "mcp_servers 被创建")
check(dd["model"] == "m" and dd["desktop"]["x"] == 1, "原有键完好")

print("8) 数组与嵌套值序列化")
ok, msg = mcp_hub.toml_write(p2, "arr", {"type": "stdio", "command": "npx",
                                         "args": ["a", "b c"], "env": {"K": "V"}, "timeout": 30000})
check(ok, "写入成功: " + msg)
e = parse(p2)["mcp_servers"]["arr"]
check(e["args"] == ["a", "b c"], "数组含空格元素正确")
check(e["env"] == {"K": "V"}, "内联表正确")
check(e["timeout"] == 30000, "整数正确")

print("9) 名称含点号也不串块")
ok, msg = mcp_hub.toml_write(p2, "a.b", {"type": "stdio", "command": "dotted"})
check(ok, "写入成功: " + msg)
check(parse(p2)["mcp_servers"]["a.b"]["command"] == "dotted", "点号名可读回")

print("10) 读回全部条目")
ents = mcp_hub.read_entries(p2, "toml", "mcp_servers")
check(sorted(ents) == ["a.b", "arr", "first"], "read_entries 正确: " + str(sorted(ents)))

print("11) 损坏写入能回滚")
p3 = fresh()
good = io.open(p3, encoding="utf-8").read()
import mcp_hub as M
orig_val = M.toml_value
try:
    M.toml_value = lambda v: "<<<invalid toml>>>"
    ok, msg = M.toml_write(p3, "alpha", {"type": "stdio", "command": "x"})
    check(not ok, "返回失败: " + msg)
    check(io.open(p3, encoding="utf-8").read() == good, "文件已回滚到原状")
finally:
    M.toml_value = orig_val

print()
cleanup_temp_dirs()
if FAIL:
    print("FAILED %d:" % len(FAIL))
    for f in FAIL:
        print("   -", f)
    sys.exit(1)
print("全部通过")
