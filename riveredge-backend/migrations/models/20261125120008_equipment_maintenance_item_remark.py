"""设备保养项 / 保养方案行增加备注字段。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_equipment_maintenance_items"
            ADD COLUMN IF NOT EXISTS "remark" TEXT;
        COMMENT ON COLUMN "apps_kuaizhizao_equipment_maintenance_items"."remark"
            IS '备注';

        ALTER TABLE "apps_kuaizhizao_equipment_maintenance_scheme_lines"
            ADD COLUMN IF NOT EXISTS "remark" TEXT;
        COMMENT ON COLUMN "apps_kuaizhizao_equipment_maintenance_scheme_lines"."remark"
            IS '备注快照（来自保养项）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_equipment_maintenance_scheme_lines"
            DROP COLUMN IF EXISTS "remark";
        ALTER TABLE "apps_kuaizhizao_equipment_maintenance_items"
            DROP COLUMN IF EXISTS "remark";
    """
