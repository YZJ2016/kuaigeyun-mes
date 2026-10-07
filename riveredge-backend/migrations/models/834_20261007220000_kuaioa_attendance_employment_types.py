"""月度考勤单 / 休息夜班登记：用工类型多选。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_attendance_sheets"
            ADD COLUMN IF NOT EXISTS "employment_types" JSONB NOT NULL DEFAULT '[]'::jsonb;

        ALTER TABLE "apps_kuaioa_attendance_day_registers"
            ADD COLUMN IF NOT EXISTS "employment_types" JSONB NOT NULL DEFAULT '[]'::jsonb;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_attendance_sheets"
            DROP COLUMN IF EXISTS "employment_types";

        ALTER TABLE "apps_kuaioa_attendance_day_registers"
            DROP COLUMN IF EXISTS "employment_types";
    """
