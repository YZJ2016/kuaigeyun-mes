---
title: 入站同步：嵌套明细（entry / FEntity）统一摊平
slug: sync-from-source-nested-detail-expand
status: delivered
domain: sync-from-source
when: 苍穹 BOM 等「表头 + 明细数组」入站、预览列只有 entry
keywords:
  - expandNestedDetailRows
  - normalizeApiBodyToRows
  - normalize_api_body_to_rows
  - NESTED_DETAIL_KEYS
  - FEntity
  - entrymaterial_number
standard: SyncFromSourceModal + normalize_api_body_to_rows
---

# 入站同步：嵌套明细（entry / FEntity）统一摊平

- 日期：2026-10-03
- 状态：已交付

## 目标

苍穹 BOM 等响应为「表头 + `entry[]`」时，预览与写入都摊成扁平行，字段映射直接选 `entrymaterial_number`、`entryqty` 等，全站入站同步共用一套。

## 何时读 / 禁止另起

- 何时读：新明细数组名、预览列只剩无用的 `entry`
- 禁止：各业务再写第二套拆行；把 `items` / `data` / `rows` 当明细键（响应外壳）

## 标准入口

| 层 | 标准 |
|----|------|
| FE 预览/映射列 | `syncSourceUtils.normalizeApiBodyToRows` → 内调 `expandNestedDetailRows` |
| BE 接口响应 | `core/services/data/sync_source_rows.normalize_api_body_to_rows` |
| BE 全同步门禁 | `fetch_sync_rows` 再跑一遍 `expand_nested_detail_rows` |
| 实现模块 | `core/services/data/sync_nested_expand.py` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 摊平算法 | `riveredge-backend/src/core/services/data/sync_nested_expand.py` |
| API 规范化 | `riveredge-backend/src/core/services/data/sync_source_rows.py` |
| 拉取门禁 | `riveredge-backend/src/apps/master_data/services/master_data_sync_common.py`（`fetch_sync_rows`） |
| FE | `riveredge-frontend/src/components/sync-from-source-modal/syncSourceUtils.ts` |
| 测试 | `riveredge-backend/tests/core/services/data/test_sync_nested_expand.py` |

## 扩展点

1. 新明细数组名：只往 `NESTED_DETAIL_KEYS` 加，前后端键名保持一致
2. 销售订单仍可把整段数组映射到目标 `items`（外壳键不是明细键）
3. 引用对象自动补别名：`entrymaterial:{number}` → `entrymaterial_number`

## 映射示例（苍穹 BOM）

| 源列（摊平后） | 目标 |
|----------------|------|
| `material_number`（或表头物料编码） | `parent_code` |
| `entrymaterial_number` | `component_code` |
| `entryqty` | `quantity` |

## 踩坑

- 摊平前若把 `entry[]` 当普通单元格，预览列只剩无用的 `entry`；必须先 expand
- 空 `entry: []` 会去掉该键并保留表头行；有明细时表头不单独成行
- BOM 匹配键 `line_key` 由父件+子件派生，见 `features/sync-bom-line-key-derived.md`

## 关联

- `principles/reuse-existing-patterns.md`
- `features/sync-from-source-multi-source-merge.md`
- `features/sync-bom-line-key-derived.md`
