"""付款申请明细带来源物料快照：品名、规格、数量。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_payment_application_lines"
            ADD COLUMN IF NOT EXISTS "material_name" VARCHAR(200);
        ALTER TABLE "apps_kuaizhizao_payment_application_lines"
            ADD COLUMN IF NOT EXISTS "material_spec" VARCHAR(200);
        ALTER TABLE "apps_kuaizhizao_payment_application_lines"
            ADD COLUMN IF NOT EXISTS "quantity" DECIMAL(16,4);
        ALTER TABLE "apps_kuaizhizao_payment_application_lines"
            ADD COLUMN IF NOT EXISTS "material_unit" VARCHAR(20);
        ALTER TABLE "apps_kuaizhizao_payment_application_lines"
            ADD COLUMN IF NOT EXISTS "source_line_id" INT;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_payment_application_lines" DROP COLUMN IF EXISTS "source_line_id";
        ALTER TABLE "apps_kuaizhizao_payment_application_lines" DROP COLUMN IF EXISTS "material_unit";
        ALTER TABLE "apps_kuaizhizao_payment_application_lines" DROP COLUMN IF EXISTS "quantity";
        ALTER TABLE "apps_kuaizhizao_payment_application_lines" DROP COLUMN IF EXISTS "material_spec";
        ALTER TABLE "apps_kuaizhizao_payment_application_lines" DROP COLUMN IF EXISTS "material_name";
    """
