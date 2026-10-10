---
title: 角色同步创建职位遇已有代码则复用
slug: role-create-position-reuse-code
status: delivered
domain: system
when: 新建角色勾选根据角色创建职位、职位代码已存在、无法同步创建职位
keywords:
  - create_position
  - 无法同步创建职位
  - RoleService.create_role
  - station
standard: RoleService.create_role：同代码职位已存在则跳过创建，不阻断角色
---

# 角色同步创建职位遇已有代码则复用

## 目标

勾选「根据角色创建职位」时，组织内已有同 `code` 职位则复用，角色仍能创建。

## 何时读 / 禁止另起

- 何时读：报错「职位代码 xxx 已存在，无法同步创建职位」；删角色后重建触屏角色
- 禁止：再加一套职位查重或改角色代码去撞库

## 标准入口

| 层 | 标准 |
|----|------|
| BE | `RoleService.create_role` + `create_position` |
| FE | 角色表单 `create_position` 开关 |

## 关键文件

| 角色 | 路径 |
|------|------|
| 创建逻辑 | `riveredge-backend/src/core/services/authorization/role_service.py` |
| Schema | `riveredge-backend/src/core/schemas/role.py` |
| 表单 | `riveredge-frontend/src/pages/system/roles/schemas/role.ts` |

## 踩坑

- 删角色不级联删职位；再勾选同步创建会被旧职位挡住
- 职位预设 `load_preset_sme` 本来就是按 code 去重跳过，角色创建应对齐

## 关联

- `principles/reuse-existing-patterns.md`
