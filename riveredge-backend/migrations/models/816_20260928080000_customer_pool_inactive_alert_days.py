from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_customer_pool_rules"
            ADD COLUMN IF NOT EXISTS "inactive_alert_days" INT NOT NULL DEFAULT 7;
        COMMENT ON COLUMN "apps_kuaizhizao_customer_pool_rules"."inactive_alert_days"
            IS '未联系提醒天数（列表徽章/筛选）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_customer_pool_rules"
            DROP COLUMN IF EXISTS "inactive_alert_days";
    """
