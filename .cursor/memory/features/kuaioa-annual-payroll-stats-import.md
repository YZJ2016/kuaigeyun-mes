---
title: 年度工资统计车间联动与月度工资导入
slug: kuaioa-annual-payroll-stats-import
status: delivered
domain: kuaioa-hr
when: 改年度工资统计筛选、人员联动、或从宽表导入 1～12 月应发工资
keywords:
  - annual-stats
  - 年度工资统计
  - import_annual_wage
  - annual-payroll-stats
standard: 人员下拉随车间过滤；导入写月度结算 basic_wage 并确认，禁止旁路年度工资表
---

# 年度工资统计车间联动与月度工资导入

## 目标

年度工资统计页：选车间后人员下拉只显示该车间员工；支持宽表导入各月应发工资并纳入年度汇总。

## 何时读 / 禁止另起

- 何时读：年度统计筛选、导入、结算与统计口径不一致
- 禁止：另建年度工资表读侧补数；导入只改展示不写结算；人员仍用手输姓名不联动车间

## 标准入口

| 层 | 标准 |
|----|------|
| FE | `apps/kuaioa/pages/hr/annual-payroll-stats/index.tsx`：`loadOaEmployeeOptions` 按 `workshop_name` 过滤；`UniImport` + `POST /payroll/annual-stats/import` |
| BE | `PayrollSettlementService.import_annual_wage_details` 写 `basic_wage` → `auto_confirm`；`AnnualPayrollStatsService.list_annual_stats` 支持 `employee_id` |
| 权限 | 查询 `kuaioa:payroll:read`；导入 `kuaioa:payroll:update` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 页 | `riveredge-frontend/src/apps/kuaioa/pages/hr/annual-payroll-stats/index.tsx` |
| API | `riveredge-backend/src/apps/kuaioa/api/payroll.py` |
| 导入服务 | `riveredge-backend/src/apps/kuaioa/services/payroll_service.py` |
| 汇总 | `riveredge-backend/src/apps/kuaioa/services/welfare_service.py` |
| Schema | `riveredge-backend/src/apps/kuaioa/schemas/payroll_import.py` |

## 扩展点

1. 导入列目前为 `wage_m01`～`wage_m12`；生活费/社保若要导入须写结算行对应扣除字段并仍走确认结算。
2. 行缺车间时回落：行车间 → 页筛选车间 → 档案车间。

## 踩坑

- 年度统计只汇总 `status=confirmed` 结算；导入默认 `auto_confirm=true`。
- 已确认结算导入前会 reopen 再写再确认，勿平行第三套状态机。
