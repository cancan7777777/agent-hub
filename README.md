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
- **一键托管** — 点行首方框，自动择优收进真源、备份原副本、就地建联接，并装到常用的几家
- **默认安装范围可调** — 技能页「默认安装」选择新增技能自动装给哪几个 agent，默认 Codex / Claude Code / Antigravity，不必一上来就铺满全部
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
| Claude Code / 桌面 Code | `~/.claude/skills` | `~/.claude.json` |
| Claude 桌面版 Cowork | 会话私有目录（只读来源） | 桌面版自管，不写入 |
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

## Claude Code、桌面 Code 与 Cowork 的共用关系

**结论：Claude Code（CLI）和桌面版 Code 模式共用 `~/.claude`，技能与插件自动互通；Cowork 模式是隔离的。**

实测依据（Claude 桌面版 2.42304.0 / CLI 2.1.299）：

| | Claude Code（CLI） | 桌面版 Code 模式 | 桌面版 Cowork 模式 |
|---|---|---|---|
| 配置目录 | `~/.claude` | `~/.claude`（同一份） | 会话私有 `.claude`，由 `CLAUDE_CONFIG_DIR` 指定 |
| 技能位置 | `~/.claude/skills` | 同上（复用 CLI 加载器） | `%LOCALAPPDATA%\Claude-3p\local-agent-mode-sessions\skills-plugin\<UUID>\<UUID>\skills` |
| 运行环境 | 本机进程 | 本机进程，工作目录是真实 Windows 路径 | 独立 Linux 虚拟机（`rootfs.vhdx`），工作目录 `/home/…` |
| Hub 分发结果 | 可用 | 可用（与 CLI 同一份，无需重复分发） | 不可用（只读来源，可单向取用） |

判定依据：
- Code 模式会话的 `cliSessionId` 落在 `~/.claude/projects/`，工作目录是 `D:\…` 这样的真实 Windows 路径，
  启动日志写着 `[CCD] 2 ~/.claude plugin(s) left to the CLI's own loader (not passed as --plugin-dir)`，
  全程没有 `CLAUDE_CONFIG_DIR` 覆盖 —— 说明它就是在本机跑 Claude Code 的加载器。
- 只有 Cowork 会话的日志里才出现 `CLAUDE_CONFIG_DIR: …\local-agent-mode-sessions\…\.claude`，
  工作目录也是 Linux VM 的 `/home/…`。

### 为什么 Codex / Claude Code / 桌面 Code 能共用

技能格式都遵循 [Agent Skills](https://agentskills.io) 规范，一个含 `SKILL.md` 的目录谁都能读，
差别只在「各家去哪个目录找」：

| Agent | 是否原生读 `~/.agents/skills` | 原生技能目录 |
|---|---|---|
| Codex | 是 | `~/.codex/skills`、`~/.agents/skills` |
| Claude Code / 桌面 Code | 否 | `~/.claude/skills` |
| Gemini CLI / Pi | 是 | 各自目录 + `~/.agents/skills` |

agent-hub 不去依赖各家是否读同一个目录，而是**在每个 agent 的原生目录里放一个目录联接，指回 `data/skills` 这一份真源**。
所以即使 Claude Code 不读 `~/.agents/skills`，它照样能读到同一个技能 —— 因为 `~/.claude/skills` 下面那个
目录本身就是真源的别名。桌面版 Code 模式直接复用 Claude Code 的加载器，也就跟着看到了。

这才是「装一次、处处可用」的真实原理：**真源唯一 + 原生目录联接**，而不是指望所有 agent 都读同一个路径。
个别 agent 若原生支持 `~/.agents/skills`，hub 会去掉重复镜像，避免同一技能被注入两次。

Cowork 不在这个圈子里：它跑在独立 Linux VM 里，只读 app 下发的插件目录，
既读不到 `~/.claude/skills`，也读不到 `~/.agents/skills`。Hub 把它登记为只读来源 ——
可以从中取技能出来分发给别人，但不往里写。

### Cowork 的内置技能可以单向取用

Cowork 那个 `skills` 目录本身就是标准的 Claude Code 插件结构（含 `.claude-plugin/plugin.json`），
本工具已支持把它里面的技能取出并分发给其他 agent：

1. 技能页找到来自「Claude 桌面版 · Cowork」的那几行（`docx`、`pdf`、`xlsx`、`pptx`、`frontend-design` 等）
2. 点行首方框托管 → 内容复制进真源，Cowork 原目录保持不动
3. 之后就能像普通技能一样分发给 Claude Code、Codex 等任意 agent

注意其中几个依赖 Cowork 自身运行时（`schedule` 定时任务、`explain-usage`、
`setup-cowork`、`consolidate-memory`），搬到别的 agent 后指令能读、但调用的工具不存在，
这类建议不要托管。纯知识型的（`docx`、`pdf`、`pdf-reading`、`xlsx`、`pptx`、`frontend-design`）搬过去可用。

**官方的 `@synced` 通道对你无效**：Claude Code 会把你在 claude.ai 账户开启的插件同步进终端，
但官方文档明确排除了一类会话 —— 凭证由 `ANTHROPIC_AUTH_TOKEN` / 网关提供的情况。
你当前通过 CC Switch 走本地网关，正好属于这一类，所以同步插件不会加载。

### 插件情况

- **CLI 与桌面 Code 模式**：插件交给同一个 CLI 加载器（日志原文 `left to the CLI's own loader`），
  所以 `~/.claude/plugins` 下已启用的插件在 Code 模式同样可用。
- **Cowork**：插件由 app 下发到会话目录，与 CLI 的 `installed_plugins.json` + 缓存是两套东西，
  路径与校验方式都不同。本工具的插件页对 Cowork 只做盘点，不写入。

---

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

1. **一键导入** — 技能页顶部「一键导入」，扫描各 agent 现有技能，择优收进真源并按默认范围分发
2. **吸收 MCP** — MCP 页「从 Codex 吸收」，把 `config.toml` 里已有的服务器读进主列表

之后新增技能只需任选一种：
放进任意一个 agent 的技能目录、放进 `data/skills/`、或在界面点「+ 添加技能」粘贴目录/zip 路径。

新增的技能只会自动装到「默认安装」里勾选的 agent（外加技能原本所在的那一家）。
装得越少，各家启动时要读的技能清单越短；其余 agent 要用，在矩阵里单独点格子即可。

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
