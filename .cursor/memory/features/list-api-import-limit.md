---
title: 单据导入拉取物料列表须分页且不超过 le
slug: list-api-import-limit
status: delivered
domain: master-data-ui
when: 导入报 limit Input should be less than or equal to 2000、物料列表 GET le=2000
keywords:
  - limit
  - 2000
  - fetchAllListItems
  - LIST_API_MAX_LIMIT
  - list_materials
  - handleListImport
standard: 导入匹配物料走 materialApi.list + fetchAllListItems，禁止单次 limit>2000
---

# 单据导入拉取物料列表须分页且不超过 le

## 目标

Web 导入按物料编码匹配时，不得对 `GET /apps/master-data/materials` 传大于 2000 的 `limit`。

## 何时读 / 禁止另起

- 何时读：导入校验失败文案含 `limit` / `less than or equal to 2000`；采购订单等单据 Excel 导入匹配物料。
- 禁止：`apiRequest(..., { params: { limit: 5000 } })` 绕过 `materialApi.list`；为导入再写一套全量物料接口。

## 标准入口

| 层 | 标准 |
|----|------|
| FE | `fetchAllListItems` + `materialApi.list`（`LIST_API_MAX_LIMIT=1000`，物料 `le=2000`） |
| BE | `list_materials` `Query(..., le=2000)` |
| 权限 | 沿用单据导入既有权限 |

## 关键文件

| 角色 | 路径 |
|------|------|
| 采购订单导入 | `riveredge-frontend/src/apps/kuaizhizao/pages/purchase-management/purchase-orders/index.tsx` |
| 物料 list 钳位/分片 | `riveredge-frontend/src/apps/master-data/services/material.ts` |
| 分页拉取 | `riveredge-frontend/src/utils/fetchAllListPages.ts` |
| 后端上限 | `riveredge-backend/src/apps/master_data/api/material.py` |

## 扩展点

1. 其它单据导入匹配物料：复用 `fetchAllListItems((p) => materialApi.list({ ...p, isActive: true }))` 或 `loadMaterialFormReferenceList`（后者最多 2000 条引用展示）。
2. 按 `ids` 补齐：`materialApi.list` 对超过 2000 的 id 列表自动分片。

## 过程

1. 采购订单导入曾用 `limit: 5000` 触发 Pydantic 422。
2. 改为分页拉取；list 客户端钳位并分片 ids。

## 踩坑

- `materialApi.list` 会 clamp `limit`；直接 `apiRequest` 不会。
- `loadMaterialFormReferenceList` 的 `maxItems=2000` 不是物料 GET 的 `limit` 参数，但全量导入仍可能漏匹配，超大批次优先 `fetchAllListItems`。

## 关联

- `principles/reuse-existing-patterns.md`
- `README.md`（加路由行）
