---
title: AOCI 何时维护、提交什么、与构建推送顺序
slug: aoci-git-commit
status: active
domain: principle
when: 要不要跑 AOCI、每次提交是否 maintain、提不提 aoci.txt
keywords:
  - aoci
  - aoci_maintain
  - aoci_update_entry
  - 勿排除索引
  - baseline.json
standard: 启用本仓 AOCI 且改了托管对象时按需维护；正式资产随变更提交；未挂载或豁免时如实报告
---

# AOCI 正式资产与 Git 提交（私有 Fork 单仓口径）

- 规则真源：外层根仓 `.cursor/rules/aoci-git-commit.mdc`、`.cursor/rules/build-push-aoci.mdc`
- 本仓单仓聚合：后端、PC 前端、`kuaigeyun-client/` 与 4 个 PRO 均在 `kuaigeyun-mes/` 内共用 `.aoci/`（不使用上游三仓分离 MCP）。

## 触发边界

- **启用本仓 AOCI MCP/CLI 且改了托管对象时**：在源码稳定后执行一次 `aoci_maintain`（有候选则整批 `aoci_update_entry`），并将更新后的正式资产随业务提交。
- **未挂载本仓 AOCI、用户明确豁免、或仅改 `.cursor/memory/**`（AOCI 已 exclude）与纯说明文档时**：跳过 maintain，并在交付说明中如实注明。
- **禁止**：用外层只读对照仓 `../kuaigeyun-aoci/.aoci/` 覆盖本仓 `.aoci/`。

## 应提交 / 勿提交

| 应提交（若触发维护） | 勿提交（本地运行时） |
| --- | --- |
| `aoci.txt`、`aoci.meta.txt`、`aoci.code.txt`、`AGENTS.md`（AOCI 块） | `.aoci/` 下 lock、ledger、batch JSON、drafts 等运行时文件 |
| `.aoci/config.json`、`.aoci/baseline.json`、`.aoci/curation.json`、`.aoci/.gitignore` | `.cursor/mcp.json` 与本机 CLI 路径 |

## 关联

- `../.cursor/rules/aoci-git-commit.mdc`
- `../.cursor/rules/build-push-aoci.mdc`
- `principles/code-push-routing.md`
