from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_equipment_spot_checks"
        ADD COLUMN IF NOT EXISTS "inspector_ids" JSONB NOT NULL DEFAULT '[]'::jsonb;
        COMMENT ON COLUMN "apps_kuaizhizao_equipment_spot_checks"."inspector_ids"
            IS '点检人ID列表（多人点检）';

        ALTER TABLE "apps_kuaizhizao_equipment_spot_checks"
        ALTER COLUMN "inspector_name" TYPE VARCHAR(500);

        UPDATE "apps_kuaizhizao_equipment_spot_checks"
        SET "inspector_ids" = jsonb_build_array("inspector_id")
        WHERE "inspector_id" IS NOT NULL
          AND (
            "inspector_ids" IS NULL
            OR "inspector_ids" = '[]'::jsonb
            OR "inspector_ids" = 'null'::jsonb
          );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_equipment_spot_checks"
        DROP COLUMN IF EXISTS "inspector_ids";
        ALTER TABLE "apps_kuaizhizao_equipment_spot_checks"
        ALTER COLUMN "inspector_name" TYPE VARCHAR(100);
    """
