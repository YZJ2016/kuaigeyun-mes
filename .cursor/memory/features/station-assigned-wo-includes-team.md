---
title: 指派给我含班组成员被指派工单
slug: station-assigned-wo-includes-team
status: delivered
domain: mes-station
when: 工位/扫码「指派给我」看不到 PC 只派班组的工单
keywords:
  - assigned_worker_id
  - assigned_team_id
  - WorkGroupMember
  - 指派给我
standard: GET 工单列表 assigned_worker_id = 本人派工 ∪ JSON 多人 ∪ 所在班组 assigned_team_id。
---

# 指派给我含班组成员被指派工单

## 目标

PC 只派班组、账号是班组成员时，工位「指派给我」和人脸自动识别工单列表要出现该工单。

## 何时读 / 禁止另起

- 何时读：班组派工、工位 mine 列表为空、扫人员码无工单。
- 禁止：工位再写一套按工序 assigned_worker_id 的客户端过滤。

## 标准入口

| 层 | 标准 |
|----|------|
| FE | `workOrderApi.list({ assigned_worker_id })`（SharedReportTerminal / StationTerminal） |
| BE | `_work_order_ids_assigned_to_worker` → `list_work_orders` / count / 扫码 `by_worker` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 过滤 | `riveredge-backend/src/apps/kuaizhizao/services/work_order_service.py` |
| 班组成员 | `WorkGroupMember.employee_id` = `User.id`，与 `assigned_team_id` = `WorkGroup.id` |

## 踩坑

- JSON 字段要用 `assigned_worker_ids__contains=[worker_id]`，标量 contains 在 JSONB 上对不上数组。
- 列表接口重启后端后才生效。
