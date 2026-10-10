---
title: 物料 / BOM / 工序：SyncPushHub + 外推
slug: sync-push-hub-master-data
status: delivered
domain: sync-push
when: 给主数据或单据加「同步/推送」Hub、外推 profile、列表勾选推送
keywords:
  - SyncPushHub
  - SyncPushHubButton
  - DocumentPushBatchPanel
  - document-push
  - preferIds
  - DOCUMENT_PUSH_KNOWN_PROFILES
  - SUPPORTED_PROFILES
  - master-data:material:push
standard: 销售订单 SyncPushHub + DocumentPushBatchPanel
---

# 物料 / BOM / 工序：SyncPushHub + 外推

- 日期：2026-09-30 ~ 2026-10-01
- 状态：已交付

## 目标

主数据三页（物料管理、工程 BOM、工序）具备与销售订单一致的「同步 / 推送」Hub：入站 sync-from-source + 出站 document-push；权限用 `:sync` / `:push`。

## 何时读 / 禁止另起

- 何时读：新 source_type 外推、列表勾选推送、Hub 按钮门禁
- 禁止：另造推送面板；只登后端或只登前端 profile 白名单

## 标准入口

| 层 | 标准 |
|----|------|
| Hub | `SyncPushHubButton` + `useToolbarSyncPushFlags('<resource>')` |
| 同步 Tab | `*SyncFromSourceModal`（contentOnly）+ `SyncFreshnessBadge` |
| 推送 Tab | `DocumentPushBatchPanel` 薄封装（如 `SalesOrderDocumentPushPanel`） |
| 推送 API | `POST /apps/kuaizhizao/document-push` |
| Profile 目录 | BE `SUPPORTED_PROFILES` + FE `DOCUMENT_PUSH_KNOWN_PROFILES`（两处都要登记） |
| 列表勾选 | 传 `preferIds` / uuid 补拉（销售：`orderIds={resolveOrderIdsFromRowKeys(selectedRowKeys)}`） |

## 关键文件

| 角色 | 路径 |
|------|------|
| 物料页 Hub | `riveredge-frontend/src/apps/master-data/pages/materials/management.tsx` |
| BOM 页 Hub | `riveredge-frontend/src/apps/master-data/pages/materials/bom/index.tsx` |
| 工序页 Hub | `riveredge-frontend/src/apps/master-data/pages/process/operations/index.tsx` |
| 物料推送面板 | `riveredge-frontend/src/apps/master-data/components/MaterialDocumentPushPanel.tsx` |
| Profile 白名单 | `riveredge-frontend/src/apps/kuaizhizao/services/document-push.ts` |
| 批次面板 | `riveredge-frontend/src/apps/kuaizhizao/components/DocumentPushBatchPanel.tsx` |
| 权限 hook | `riveredge-frontend/src/hooks/useToolbarSyncPushFlags.ts` |
| FE manifest | `riveredge-frontend/src/apps/master-data/manifest.json` |
| BE manifest | `riveredge-backend/src/apps/master_data/manifest.json` |
| Push 服务 | `riveredge-backend/src/apps/kuaizhizao/services/document_push_service.py` |
| 就绪映射 | `riveredge-backend/src/core/services/integration/document_push_readiness.py` |
| 物料/BOM/工序 Push | `kingdee_material_push_service.py` / `kingdee_engineering_bom_push_service.py` / `kingdee_process_operation_push_service.py`（同 apps 下） |
| 预设 | `riveredge-backend/src/core/services/integration/kingdee_galaxy_api_presets.py` |
| BOM sync | `engineering_bom_sync_service.py` + material.py `/bom/sync-binding` |
| 工序 sync | `operation_sync_service.py` + process.py `/operations/sync-binding` |
| Binding 模型 | `master_data_sync_binding.py`（EngineeringBomSyncBinding / OperationSyncBinding） |
| 迁移 | `riveredge-backend/migrations/models/819_20260930180000_bom_operation_sync_binding.py` |
| 权限同步脚本 | `riveredge-backend/scripts/sync_master_data_manifest.py` |

## 权限码

- `master-data:material:sync` / `:push`
- `master-data:process:engineering-bom:sync` / `:push`
- `master-data:process:operation:sync` / `:push`

## 扩展点

1. BE：`Kingdee*PushService` + `SUPPORTED_PROFILES` + `ensure_default_push_handlers_registered` + presets + readiness
2. FE：`DOCUMENT_PUSH_KNOWN_PROFILES` + `DOCUMENT_PUSH_PROFILE_LABEL_KEYS` + zh-CN profile 文案
3. 薄封装 `*DocumentPushPanel`（抄销售订单，勿改 `DocumentPushBatchPanel` 骨架）
4. 页面：Hub + 列表勾选 ids/uuids
5. manifest `:push`（及如需 `:sync`）→ `sync_master_data_manifest.py`
6. 写本记忆库一篇 features 笔记并更新 `README.md`

## 过程

1. manifest 权限 + 本环境 sync（租户 1 已写入 6 码）
2. 物料：现有 sync + 新 push + Hub 换门禁
3. BOM/工序：binding 表 819 + sync API/Modal + push + Hub
4. 对齐销售：列表勾选传入 preferIds（工序另传 uuid 补拉 get）

## 踩坑

- FE `DOCUMENT_PUSH_KNOWN_PROFILES` 漏登 → 误报「可用推送目标都已添加」
- `needsKingdeeConnector` 只看已保存 targetProfiles → 首次添加目标时 API 下拉不加载；已改为含 settingProfile/pendingNewProfile

## source_type / profile

| source_type | target_profile | FormId |
|-------------|----------------|--------|
| material | kingdee_bd_material | BD_MATERIAL |
| engineering_bom | kingdee_eng_bom | ENG_BOM |
| process_operation | kingdee_eng_process | ENG_Process |

## 关联

- `principles/reuse-existing-patterns.md`
- `.cursor/rules/reuse-existing-patterns.mdc`
- `features/sync-from-source-multi-source-merge.md`
- 冒烟（本机）：`.tmp/smoke_sync_push_hub.py`
