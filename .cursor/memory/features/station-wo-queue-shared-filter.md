---
title: 工位工单队列筛选固定/共享同一套
slug: station-wo-queue-shared-filter
status: delivered
domain: mes-station
when: 固定工位筛选与共享不一致、全部/指派/缺料/生产中/已冻结、工单搜索模糊
keywords:
  - workOrderQueue
  - buildWorkOrderQueueListParams
  - isQueueLoadableWorkOrder
  - matchesKeyword
  - WoQueueScope
  - StationTerminal
  - SharedReportTerminal
standard: 队列请求与客户端筛选只在 workOrderQueue；禁止 work_center_id 收窄队列；搜索走 keyword+客户端模糊
---

# 工位工单队列筛选固定/共享同一套

## 目标

固定工位与共享报工的工单筛选/搜索语义一致。

## 标准入口

| 层 | 标准 |
|----|------|
| 请求参数 | `buildWorkOrderQueueListParams`（mine / keyword；**不传** work_center_id） |
| 载入状态 | `isQueueLoadableWorkOrder`（released / in_progress） |
| 客户端筛/排 | `filterAndSortWorkOrders` |
| 模糊搜索 | 后端 `keyword` + 客户端分词/多字段/顺序子序列 |

## 踩坑

- 工单头 `work_center_id` 常空或与工序工作中心不一致；固定工位用它收窄会漏单，已废止。
- 工位绑定信息仍用于安灯/设备等，只是不再过滤工单队列。

## 关键文件

`kuaigeyun-client/riveredge-app-station/src/utils/workOrderQueue.ts`
`StationTerminal` / `SharedReportTerminal`
