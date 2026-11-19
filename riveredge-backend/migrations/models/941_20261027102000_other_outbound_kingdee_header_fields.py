"""其他出库单金蝶外推表头字段（领用部门、领用人、客户）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_other_outbounds"
            ADD COLUMN IF NOT EXISTS "pick_department_id" INT,
            ADD COLUMN IF NOT EXISTS "pick_department_code" VARCHAR(64),
            ADD COLUMN IF NOT EXISTS "pick_department_name" VARCHAR(100),
            ADD COLUMN IF NOT EXISTS "picker_id" INT,
            ADD COLUMN IF NOT EXISTS "picker_name" VARCHAR(100),
            ADD COLUMN IF NOT EXISTS "picker_operator_number" VARCHAR(64),
            ADD COLUMN IF NOT EXISTS "customer_id" INT,
            ADD COLUMN IF NOT EXISTS "customer_name" VARCHAR(200),
            ADD COLUMN IF NOT EXISTS "customer_number" VARCHAR(64);
        COMMENT ON COLUMN "apps_kuaizhizao_other_outbounds"."pick_department_code"
            IS '金蝶领用部门编码 pickdept_number';
        COMMENT ON COLUMN "apps_kuaizhizao_other_outbounds"."picker_operator_number"
            IS '金蝶领用人工号 pickeroperator_number';
        COMMENT ON COLUMN "apps_kuaizhizao_other_outbounds"."customer_number"
            IS '金蝶客户编码 customer_number（客户领用场景）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_other_outbounds"
            DROP COLUMN IF EXISTS "pick_department_id",
            DROP COLUMN IF EXISTS "pick_department_code",
            DROP COLUMN IF EXISTS "pick_department_name",
            DROP COLUMN IF EXISTS "picker_id",
            DROP COLUMN IF EXISTS "picker_name",
            DROP COLUMN IF EXISTS "picker_operator_number",
            DROP COLUMN IF EXISTS "customer_id",
            DROP COLUMN IF EXISTS "customer_name",
            DROP COLUMN IF EXISTS "customer_number";
    """
