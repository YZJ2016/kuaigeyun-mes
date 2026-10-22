---
title: 月度考勤按产线拉人
slug: kuaioa-attendance-line-roster
status: delivered
domain: kuaioa
when: 考勤单选了产线后人员空白、分产线后刷新名单仍无员工
keywords:
  - production_line_name
  - _list_workshop_employees
  - 月度考勤
  - 刷新名单
  - 分产线
standard: 填了产线则按产线身份键匹配员工；未填产线才按车间
---

# 月度考勤按产线拉人

## 目标

考勤单勾选产线时，填报表能带出该产线员工，不因车间字符串不一致或「编码 名称」展示串而空白。

## 何时读 / 禁止另起

- 何时读：报「分产线后考勤没人」「产线考勤点进去空白」
- 禁止：在填报表前端硬凑人员；读侧 invent 员工行

## 标准入口

| 层 | 标准 |
|----|------|
| BE | `AttendanceService._list_workshop_employees` + `_production_line_identity_values` |
| FE | 新建考勤换车间时清掉不属于该车间的产线；真源 pro `kuaioa` 与主仓组装同步 |

## 关键文件

| 角色 | 路径 |
|------|------|
| 拉人 | `riveredge-backend/.../kuaioa/services/attendance_service.py`（pro 同路径） |
| 列表 | `.../kuaioa/pages/hr/attendance/index.tsx` |

## 扩展点

1. 有产线：身份键交集匹配（名称 / `编码 名称` / 编码）；同车间优先，否则仍返回产线命中
2. 无产线：仅 `workshop_name` 过滤
3. 已建空白草稿：点「刷新名单」走 `refresh_roster` → `_generate_days_for_sheet(only_missing=True)`

## 踩坑

- 员工档案须已填 `production_line_name`；只建产线考勤单、档案无产线 → 仍为空
- 组装态改 kuaioa 须回写 `kuaigeyun-pro`

## 关联

- `features/leave-attendance-employee-match.md`
- `features/permission-display-echo.md`（车间产线下拉回显）
