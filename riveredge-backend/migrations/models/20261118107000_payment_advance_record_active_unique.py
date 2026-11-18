"""垫付台账：同一付款单仅允许一条未删除记录（防并发确认重复入账）。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE UNIQUE INDEX IF NOT EXISTS "uq_payment_advance_records_active_payment"
            ON "apps_kuaicaiwu_payment_advance_records" ("tenant_id", "payment_id")
            WHERE "deleted_at" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uq_payment_advance_records_active_payment";
    """
