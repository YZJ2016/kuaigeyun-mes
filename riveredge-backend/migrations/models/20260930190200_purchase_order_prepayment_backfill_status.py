"""采购订单记下预付补齐结果，失败不再只留在日志里。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_orders"
            ADD COLUMN IF NOT EXISTS "prepayment_backfill_status" VARCHAR(20);
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_orders"."prepayment_backfill_status"
            IS '预付补齐状态：空=还没跑过，missing=未补齐，backfilled=已补齐';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_orders"
            DROP COLUMN IF EXISTS "prepayment_backfill_status";
    """
