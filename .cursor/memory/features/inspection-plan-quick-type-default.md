---
title: 快速新建质检方案默认并锁定方案类型
slug: inspection-plan-quick-type-default
status: delivered
domain: master-data-ui
when: 快速新增质检方案、方案类型空白、planTypeLockedHint、IQC/FQC/OQC quickCreate
keywords:
  - InspectionPlanFormModal
  - defaultPlanType
  - lockPlanType
  - plan_type
  - InspectionStagesEditor
  - 快速创建检验方案
standard: InspectionPlanFormModal 传 defaultPlanType + lockPlanType，初始值走 FormModalTemplate.initialValues
---

# 快速新建质检方案默认并锁定方案类型

## 目标

物料/工序/来料检验页「快速新建质检方案」打开时，方案类型须按场景预填并锁定显示。

## 何时读 / 禁止另起

- 何时读：弹窗显示锁定提示但下拉仍是「请选择方案类型」；IQC/FQC/OQC/IPQC 快速新建。
- 禁止：另写一套质检方案弹窗；仅靠 `setFieldsValue` 而不传 `initialValues`。

## 标准入口

| 层 | 标准 |
|----|------|
| FE 弹窗 | `InspectionPlanFormModal`：`defaultPlanType` + `lockPlanType` + `initialValues` + `afterOpenChange` 再灌一次 |
| FE 物料分场景 | `InspectionStagesEditor`：`STAGE_PLAN_TYPE` → iqc/incoming、fqc/finished、oqc/outbound、ipqc/process |
| FE 来料页 | `incoming-inspection`：`defaultPlanType="incoming"` `lockPlanType` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 弹窗 | `riveredge-frontend/src/apps/kuaizhizao/components/InspectionPlanFormModal.tsx` |
| 分场景编辑 | `riveredge-frontend/src/apps/master-data/components/InspectionStagesEditor.tsx` |
| Form 壳 | `riveredge-frontend/src/components/layout-templates/FormModalTemplate.tsx`（`destroyOnHidden`） |

## 踩坑

- `FormModalTemplate` 使用 `destroyOnHidden`：关闭后表单销毁，打开时若只 `setFieldsValue` 且早于 ProForm 就绪，`plan_type` 会丢。
- 锁定文案勿写死「来料」；用 `planTypeLockedHintTyped` + `QUALITY_PLAN_TYPE_I18N`。

## 关联

- `features/equipment-factory-binding-quick-add.md`（UniDropdown.quickCreate 模式）
- `principles/reuse-existing-patterns.md`
