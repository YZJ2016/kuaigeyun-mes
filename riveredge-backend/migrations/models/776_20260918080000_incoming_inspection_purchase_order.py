from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_incoming_inspections"
    ADD COLUMN IF NOT EXISTS "purchase_order_id" INT,
    ADD COLUMN IF NOT EXISTS "purchase_order_code" VARCHAR(50);

COMMENT ON COLUMN "apps_kuaizhizao_incoming_inspections"."purchase_order_id" IS '采购订单ID（从来料前下推）';
COMMENT ON COLUMN "apps_kuaizhizao_incoming_inspections"."purchase_order_code" IS '采购订单编码';

CREATE INDEX IF NOT EXISTS "idx_incoming_insp_po"
    ON "apps_kuaizhizao_incoming_inspections" ("tenant_id", "purchase_order_id")
    WHERE "deleted_at" IS NULL AND "purchase_order_id" IS NOT NULL;
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP INDEX IF EXISTS "idx_incoming_insp_po";
ALTER TABLE "apps_kuaizhizao_incoming_inspections"
    DROP COLUMN IF EXISTS "purchase_order_code",
    DROP COLUMN IF EXISTS "purchase_order_id";
"""
