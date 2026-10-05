"""班次增加午休时段；工作日历窗口来源统一为按班次。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_shifts"
            ADD COLUMN IF NOT EXISTS "break_start" TIME;
        ALTER TABLE "apps_master_data_shifts"
            ADD COLUMN IF NOT EXISTS "break_end" TIME;
        COMMENT ON COLUMN "apps_master_data_shifts"."break_start" IS '中午休息开始时刻';
        COMMENT ON COLUMN "apps_master_data_shifts"."break_end" IS '中午休息结束时刻';

        UPDATE "apps_master_data_work_calendar_configs"
           SET "window_source" = 'shift'
         WHERE "deleted_at" IS NULL
           AND COALESCE("window_source", '') <> 'shift';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_shifts" DROP COLUMN IF EXISTS "break_end";
        ALTER TABLE "apps_master_data_shifts" DROP COLUMN IF EXISTS "break_start";
    """
