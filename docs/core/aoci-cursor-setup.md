# AOCI + Cursor 配置说明（RiverEdge）

本仓库已接入 [AOCI-CODE](https://github.com/aoci-spec/aoci-code)（认知索引 + MCP）。本文只说明**本机怎么用**，不替代 `AGENTS.md` 与 AOCI 官方 README。

## 已完成的配置

| 项 | 位置 / 状态 |
|---|---|
| CLI | `D:/aoci/aoci.exe`（本机绝对路径，勿提交） |
| 初始化 | `aoci init --agent cursor --locale zh-CN` |
| 基线 | `aoci scan` → `.aoci/baseline.json` |
| Cursor MCP | 用户级 `~/.cursor/mcp.json` + 各仓 `.cursor/mcp.json`：`aoci` / `aoci-client` / `aoci-pro` 各绑一仓（`.cursor/` gitignore） |
| 宿主规则 | 根目录 `AGENTS.md`（含 `<!-- aoci:begin/end -->`） |
| 索引卷 | `aoci.txt` / `aoci.meta.txt` / `aoci.code.txt` |
| AI 端点 | **未启用**（纯离线；无源码外发） |

## 你需要做的一次性操作

1. **重载 Cursor**：命令面板 → `Developer: Reload Window`。
2. **Settings → MCP**：确认 **aoci**、**aoci-client**、**aoci-pro** 三个服务均启用；若报错，检查 `C:/Users/Administrator/Tools/aoci/aoci.exe`（或本机等价路径）是否存在、杀毒是否拦截。
3. **按任务选仓**后新开 Agent 对话：
   - 主仓 PC/API → 服务 `aoci`（`--repo D:/kuaigeyun-pro/kuaigeyun`）
   - 工位/移动/TV/小程序 → `aoci-client`
   - 闭源 Pro 包 → `aoci-pro`
   - 对该服务：`aoci_rules` → `aoci_overview`（或 maintain 批次流程）
   - `check_only` 核对 `runtime_repository_root` 是否为目标仓

说明：`aoci mcp` 单进程只能绑一个 `--repo`，故必须三个 MCP 条目。Maintain 须在 Cursor 已连接对应 MCP 的 Agent 里做。详见 `.cursor/memory/features/aoci-mcp-three-repos.md`。

## 索引进度（维护时自行 `aoci status`）

- 全库约 **5800+** 待写 Entry，默认每批最多 **50** 条（`.aoci/config.json` → `code_cognition_batch_entries`）。
- 根目录 5 个文件已写入示例 Entry；其余按 MCP 批次推进即可。

## Git 建议

| 建议提交 | 不建议提交 |
|---|---|
| `AGENTS.md`、`aoci.txt`、`aoci.meta.txt`、`aoci.code.txt` | `.cursor/`（含 `mcp.json`） |
| `.aoci/baseline.json`、`.aoci/config.json`、`.aoci/curation.json`（若有） | `.aoci/ledger.jsonl`、`verify_history/` 等运行时 |
| `.gitattributes`（AOCI 与 LF 契约） | 本机 `aoci.exe` 路径 |

## 常用 CLI（Git Bash）

```bash
D:/aoci/aoci.exe --repo f:/dev/riveredge doctor
D:/aoci/aoci.exe --repo f:/dev/riveredge status
D:/aoci/aoci.exe --repo f:/dev/riveredge verify
D:/aoci/aoci.exe --repo f:/dev/riveredge index agent guide --agent cursor
```

可选：启用 AI 批量起草时执行 `aoci ai setup`（会配置外发端点，需团队同意后再开）。
