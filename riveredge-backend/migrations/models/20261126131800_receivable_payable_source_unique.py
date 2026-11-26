from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 建唯一索引前先清理存量重复：同 (tenant_id, source_type, source_id)
        -- 命中索引谓词的多行中软删 id 较小者，保留最新一条。
        UPDATE "apps_kuaicaiwu_receivables" t
        SET "deleted_at" = NOW(), "updated_at" = NOW()
        WHERE t."deleted_at" IS NULL
          AND t."source_id" IS NOT NULL
          AND t."status" <> '已作废'
          AND EXISTS (
            SELECT 1
            FROM "apps_kuaicaiwu_receivables" n
            WHERE n."tenant_id" = t."tenant_id"
              AND n."source_type" = t."source_type"
              AND n."source_id" = t."source_id"
              AND n."deleted_at" IS NULL
              AND n."status" <> '已作废'
              AND n."id" > t."id"
          );

        UPDATE "apps_kuaicaiwu_payables" t
        SET "deleted_at" = NOW(), "updated_at" = NOW()
        WHERE t."deleted_at" IS NULL
          AND t."source_id" IS NOT NULL
          AND t."status" <> '已作废'
          AND EXISTS (
            SELECT 1
            FROM "apps_kuaicaiwu_payables" n
            WHERE n."tenant_id" = t."tenant_id"
              AND n."source_type" = t."source_type"
              AND n."source_id" = t."source_id"
              AND n."deleted_at" IS NULL
              AND n."status" <> '已作废'
              AND n."id" > t."id"
          );

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
