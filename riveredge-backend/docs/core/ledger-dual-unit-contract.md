# 台账双计量契约（主单位 / 副单位）

## 三层单位（勿混用）

| 金蝶 / ORM | 语义 | 对外 API |
|---|---|---|
| `inventory_unit` / `MaterialBatch.quantity` | **库存单位**与库存量 | `primary_unit` / `primary_quantity` |
| `base_unit` / `MaterialBatch.base_quantity` | **基本单位**与基本量（过账真源，不对用户称「副」） | **不对外**（Breaking 域已移除 legacy 键） |
| 物料 `units[]` 第一个 **固定换算**辅助单位 / `MaterialBatch.aux_quantity` | **辅助单位**与辅助量 | `secondary_unit` / `secondary_quantity` |

- **单据行** `aux_quantity` / `aux_unit` 为业务双录，与台账 `secondary_*` 语义一致（辅助），但过账仍先归基本量再写批次。
- **台账双单位**（展示四列）：物料存在至少一个固定辅助单位；`material_ledger_is_dual_unit` 据此判定，**不是**「库存单位 ≠ 基本单位」。

## 金蝶即时库存字段对照

| 本地写入 | 金蝶/映射源（已知） | 说明 |
|---|---|---|
| `quantity` | `avbqty` / `qty` | 库存单位数量 |
| `base_quantity` | `baseqty` / `FBaseQty` / `base_qty` | **基本单位**数量 |
| `aux_quantity` | 即时库存：苍穹 `avbqty2nd`/`qty2nd`；**采购入库分录写入/回显：`qtyunit2nd`**（勿与库存字段混用）；星空等 `secqty` | **辅助单位**数量 |
| 物料 `units[]` 固定辅助 | 苍穹 `unit2nd.number`；星空 `secunit*`（写路径补齐） | API `secondary_unit` |

**辅助数量候选键**（连接器字段映射可配置，按序尝试）：`avbqty2nd`、`qty2nd`、`secqty`、`sec_qty`、`auxqty`、`aux_qty`、`FSecQty`、`FExtAuxUnitQty`、`muqty`。

**辅助单位候选键**：`unit2nd.number`、`unit2nd.name`、`unit2nd`、`secunit_number`、`secunit.number`、`secunit_name`、`secunit`、`auxunit_number`。

**禁止**把 `baseqty` 当作辅助数量。同步写路径允许在 **有固定辅助单位** 且已有 `base_quantity` 时，用物料 n/d 将基本量换算为辅助量写入 `aux_quantity`（写路径换算，非读侧 enrich）。

若物料尚无**固定**辅助单位（含仅有浮动换算），但库存行同时带辅助单位与辅助量：即时库存同步会按本行「基本量/辅助量」推算 n/d，写入/覆盖为 `Material.units` 固定换算（否则副单位会回落成主单位）。

## 与单据行 aux_* 的区别

- **业务双录**：`quantity` + `aux_quantity` / `aux_unit` / `unit_conversion_rate`（销售、采购等场景单位）。
- **台账双计量**：过账真源 `inventory_posting_utils`；对外字段 `primary_*` / `secondary_*`（副 = 辅助）。

## 单单位物料

无固定辅助单位：`secondary_unit` 与 `primary_unit` 相同，`secondary_quantity` 与 `primary_quantity` 相同；同步可无 baseqty，基本量与库存量对齐。

## 多辅助单位

即时库存/余额 API **仅展示第一个固定换算辅助单位**；其余辅助单位不在四列体现。

## Breaking（仓储报表域）

`/apps/kuaizhizao/reports/inventory/*` 响应不再返回 `quantity`、`base_quantity`、`inventory_unit`、`base_unit`。

`secondary_*` 语义修正（2026-11）：由误用的「基本单位/基本量」改为 **辅助单位/辅助量**；键名不变，集成方须改读含义。

## 集成方对照

| 键 | 含义 |
|---|---|
| primary_unit | 库存单位 |
| primary_quantity | 库存单位数量 |
| secondary_unit | 第一个固定辅助单位（无则同 primary） |
| secondary_quantity | 辅助单位数量（无则同 primary） |

入库/出库确认明细：`primary_quantity`（库存单位）+ 可选 `secondary_quantity`（**辅助**数量，台账双单位时必填）。

其他出入库详情明细响应除行字段 `inbound_quantity`/`outbound_quantity`/`aux_*` 外，同步返回与即时库存一致的 `primary_unit` / `secondary_unit` / `primary_quantity` / `secondary_quantity`。

## 数据修复

历史误把 `base_quantity` 当副数量展示：有固定辅助单位的批次需 **金蝶即时库存全量重同步**（先物料多单位，再库存）。诊断：`scripts/repair_ledger_dual_unit_batches.py`。
