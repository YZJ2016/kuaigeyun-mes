"""节日福利发放单支持多车间。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_welfare_batches"
            ADD COLUMN IF NOT EXISTS "workshop_names" JSONB NOT NULL DEFAULT '[]'::jsonb;

        ALTER TABLE "apps_kuaioa_welfare_batches"
            ALTER COLUMN "workshop_name" TYPE VARCHAR(500);

        UPDATE "apps_kuaioa_welfare_batches"
        SET "workshop_names" = CASE
            WHEN COALESCE(TRIM("workshop_name"), '') = '' THEN '[]'::jsonb
            ELSE jsonb_build_array(TRIM("workshop_name"))
        END
        WHERE "workshop_names" IS NULL
           OR "workshop_names" = '[]'::jsonb
           OR "workshop_names" = 'null'::jsonb;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_welfare_batches"
            DROP COLUMN IF EXISTS "workshop_names";
    """
