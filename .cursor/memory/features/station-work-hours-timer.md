---
title: 工位报工工时计时口径
slug: station-work-hours-timer
status: delivered
domain: mes-station
when: 工位工时不对、计时含停机、多次报工工时翻倍、标准工时×数量
keywords:
  - work_hours
  - 工时
  - 计时
  - actual_start
  - reportingWorkTime
standard: 固定工位「本次」净工时（开工跑/暂停停/报工清零）；提交 0 时后端用标准工时×数量；PC 用起止时刻三向联动
---

# 工位报工工时计时口径

## 目标

工位报工 `work_hours` 表示**本次报工**净作业时间，不含停机，不跨次累加。

## 何时读 / 禁止另起

- 何时读：工位工时偏大、暂停后仍涨、连报工时翻倍
- 禁止：用 `Date.now()-actual_start` 回填（含停机）；报工后不清零继续累加；另写一套与 `reportingWorkTime` 平行的 PC 联动

## 标准入口

| 场景 | 口径 |
|------|------|
| 固定工位 | `StationTerminal` 本会话计时；暂停冻结；报工成功清零；标签「本次计时中」 |
| 共享报工 | 手工填；0 交给后端推导 |
| PC 报工 | `utils/reportingWorkTime.ts` 起止+工时三向联动 |
| PC 默认填 | `standard_time × 数量` |
| 后端兜底 | `ReportingService._derive_work_hours_from_operation`：`work_hours<=0` → 标准工时×报工数量 |

## 关键文件

| 角色 | 路径 |
|------|------|
| 工位计时 | `kuaigeyun-client/.../StationTerminal/index.tsx` |
| PC 联动 | `riveredge-frontend/.../utils/reportingWorkTime.ts` |
| 后端推导 | `reporting_service.py` `_derive_work_hours_from_operation` |

## 踩坑

- `check-shortage` 类比：开工墙钟 ≠ 净工时
- 状态码要含中文「进行中/暂停」否则计时不跑
- 提交 0 会被后端改成标准工时×数量，工位若要「如实 0」需显式传极小正数或改后端（当前按推导设计）
