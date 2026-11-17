"""库位：可直挂仓库 + 金蝶源仓位号（4d124a088e 域：整仓库位/独立仓位支持）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_storage_locations"
            ALTER COLUMN "storage_area_id" DROP NOT NULL;
        ALTER TABLE "apps_master_data_storage_locations"
            ADD COLUMN IF NOT EXISTS "warehouse_id" INT;
        COMMENT ON COLUMN "apps_master_data_storage_locations"."warehouse_id"
            IS '所属仓库（可选；未挂库区时可直挂）';
        ALTER TABLE "apps_master_data_storage_locations"
            ADD COLUMN IF NOT EXISTS "source_location_code" VARCHAR(50);
        COMMENT ON COLUMN "apps_master_data_storage_locations"."source_location_code"
            IS '苍穹仓位号 location_number（回写金蝶；可与本地 code 不同）';
        CREATE INDEX IF NOT EXISTS "idx_apps_master_data_storage_locations_warehouse_id"
            ON "apps_master_data_storage_locations" ("warehouse_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_apps_master_data_storage_locations_warehouse_id";
        ALTER TABLE "apps_master_data_storage_locations"
            DROP COLUMN IF EXISTS "source_location_code",
            DROP COLUMN IF EXISTS "warehouse_id";
        DELETE FROM "apps_master_data_storage_locations"
            WHERE "storage_area_id" IS NULL;
        ALTER TABLE "apps_master_data_storage_locations"
            ALTER COLUMN "storage_area_id" SET NOT NULL;
    """
