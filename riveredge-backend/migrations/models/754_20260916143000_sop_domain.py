"""SOP 业务域分域：PE 制造 / QC 材料（R-01 #55）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_sop"
            ADD COLUMN IF NOT EXISTS "sop_domain" VARCHAR(10) NOT NULL DEFAULT 'pe';
        UPDATE "apps_master_data_sop"
            SET "sop_domain" = 'pe'
            WHERE "sop_domain" IS NULL OR TRIM("sop_domain") = '';
        CREATE INDEX IF NOT EXISTS "idx_master_data_sop_domain"
            ON "apps_master_data_sop" ("tenant_id", "sop_domain");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_master_data_sop_domain";
        ALTER TABLE "apps_master_data_sop" DROP COLUMN IF EXISTS "sop_domain";
    """
