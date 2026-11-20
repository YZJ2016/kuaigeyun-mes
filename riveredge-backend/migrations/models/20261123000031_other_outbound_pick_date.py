"""
其他出库单：领用日期。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_other_outbounds"
            ADD COLUMN IF NOT EXISTS "pick_date" DATE;

        COMMENT ON COLUMN "apps_kuaizhizao_other_outbounds"."pick_date"
            IS '领用日期';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_other_outbounds" DROP COLUMN IF EXISTS "pick_date";
    """
