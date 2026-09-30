"""来料检验单挂可空委外收货，供必检收货在确认前关联检验单。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_incoming_inspections"
            ADD COLUMN IF NOT EXISTS "outsource_material_receipt_id" INT;
        ALTER TABLE "apps_kuaizhizao_incoming_inspections"
            ADD COLUMN IF NOT EXISTS "outsource_material_receipt_code" VARCHAR(50);
        COMMENT ON COLUMN "apps_kuaizhizao_incoming_inspections"."outsource_material_receipt_id" IS '委外收货单ID';
        COMMENT ON COLUMN "apps_kuaizhizao_incoming_inspections"."outsource_material_receipt_code" IS '委外收货单编码';
        CREATE INDEX IF NOT EXISTS "idx_iqc_outsource_material_receipt"
            ON "apps_kuaizhizao_incoming_inspections" ("tenant_id", "outsource_material_receipt_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_iqc_outsource_material_receipt";
        ALTER TABLE "apps_kuaizhizao_incoming_inspections"
            DROP COLUMN IF EXISTS "outsource_material_receipt_code";
        ALTER TABLE "apps_kuaizhizao_incoming_inspections"
            DROP COLUMN IF EXISTS "outsource_material_receipt_id";
    """
