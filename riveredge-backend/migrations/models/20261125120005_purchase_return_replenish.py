from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_returns"
        ADD COLUMN IF NOT EXISTS "replenish" BOOL NOT NULL DEFAULT FALSE;
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_returns"."replenish"
            IS '是否补货（是则释放采购订单可再次下推入库的数量）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_returns"
        DROP COLUMN IF EXISTS "replenish";
    """
