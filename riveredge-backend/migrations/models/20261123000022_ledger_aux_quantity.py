"""
台账辅助数量：与基本量并列，对外 secondary_quantity 真源。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_material_batches"
        ADD COLUMN IF NOT EXISTS "aux_quantity" DECIMAL(18,4) NOT NULL DEFAULT 0;
        COMMENT ON COLUMN "apps_master_data_material_batches"."aux_quantity"
            IS '辅助单位数量（对外 secondary_quantity 真源）';
        UPDATE "apps_master_data_material_batches"
        SET "aux_quantity" = COALESCE("quantity", 0)
        WHERE "aux_quantity" IS NULL OR "aux_quantity" = 0;

        ALTER TABLE "apps_kuaizhizao_line_side_inventory"
        ADD COLUMN IF NOT EXISTS "aux_quantity" DECIMAL(18,4) NOT NULL DEFAULT 0;
        COMMENT ON COLUMN "apps_kuaizhizao_line_side_inventory"."aux_quantity"
            IS '辅助单位数量';
        UPDATE "apps_kuaizhizao_line_side_inventory"
        SET "aux_quantity" = COALESCE("quantity", 0)
        WHERE "aux_quantity" IS NULL OR "aux_quantity" = 0;

        ALTER TABLE "apps_kuaizhizao_material_stock_movements"
        ADD COLUMN IF NOT EXISTS "aux_quantity" DECIMAL(18,4);
        COMMENT ON COLUMN "apps_kuaizhizao_material_stock_movements"."aux_quantity"
            IS '辅助单位数量（流水快照）';
        UPDATE "apps_kuaizhizao_material_stock_movements"
        SET "aux_quantity" = "quantity"
        WHERE "aux_quantity" IS NULL;
        """
