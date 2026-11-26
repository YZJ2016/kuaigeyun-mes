"""
物料批次唯一键纳入 location_code：对齐金蝶即时库存「仓库+仓位」维度。
空库位统一为空串，避免 NULL 破坏唯一索引。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_master_data_material_batches"
        SET "location_code" = ''
        WHERE "location_code" IS NULL;

        ALTER TABLE "apps_master_data_material_batches"
        ALTER COLUMN "location_code" SET DEFAULT '';

        ALTER TABLE "apps_master_data_material_batches"
        ALTER COLUMN "location_code" SET NOT NULL;

        COMMENT ON COLUMN "apps_master_data_material_batches"."location_code"
            IS '库位编码（空串=未分库位；与仓库共同构成库存维度）';

        DROP INDEX IF EXISTS "uidx_material_batch_ownership_wh_qs";
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_material_batch_ownership_wh_qs_loc"
            ON "apps_master_data_material_batches"
            (
                "tenant_id",
                "material_id",
                "batch_no",
                "ownership_type",
                "customer_id",
                "warehouse_id",
                "quality_status",
                "location_code"
            )
            WHERE "deleted_at" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uidx_material_batch_ownership_wh_qs_loc";
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_material_batch_ownership_wh_qs"
            ON "apps_master_data_material_batches"
            (
                "tenant_id",
                "material_id",
                "batch_no",
                "ownership_type",
                "customer_id",
                "warehouse_id",
                "quality_status"
            )
            WHERE "deleted_at" IS NULL;

        ALTER TABLE "apps_master_data_material_batches"
        ALTER COLUMN "location_code" DROP NOT NULL;
    """

# 对应上游 949_20261027170000_material_batch_location_unique.py
