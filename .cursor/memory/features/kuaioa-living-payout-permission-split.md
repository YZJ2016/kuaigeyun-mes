---
title: 生活费发放表与预支权限拆分
slug: kuaioa-living-payout-permission-split
status: delivered
domain: kuaioa
when: 生活费预支勾选带动发放表、权限矩阵联动、living-payout 独立权限
keywords:
  - living-payout
  - living-advance
  - 生活费发放表
  - 生活费预支
  - 权限联动
standard: 发放表菜单与 API 用 kuaioa:living-payout:*，禁止再挂 living-advance:read
---

# 生活费发放表与预支权限拆分

## 目标

角色功能权限里「生活费预支」与「生活费发放表」可独立勾选。

## 何时读 / 禁止另起

- 何时读：发放表菜单权限、矩阵两行联动勾选
- 禁止：发放表菜单再挂 `kuaioa:living-advance:read`（同资源会共用查看/新建等动作）

## 标准入口

| 层 | 标准 |
|----|------|
| 菜单 | `kuaioa:living-payout:read`（kuaioa / haoligo manifest） |
| 权限码 | `kuaioa:living-payout:read` / `export` |
| FE | `living-payout/index.tsx` → `useResourcePermissions('kuaioa:living-payout')` |
| BE | `GET /living-payout` → `require_permission_codes("kuaioa:living-payout:read")` |

## 踩坑

- 两菜单曾共用 `living-advance` 资源，矩阵把预支的新建等动作挂到发放表行上，勾选即联动
- 拆分后须 sync-manifest；需要发放表的角色须另勾 `living-payout` 查看（及导出）
