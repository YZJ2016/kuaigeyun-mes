from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaicaiwu_payables"
        SET "total_amount" = -ABS("total_amount")
        WHERE "source_type" = '采购退货'
          AND "total_amount" > 0
          AND "deleted_at" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaicaiwu_payables"
        SET "total_amount" = ABS("total_amount")
        WHERE "source_type" = '采购退货'
          AND "total_amount" < 0
          AND "deleted_at" IS NULL;
    """
