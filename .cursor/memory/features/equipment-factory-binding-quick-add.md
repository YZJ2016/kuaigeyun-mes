---
title: 设备台账工厂绑定：车间 / 产线 / 工位 / 工作中心快速新增
slug: equipment-factory-binding-quick-add
status: delivered
domain: master-data-ui
when: 下拉内快速新增车间/产线/工位/工作中心、设备或计量器具绑定工厂对象
keywords:
  - EquipmentFactoryBindingFields
  - UniDropdown
  - quickCreate
  - WorkshopFormModal
  - ProductionLineFormModal
  - WorkstationFormModal
  - WorkCenterFormModal
standard: 工序 OperationFormModal 的 UniDropdown + 主数据既有 FormModal
---

# 设备台账工厂绑定：车间 / 产线 / 工位 / 工作中心快速新增

- 日期：2026-10-03
- 状态：已交付

## 目标

设备新建/编辑时，关联车间、产线（线组）、工位、工作中心可在下拉内快速新增，不另做一套表单。

## 何时读 / 禁止另起

- 何时读：任何下拉「快速新增」工厂对象
- 禁止：平行 API 或平行弹窗；改设备台账/计量器具的性质与类型分流逻辑

## 标准入口

- FE：`EquipmentFactoryBindingFields`（设备台账 / 计量器具等凡挂此组件的表单）
- 快速新增弹窗：主数据既有 FormModal
- 下拉：`UniDropdown.quickCreate`

## 关键文件

| 角色 | 路径 |
|------|------|
| 设备级联字段 | `riveredge-frontend/src/apps/kuaizhizao/components/EquipmentFactoryBindingFields.tsx` |
| 产线弹窗 | `riveredge-frontend/src/apps/master-data/components/ProductionLineFormModal.tsx` |
| 工位弹窗 | `riveredge-frontend/src/apps/master-data/components/WorkstationFormModal.tsx` |
| 文案（产线） | `field.workstation.quickAddProductionLine` |
| 文案（车间/工位/工作中心） | `field.operation.quickAddWorkshop` / `quickAddWorkstation` / `quickAddWorkCenter` |

## 扩展点

1. 下拉改为 `UniDropdown` + `quickCreate.onClick` 打开既有 `*FormModal`
2. `onSuccess` 刷新选项并 `setFieldsValue` 写回 id/code/name，并清空下游级联
3. 产线依赖车间：无车间时下拉禁用；弹窗用 `defaultWorkshopId` 预填 `workshopId`
4. 工位依赖产线：无产线时下拉禁用；弹窗用 `defaultProductionLineId` 预填 `productionLineId`

## 过程

1. 车间、工作中心先按工序下拉接 FormModal
2. 产线对齐工位页 `WorkstationFormModal` → `ProductionLineFormModal`
3. 工位对齐同一组件 + `defaultProductionLineId`

## 踩坑

- 先选车间和产线，再打开工位下拉点「快速新增工位」
- 保存后设备表单应选中新工位；若该工位已绑工作中心则自动带出

## 关联

- `principles/reuse-existing-patterns.md`
