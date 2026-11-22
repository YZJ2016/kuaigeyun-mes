"""客户 partner_type/biz_function 列（上游 947 迁移的时间戳 remap 落位）。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_customers"
        ADD COLUMN IF NOT EXISTS "partner_type" VARCHAR(20);
        ALTER TABLE "apps_master_data_customers"
        ADD COLUMN IF NOT EXISTS "biz_function" VARCHAR(50);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_customers" DROP COLUMN IF EXISTS "partner_type";
        ALTER TABLE "apps_master_data_customers" DROP COLUMN IF EXISTS "biz_function";
    """
