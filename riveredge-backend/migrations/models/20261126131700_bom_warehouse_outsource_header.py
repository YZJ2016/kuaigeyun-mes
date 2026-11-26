"""BOM 版本头：主件仓库、制造部门、附件；子件行：仓库、是否委外。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_bom"
            ADD COLUMN IF NOT EXISTS "material_warehouse_id" INT,
            ADD COLUMN IF NOT EXISTS "manufacturing_department_id" INT,
            ADD COLUMN IF NOT EXISTS "attachments" JSONB,
            ADD COLUMN IF NOT EXISTS "warehouse_id" INT,
            ADD COLUMN IF NOT EXISTS "is_outsource" BOOL NOT NULL DEFAULT false;
        COMMENT ON COLUMN "apps_master_data_bom"."material_warehouse_id" IS '主物料默认发料仓库（版本级）';
        COMMENT ON COLUMN "apps_master_data_bom"."manufacturing_department_id" IS '制造部门（版本级）';
        COMMENT ON COLUMN "apps_master_data_bom"."attachments" IS 'BOM版本附件';
        COMMENT ON COLUMN "apps_master_data_bom"."warehouse_id" IS '子件发料仓库';
        COMMENT ON COLUMN "apps_master_data_bom"."is_outsource" IS '子件是否委外';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_bom"
            DROP COLUMN IF EXISTS "material_warehouse_id",
            DROP COLUMN IF EXISTS "manufacturing_department_id",
            DROP COLUMN IF EXISTS "attachments",
            DROP COLUMN IF EXISTS "warehouse_id",
            DROP COLUMN IF EXISTS "is_outsource";
    """

# 对应上游 1036_20261115170000_bom_warehouse_outsource_header.py
