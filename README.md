# agent-hub

统一管理多个 AI coding agent 的 Skill 与 MCP 配置。装一次，处处可用。

## 解决什么问题

同时用好几个 agent 时，每装一个技能都要在各家目录里重复一遍：
`~/.codex/skills`、`~/.claude/skills`、`~/.cursor/skills`、`~/.gemini/config/skills` ……
副本一多就会出现版本漂移——同一个技能在 A 里是新版、在 B 里还是旧版，而且重复占磁盘。

agent-hub 的做法是**只保留一份真源**，其余位置全部换成目录联接（Windows Junction / POSIX symlink）指回真源。
改一处，所有 agent 同时生效；删一处副本，不会伤到真源。

## 功能

- **可视化控制台** — 浏览器里的「技能 × agent」矩阵，一眼看清每个技能装在了哪些 agent
- **一键托管** — 点行首方框，自动择优收进真源、备份原副本、就地建联接，并铺满所有 agent
- **单个开关** — 矩阵里每个方格独立控制某个 agent 要不要这个技能
- **MCP 统一分发** — 主列表一份，按各家原生格式写入：Codex 写 `config.toml`，OpenCode 写 `opencode.jsonc`，其余写各自 `mcp.json`
- **外部改动自动同步** — 后台监听各 agent 目录与配置文件，你在任何一家新增技能或 MCP，界面约 2 秒内自动发现并纳入管理
- **三页搜索** — 技能 / MCP / 插件都支持多关键词检索（空格为 AND）与命中高亮
- **插件盘点** — 跨 agent 列出已安装插件与来源市场（各家插件格式互不兼容，此页只读）
- **安全可回滚** — 任何被替换的目录先压成 zip 存进 `data/backups/`；写 `config.toml` 采用最小文本编辑 + 回读校验，失败自动回滚

## 支持的 agent

| Agent | 技能目录 | MCP 配置 |
|---|---|---|
| Codex / ChatGPT | `~/.codex/skills` | `~/.codex/config.toml` |
| Claude Code | `~/.claude/skills` | `~/.claude.json` |
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

要增减支持范围，只需编辑 `core/registry.py` 里的 `AGENTS` 列表。
`~/.agents/skills` 是 [Agent Skills](https://agentskills.io) 规范的标准位置，
Codex、Gemini CLI、Pi 等都会原生读取它。

## 快速开始

需要 Python 3.11 以上（用到 `tomllib`），无第三方依赖。

```bash
git clone https://github.com/cancan7777777/agent-hub.git
cd agent-hub

# Windows：双击 start-hub.cmd，或
pwsh -File ./start-hub.ps1

# macOS / Linux
python core/server.py
```

然后打开 http://127.0.0.1:8765/ 。

首次运行是**空库**：真源里没有任何技能，MCP 主列表也是空的。
两种起步方式：

1. **一键导入** — 技能页顶部「一键导入」，扫描各 agent 现有技能，择优收进真源并铺满
2. **吸收 MCP** — MCP 页「从 Codex 吸收」，把 `config.toml` 里已有的服务器读进主列表

之后新增技能只需任选一种：
放进任意一个 agent 的技能目录、放进 `data/skills/`、或在界面点「+ 添加技能」粘贴目录/zip 路径。

## 目录结构

```
agent-hub/
├── start-hub.ps1 / .cmd     启动
├── stop-hub.ps1             停止
├── core/                    后端
│   ├── server.py              HTTP 服务与 API
│   ├── registry.py            agent 路径约定
│   ├── scan.py                扫描与矩阵
│   ├── consolidate.py         收敛与托管
│   ├── mcp_hub.py             MCP 分发
│   ├── mcp_format.py          各家 MCP 格式互转
│   ├── jsonc_patch.py         保注释的 JSONC 定点编辑
│   ├── plugin_hub.py          插件盘点
│   ├── watcher.py             外部改动监听与自动归集
│   └── fsutil.py              指纹缓存 / 联接 / 安全删除
├── ui/                      前端（无框架，字体本地化可离线运行）
├── data/
│   ├── skills/                真源
│   ├── backups/               改动前的 zip 备份
│   ├── mcp.json               MCP 主列表
│   └── state.json             偏好设置
├── logs/                    运行日志
└── tests/                   测试
```

`data/` 与 `logs/` 属于运行期产物，已在 `.gitignore` 中排除，不会被提交。

## 运行测试

```bash
python tests/test_jsonc_patch.py
```

覆盖 JSONC 定点编辑的注释保真、缩进、增删覆盖、幂等与损坏输入，
以及 MCP 写入的端到端往返。

## 工作机制

**指纹缓存** — 每个技能目录按「相对路径 + mtime + 体积」算廉价签名，签名未变则复用已缓存的内容哈希；
多个联接指向同一真源时按真实路径归并，只计算一次。因此首次扫描约 1 秒，之后热扫描在百毫秒级。

**局部更新** — 点击方格后端只重算受影响的那一行并返回，前端只替换该行 DOM，
因此不跳顶、不丢焦点。输入搜索时同理，只重绘列表容器。

**安全删除** — 删除实体目录时自行递归，绝不跨重解析点，
避免 `rmtree` 跟随联接把真源掏空。删除前一律先备份成 zip。

**JSONC 保真** — OpenCode 的配置允许写注释。改它时不做整体反序列化，
而是定位到目标成员做文本级替换，用户手写的注释与排版原样保留。

## 已知边界

- **插件不做跨工具统一**。各家插件清单格式、缓存结构与签名机制互不兼容，
  强行统一会撞上应用自身的更新逻辑。插件页只提供盘点与对照。
- **部分 agent 的技能目录约定未经官方文档确认**（界面标为「未验证」）：
  Trae、Qoder、ZCode、DeepSeek Harness。联接会正常创建，
  但对应应用是否读取该目录需要在应用内确认一次。
- **改完技能需重启 agent**。多数 agent 只在启动时扫描技能目录，不做热加载。
- **服务只监听 127.0.0.1**，不提供远程访问，也不做任何网络请求。

## License

MIT
