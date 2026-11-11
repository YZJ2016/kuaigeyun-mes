# 金蝶强一致实施 SOP（单租户）

适用：已启用金蝶外推/入站、连接器组织与 `InventorySyncBinding` 已配置的租户（连枝横 `tenant_id=2`、组织 `BU-00001`）。

## 一致口径（五条）

| 维度 | 金蝶真源 | 本系统 |
|------|----------|--------|
| 基础资料 | 苍穹主数据 API | 入站同步绑定；禁止手工改编码后不同步 |
| 业务单据状态 | 审核/过账/删除 | 与 `DocumentRelation` + 外推日志一致 |
| 库存 | `getInventoryAvbQty` 仓+仓位 | `MaterialBatch` 同 key；空仓位禁止有量 |
| 金额 | 立账/应付应收 | 业财对账 + 入库/发票策略 |
| 单据状态 | 已审已过账 | 撤回须先金蝶成功再本地 |

## 执行顺序（每次大对齐）

1. **审计**：`TENANT_ID=<id> PYTHONPATH=src .venv/bin/python scripts/tenant_kingdee_strong_consistency.py --audit`
2. **清红灯**：按输出逐单处理（过账补推、撤回补金蝶、或本地反过账）；直至即时库存同步不再报 `仓储单据与金蝶未对齐`
3. **基础资料**：仓库 → 仓位关系 → 仓位 → 物料/客商 → 单位/批号管理（参数中心定时或手工全量）
4. **库存**：`--repair-empty-locations --apply`（空仓位归无货架）→ 即时库存全量入站
5. **金额/订单**：采购/销售/工单入站按需；财务用「业财单据对账」「往来对账」
6. **复核**：`scripts/lzh_reconcile_report.py`（四租户物料客商）+ 抽单金额

## 连枝横专项治理

- 合并或停用重复仓 **`1004` / `W1004`**（同名「3楼1#」），库存迁到金蝶现用编码
- 洗衣粉类物料：仓位统一 `W1004_无货架` 后再确认其他出库
- 禁止金蝶 ERP 手工改库存不同步入站

## 脚本

- `scripts/tenant_kingdee_strong_consistency.py` — 红灯、重复仓、空仓位
- `scripts/lzh_reconcile_report.py` — 与金蝶 PDF 体例物料客商对比
