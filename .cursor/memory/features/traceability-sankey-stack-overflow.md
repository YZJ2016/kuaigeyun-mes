---
title: 追溯桑基/流程 Maximum call stack
slug: traceability-sankey-stack-overflow
status: delivered
domain: kuaizhizao-quality
when: 追溯管理导出报告或看图时报 Maximum call stack / 快制造应用加载错误
keywords:
  - 追溯报告
  - Maximum call stack
  - dropDirectedSankeyCycles
  - TraceSankeyChart
  - dagre
standard: 去环用迭代 DFS；图表错误隔离在 SankeyChartErrorBoundary
updated: 2026-10-09
---

# 追溯桑基/流程爆栈

## 何时读 / 禁止另起

- 何时读：质量追溯「导出追溯报告」或切换桑基/流程图后整应用崩溃
- 禁止：不要再写递归 DFS 去环；不要让图表错误冒泡到 `AppErrorBoundary`

## 标准入口

| 层 | 标准 |
|----|------|
| FE 去环 | `traceToSankey.dropDirectedSankeyCycles`（显式栈） |
| FE 桑基 | `TraceSankeyChart` + 局部 ErrorBoundary |
| FE 流程 | `traceability/index.tsx` graphBundle 边先去环再 dagre |
| FE 导出 | `traceabilityApi.downloadReport` 截断错误文案 |

## 踩坑

- 用户点「导出」时页面已在渲染桑基图；长链递归 dfs / d3 遇环会 `Maximum call stack size exceeded`，被快制造 `AppErrorBoundary` 收成「应用加载错误」
- 后端 PDF 失败堆栈很长时勿整段塞进 `message.error`
