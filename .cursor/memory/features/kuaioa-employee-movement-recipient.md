---
title: 入离职登记人员接收人通知
slug: kuaioa-employee-movement-recipient
status: delivered
domain: kuaioa
when: 入离职明细登记要选接收人、车间主任/人事通知、movement recipient
keywords:
  - recipient_user_id
  - hire_recipient
  - leave_recipient
  - employee-movements
  - 人员接收人
  - 入离职明细
standard: 登记表单 ProFormSelect+searchUserDisplay → create/update 传 recipient_user_id → 落库姓名 + MessageService 站内信
---

# 入离职登记人员接收人通知

## 目标

入职、临时工、离职登记时选择「人员接收人」，提交后向其发站内通知并在入离职明细展示。

## 何时读 / 禁止另起

- 何时读：改入离职登记通知、接收人字段、movements 列表接收人列
- 禁止：另写审批流冒充通知；用员工档案下拉代替系统用户选人；只在前端 toast 不发站内信

## 标准入口

| 层 | 标准 |
|----|------|
| FE | `apps/kuaioa/pages/hr/employee-movements`：`recipient_user_id` + `searchUserDisplay` |
| BE | `EmployeeProfileService.create_profile` / `update_profile`：解析用户、写 `hire_recipient_*` / `leave_recipient_*`、`MessageService.send_message` |
| 迁移 | `907_..._kuaioa_employee_movement_recipient` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 列表页 | `riveredge-frontend/src/apps/kuaioa/pages/hr/employee-movements/index.tsx` |
| 服务 | `riveredge-backend/src/apps/kuaioa/services/employee_service.py` |
| 模型 | `riveredge-backend/src/apps/kuaioa/models/employee.py` |

## 扩展点

1. 入职/临时工：写 `hire_recipient_user_id/name`，通知文案区分用工类型
2. 离职：写 `leave_recipient_user_id/name`，仅当本次更新落为 left 且带了 recipient
3. 档案页普通新建可不传 recipient（可选）；入离职页前端必填
4. 列表 `list_movements` 按类型回显对应接收人姓名

## 踩坑

- `recipient_user_id` 不是 ORM 字段，update 时必须 `payload.pop`，否则 setattr 报错
- 选人须用系统用户 ID（`searchUserDisplay` → `value: u.id`），不要用 UniUserSelect 的 uuid 直传 MessageService
- 通知失败只打日志，不回滚登记（与设备报修等站内信一致）
