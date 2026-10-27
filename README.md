# agent-hub

统一管理多个 AI coding agent 的 Skill 与 MCP 配置。装一次，处处可用。

同时用好几个 agent 时，每装一个技能都要在各家目录里重复一遍。agent-hub 的做法是
**只保留一份真源（`data/skills/`）**，其余位置全部换成目录联接指回真源——改一处，所有 agent 同时生效。

## 两种用法

**桌面版（Windows，推荐）** — 双击 `AgentHub.exe`，原生窗口，不依赖浏览器。
首次启动自动把源码项目里的 `data/` 迁移到 `%LOCALAPPDATA%\AgentHub`，之后数据独立存放。

**源码运行** — 需要 Python 3.11+（用到 `tomllib`），无第三方依赖：

```bash
git clone https://github.com/cancan7777777/agent-hub.git
cd agent-hub

# Windows：双击 start-hub.cmd，或
pwsh -File ./start-hub.ps1

# macOS / Linux
python core/server.py
```

然后打开 http://127.0.0.1:8765/ 。

## 功能

- **技能 × agent 矩阵** — 一眼看清每个技能装在哪些 agent，每个方格独立开关
- **一键托管** — 自动收进真源、备份原副本、就地建联接，并装到常用几家
- **MCP 统一分发** — 主列表一份，按各家原生格式写入（`config.toml` / `opencode.jsonc` / 各自 `mcp.json`）
- **外部改动自动同步** — 后台监听各 agent 目录，任何一家新增技能或 MCP，约 2 秒内自动纳入
- **开机自启**（Windows）— 一键写入当前用户启动项，不需要管理员权限
- **安全可回滚** — 替换前先备份成 zip 存 `data/backups/`；写配置最小编辑 + 回读校验，失败自动回滚

## 支持的 agent

| Agent | 技能目录 | MCP 配置 |
|---|---|---|
| Codex / ChatGPT | `~/.codex/skills` | `~/.codex/config.toml` |
| Claude Code / 桌面 Code | `~/.claude/skills` | `~/.claude.json` |
| Claude 桌面版 Cowork | 会话私有目录（只读来源） | 不写入 |
| Cursor | `~/.cursor/skills` | `~/.cursor/mcp.json` |
| Gemini CLI | `~/.gemini/config/skills` | `~/.gemini/config/mcp_config.json` |
| Antigravity | `~/.gemini/antigravity/builtin/skills` | 同 Gemini CLI |
| OpenCode | `~/.config/opencode/skills` | `~/.config/opencode/opencode.jsonc` |
| Pi Coding Agent | `~/.pi/agent/skills` | `~/.pi/agent/mcp.json` |
| Trae CN | `~/.trae-cn/builtin_skills` | `~/.trae-cn/mcp.json` |
| Qoder CN | `~/.qoder-cn/skills` | `~/.qoder-cn/mcp.json` |
| WorkBuddy | `~/.workbuddy/skills` | `~/.workbuddy/mcp.json` |
| ZCode | `~/.zcode/skills` | `~/.zcode/cli/mcp.json` |
| DeepSeek Harness | `~/.dsh/skills` | `~/.dsh/mcp.json` |

要增减支持范围，编辑 `core/registry.py` 里的 `AGENTS` 列表。
`~/.agents/skills` 是 [Agent Skills](https://agentskills.io) 规范的标准位置，Codex、Gemini CLI、Pi 等原生读取。

## Claude Code 与桌面版的关系

**Claude Code（CLI）和桌面版 Code 模式共用 `~/.claude`，技能与插件自动互通；Cowork 模式隔离。**

Cowork 跑在独立 Linux 虚拟机里，只读 app 下发的插件目录。Hub 把它登记为只读来源：
可以把它内置的技能（`docx`、`pdf`、`xlsx`、`pptx` 等）取出来分发给其他 agent，但不往里写。

## 首次使用

首次运行是空库，两种起步方式：

1. **一键导入** — 技能页顶部按钮，扫描各 agent 现有技能，择优收进真源并按默认范围分发
2. **吸收 MCP** — MCP 页「从 Codex 吸收」，读进已有配置

之后新增技能任选：放进任意 agent 的技能目录、放进 `data/skills/`、或在界面点「+ 添加技能」。

## 目录结构

```
agent-hub/
├── desktop.py                 桌面版入口（pywebview 原生窗口）
├── tools/                     打包脚本（PyInstaller spec、图标）
├── start-hub.ps1 / .cmd       浏览器版启动
├── stop-hub.ps1               停止
├── core/                      后端（server / registry / scan / consolidate / mcp_hub / watcher ...）
├── ui/                        前端（无框架，可离线运行）
├── data/                      skills 真源、mcp.json、backups（运行期产物，不入库）
└── tests/                     测试
```

## 打包桌面版（可选）

```powershell
python -m venv .buildenv
.buildenv\Scripts\pip install pywebview pyinstaller
.buildenv\Scripts\pyinstaller --noconfirm tools\AgentHub.spec
# 产物：dist\AgentHub.exe
```

## 运行测试

```bash
python tests/test_jsonc_patch.py
```

## 已知边界

- 插件不做跨工具统一（各家格式与签名机制互不兼容），插件页只做盘点
- 改完技能需重启 agent——多数 agent 只在启动时扫描技能目录
- 服务只监听 `127.0.0.1`，不提供远程访问，也不做任何网络请求

## License

MIT
