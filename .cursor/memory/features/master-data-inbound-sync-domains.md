---
title: 主数据入站同步三域（多单位/批号管理/库位关系）
slug: master-data-inbound-sync-domains
status: delivered
domain: master-data
when: 物料多单位/批号管理/库位关系入站同步、SyncFromSourceModal 域扩展、绑定模型新增
keywords:
  - material_multi_unit
  - material_batch_manage
  - warehouse_location_ref
  - MaterialMultiUnitSyncBinding
  - sync-binding
  - sync-from-source
  - 其他同步
standard: 服务直接落 `apps.master_data.services.*_sync_service`，不走 kuaiconnect 薄代理
---

# 主数据入站同步三域（多单位/批号管理/库位关系）

## 目标

物料管理页「其他同步」下拉提供辅单位换算、批号管理开关的入站同步；仓库列表提供库位关系同步（写入库位所属仓库）。

## 何时读 / 禁止另起

- 何时读：新增主数据入站同步域、排查 multi-unit/batch-manage/location-ref 端点、加第 4 个域时。
- 禁止：不要复制 kuaiconnect 薄代理结构；不要在 api 层用 `inbound_sync_gate`（本地按直连 service 懒加载模式）。

## 标准入口

| 层 | 标准 |
|----|------|
| FE | `management.tsx` `MaterialOtherSyncDropdown`；`warehouses/index.tsx` `UniSyncButton` → `WarehouseLocationRefSyncFromSourceModal` |
| BE | `api/material.py` `/multi-unit|batch-manage/sync-*`；`api/warehouse.py` `/warehouses/location-ref/sync-*` |
| 权限 | `require_master_data_module_access("material"/"warehouse")` |

## 关键文件

| 角色 | 路径 |
|------|------|
| BE 服务 | `riveredge-backend/src/apps/master_data/services/{material_multi_unit,material_batch_manage,warehouse_location_ref}_sync_service.py` |
| BE 绑定模型 | `apps/master_data/models/master_data_sync_binding.py`（含 StorageLocationSyncBinding） |
| BE 运行历史 | `core/services/data/sync_run_history_service.py::list_inbound_entity_sync_run_history_rows` |
| FE Modal | `apps/master-data/components/{MaterialMultiUnit,MaterialBatchManage,WarehouseLocationRef}SyncFromSourceModal.tsx` |
| FE 配置 | `apps/master-data/{materialMultiUnit,materialBatchManage,warehouseLocationRef}SyncConfig.ts` + `pages/**/{materialMultiUnit,materialBatchManage,warehouseLocationRef}SyncFields.ts` |
| FE 服务 | `apps/master-data/services/{material,warehouse}.ts`（`syncWarehousesFromSource` 为 NDJSON `apiRequestSyncNdjson` 版） |

## 扩展点

1. 新域：绑定模型类（表已按迁移模式建）+ service（继承 `master_data_sync_common` 工具函数）+ api 端点三元组（sync-binding GET/PUT、sync-from-source POST、sync-run-history GET）+ FE Modal/Config/Fields 三件套 + i18n `*Sync*` 键。
2. `entity_type` 串（`material_multi_unit` / `material_batch_manage` / `warehouse_location_ref`）必须与 binding model、`historySourceType`、run-history 查询一致。
3. import 适配：`master_data_sync_common` 用 `apps.master_data.services.master_data_sync_common`；`sync_binding_sources` 用 `core.services.data.sync_binding_sources`（本地等价层）。
