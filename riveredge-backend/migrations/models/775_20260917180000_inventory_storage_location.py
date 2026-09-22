from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_master_data_material_batches"
    ADD COLUMN IF NOT EXISTS "location_id" INT,
    ADD COLUMN IF NOT EXISTS "location_code" VARCHAR(50);

COMMENT ON COLUMN "apps_master_data_material_batches"."location_id" IS '库位ID（可选）';
COMMENT ON COLUMN "apps_master_data_material_batches"."location_code" IS '库位编码（可选）';

CREATE INDEX IF NOT EXISTS "idx_material_batches_location_code"
    ON "apps_master_data_material_batches" ("tenant_id", "location_code")
    WHERE "deleted_at" IS NULL AND "location_code" IS NOT NULL;

ALTER TABLE "apps_kuaizhizao_line_side_inventory"
    ADD COLUMN IF NOT EXISTS "location_id" INT,
    ADD COLUMN IF NOT EXISTS "location_code" VARCHAR(50);

COMMENT ON COLUMN "apps_kuaizhizao_line_side_inventory"."location_id" IS '库位ID（可选）';
COMMENT ON COLUMN "apps_kuaizhizao_line_side_inventory"."location_code" IS '库位编码（可选）';

-- 历史入库明细回填：采购入库 / 其他入库已确认行 → 批次库位
UPDATE "apps_master_data_material_batches" AS b
SET
    location_id = src.location_id,
    location_code = src.location_code
FROM (
    SELECT DISTINCT ON (pri.tenant_id, pri.material_id, pri.batch_number, COALESCE(NULLIF(pri.warehouse_id, 0), pr.warehouse_id))
        pri.tenant_id,
        pri.material_id,
        pri.batch_number,
        COALESCE(NULLIF(pri.warehouse_id, 0), pr.warehouse_id) AS warehouse_id,
        pri.location_id,
        pri.location_code
    FROM "apps_kuaizhizao_purchase_receipt_items" pri
    INNER JOIN "apps_kuaizhizao_purchase_receipts" pr
        ON pr.id = pri.receipt_id AND pr.tenant_id = pri.tenant_id
    WHERE pri.deleted_at IS NULL
      AND pri.batch_number IS NOT NULL
      AND TRIM(pri.batch_number) <> ''
      AND pri.location_code IS NOT NULL
      AND TRIM(pri.location_code) <> ''
      AND pri.status = '已入库'
    ORDER BY pri.tenant_id, pri.material_id, pri.batch_number,
             COALESCE(NULLIF(pri.warehouse_id, 0), pr.warehouse_id),
             pri.updated_at DESC
) AS src
WHERE b.deleted_at IS NULL
  AND b.tenant_id = src.tenant_id
  AND b.material_id = src.material_id
  AND b.batch_no = src.batch_number
  AND b.warehouse_id = src.warehouse_id
  AND (b.location_code IS NULL OR TRIM(b.location_code) = '');

UPDATE "apps_master_data_material_batches" AS b
SET
    location_id = src.location_id,
    location_code = src.location_code
FROM (
    -- 其他入库明细无行级 warehouse_id，仓库只在头表
    SELECT DISTINCT ON (oi.tenant_id, oi.material_id, oi.batch_number, oh.warehouse_id)
        oi.tenant_id,
        oi.material_id,
        oi.batch_number,
        oh.warehouse_id AS warehouse_id,
        oi.location_id,
        oi.location_code
    FROM "apps_kuaizhizao_other_inbound_items" oi
    INNER JOIN "apps_kuaizhizao_other_inbounds" oh
        ON oh.id = oi.inbound_id AND oh.tenant_id = oi.tenant_id
    WHERE oi.deleted_at IS NULL
      AND oi.batch_number IS NOT NULL
      AND TRIM(oi.batch_number) <> ''
      AND oi.location_code IS NOT NULL
      AND TRIM(oi.location_code) <> ''
      AND oi.status = '已入库'
    ORDER BY oi.tenant_id, oi.material_id, oi.batch_number,
             oh.warehouse_id,
             oi.updated_at DESC
) AS src
WHERE b.deleted_at IS NULL
  AND b.tenant_id = src.tenant_id
  AND b.material_id = src.material_id
  AND b.batch_no = src.batch_number
  AND b.warehouse_id = src.warehouse_id
  AND (b.location_code IS NULL OR TRIM(b.location_code) = '');
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP INDEX IF EXISTS "idx_material_batches_location_code";

ALTER TABLE "apps_master_data_material_batches"
    DROP COLUMN IF EXISTS "location_id",
    DROP COLUMN IF EXISTS "location_code";

ALTER TABLE "apps_kuaizhizao_line_side_inventory"
    DROP COLUMN IF EXISTS "location_id",
    DROP COLUMN IF EXISTS "location_code";
"""
