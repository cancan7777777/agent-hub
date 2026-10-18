"""jsonc_patch 的边界测试：注释保真、缩进、增删覆盖、始终可解析。"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
import jsonc_patch as J           # noqa: E402
import mcp_hub                    # noqa: E402

NL = chr(10)
Q = chr(34)
FAIL = []


def check(cond, label):
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        FAIL.append(label)


def parse(text):
    return json.loads(mcp_hub.mcp_format.strip_jsonc(text))


BASE = NL.join([
    "{",
    "  // 我的配置，这行注释必须活着",
    '  "$schema": "https://opencode.ai/config.json",',
    '  "shell": "pwsh",   /* 块注释也要活着 */',
    '  "mcp": {',
    '    "jira": { "type": "remote", "url": "https://jira/mcp", "enabled": true }',
    "  }",
    "}",
    "",
])
COMMENTS = ("这行注释必须活着", "块注释也要活着")


def has_comments(text):
    return all(c in text for c in COMMENTS)


print("1) 新增成员")
t1, ok1 = J.add_member(BASE, "mcp", "playwright",
                       {"type": "local", "command": ["npx", "@playwright/mcp@latest"], "enabled": True})
check(ok1, "返回 ok")
check(has_comments(t1), "注释保留")
check(sorted(parse(t1)["mcp"]) == ["jira", "playwright"], "两个成员都在")
check((NL + "    " + Q + "playwright") in t1, "新成员缩进为 4 空格")

print("2) 覆盖同名成员（停用）")
t2, ok2 = J.add_member(t1, "mcp", "playwright",
                       {"type": "local", "command": ["npx", "@playwright/mcp@latest"], "enabled": False})
check(ok2, "返回 ok")
check(has_comments(t2), "注释保留")
check(list(parse(t2)["mcp"]).count("playwright") == 1, "没有重复键")
check(parse(t2)["mcp"]["playwright"]["enabled"] is False, "enabled 变为 false")
check(parse(t2)["mcp"]["jira"]["enabled"] is True, "jira 未被波及")
check((NL + "    " + Q + "playwright") in t2, "覆盖后缩进仍为 4 空格")

print("3) 删除中间成员")
t3, ok3 = J.remove_member(t2, "mcp", "jira")
check(ok3, "返回 ok")
check(has_comments(t3), "注释保留")
check(sorted(parse(t3)["mcp"]) == ["playwright"], "只剩 playwright")

print("4) 删除末位成员")
t4, ok4 = J.remove_member(t3, "mcp", "playwright")
check(ok4, "返回 ok")
check(has_comments(t4), "注释保留")
check(list(parse(t4)["mcp"]) == [], "容器已空且可解析")

print("5) 空容器再新增")
t5, ok5 = J.add_member(t4, "mcp", "matlab", {"type": "local", "command": ["npx", "matlab-mcp"]})
check(ok5, "返回 ok")
check(has_comments(t5), "注释保留")
check(sorted(parse(t5)["mcp"]) == ["matlab"], "成员写入")

print("6) 原本没有 mcp 键")
NO_MCP = NL.join(["{", "  // 只有注释", '  "shell": "pwsh"', "}", ""])
t6, ok6 = J.add_member(NO_MCP, "mcp", "x", {"type": "local", "command": ["a"]})
check(ok6, "返回 ok")
check("// 只有注释" in t6, "注释保留")
check(sorted(parse(t6)["mcp"]) == ["x"], "mcp 键被创建")
check((NL + "  " + Q + "mcp") in t6, "mcp 键缩进为 2 空格")

print("7) 单行紧凑容器")
TIGHT = NL.join(["{", '  "mcp": { "a": { "type": "local" } }', "}", ""])
t7, ok7 = J.add_member(TIGHT, "mcp", "b", {"type": "local"})
check(ok7, "返回 ok")
check(sorted(parse(t7)["mcp"]) == ["a", "b"], "两个成员都在")

print("8) 删除不存在的成员应为 no-op")
t8, ok8 = J.remove_member(BASE, "mcp", "ghost")
check(not ok8, "返回未改动")
check(t8 == BASE, "文本完全不变")

print("9) 反复读写幂等")
cur = BASE
for i in range(6):
    cur, _ = J.add_member(cur, "mcp", "loop", {"type": "local", "command": ["n", str(i)]})
check(list(parse(cur)["mcp"]).count("loop") == 1, "多次覆盖仍只有一个键")
check(parse(cur)["mcp"]["loop"]["command"] == ["n", "5"], "最后一次生效")
check(has_comments(cur), "注释保留")

print("10) 损坏文件不崩溃")
BROKEN = NL.join(["{", '  "mcp": { "a": 1 ', "}"])
try:
    J.add_member(BROKEN, "mcp", "b", {"type": "local"})
    check(True, "未抛异常")
except Exception as e:
    check(False, "未抛异常（实际抛出 %s）" % type(e).__name__)

print("11) mcp_hub 端到端（临时文件）")
import tempfile
with tempfile.TemporaryDirectory(prefix="hubtest-") as d:
    p = os.path.join(d, "opencode.jsonc")
    open(p, "w", encoding="utf-8").write(BASE)
    std = {"type": "stdio", "command": "npx", "args": ["@playwright/mcp@latest"]}
    okw, msgw = mcp_hub.write_entry(p, "opencode", "mcp", "playwright", std, agent_id="opencode")
    check(okw, "write_entry ok: " + msgw)
    off, msgo = mcp_hub.write_entry(p, "opencode", "mcp", "playwright", std, on=False, agent_id="opencode")
    check(off, "停用 ok: " + msgo)
    body = open(p, encoding="utf-8").read()
    check(has_comments(body), "落盘后注释仍在")
    check("jira" in body, "原有 jira 未被破坏")
    ent = mcp_hub.read_entries(p, "opencode", "mcp")
    check(sorted(ent) == ["jira", "playwright"], "读回两个成员")
    check(mcp_hub.entry_is_off("opencode", ent["playwright"]), "停用状态可读回")
    back = mcp_hub.std_from_entry("opencode", ent["playwright"])
    check(back.get("command") == "npx" and back.get("args") == ["@playwright/mcp@latest"], "标准条目往返一致")
    okd, msgd = mcp_hub.write_entry(p, "opencode", "mcp", "playwright", None, agent_id="opencode")
    check(okd and sorted(mcp_hub.read_entries(p, "opencode", "mcp")) == ["jira"], "删除生效: " + msgd)

print()
if FAIL:
    print("FAILED %d 项:" % len(FAIL))
    for f in FAIL:
        print("   -", f)
    sys.exit(1)
print("全部通过")
