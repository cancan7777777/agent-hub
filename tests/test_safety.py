"""端到端安全测试：删除前必须备份；内置技能原目录不得被联接替换。"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

NL = chr(10)
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAIL = []


def check(cond, label):
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        FAIL.append(label)


def mkskill(root, name, desc="示例", body="content"):
    p = os.path.join(root, name)
    os.makedirs(p, exist_ok=True)
    io.open(os.path.join(p, "SKILL.md"), "w", encoding="utf-8").write(
        "---" + NL + "name: " + name + NL + "description: " + desc + NL + "---" + NL + body + NL)
    return p


def build_env():
    """造一个隔离的假 HOME + 独立的 hub 副本，绝不碰真实配置。"""
    fake = tempfile.mkdtemp(prefix="hubsec-")
    hub = os.path.join(fake, "hub")
    shutil.copytree(REPO, hub, ignore=shutil.ignore_patterns(
        "__pycache__", "mcp.json", "state.json", "fingerprint.cache.json"))
    home = os.path.join(fake, "home")
    codex = os.path.join(home, ".codex", "skills")
    cursor = os.path.join(home, ".cursor", "skills")
    trae = os.path.join(home, ".trae-cn", "builtin_skills")
    os.makedirs(codex, exist_ok=True)
    os.makedirs(cursor, exist_ok=True)
    mkskill(codex, "plain-skill", "普通技能", "v1")
    mkskill(trae, "TRAE-security-review", "内置技能", "trae-original-bytes")
    io.open(os.path.join(home, ".codex", "config.toml"), "w", encoding="utf-8").write(
        "model = " + chr(34) + "m" + chr(34) + NL)
    return fake, hub, home, dict(codex=codex, cursor=cursor, trae=trae)


def start(hub, home, port):
    env = dict(os.environ)
    env.update(USERPROFILE=home, HOME=home, HUB_NO_BROWSER="1",
               PYTHONIOENCODING="utf-8", HUB_NO_WATCH="1")
    # 桌面版技能目录走 LOCALAPPDATA，一并指向假目录，保证测试完全隔离
    env["LOCALAPPDATA"] = os.path.join(home, "AppData", "Local")
    env["APPDATA"] = os.path.join(home, "AppData", "Roaming")
    proc = subprocess.Popen([sys.executable, "server.py", str(port)],
                            cwd=os.path.join(hub, "core"), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc


def api(port, path, obj=None):
    url = "http://127.0.0.1:%d%s" % (port, path)
    data = None if obj is None else json.dumps(obj).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=120).read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"__http__": e.code, "body": e.read().decode("utf-8", "replace")[:400]}


def kind(p):
    if not os.path.lexists(p):
        return "missing"
    if os.path.islink(p):
        return "symlink"
    try:
        if os.path.isjunction(p):
            return "junction"
    except Exception:
        pass
    return "real"


def backups(hub):
    d = os.path.join(hub, "data", "backups")
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


print("=== A) 收回实体副本必须先备份 ===")
fake, hub, home, D = build_env()
proc = start(hub, home, 8801)
try:
    time.sleep(3.5)
    # 把内置技能实体放进 cursor（模拟用户手工放的副本）
    mkskill(D["cursor"], "plain-skill", "普通技能", "cursor-local-edit")
    tgt = os.path.join(D["cursor"], "plain-skill")
    check(kind(tgt) == "real", "cursor 下是实体副本")
    n0 = len(backups(hub))
    r = api(8801, "/api/skill/agent", {"skill": "plain-skill", "agent": "cursor", "on": False})
    check(r.get("ok") is True, "收回成功: " + str(r.get("detail")))
    check(kind(tgt) == "missing", "实体副本已移除")
    new = [b for b in backups(hub) if "retract-" in b]
    check(len(new) >= 1, "生成了 retract 备份: " + str(new[:2]))
    if new:
        zp = os.path.join(hub, "data", "backups", new[0])
        with zipfile.ZipFile(zp) as z:
            names = z.namelist()
            hit = [n for n in names if n.endswith("SKILL.md")]
            data = z.read(hit[0]).decode("utf-8") if hit else ""
        check("cursor-local-edit" in data, "备份里保住了被删内容")
finally:
    proc.terminate()
    try:
        proc.communicate(timeout=8)
    except Exception:
        proc.kill()
    shutil.rmtree(fake, ignore_errors=True)

print()
print("=== B) 内置技能：原目录保留实体，仅作为分发来源 ===")
fake, hub, home, D = build_env()
proc = start(hub, home, 8802)
try:
    time.sleep(3.5)
    tr = os.path.join(D["trae"], "TRAE-security-review")
    r = api(8802, "/api/skill/agent", {"skill": "TRAE-security-review", "agent": "cursor", "on": True})
    check(r.get("ok") is True, "分发给 cursor 成功: " + str(r.get("detail"))[:120])
    check(kind(tr) == "real", "trae 原目录仍是实体（未被联接替换）")
    io_body = io.open(os.path.join(tr, "SKILL.md"), encoding="utf-8").read()
    check("trae-original-bytes" in io_body, "trae 原目录内容完好")
    cu = os.path.join(D["cursor"], "TRAE-security-review")
    check(kind(cu) == "junction", "cursor 下是联接")
    canon = os.path.join(hub, "data", "skills", "TRAE-security-review")
    check(os.path.isdir(canon), "真源已建立")
    r2 = api(8802, "/api/skill/agent", {"skill": "TRAE-security-review", "agent": "cursor", "on": False})
    check(r2.get("ok") is True, "收回 cursor 成功")
    check(kind(tr) == "real" and os.path.isfile(os.path.join(tr, "SKILL.md")),
          "收回后 trae 内置技能依然完好")
    check(kind(cu) == "missing", "cursor 已清空")
finally:
    proc.terminate()
    try:
        proc.communicate(timeout=8)
    except Exception:
        proc.kill()
    shutil.rmtree(fake, ignore_errors=True)

print()
print("=== C) 装上时覆盖实体副本也要备份 ===")
fake, hub, home, D = build_env()
proc = start(hub, home, 8803)
try:
    time.sleep(3.5)
    cu = os.path.join(D["cursor"], "plain-skill")
    mkskill(D["cursor"], "plain-skill", "普通技能", "unique-cursor-payload")
    r = api(8803, "/api/skill/agent", {"skill": "plain-skill", "agent": "cursor", "on": True})
    check(r.get("ok") is True, "分发成功")
    check(kind(cu) == "junction", "cursor 变为联接")
    # 不变量：被覆盖的内容必须能在某个备份里找回（host- 或 cell- 前缀皆可）
    saved = False
    for b in backups(hub):
        try:
            with zipfile.ZipFile(os.path.join(hub, "data", "backups", b)) as z:
                md = [x for x in z.namelist() if x.endswith("SKILL.md")]
                if md and "unique-cursor-payload" in z.read(md[0]).decode("utf-8"):
                    saved = True
                    break
        except Exception:
            continue
    check(saved, "被覆盖的实体内容已存进备份（可回滚）")
    check(bool([b for b in backups(hub)]), "备份目录非空")
finally:
    proc.terminate()
    try:
        proc.communicate(timeout=8)
    except Exception:
        proc.kill()
    shutil.rmtree(fake, ignore_errors=True)

print()
if FAIL:
    print("FAILED %d:" % len(FAIL))
    for f in FAIL:
        print("   -", f)
    sys.exit(1)
print("全部通过")
