---
title: SOP 现场匹配与分域隔离
slug: sop-shopfloor-match-domain
status: delivered
domain: master-data
when: SOP 配错物料、工序兜底、QC 材料 SOP、职位以外的 SOP 编码冲突、无法同步创建职位无关
keywords:
  - collect_shopfloor_sops
  - sop_domain
  - get_sop_for_material
  - 标准操作 SOP
standard: 工位/报工/工单相关 SOP 只走 collect_shopfloor_sops；禁止再写一套按工序全表捞
---

# SOP 现场匹配与分域隔离

## 目标

现场匹配不串料；PE/QC 编码与绑定按域隔离；文控发布强制启用。

## 何时读 / 禁止另起

- 何时读：工位配到别的产品 SOP、QC SOP 不出现、SOP 编码已存在
- 禁止：在 StationService / 工单卡再手写 SOP.filter(operation_id=…) 全表兜底

## 标准入口

| 层 | 标准 |
|----|------|
| 匹配 | `collect_shopfloor_sops` + `pick_unique_shopfloor_sop` |
| 择一 | `ProcessService.get_sop_for_material` / `get_sop_for_reporting` |
| 列表 | `list_sops_for_material_operation` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 匹配 | `riveredge-backend/src/apps/master_data/services/process_service.py` |
| 文控 | `riveredge-backend/src/apps/master_data/services/sop_control_service.py` |
| 说明 | `docs/apps/master-data/sop.md` |

## 踩坑

- 第 5 档只允许未绑物料/组的工序模板
- 同档多份择一抛 ValidationError，工单 has_esop 把该错误当成「有 SOP」
- 物理表 `apps_master_data_sop`，自定义字段逻辑名 `master_data_sops`

## 关联

- `docs/apps/master-data/sop.md`
