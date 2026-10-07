# AOCI + Cursor 配置说明（RiverEdge）

本仓库已接入 [AOCI-CODE](https://github.com/aoci-spec/aoci-code)（认知索引 + MCP）。本文只说明**本机怎么用**，不替代 `AGENTS.md` 与 AOCI 官方 README。

## 已完成的配置

| 项 | 位置 / 状态 |
|---|---|
| CLI | `D:/aoci/aoci.exe`（本机绝对路径，勿提交） |
| 初始化 | `aoci init --agent cursor --locale zh-CN` |
| 基线 | `aoci scan` → `.aoci/baseline.json` |
| Cursor MCP | `.cursor/mcp.json`（整目录已在根 `.gitignore`，含本机路径） |
| 宿主规则 | 根目录 `AGENTS.md`（含 `<!-- aoci:begin/end -->`） |
| 索引卷 | `aoci.txt` / `aoci.meta.txt` / `aoci.code.txt` |
| AI 端点 | **未启用**（纯离线；无源码外发） |

## 你需要做的一次性操作

1. **重载 Cursor**：命令面板 → `Developer: Reload Window`。
2. **Settings → MCP**：确认服务器 **aoci** 为启用；若报错，检查 `D:/aoci/aoci.exe` 是否存在、杀毒是否拦截。
3. **新开 Agent 对话**（本仓库根 `f:\dev\riveredge`），按顺序：
   - 调用 **`aoci_rules`**
   - 无参调用 **`aoci_maintain`**（领取当前机器批次候选）
   - 根据源码为每条候选写 FRAS，再 **`aoci_update_entry`** 提交**整批**
   - `remaining` 非零则重复 maintain → 写 → update，直到 Guide 指示进入 Verify

说明：在 Cursor 外（脚本管道）启动 `aoci mcp` 在 Windows 上可能失败；**Maintain 必须在 Cursor 已连接 MCP 的 Agent 里做**。

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
