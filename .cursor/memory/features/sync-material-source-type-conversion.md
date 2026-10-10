---
title: 物料来源类型转换依赖 FieldKeys
slug: sync-material-source-type-conversion
status: delivered
domain: sync-from-source
when: 来源类型编码转换没生效、FErpClsID、source_type 仍是 Buy
keywords:
  - source_type_conversion_map
  - FErpClsID
  - 来源类型转换
  - source_type
standard: API.source_type_conversion_map + 物料同步 field_mapping 映到 source_type + FieldKeys 含来源字段
---

# 物料来源类型转换依赖 FieldKeys

## 目标

金蝶物料属性（FErpClsID）经接口「来源类型编码转换」落到本地 `source_type`（Buy/Make/…）。

## 何时读 / 禁止另起

- 何时读：接口页已配转换表但同步后物料仍默认外购/类型不对
- 禁止：另在同步弹窗再做一套转换 UI；勿只改文案不查 FieldKeys

## 标准入口

| 层 | 标准 |
|----|------|
| 配置 UI | `ApiFormModal` → `source_type_conversion_map_entries` → 存 `core_apis.source_type_conversion_map` |
| 同步 | `MaterialSyncService.sync_from_source` 读绑定 API 的 conversion_map，`_coerce_material_extra_value` 转换 |
| 预置 | `MATERIAL_QUERY_FIELD_KEYS` 须含 `FErpClsID`；`material_preset_needs_upgrade` 缺列则升级 |

## 生效三条件（缺一则「没生效」）

1. 接口 `source_type_conversion_map` 有条目（`field_name` 如 `FErpClsID`，mapping `1→Buy`…）
2. 物料同步字段映射：`FErpClsID → source_type`
3. **请求体 FieldKeys 含 `FErpClsID`**（最常见漏项：转换与映射都配了，但 ExecuteBillQuery 根本没拉该列）

## 关键文件

| 角色 | 路径 |
|------|------|
| 表单 | `riveredge-frontend/src/pages/system/apis/ApiFormModal.tsx` |
| 转换提交 | `riveredge-frontend/src/pages/system/apis/apiFormUtils.ts` |
| 同步 | `riveredge-backend/src/apps/master_data/services/material_sync_service.py` |
| 预置 | `riveredge-backend/src/core/services/integration/kingdee_galaxy_api_presets.py` |
| 向导字段 | `riveredge-backend/src/core/services/integration/kingdee_execute_bill_query_catalog.py` |

## 踩坑

- 转换配置存库成功 ≠ 查询带了字段；缺 `FErpClsID` 时新建物料默认 Buy，更新则不改 `source_type`
- `field_name` 填 `FErpClsID` 时，绑定映射的来源字段名须一致，才会命中 `source_field_names` 分支
- 「加载常用接口」升级依赖 `material_preset_needs_upgrade`；须识别缺 `FErpClsID`
