"""客户回访增加状态字段：待登记 / 已完成。

下推生成的回访多为待登记；完成回访后写入已完成。
已有数据按是否已评满意度回填。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_customer_return_visits"
            ADD COLUMN IF NOT EXISTS "status" VARCHAR(20) NOT NULL DEFAULT '待登记';
        COMMENT ON COLUMN "apps_kuaizhizao_customer_return_visits"."status" IS '状态 待登记/已完成';
        UPDATE "apps_kuaizhizao_customer_return_visits"
           SET "status" = '已完成'
         WHERE "satisfaction_score" IS NOT NULL
           AND ("status" IS NULL OR "status" = '待登记');
        CREATE INDEX IF NOT EXISTS "idx_kz_return_visits_tenant_status"
            ON "apps_kuaizhizao_customer_return_visits" ("tenant_id", "status");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_kz_return_visits_tenant_status";
        ALTER TABLE "apps_kuaizhizao_customer_return_visits"
            DROP COLUMN IF EXISTS "status";
    """
