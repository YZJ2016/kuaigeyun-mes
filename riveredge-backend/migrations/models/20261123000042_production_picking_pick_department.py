"""生产领料单增加领用部门字段。

上游同步：985_20261102224500_production_picking_pick_department
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_production_pickings"
            ADD COLUMN IF NOT EXISTS "pick_department_id" INT,
            ADD COLUMN IF NOT EXISTS "pick_department_code" VARCHAR(64),
            ADD COLUMN IF NOT EXISTS "pick_department_name" VARCHAR(100);
        COMMENT ON COLUMN "apps_kuaizhizao_production_pickings"."pick_department_id" IS '领用部门ID';
        COMMENT ON COLUMN "apps_kuaizhizao_production_pickings"."pick_department_code" IS '领用部门编码';
        COMMENT ON COLUMN "apps_kuaizhizao_production_pickings"."pick_department_name" IS '领用部门名称';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_production_pickings"
            DROP COLUMN IF EXISTS "pick_department_id",
            DROP COLUMN IF EXISTS "pick_department_code",
            DROP COLUMN IF EXISTS "pick_department_name";
    """
