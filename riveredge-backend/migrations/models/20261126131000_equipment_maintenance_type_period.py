"""设备保养方案维护类型：小修/中修/大修改为月度/季度/半年度/年度体系。

真源：apps.kuaizhizao.constants.maintenance_scheme
历史维修档位回填：小修→月度、中修→季度、大修→年度（方案与计划快照同步）。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_equipment_maintenance_schemes"
            SET "maintenance_type" = '月度'
            WHERE "maintenance_type" = '小修';
        UPDATE "apps_kuaizhizao_equipment_maintenance_schemes"
            SET "maintenance_type" = '季度'
            WHERE "maintenance_type" = '中修';
        UPDATE "apps_kuaizhizao_equipment_maintenance_schemes"
            SET "maintenance_type" = '年度'
            WHERE "maintenance_type" = '大修';

        UPDATE "apps_kuaizhizao_maintenance_plans"
            SET "maintenance_type" = '月度'
            WHERE "maintenance_type" = '小修';
        UPDATE "apps_kuaizhizao_maintenance_plans"
            SET "maintenance_type" = '季度'
            WHERE "maintenance_type" = '中修';
        UPDATE "apps_kuaizhizao_maintenance_plans"
            SET "maintenance_type" = '年度'
            WHERE "maintenance_type" = '大修';

        COMMENT ON COLUMN "apps_kuaizhizao_equipment_maintenance_schemes"."maintenance_type"
            IS '维护类型（日常保养、月度、季度、半年度、年度）';
        COMMENT ON COLUMN "apps_kuaizhizao_maintenance_plans"."maintenance_type"
            IS '维护类型快照（日常保养、月度、季度、半年度、年度；来自保养方案）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_equipment_maintenance_schemes"
            SET "maintenance_type" = '小修'
            WHERE "maintenance_type" = '月度';
        UPDATE "apps_kuaizhizao_equipment_maintenance_schemes"
            SET "maintenance_type" = '中修'
            WHERE "maintenance_type" = '季度';
        UPDATE "apps_kuaizhizao_equipment_maintenance_schemes"
            SET "maintenance_type" = '大修'
            WHERE "maintenance_type" = '年度';

        UPDATE "apps_kuaizhizao_maintenance_plans"
            SET "maintenance_type" = '小修'
            WHERE "maintenance_type" = '月度';
        UPDATE "apps_kuaizhizao_maintenance_plans"
            SET "maintenance_type" = '中修'
            WHERE "maintenance_type" = '季度';
        UPDATE "apps_kuaizhizao_maintenance_plans"
            SET "maintenance_type" = '大修'
            WHERE "maintenance_type" = '年度';

        COMMENT ON COLUMN "apps_kuaizhizao_equipment_maintenance_schemes"."maintenance_type"
            IS '维护类型（日常保养、小修、中修、大修）';
        COMMENT ON COLUMN "apps_kuaizhizao_maintenance_plans"."maintenance_type"
            IS '维护类型（日常保养、小修、中修、大修）';
    """

# 对应上游 1005_20261107220000_equipment_maintenance_type_period.py
