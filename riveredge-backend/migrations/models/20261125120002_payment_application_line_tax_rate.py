"""付款申请明细行税率（百分比）；历史头表税率回填明细。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_payment_application_lines"
            ADD COLUMN IF NOT EXISTS "tax_rate" DECIMAL(6,2) NOT NULL DEFAULT 0;
        COMMENT ON COLUMN "apps_kuaizhizao_payment_application_lines"."tax_rate"
            IS '税率百分比（如13表示13%）；自来源订单/入库行快照';

        UPDATE "apps_kuaizhizao_payment_application_lines" AS l
        SET "tax_rate" = a."tax_rate"
        FROM "apps_kuaizhizao_payment_applications" AS a
        WHERE l."application_id" = a."id"
          AND l."tenant_id" = a."tenant_id"
          AND (l."tax_rate" IS NULL OR l."tax_rate" = 0)
          AND COALESCE(a."tax_rate", 0) > 0;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_payment_application_lines"
            DROP COLUMN IF EXISTS "tax_rate";
    """