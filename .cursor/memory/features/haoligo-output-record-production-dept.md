---
title: 产出单制令单带出生产部门
slug: haoligo-output-record-production-dept
status: delivered
domain: dedicated-haoligo
when: 改注塑机/设备产出单扫码或「带出」制令单字段映射、生产部门列
keywords:
  - production_department
  - output-record
  - preview-by-work-order
  - 生产部门
  - 制令单带出
standard: 数据集列映射 production_department_column → prefill/create 同路径带出
---

# 产出单制令单带出生产部门

## 目标

注塑机产出单与设备产出单在扫码/「带出」制令单时，从 ERP 数据集带出生产部门并落库；PC 与 `.custom/haoli-go/mobile` 同步。

## 何时读 / 禁止另起

- 何时读：改产出单 prefill、数据集绑定列、手机端 `equip/output-record`
- 禁止：在前端硬猜部门名；另起第二套制令单查询 API

## 标准入口

| 层 | 标准 |
|----|------|
| BE | `preview_equipment_output_by_work_order` + binding `production_department_column` |
| FE PC | `equipment/documents/output-record` 数据集配置 + 只读「生产部门」 |
| Mobile | `equip/output-record/new.tsx` 扫码/带出写 `production_department` |
| 迁移 | `911_..._haoligo_equipment_output_production_department` |

## 关键文件

| 角色 | 路径 |
|------|------|
| Model | `riveredge-backend/src/apps/haoligo/models/equipment_operations.py` |
| API | `riveredge-backend/src/apps/haoligo/api/routes_equipment_documents.py` |
| PC | `riveredge-frontend/src/apps/haoligo/pages/equipment/documents/output-record/index.tsx` |
| Mobile | `.custom/haoli-go/mobile/app/equip/output-record/new.tsx` |

## 扩展点

1. 数据集绑定增加列映射字段即可，prefill 统一读 binding
2. 注塑机/设备共用同一 output-record API（`family` 参数）

## 踩坑

- 须在列表「数据集」配置「生产部门列」，否则带出为空（不是前端兜底猜）
- 列表列序：`haoligo_eq_prod_dept` rank `11.5`（制令单后、设备前）；变更后 bump `columnPersistenceId`（当前 v3）
- 列表筛选：独立 query `production_department`（icontains），搜索区文案「按照生产部门查询」

## 关联

- `features/haoligo-order-tracking-workflow.md`（同日定制交付）
