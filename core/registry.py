"""registry - agent 注册表与真源目录定义（所有路径常量集中在此）。"""
from __future__ import annotations
import json, os
from fsutil import USERPROFILE, expand

# 项目根目录由本文件位置推导，克隆到任意路径都能运行
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "core")
DATA = os.path.join(ROOT, "data")
LOGS = os.path.join(ROOT, "logs")

# 真源：所有共享技能实体只存在这一份
CANONICAL = os.path.join(DATA, "skills")
MCP_MASTER = os.path.join(DATA, "mcp.json")
STATE = os.path.join(DATA, "state.json")
FPCACHE = os.path.join(DATA, "fingerprint.cache.json")
BACKUPS = os.path.join(DATA, "backups")

# ~/.agents/skills 是 Agent Skills 规范的标准位置，多个 agent 原生读取
AGENTS_DIR = os.path.join(USERPROFILE, ".agents")
AGENTS_SKILLS = os.path.join(AGENTS_DIR, "skills")

G = os.path.join(USERPROFILE, ".gemini")

AGENTS = [
    dict(id="codex", name="Codex / ChatGPT", vendor="OpenAI", color="#10a37f", verified=True,
         icon='<path d="M12 2 3 7v10l9 5 9-5V7Z"/><path d="M12 22V12M3 7l9 5 9-5"/>',
         skills=[dict(path=os.path.join(USERPROFILE, ".codex", "skills"), role="agent",
                      protect=[".system"]),
               dict(path=AGENTS_SKILLS, role="canonical", native_read=True, retire=True)],
         mcp=dict(path=os.path.join(USERPROFILE, ".codex", "config.toml"), format="toml", key="mcp_servers"),
         plugins=[dict(path=os.path.join(USERPROFILE, ".codex", "plugins"), kind="dir"),
                  dict(path=os.path.join(USERPROFILE, ".codex", "config.toml"), kind="toml_plugins")],
         note="原生读取 .codex\\skills 与 .agents\\skills 两处。"),

    dict(id="claude", name="Claude Code（CLI）", vendor="Anthropic", color="#d97757", verified=True,
         icon='<path d="M12 3c2.5 3 4 5.5 4 8a4 4 0 0 1-8 0c0-2.5 1.5-5 4-8Z"/><path d="M9 21h6"/>',
         skills=[dict(path=os.path.join(USERPROFILE, ".claude", "skills"), role="agent")],
         mcp=dict(path=os.path.join(USERPROFILE, ".claude.json"), format="json", key="mcpServers"),
         plugins=[dict(path=os.path.join(USERPROFILE, ".claude", "plugins", "installed_plugins.json"), kind="claude_json")],
         note="终端里的 claude 命令。技能读 ~/.claude/skills 与 ~/.agents/skills；"
              "与 Claude 桌面版互不可见。"),
    dict(id="cursor", name="Cursor", vendor="Anysphere", color="#5b8def", verified=False,
         icon='<path d="M4 3l14 8-6 1.6L9.6 19Z"/>',
         skills=[dict(path=os.path.join(USERPROFILE, ".cursor", "skills"), role="agent")],
         mcp=dict(path=os.path.join(USERPROFILE, ".cursor", "mcp.json"), format="json", key="mcpServers"),
         plugins=[dict(path=os.path.join(USERPROFILE, ".cursor", "plugins"), kind="dir")],
         note="mcp.json 首次添加服务器后才存在。"),

    dict(id="gemini", name="Gemini CLI", vendor="Google", color="#1a73e8", verified=True,
         icon='<path d="M12 2 14.6 9.4 22 12l-7.4 2.6L12 22l-2.6-7.4L2 12l7.4-2.6Z"/>',
         skills=[dict(path=os.path.join(G, "config", "skills"), role="agent")],
         mcp=dict(path=os.path.join(G, "config", "mcp_config.json"), format="json", key="mcpServers"),
         plugins=[dict(path=os.path.join(G, "config", "plugins"), kind="dir")],
         note="读写 ~/.gemini/config：skills 目录 + mcp_config.json。"),

    dict(id="antigravity", name="Antigravity", vendor="Google", color="#4285f4", verified=True,
         icon='<path d="M12 16V4"/><path d="m8 8 4-4 4 4"/><path d="M4 20h16"/>',
         skills=[dict(path=os.path.join(G, "antigravity", "builtin", "skills"), role="agent",
                      protect=["agy-customizations", "antigravity_guide", "generative_ui",
                               "migrate-workflows", "permissioned-github"])],
         mcp=dict(path=os.path.join(G, "config", "mcp_config.json"), format="json", key="mcpServers"),
         plugins=[],
         note="与 Gemini CLI 共用 mcp_config.json；内置技能受保护，自定义技能放 ~/.agents/skills。"),

    dict(id="opencode", name="OpenCode", vendor="SST", color="#ff5c35", verified=True,
         icon='<path d="m8 8-4 4 4 4M16 8l4 4-4 4M13.5 5.5l-3 13"/>',
         skills=[dict(path=os.path.join(USERPROFILE, ".config", "opencode", "skills"), role="agent")],
         mcp=dict(path=os.path.join(USERPROFILE, ".config", "opencode", "opencode.jsonc"),
                  format="opencode", key="mcp"),
         plugins=[],
         note="技能 ~/.config/opencode/skills；MCP 在 opencode.jsonc 的 mcp 键（type: local/remote）。"),

    dict(id="pi", name="Pi Coding Agent", vendor="badlogic", color="#0f766e", verified=True,
         icon='<path d="M9 3h6M12 3v7"/><path d="M7 10h10l-1.2 4.5a3 3 0 0 1-2.9 2.2H11a3 3 0 0 0-2.9 2.2L7 22"/>',
         skills=[dict(path=os.path.join(USERPROFILE, ".pi", "agent", "skills"), role="agent")],
         mcp=dict(path=os.path.join(USERPROFILE, ".pi", "agent", "mcp.json"), format="json", key="mcpServers"),
         plugins=[],
         note="agent 目录 ~/.pi/agent：skills/ 与 mcp.json；也原生读 ~/.agents/skills。"),

    dict(id="trae", name="Trae CN", vendor="ByteDance", color="#7c5cff", verified=False,
         icon='<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M9 9h6M12 9v6"/>',
         skills=[dict(path=os.path.join(USERPROFILE, ".trae-cn", "builtin_skills"), role="agent",
                      protect=["_shared", "TRAE-security-review"])],
         mcp=dict(path=os.path.join(USERPROFILE, ".trae-cn", "mcp.json"), format="json", key="mcpServers"),
         plugins=[dict(path=os.path.join(USERPROFILE, ".trae-cn", "plugins"), kind="dir")],
         note="builtin_skills 为程序目录；mcps\\ 是会话缓存，勿手写入。"),

    dict(id="qoder", name="Qoder CN", vendor="Alibaba", color="#ff6a00", verified=False,
         icon='<circle cx="11" cy="11" r="6"/><path d="m20 20-4.6-4.6"/><path d="M11 8v3.2l2.2 1.2"/>',
         skills=[dict(path=os.path.join(USERPROFILE, ".qoder-cn", "skills"), role="agent")],
         mcp=dict(path=os.path.join(USERPROFILE, ".qoder-cn", "mcp.json"), format="json", key="mcpServers"),
         plugins=[dict(path=os.path.join(USERPROFILE, ".qoder-cn", "plugins", "installed_plugins_v2.json"), kind="claude_json")],
         note="mcp-router.json 是运行时端口表，不是服务器定义。"),

    dict(id="workbuddy", name="WorkBuddy", vendor="Tencent", color="#2080e0", verified=True,
         icon='<rect x="4" y="7" width="16" height="12" rx="3"/><path d="M9 7V5a3 3 0 0 1 6 0v2"/><path d="M9.5 13h.01M14.5 13h.01"/>',
         skills=[dict(path=os.path.join(USERPROFILE, ".workbuddy", "skills"), role="agent")],
         mcp=dict(path=os.path.join(USERPROFILE, ".workbuddy", "mcp.json"), format="json", key="mcpServers"),
         plugins=[dict(path=os.path.join(USERPROFILE, ".workbuddy", "plugins", "installed_plugins.json"), kind="claude_json")],
         note="connectors\\ 内的 mcp.json 为市场目录缓存，不纳入分发。"),

    dict(id="zcode", name="ZCode", vendor="Z.ai", color="#e4393c", verified=False,
         icon='<path d="m8 8-4 4 4 4M16 8l4 4-4 4M13.6 5.6l-3.2 12.8"/>',
         skills=[dict(path=os.path.join(USERPROFILE, ".zcode", "skills"), role="agent")],
         mcp=dict(path=os.path.join(USERPROFILE, ".zcode", "cli", "mcp.json"), format="json", key="mcpServers"),
         plugins=[dict(path=os.path.join(USERPROFILE, ".zcode", "cli", "plugins", "data"), kind="dir")],
         note="插件沿用 Claude 风格 marketplace；技能目录约定未验证。"),

    dict(id="dsh", name="DeepSeek Harness", vendor="DeepSeek", color="#4d6bfe", verified=False,
         icon='<path d="M4 6h16M4 12h10M4 18h7"/><circle cx="18.5" cy="15.5" r="2.8"/>',
         skills=[dict(path=os.path.join(USERPROFILE, ".dsh", "skills"), role="agent")],
         mcp=dict(path=os.path.join(USERPROFILE, ".dsh", "mcp.json"), format="json", key="mcpServers"),
         plugins=[dict(path=os.path.join(USERPROFILE, ".dsh", "profiles", "desktop"), kind="dir")],
         note="配置走 cordis profile 分层补丁，技能目录约定未验证。"),
]

