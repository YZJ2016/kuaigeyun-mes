---
title: BOM 匹配键 line_key：父件+子件派生
slug: sync-bom-line-key-derived
status: delivered
domain: sync-from-source
when: 工程 BOM 同步报「须包含匹配键 line_key」或要把 line_key 加进必填映射
keywords:
  - line_key
  - mapping_covers_match_key
  - _ensure_bom_line_keys
  - BOM_SYNC_REQUIRED_TARGETS
  - parent_code
  - component_code
standard: createEngineeringBomSyncConfig（matchKeyField=line_key）
---

# BOM 匹配键 line_key：父件+子件派生，不必直接映射

- 日期：2026-10-03
- 状态：已交付

## 目标

绑定默认 `match_key_field=line_key`（`parent|version|component`），用户只需映射 `parent_code` + `component_code`（+ `quantity`），保存/同步不应再报「须包含匹配键 line_key」。

## 何时读 / 禁止另起

- 何时读：BOM 匹配键、自定义 match_key 覆盖规则
- 禁止：把 `line_key` 加进 `requiredTargets` 或目标字段列表逼用户选源列

## 标准入口

| 层 | 行为 |
|----|------|
| BE 校验 | `mapping_covers_match_key`：`line_key` 可由父件目标∪子件目标覆盖 |
| BE 写入前 | `_ensure_bom_line_keys` 按父件/版本/子件补齐 `line_key` |
| FE 必填 | `BOM_SYNC_REQUIRED_TARGETS` = parent_code / component_code / quantity（不含 line_key） |

## 关键文件

| 角色 | 路径 |
|------|------|
| 覆盖校验 | `riveredge-backend/src/core/services/data/sync_binding_sources.py` |
| 写入补齐 | `riveredge-backend/src/apps/master_data/services/engineering_bom_sync_service.py` |
| FE 配置 | `riveredge-frontend/src/apps/master-data/bomSyncConfig.ts`（`matchKeyField: 'line_key'`） |
| 测试 | `riveredge-backend/tests/core/services/data/test_sync_match_key_coverage.py` |

## 扩展点

- 其它派生匹配键：在 `mapping_covers_match_key` 显式声明覆盖规则，不要改成「用户必须映射合成键」

## 踩坑

- 父件别名：`parent_code` / `material_code` / `parent_main_code`；子件：`component_code` / `child_code` / `component_main_code`
- 嵌套 JSON 须先摊平再映射，见 `features/sync-from-source-nested-detail-expand.md`

## 关联

- `features/sync-from-source-nested-detail-expand.md`
- `features/sync-from-source-multi-source-merge.md`
- `principles/reuse-existing-patterns.md`
