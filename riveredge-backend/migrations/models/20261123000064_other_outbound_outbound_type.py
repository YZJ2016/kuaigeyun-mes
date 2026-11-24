"""其他出库单增加出库类型（物料出库/资产出库）。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_other_outbounds"
        ADD COLUMN IF NOT EXISTS "outbound_type" VARCHAR(20) NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_other_outbounds"
        DROP COLUMN IF EXISTS "outbound_type";
    """