"""
采购申请：采购类型 order_type。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_requisitions"
            ADD COLUMN IF NOT EXISTS "order_type" VARCHAR(20) NOT NULL DEFAULT '标准采购';

        COMMENT ON COLUMN "apps_kuaizhizao_purchase_requisitions"."order_type"
            IS '采购类型：标准采购、资产采购、服务采购';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_requisitions" DROP COLUMN IF EXISTS "order_type";
    """
