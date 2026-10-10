---
title: 苍穹仓库列表自动带 createorg_number
slug: cosmic-warehouse-createorg
status: delivered
domain: sync-from-source
when: 仓库列表查询报 createorg_number 必填、苍穹 batchQuery data
keywords:
  - createorg_number
  - bd_warehouse
  - batchQuery
  - prepare_kingdee_cosmic_outbound
  - query_warehouse
standard: 仓库 batchQuery 请求体 data.createorg_number + pageNo/pageSize
---

# 苍穹仓库列表自动带 createorg_number

## 目标

仓库列表走 `POST /kapi/v2/basedata/bd_warehouse/batchQuery`，请求体为：

```json
{
  "data": { "createorg_number": "WANG" },
  "pageNo": 1,
  "pageSize": 1000
}
```

`createorg_number` 必须在 `data` 内，不是 Query。默认示例与供应商查询相同（`WANG`），按现场创建组织编码改接口请求体即可。

## 何时读 / 禁止另起

- 何时读：仓库列表报 createorg_number 必填
- 禁止：不要另做连接器专用组织表单当唯一入口；以接口请求体为准

## 标准入口

| 层 | 标准 |
|----|------|
| 预设 | `build_warehouse_batch_query_preset_body` |
| 发出 | `prepare_kingdee_cosmic_outbound` 写入 `data.createorg_number` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 预设 | `riveredge-backend/src/core/services/integration/kingdee_cosmic_api_presets.py` |
| 发出 | `riveredge-backend/src/core/services/integration/kingdee_cosmic_paths.py` |

## 踩坑

- 空 `data: {}` 金蝶会报 createorg_number 必填
- 已有接口不会自动覆盖 pageSize；缺字段时补 `createorg_number`
