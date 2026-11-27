# AOCI + Cursor 配置说明（kuaigeyun-mes 私有 Fork）

本仓库保留 [AOCI-CODE](https://github.com/aoci-spec/aoci-code) 认知索引资产（`aoci.txt`、`aoci.meta.txt`、`aoci.code.txt` 与 `.aoci/`）。本文仅说明本私有 Fork 的本机接入约定，不替代根目录 `AGENTS.md` 中的 AOCI 协议块。

## 本仓约定（单仓聚合）

- **单仓索引**：后端、PC 前端、`kuaigeyun-client/` 与本仓内 4 个 PRO 均位于 `kuaigeyun-mes/` 内，共用本仓 `.aoci/`；**不再使用**上游 `aoci` / `aoci-client` / `aoci-pro` 三仓分离 MCP。
- **只读对照仓**：外层 `../kuaigeyun-aoci/` 仅用于评估上游认知意图与参考 `../kuaigeyun-aoci/.cursor/skills/`，**禁止**将其 `.aoci/` 覆盖到本仓。
- **本机路径不入库**：`.cursor/mcp.json` 与本机 AOCI CLI 路径属机器私有配置，禁止提交任何盘符绝对路径进仓库。

## Git 提交边界

| 应提交（若触发维护） | 勿提交（本地运行时） |
| --- | --- |
| `AGENTS.md`、`aoci.txt`、`aoci.meta.txt`、`aoci.code.txt` | `.cursor/mcp.json`、本机 CLI 路径 |
| `.aoci/baseline.json`、`.aoci/config.json`、`.aoci/curation.json`、`.aoci/.gitignore` | `.aoci/ledger.jsonl`、`verify_history/`、`drafts/` 等运行时文件 |

触发与豁免规则见 `.cursor/rules/aoci-git-commit.mdc` 与 `.cursor/rules/build-push-aoci.mdc`。
