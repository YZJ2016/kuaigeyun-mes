---
title: 入站多源：只补缺字段 + 按匹配键合并写入
slug: sync-from-source-multi-source-merge
status: delivered
domain: sync-from-source
when: 多来源入站同步、补充源映射、match_key 合并
keywords:
  - SyncFromSourceModal
  - multiSourceMapping
  - merge_mapped_rows_by_match_key
  - matchKeyField
  - siblingCoveredTargets
standard: SyncFromSourceModal（全站入站同步唯一入口）
---

# 入站多源：只补缺字段 + 按匹配键合并写入

- 日期：2026-10-02
- 状态：已交付

## 目标

多来源入站时，首个来源映射完整必填；后续来源只需映射匹配键，并补齐尚未覆盖的字段；服务端按匹配键合并（后源只填空字段）再写入。

## 何时读 / 禁止另起

- 何时读：第二数据源、并集校验、补充源必填收缩
- 禁止：再写第二套「多源补字段」面板或按源分别 upsert 导致缺 name 被 skip

## 标准入口

| 层 | 标准 |
|----|------|
| FE 组件 | `SyncFromSourceModal` + `SyncSourceSettingModal` |
| FE 辅助 | `multiSourceMapping.ts`（并集校验 / 补充源必填） |
| BE 拉取合并 | `fetch_mapped_rows_from_sources(..., match_key=)` → `merge_mapped_rows_by_match_key` |
| 物料特例 | 按源预转换 `source_type` 后合并，再单次 `_upsert_materials` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 多源映射 | `riveredge-frontend/src/components/sync-from-source-modal/multiSourceMapping.ts` |
| 来源设置 | `riveredge-frontend/src/components/sync-from-source-modal/SyncSourceSettingModal.tsx` |
| 确认同步 | `riveredge-frontend/src/components/sync-from-source-modal/index.tsx` |
| 类型 | `riveredge-frontend/src/components/sync-from-source-modal/types.ts` |
| 合并 | `riveredge-backend/src/core/services/data/sync_binding_sources.py` |
| 物料 | `riveredge-backend/src/apps/master_data/services/material_sync_service.py` |

i18n：`components.syncFromSource.supplemental*` / `unionMappingRequired`。各 `*_sync_service.py` 传入 `match_key=match_key`。

## 扩展点

1. 新同步页：在 `SyncFromSourceConfig` 设 `matchKeyField`（默认 `requiredTargets[0]`）
2. 自定义 `validateMapping`：确认同步时按并集调用（`coverage: 'union'`）；单源保存仍走完整校验；补充源保存不跑自定义全量校验

## 过程

1. 旧逻辑：每个来源都校验全部 `requiredTargets` → 第二源被迫重填 name 等
2. 仅改 FE 不够：concat 后 upsert 对缺 name 的行会 skip；必须 BE 按匹配键补齐合并

## 踩坑

- 物料曾按源分别 upsert + 各源 conversion_map；合并前须按源预转换 `source_type`，否则多接口转换表冲突
- 补充源若仍展示「未被兄弟覆盖的可选列」，用户会误以为还要再填；应只显示 matchKey + 未覆盖必填 + `supplementalDefaultTargets`（物料默认带 `source_type`）
- 拉取预览禁止对兄弟已覆盖字段做自动建议

## 关联

- `principles/reuse-existing-patterns.md`
- `features/sync-from-source-nested-detail-expand.md`
- `features/sync-bom-line-key-derived.md`
- `features/sync-push-hub-master-data.md`
