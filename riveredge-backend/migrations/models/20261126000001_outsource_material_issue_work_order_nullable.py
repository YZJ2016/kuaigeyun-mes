"""
委外发料单允许不挂委外工单：工序委外场景下 outsource_work_order_id/code 可空。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_outsource_material_issues"
            ALTER COLUMN "outsource_work_order_id" DROP NOT NULL;

        ALTER TABLE "apps_kuaizhizao_outsource_material_issues"
            ALTER COLUMN "outsource_work_order_code" DROP NOT NULL;

        COMMENT ON COLUMN "apps_kuaizhizao_outsource_material_issues"."outsource_work_order_id"
            IS '委外工单ID';
        COMMENT ON COLUMN "apps_kuaizhizao_outsource_material_issues"."outsource_work_order_code"
            IS '委外工单编码';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_outsource_material_issues"
        SET "outsource_work_order_id" = 0
        WHERE "outsource_work_order_id" IS NULL;

        UPDATE "apps_kuaizhizao_outsource_material_issues"
        SET "outsource_work_order_code" = ''
        WHERE "outsource_work_order_code" IS NULL;

        ALTER TABLE "apps_kuaizhizao_outsource_material_issues"
            ALTER COLUMN "outsource_work_order_id" SET NOT NULL;

        ALTER TABLE "apps_kuaizhizao_outsource_material_issues"
            ALTER COLUMN "outsource_work_order_code" SET NOT NULL;
    """
