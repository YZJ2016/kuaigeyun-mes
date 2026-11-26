from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_kuaicaiwu_receivables_source
        ON "apps_kuaicaiwu_receivables" ("tenant_id", "source_type", "source_id")
        WHERE "source_id" IS NOT NULL AND "deleted_at" IS NULL AND "status" <> '已作废';

        CREATE UNIQUE INDEX IF NOT EXISTS uq_kuaicaiwu_payables_source
        ON "apps_kuaicaiwu_payables" ("tenant_id", "source_type", "source_id")
        WHERE "source_id" IS NOT NULL AND "deleted_at" IS NULL AND "status" <> '已作废';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS uq_kuaicaiwu_receivables_source;
        DROP INDEX IF EXISTS uq_kuaicaiwu_payables_source;
    """
