---
title: BOM 主物料自制件下拉空列表
slug: bom-main-material-make-scope
status: delivered
domain: master-data-ui
when: BOM 新建选自制件找不到物料、mainMaterialScope make 空
keywords:
  - mainMaterialScope
  - sourceType
  - Make
  - BOM
  - limit 1000
standard: BOM 弹窗拉物料时 make 范围传 sourceType=Make，勿只靠本地筛前 1000 条
---

# BOM 主物料自制件下拉空列表

## 目标

BOM 创建弹窗「自制件」范围能选到库内 `source_type=Make` 的主物料。

## 何时读 / 禁止另起

- 何时读：BOM 主物料下拉自制件为空、切换「全部物料」才有
- 禁止：把 limit 盲目调到全库；勿再只前端 `sourceType===Make` 筛无过滤的前 N 条

## 标准入口

| 层 | 标准 |
|----|------|
| FE | `bom/index.tsx`：`materialApi.list({ sourceType: 'Make', mastersOnly: true })`（scope=make） |
| BE | `GET /materials?sourceType=Make`（已支持） |

## 踩坑

- 库内可能有上百 Make，但按 `main_code`/`id` 排序时排在 5000+；`limit:1000` 全是 Buy → 本地再筛 Make = 空
- 与「来源类型转换未生效、物料全是 Buy」不同：即使已有 Make，也会被 1000 截断挡住