SOURCE_ONLY = dict(id="ccswitch", name="CC Switch（技能来源）", vendor="farion1231", color="#8b5cf6",
                   icon='<path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3"/><circle cx="12" cy="12" r="3"/>',
                   verified=True, read_only=True,
                   skills=[dict(path=os.path.join(USERPROFILE, ".cc-switch", "skills"), role="source")],
                   mcp=None, plugins=[], note="只读来源，不写入，避免其自动同步打散联接。")


def _claude_desktop_skill_dirs():
    r"""Claude 桌面版（local agent mode）的技能目录。

    实际路径含两个易变 UUID 段：
      %LOCALAPPDATA%\<Root>\local-agent-mode-sessions\skills-plugin\<固定>\<会话>\skills
    所以用通配发现而不是写死。整个目录由 app 托管（含 manifest.json 与
    .claude-plugin），注册为只读来源，不向其中写入。
    """
    import glob
    base = os.environ.get("LOCALAPPDATA") or os.path.join(USERPROFILE, "AppData", "Local")
    out = []
    for root in ("Claude-3p", "Claude"):
        pat = os.path.join(base, root, "local-agent-mode-sessions",
                           "skills-plugin", "*", "*", "skills")
        for p in sorted(glob.glob(pat)):
            if os.path.isdir(p):
                out.append(p)
    return out


CLAUDE_DESKTOP = dict(
    id="claude-desktop", name="Claude 桌面版", vendor="Anthropic", color="#c15b3c",
    icon='<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    verified=True, read_only=True,
    skills=[dict(path=p, role="source") for p in _claude_desktop_skill_dirs()],
    mcp=None, plugins=[],
    note="桌面版技能由 app 托管（路径含会话 UUID，不写入）；"
         "与 Claude Code 的 ~/.claude/skills 互不可见。")

def refresh_desktop_sources():
    """桌面端技能路径含会话 UUID，会随会话变化；每次扫描前重新发现。"""
    dirs = _claude_desktop_skill_dirs()
    cur = [s["path"] for s in CLAUDE_DESKTOP["skills"]]
    if dirs != cur:
        CLAUDE_DESKTOP["skills"] = [dict(path=p, role="source") for p in dirs]
    return CLAUDE_DESKTOP["skills"]


# 只读来源：会被扫描展示，但不参与分发与写入
SOURCES = [SOURCE_ONLY, CLAUDE_DESKTOP]


def load_state() -> dict:
    p = os.path.join(DATA, "state.json")
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {}


def save_state(st: dict):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "state.json"), "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, indent=2)
