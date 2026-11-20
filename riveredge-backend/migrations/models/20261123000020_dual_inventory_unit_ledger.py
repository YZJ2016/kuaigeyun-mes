"""
金蝶式双计量：物料库存单位 + 台账基本数量。

- apps_master_data_materials.inventory_unit（默认等于 base_unit）
- 批次/线边/流水 base_quantity（回填等于 quantity）
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_materials"
        ADD COLUMN IF NOT EXISTS "inventory_unit" VARCHAR(20);
        COMMENT ON COLUMN "apps_master_data_materials"."inventory_unit"
            IS '库存单位（金蝶库存单位；默认同基础单位）';
        UPDATE "apps_master_data_materials"
        SET "inventory_unit" = "base_unit"
        WHERE ("inventory_unit" IS NULL OR TRIM("inventory_unit") = '')
          AND "base_unit" IS NOT NULL
          AND TRIM("base_unit") <> '';
        UPDATE "apps_master_data_materials"
        SET "inventory_unit" = '件'
        WHERE "inventory_unit" IS NULL OR TRIM("inventory_unit") = '';

        ALTER TABLE "apps_master_data_material_batches"
        ADD COLUMN IF NOT EXISTS "base_quantity" DECIMAL(18,4) NOT NULL DEFAULT 0;
        COMMENT ON COLUMN "apps_master_data_material_batches"."quantity"
            IS '库存单位数量（当前库存）';
        COMMENT ON COLUMN "apps_master_data_material_batches"."base_quantity"
            IS '基本单位数量（当前库存）';
        UPDATE "apps_master_data_material_batches"
        SET "base_quantity" = COALESCE("quantity", 0)
        WHERE "base_quantity" IS NULL OR "base_quantity" = 0;

        ALTER TABLE "apps_kuaizhizao_line_side_inventory"
        ADD COLUMN IF NOT EXISTS "base_quantity" DECIMAL(18,4) NOT NULL DEFAULT 0;
        COMMENT ON COLUMN "apps_kuaizhizao_line_side_inventory"."quantity"
            IS '库存单位数量';
        COMMENT ON COLUMN "apps_kuaizhizao_line_side_inventory"."base_quantity"
            IS '基本单位数量';
        UPDATE "apps_kuaizhizao_line_side_inventory"
        SET "base_quantity" = COALESCE("quantity", 0)
        WHERE "base_quantity" IS NULL OR "base_quantity" = 0;

        ALTER TABLE "apps_kuaizhizao_material_stock_movements"
        ADD COLUMN IF NOT EXISTS "base_quantity" DECIMAL(18,4);
        ALTER TABLE "apps_kuaizhizao_material_stock_movements"
        ADD COLUMN IF NOT EXISTS "base_qty_before" DECIMAL(18,4);
        ALTER TABLE "apps_kuaizhizao_material_stock_movements"
        ADD COLUMN IF NOT EXISTS "base_qty_after" DECIMAL(18,4);
        COMMENT ON COLUMN "apps_kuaizhizao_material_stock_movements"."base_quantity"
            IS '有符号基本单位数量（出库负、入库正）';
        UPDATE "apps_kuaizhizao_material_stock_movements"
        SET "base_quantity" = "quantity"
        WHERE "base_quantity" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_material_stock_movements"
        DROP COLUMN IF EXISTS "base_qty_after";
        ALTER TABLE "apps_kuaizhizao_material_stock_movements"
        DROP COLUMN IF EXISTS "base_qty_before";
        ALTER TABLE "apps_kuaizhizao_material_stock_movements"
        DROP COLUMN IF EXISTS "base_quantity";
        ALTER TABLE "apps_kuaizhizao_line_side_inventory"
        DROP COLUMN IF EXISTS "base_quantity";
        ALTER TABLE "apps_master_data_material_batches"
        DROP COLUMN IF EXISTS "base_quantity";
        ALTER TABLE "apps_master_data_materials"
        DROP COLUMN IF EXISTS "inventory_unit";
    """
