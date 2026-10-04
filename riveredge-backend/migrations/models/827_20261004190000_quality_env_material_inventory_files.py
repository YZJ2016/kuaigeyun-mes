"""环保资料补物料与材料说明；库存验证返工补年度计划与月汇总附件。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_supplier_eval_env_docs"
            ADD COLUMN IF NOT EXISTS "material_id" INT,
            ADD COLUMN IF NOT EXISTS "material_code" VARCHAR(50),
            ADD COLUMN IF NOT EXISTS "material_name" VARCHAR(200),
            ADD COLUMN IF NOT EXISTS "material_description" TEXT;
        CREATE INDEX IF NOT EXISTS "idx_kuaizhizao_env_doc_material"
            ON "apps_kuaizhizao_supplier_eval_env_docs" ("tenant_id", "material_id");

        ALTER TABLE "apps_kuaizhizao_rework_orders"
            ADD COLUMN IF NOT EXISTS "inventory_annual_plan" JSONB,
            ADD COLUMN IF NOT EXISTS "inventory_monthly_summary" JSONB;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_kuaizhizao_env_doc_material";
        ALTER TABLE "apps_kuaizhizao_supplier_eval_env_docs"
            DROP COLUMN IF EXISTS "material_description",
            DROP COLUMN IF EXISTS "material_name",
            DROP COLUMN IF EXISTS "material_code",
            DROP COLUMN IF EXISTS "material_id";
        ALTER TABLE "apps_kuaizhizao_rework_orders"
            DROP COLUMN IF EXISTS "inventory_monthly_summary",
            DROP COLUMN IF EXISTS "inventory_annual_plan";
    """
