# 金蝶强一致实施 SOP（单租户）

适用：已启用金蝶外推/入站、连接器组织与 `InventorySyncBinding` 已配置的租户（连枝横 `tenant_id=2`、组织 `BU-00001`）。

## 一致口径（五条）

| 维度 | 金蝶真源 | 本系统 |
|------|----------|--------|
| 基础资料 | 苍穹主数据 API | 各模块 **sync-from-source** 入站绑定；禁止手工改编码后不同步 |
| 业务单据状态 | 审核/过账/删除 | 与 `DocumentRelation` + 外推日志一致 |
| 库存 | `getInventoryAvbQty` 仓+仓位 | **即时库存全量入站** 覆盖本地批次；禁止 SQL 改 `MaterialBatch` 仓位 |
| 金额 | 立账/应付应收 | 业财对账 + 入库/发票策略 |
| 单据状态 | 已审已过账 | 撤回须先金蝶成功再本地 |

## 执行顺序（每次大对齐）

1. **审计**（只读）
   - API：`GET /api/v1/apps/kuaizhizao/reports/kingdee-consistency/audit`
   - 或运维：`TENANT_ID=<id> PYTHONPATH=src uv run python scripts/tenant_kingdee_strong_consistency.py --audit`
2. **清红灯**：按审计 `remediation` 走系统接口（勿改库）
   - 过账未关联：`POST /api/v1/apps/kuaizhizao/document-push`（`target_profile: *`）
   - 撤回失败：对应仓储 `.../withdraw` 重试
3. **基础资料链**：`POST .../reports/kingdee-consistency/sync-master-data`（单位→分组→物料→多单位→批号→客商→仓库→**仓位关系**→仓位）
4. **库存**：红灯为 0 后 `POST .../reports/kingdee-consistency/sync-inventory` 或报表页「即时库存」**全量入站**
5. **金额/订单**：采购/销售/工单入站按需；财务用「业财单据对账」「往来对账」
6. **复核**：`scripts/lzh_reconcile_report.py`（物料客商）+ 抽单金额

## 连枝横专项治理

- 合并或停用重复仓 **`1004` / `W1004`**（同名「3楼1#」）：金蝶仓库入站 + 数据治理，勿手工迁批次
- 洗衣粉等：**全量即时库存入站** 后仓位与金蝶 `无货架` 对齐，再确认其他出库
- 禁止金蝶 ERP 手工改库存不同步入站

## 脚本与 API（唯一修复路径）

| 能力 | 入口 |
|------|------|
| 审计 | `tenant_kingdee_strong_consistency.py --audit` / kingdee-consistency GET |
| 主数据 | `--sync-master-data` / sync-master-data POST |
| 库存 | `--sync-inventory` / sync-inventory POST（与 `inventory/sync-from-source` 同服务） |
| 外推 | `document-push` |
| 主数据逐类 | 主数据各列表「从数据接口同步」同服务 |

**已废弃**：`--repair-empty-locations` 直接 UPDATE 批次（与金蝶灌库口径冲突）。
