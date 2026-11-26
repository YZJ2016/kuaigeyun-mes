"""
批号/序列号规则：租户级默认标记 is_default
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "core_batch_rules"
        ADD COLUMN IF NOT EXISTS "is_default" BOOLEAN NOT NULL DEFAULT FALSE;
        COMMENT ON COLUMN "core_batch_rules"."is_default" IS '租户未指定物料默认规则时，优先于系统内置 BATCH_DEFAULT 使用';

        ALTER TABLE "core_serial_rules"
        ADD COLUMN IF NOT EXISTS "is_default" BOOLEAN NOT NULL DEFAULT FALSE;
        COMMENT ON COLUMN "core_serial_rules"."is_default" IS '租户未指定物料默认规则时，优先于系统内置 SERIAL_DEFAULT 使用';

        CREATE INDEX IF NOT EXISTS "idx_core_batch_rules_tenant_default"
        ON "core_batch_rules" ("tenant_id", "is_default")
        WHERE "deleted_at" IS NULL AND "is_default" = TRUE;

        CREATE INDEX IF NOT EXISTS "idx_core_serial_rules_tenant_default"
        ON "core_serial_rules" ("tenant_id", "is_default")
        WHERE "deleted_at" IS NULL AND "is_default" = TRUE;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_core_serial_rules_tenant_default";
        DROP INDEX IF EXISTS "idx_core_batch_rules_tenant_default";
        ALTER TABLE "core_serial_rules" DROP COLUMN IF EXISTS "is_default";
        ALTER TABLE "core_batch_rules" DROP COLUMN IF EXISTS "is_default";
    """