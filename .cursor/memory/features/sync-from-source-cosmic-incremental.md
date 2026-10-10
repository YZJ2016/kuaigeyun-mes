---
title: 入站同步：苍穹增量水位 + 无变更跳过
slug: sync-from-source-cosmic-incremental
status: delivered
domain: sync-from-source
when: 定时增量、苍穹 batchQuery、无变更却显示更新、只拉第 1 页
keywords:
  - incremental
  - last_success_at
  - kingdee_cosmic_since_filter
  - apply_kingdee_since_filter
  - record_fields_unchanged
  - start_modifytime
standard: SyncFromSourceModal + fetch_rows_from_api + resolve_incremental_since
---

# 入站同步：苍穹增量水位 + 无变更跳过

- 日期：2026-10-03
- 状态：已交付

## 目标

定时增量在苍穹 `batchQuery` / `sys/query` 上真正按水位少拉；本地已存在且字段未变的行计为「跳过」，不再一律「更新」。

## 何时读 / 禁止另起

- 何时读：新 Cosmic 接口增量、物料/BOM upsert 跳过无变更
- 禁止：另写字段比较；对空 `data: {}` 乱塞 `start_modifytime`（易 400）

## 标准入口

| 层 | 标准 |
|----|------|
| FE | 同步方式选「定时增量」→ 请求带 `incremental: true`，用水位 `last_success_at` |
| BE 拉取 | `sync_from_source_fetch.fetch_rows_from_api` |
| 星空增量 | `kingdee_since_filter.apply_kingdee_since_filter`（FilterString） |
| 苍穹增量 | `kingdee_cosmic_since_filter`（filter / start_modifytime + 行级兜底） |
| 写入跳过 | `record_fields_unchanged`（物料 / 工程 BOM upsert） |

## 关键文件

| 角色 | 路径 |
|------|------|
| 苍穹 since | `riveredge-backend/src/core/services/integration/kingdee_cosmic_since_filter.py` |
| 拉取 | `riveredge-backend/src/core/services/data/sync_from_source_fetch.py` |
| 无变更 | `riveredge-backend/src/apps/master_data/services/master_data_sync_common.py` |
| 物料/BOM | `material_sync_service.py` / `engineering_bom_sync_service.py` |
| 测试 | `riveredge-backend/tests/core/services/integration/test_kingdee_cosmic_since_filter.py` |
| 测试 | `riveredge-backend/tests/apps/master_data/test_sync_values_equal.py` |

## 扩展点

1. 新 Cosmic 接口若 data 已有 `start_*time`，会自动补 `start_modifytime`
2. 已有 `filter`（body / data / sys query params）会追加 `modifytime GE '...'`
3. basedata 空 `data: {}` 不乱塞未知字段；靠翻页 + 行级 modifytime + 无变更跳过
4. 其它主数据 upsert 要跳过无变更：复用 `record_fields_unchanged`

## 过程

1. 仅 `manual_full` 时 `since` 为空，每次全量——需改成「定时增量」
2. 苍穹 batchQuery 与星空 FilterString 信封不同，旧 `apply_kingdee_since_filter` 对 Cosmic 是空操作
3. 苍穹原先只拉第 1 页；增量场景一并翻页

## 踩坑

- 空 data 注入 `start_modifytime` 可能触发「属性不存在」；只在已有 start_* 时写入
- 源行无修改时间时行级过滤不丢弃（避免误杀）；靠本地无变更跳过消化重复行

## 关联

- `principles/reuse-existing-patterns.md`
- `features/sync-from-source-multi-source-merge.md`
