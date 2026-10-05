"""自动报工：报工记录类型/产线，绑定表产线与当前产品。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_reporting_records"
            ADD COLUMN IF NOT EXISTS "origin" VARCHAR(20);
        ALTER TABLE "apps_kuaizhizao_reporting_records"
            ADD COLUMN IF NOT EXISTS "production_line_id" INT;
        ALTER TABLE "apps_kuaizhizao_reporting_records"
            ADD COLUMN IF NOT EXISTS "production_line_code" VARCHAR(50);
        ALTER TABLE "apps_kuaizhizao_reporting_records"
            ADD COLUMN IF NOT EXISTS "production_line_name" VARCHAR(200);
        COMMENT ON COLUMN "apps_kuaizhizao_reporting_records"."origin" IS '报工类型：manual | auto';
        COMMENT ON COLUMN "apps_kuaizhizao_reporting_records"."production_line_id" IS '数量来源产线 ID';
        COMMENT ON COLUMN "apps_kuaizhizao_reporting_records"."production_line_code" IS '数量来源产线编码';
        COMMENT ON COLUMN "apps_kuaizhizao_reporting_records"."production_line_name" IS '数量来源产线名称';

        ALTER TABLE "apps_ind_relay_auto_report_bindings"
            ADD COLUMN IF NOT EXISTS "production_line_id" INT;
        ALTER TABLE "apps_ind_relay_auto_report_bindings"
            ADD COLUMN IF NOT EXISTS "production_line_code" VARCHAR(50);
        ALTER TABLE "apps_ind_relay_auto_report_bindings"
            ADD COLUMN IF NOT EXISTS "production_line_name" VARCHAR(200);
        ALTER TABLE "apps_ind_relay_auto_report_bindings"
            ADD COLUMN IF NOT EXISTS "bound_product_id" INT;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_reporting_records" DROP COLUMN IF EXISTS "origin";
        ALTER TABLE "apps_kuaizhizao_reporting_records" DROP COLUMN IF EXISTS "production_line_id";
        ALTER TABLE "apps_kuaizhizao_reporting_records" DROP COLUMN IF EXISTS "production_line_code";
        ALTER TABLE "apps_kuaizhizao_reporting_records" DROP COLUMN IF EXISTS "production_line_name";
        ALTER TABLE "apps_ind_relay_auto_report_bindings" DROP COLUMN IF EXISTS "production_line_id";
        ALTER TABLE "apps_ind_relay_auto_report_bindings" DROP COLUMN IF EXISTS "production_line_code";
        ALTER TABLE "apps_ind_relay_auto_report_bindings" DROP COLUMN IF EXISTS "production_line_name";
        ALTER TABLE "apps_ind_relay_auto_report_bindings" DROP COLUMN IF EXISTS "bound_product_id";
    """
