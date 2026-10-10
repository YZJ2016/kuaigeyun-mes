---
title: AOCI MCP 三仓绑定
slug: aoci-mcp-three-repos
status: active
domain: tooling
when: AOCI 只读到主仓、工位/Pro 搜不到 Entry、要配 Cursor MCP
keywords:
  - aoci-client
  - aoci-pro
  - mcp.json
  - runtime_repository_root
  - 三仓 AOCI
standard: 三个 MCP 服务各绑一仓；任务落在哪仓就调哪套 aoci_* 工具
---

# AOCI MCP 三仓绑定

## 目标

多根工作区同时能读主仓 / client / pro 的正式索引，互不合并。

## 标准入口

| MCP 服务名（Cursor 可能显示为 `user-*`） | `--repo` |
|---|---|
| `aoci` | `D:/kuaigeyun-pro/kuaigeyun` |
| `aoci-client` | `D:/kuaigeyun-pro/kuaigeyun-client` |
| `aoci-pro` | `D:/kuaigeyun-pro/kuaigeyun-pro` |

CLI：`C:/Users/Administrator/Tools/aoci/aoci.exe`（与 `C:/aoci/bin/aoci.exe` 同版亦可）。

配置落点（本机，勿提交）：

- 用户级：`C:/Users/Administrator/.cursor/mcp.json`
- 各仓：`<repo>/.cursor/mcp.json`

## Agent 怎么用

1. 先看任务落点：PC/API → `aoci`；工位/移动/TV/小程序 → `aoci-client`；闭源 Pro 包 → `aoci-pro`
2. 对该服务调 `aoci_rules` → `aoci_overview`（或 check_only 核对 `runtime_repository_root`）
3. 禁止用主仓 Overview 代替 client/pro 认知

## 踩坑

- `aoci mcp` 全局只有一个 `--repo`，不能一条 args 塞三仓
- 改完 mcp.json 需 **Reload Window**，并在 Settings → MCP 确认三个服务均已启用
- `check_only` 若 `runtime_repository_root` 仍是单仓，说明对应服务未起来或仍在用旧进程

## 关联

- `principles/three-repo-map.md`
- `docs/core/aoci-cursor-setup.md`
