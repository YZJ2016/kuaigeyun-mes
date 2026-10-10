---
title: 工位交接班摘要归属
slug: station-shift-handover-summary
status: delivered
domain: mes-station
when: 交接班数量全 0、shift summary、device_info.workstation_id、停机归属
keywords:
  - 交接班
  - shift summary
  - get_shift_summary
  - workstation_id
  - device_info
  - ShiftHandoverModal
standard: 固定工位报工写 device_info.workstation_id；暂停带 workstation_id；摘要按工位过滤并兼容历史未写工位的固定报工
---

# 工位交接班摘要归属

## 目标

固定工位交班弹窗（完成数/报工次数/停机/安灯）按本工位统计，不为 0。

## 何时读 / 禁止另起

- 何时读：交班摘要全 0、改 shift summary 过滤、改工位报工 device_info
- 禁止：另写一套按车间/产线汇总；共享报工计入固定工位交班

## 标准入口

| 层 | 标准 |
|----|------|
| FE 报工 | `StationTerminal` → `reportingApi.quickCreate` 的 `device_info`：`mode:fixed` + `workstation_id` + `client:riveredge-app-station` |
| FE 暂停 | `useDowntimeActions.pause(..., workstationId)` → `OperationPauseRequest.workstation_id` |
| FE 弹窗 | `ShiftHandoverModal` → `stationApi.getShiftSummary({ shift_start, workstation_id })` |
| BE | `StationService.get_shift_summary`：报工按 `device_info.workstation_id`；停机按 remarks `workstation_id=`；安灯按表字段 |

## 关键文件

| 角色 | 路径 |
|------|------|
| 固定工位报工 | `kuaigeyun-client/riveredge-app-station/src/pages/StationTerminal/index.tsx` |
| 暂停 | `.../components/station/DowntimeReasonModal.tsx`、`services/stationApi.ts` |
| 交班 UI | `.../components/station/ShiftHandoverModal.tsx` |
| 摘要服务 | `riveredge-backend/src/apps/kuaizhizao/services/station_service.py` |
| Schema | `schemas/station.py`（Pause 含 `workstation_id`） |

## 扩展点

1. 共享报工：`mode:shared` / `client:station-app`，摘要工位过滤时排除
2. 历史未写工位：`client==riveredge-app-station` 或 `mode==fixed` 仍计入（多工位略偏大，优于全 0）
3. 停机：有 tagged 用 tagged；全无标记则用未打标停机；有他工位标记则不混入

## 踩坑

- 只改摘要过滤不够：写路径不带 `workstation_id` 时严格过滤恒为 0
- `device_info` 是 JSONField；偶发字符串时需 json.loads
- 共享与固定 client 不同，勿混用
