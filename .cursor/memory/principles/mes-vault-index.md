---
title: MES Vault 入口与源码图谱
slug: mes-vault-index
status: active
domain: principle
when: 任何本仓 MES 开发、改架构/调用链/客户端边界
keywords:
  - architecture-map
  - 代码结构图谱
  - ai-change-protocol
  - D盘
  - E盘
  - obsidian-memory
standard: E:\AI-Memory\30-Knowledge\MES-Codebase\architecture-map.md
---

# MES Vault 入口与源码图谱

- 写入：2026-10-03
- 真源在 Vault，本篇只指路，不复制图谱正文。

## 两套记忆各管什么

| 位置 | 用途 |
|------|------|
| `E:\AI-Memory` | 跨工具永久记忆：结构图谱、变更协议、业务不变量、纠错台账、测试与 SOP |
| `.cursor/memory/` | 本仓已落地功能的标准入口/扩展点（SyncPushHub 等），给 Grep 用 |

## 开发时怎么读（自主分层）

**每个 MES 改代码任务都读**

- `E:\AI-Memory\MEMORY.md`
- `E:\AI-Memory\30-Knowledge\MES-Codebase\architecture-map.md` — PC/Mobile/Station → `/api/v1` → FastAPI → `apps/*` → PG；关键文件入口在第 10 节
- `E:\AI-Memory\30-Knowledge\MES-Codebase\ai-change-protocol.md` — 证据门槛、禁止事项、D/E 不互拷

**按任务选读**

- 工单/库存/BOM/质量/权限：`development-standards.md` 对应节
- 修过的同类坑：`correction-ledger.md` 按关键词搜
- 跑测试或提交：`test-knowledge.md`
- Web 构建推送：`web-build-push-sop.md` + `features/fast-deploy-scripts.md`
- 同步/外推等已有标准实现：`.cursor/memory/README.md` 路由表

**默认不读**

- 整个 Vault、Inbox、人物、无关项目、金泽调查报告
- `kuaigeyun-workspaces.md` 里的 P5/P6/C 批次长交付（除非任务就是那些批次）
- AOCI 完整 Overview（索引未对齐时用 check_only；不能当图谱替代品）

## MCP

- 已有：`obsidian-memory`（filesystem）可读 Vault 与 `.cursor/memory`
- **没有**接入可查询的 codebase-memory / `search_graph` MCP。调用链用图谱第 5 节 + Grep/读源码。未核到本机服务命令前，不往 `mcp.json` 里加猜测用的图数据库 MCP。

## 关联

- `E:\AI-Memory\30-Knowledge\MES-Codebase\README.md`
- `.cursor/rules/ai-memory.mdc`
- `principles/three-repo-map.md` — 主仓 / client / pro 职责与跨端落点总表
- `principles/reuse-existing-patterns.md`
