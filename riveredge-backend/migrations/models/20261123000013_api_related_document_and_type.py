"""core_apis：关联单据、接口类型（标准/自定义）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "core_apis"
            ADD COLUMN IF NOT EXISTS "related_document_code" VARCHAR(64);
        ALTER TABLE "core_apis"
            ADD COLUMN IF NOT EXISTS "api_interface_type" VARCHAR(20) NOT NULL DEFAULT 'custom';
        COMMENT ON COLUMN "core_apis"."related_document_code" IS '关联 MES 单据 source_type（可选）';
        COMMENT ON COLUMN "core_apis"."api_interface_type" IS '接口类型：standard 标准API / custom 自定义API';
        CREATE INDEX IF NOT EXISTS "idx_core_apis_related_document_code"
            ON "core_apis" ("tenant_id", "related_document_code");
        CREATE INDEX IF NOT EXISTS "idx_core_apis_api_interface_type"
            ON "core_apis" ("tenant_id", "api_interface_type");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_core_apis_api_interface_type";
        DROP INDEX IF EXISTS "idx_core_apis_related_document_code";
        ALTER TABLE "core_apis" DROP COLUMN IF EXISTS "api_interface_type";
        ALTER TABLE "core_apis" DROP COLUMN IF EXISTS "related_document_code";
    """
