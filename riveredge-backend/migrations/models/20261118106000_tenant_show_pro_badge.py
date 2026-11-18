"""组织表：高级应用 PRO 徽章显示开关（默认开启）。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "infra_tenants"
            ADD COLUMN IF NOT EXISTS "show_pro_badge" BOOL NOT NULL DEFAULT TRUE;
        COMMENT ON COLUMN "infra_tenants"."show_pro_badge" IS '高级应用是否显示PRO徽章（默认开启）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "infra_tenants"
            DROP COLUMN IF EXISTS "show_pro_badge";
    """
