---
title: 工序暂停跨端对齐
slug: station-pause-cross-client
status: delivered
domain: mes-station
when: 暂停是否与 PC/移动对齐、停机原因码、pause/resume API
keywords:
  - pause
  - resume
  - 暂停
  - DOWNTIME_REASONS
  - PAUSE_REASONS
  - material_shortage
standard: 三端共用 POST .../operations/{id}/pause|resume；原因码以后端 DOWNTIME_REASON_LABELS 为准；PC 工单页仅展示/拦报工，无持久化暂停操作
---

# 工序暂停跨端对齐

## 标准入口

| 端 | 行为 |
|----|------|
| 后端 | `StationService.pause/resume_work_order_operation`；API `.../operations/{id}/pause\|resume` |
| 工位 | `DowntimeReasonModal` + `stationApi.pauseOperation`（可带 `workstation_id`）；恢复无二次确认 |
| 移动 | `work-order-detail` 工序行；`pauseOperation`/`resumeOperation`；恢复无确认；暂停后可跟安灯 |
| PC 工单 | **展示** paused、拦报工、浮窗看原因；**无** pause/resume 写操作 |
| PC kiosk | 本地「暂停」占位，注释写明未持久化 |

## 原因码（唯一标准）

`material_shortage` / `material_wait` / `equipment_fault` / `tool_change` / `quality_issue` / `break` / `other`

## 踩坑

- 勿把 PC kiosk 本地暂停当成已对齐
- 工位曾缺「缺料/换刀」仅有「待料」——已与移动/后端拉齐
