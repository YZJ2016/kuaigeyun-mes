---
title: 跨仓文档与开发记忆检索入口
slug: mes-vault-index
status: active
domain: principle
when: 任何本仓 MES 开发、改架构/调用链/客户端边界
keywords:
  - architecture-map
  - doc-map
  - 代码结构图谱
  - 跨仓文档
standard: ../docs/00.doc-map.md
---

# 跨仓文档与开发记忆检索入口

> 原上游记录中的本机 Vault 路径不适用于本私有 Fork；本仓所有权威规范与文档均在工作区仓库内维护。

## 权威文档分层

| 位置 | 用途 |
| --- | --- |
| `../AGENTS.md` | L1 项目总纲：跨仓边界、红线、多选项决策、14 位迁移号、上游同步规程 |
| `../docs/00.doc-map.md` | 跨仓总索引：外层 `02.requirements` / `03.design` / `04.specs` / `05.manuals` 与主仓文档映射 |
| `AGENTS.md` | L2 本仓私有 Fork 边界 + AOCI 接入合同 |
| `../.cursor/rules/*.mdc` | L3 全局与业务代码/交付契约（统一收口在外层根仓，按 `kuaigeyun-mes/...` globs 触发） |
| `.cursor/memory/` | 已落地功能的标准入口/扩展点/踩坑笔记（给关键词路由与 Grep 用） |
| `docs/core/` 与 `riveredge-backend/docs/` | 权限、应用层、双单位、API 写防护、配置中心等核心契约 |
| `../docs/06.upstream-sync/` | 上游同步唯一现行真源（`台账.md` + `文件级台账.tsv`；`archive/` 仅回溯；脚本 `../scripts/sync_upstream_audit.py`） |
| `../.agents/skills/` | 外层根仓业务 Skills（新建 PC 页、UniTable、详情抽屉等，19 个） |

## 开发时怎么读（自主分层）

1. **先查总纲与总索引**：`../AGENTS.md`、`../docs/00.doc-map.md`、`AGENTS.md`。
2. **定位功能标准做法**：按 `.cursor/memory/README.md` 关键词表只打开命中的 1～3 篇。
3. **查真实代码结构**：优先使用 CodeGraph / 源码定位，不依赖过时静态图谱。

## 关联

- `.cursor/rules/ai-memory.mdc`
- `principles/three-repo-map.md`
- `principles/reuse-existing-patterns.md`
