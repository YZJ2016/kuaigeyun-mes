---
title: 工装保养/维修方案快速新建保养项与维修项
slug: tool-scheme-item-quick-create
status: delivered
domain: master-data-ui
when: 工装保养方案、维修方案添加项目暂无数据、快速新建保养项/维修项、FormListDetailTable bulkAdd quickCreate
keywords:
  - tool-maintenance-schemes
  - tool-repair-schemes
  - ToolOpsItemQuickCreateModal
  - FormListDetailTable
  - bulkAdd.quickCreate
  - UniDropdown
standard: FormListDetailTable.bulkAdd.quickCreate + UniDropdown 行内 quickCreate + ToolOpsItemQuickCreateModal
---

# 工装保养/维修方案快速新建保养项与维修项

## 目标

在工装保养方案 / 维修方案编辑弹窗内，无需先去保养项/维修项列表建档，即可快速新建并纳入当前方案行。

## 何时读 / 禁止另起

- 何时读：方案「添加项目」多选为空、要在方案里快速建保养项/维修项；设备/模具方案要对齐同一交互。
- 禁止：另写一套 Select popupRender；绕过 `UniDropdown` / `QuickCreateModal`；在方案页内联第二套保养项完整 FormModal。

## 标准入口

| 层 | 标准 |
|----|------|
| 批量选择 | `FormListDetailTable` `bulkAdd.quickCreate` → 弹窗内 `UniDropdown` 底栏 |
| 行内选择 | `Form.Item` + `UniDropdown.quickCreate` |
| 新建弹窗 | `ToolOpsItemQuickCreateModal`（编码+名称，`is_active: true`） |
| 权限 | `kuaizhizao:tool-maintenance-item:create` / `tool-repair-item:create` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 保养方案 | `riveredge-frontend/src/apps/kuaizhizao/pages/equipment-management/tool-maintenance-schemes/index.tsx` |
| 维修方案 | `riveredge-frontend/src/apps/kuaizhizao/pages/equipment-management/tool-repair-schemes/index.tsx` |
| 快速新建弹窗 | `.../equipment-management/shared/ToolOpsItemQuickCreateModal.tsx` |
| 明细表扩展 | `riveredge-frontend/src/components/form-list-detail-table/FormListDetailTable.tsx`（`quickCreate` + `pickBulkValue`） |

## 扩展点

1. 保存成功后：刷新 `itemOptions`；批量选择中则 `linesTableRef.pickBulkValue(id)`；行内则 `setFieldValue(['lines', index, 'item_id'], id)`。
2. 设备/模具方案可复用同一 `FormListDetailTable.bulkAdd.quickCreate` 契约，另写对应 Item QuickCreateModal 即可。

## 踩坑

- 快速新建弹窗 zIndex 须高于方案 FormModal 与批量选择弹窗（`MODAL_NESTED_ABOVE_PARENT_OFFSET * 2`）。
- 异步保存后写回目标用 ref，勿只靠 state 闭包。

## 关联

- `features/equipment-factory-binding-quick-add.md`
- `principles/reuse-existing-patterns.md`
