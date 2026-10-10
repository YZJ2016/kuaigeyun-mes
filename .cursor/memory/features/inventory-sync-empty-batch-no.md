---
title: 即时库存同步空批号落空串
slug: inventory-sync-empty-batch-no
status: delivered
domain: sync-from-source
when: 即时库存同步报 batch_no 非空、源数据无批号、库存同步写入 MaterialBatch
keywords:
  - InventorySyncService
  - normalize_inventory_sync_batch_no
  - batch_no
  - 即时库存同步
standard: 无批号写空串，按物料+批号+仓库更新已有批次，禁止传 null。
---

# 即时库存同步空批号落空串

## 目标

源即时库存没有批号时仍能写入 `MaterialBatch`，与库存增减空串口径一致。

## 何时读 / 禁止另起

- 何时读：即时库存「从数据接口同步」失败、`batch_no is non nullable`。
- 禁止：把 `batch_no` 改成可空列；为无批号另建一张库存表。

## 标准入口

| 层 | 标准 |
|----|------|
| BE | `InventorySyncService._upsert_batches` |
| 归一 | `normalize_inventory_sync_batch_no` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 服务 | `riveredge-backend/src/apps/kuaizhizao/services/inventory_sync_service.py` |
| 模型 | `riveredge-backend/src/apps/master_data/models/material_batch.py` |

## 扩展点

1. 匹配键：`(material_id, batch_no, warehouse_id)`，默认自购 + 合格。
2. 已有行则更新数量，避免 unique 冲突。

## 踩坑

- `cell_str(...) or None` 会把空批号写成 null，Tortoise `bulk_create` 直接失败。
- 只在本批映射行里找 existing、不查库，第二次同步会撞唯一约束。

## 关联

- `features/sync-from-source-multi-source-merge.md`
