"""最低工资配置：执行结束日期、当前执行标记；已有最新一条标为当前执行。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_minimum_wage_configs"
            ADD COLUMN IF NOT EXISTS "end_date" DATE;
        ALTER TABLE "apps_kuaioa_minimum_wage_configs"
            ADD COLUMN IF NOT EXISTS "is_current" BOOL NOT NULL DEFAULT FALSE;
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_min_wage_tenant_current"
            ON "apps_kuaioa_minimum_wage_configs" ("tenant_id", "is_current");
        UPDATE "apps_kuaioa_minimum_wage_configs" AS cfg
        SET "is_current" = TRUE
        WHERE cfg."deleted_at" IS NULL
          AND cfg."id" = (
            SELECT c2."id"
            FROM "apps_kuaioa_minimum_wage_configs" AS c2
            WHERE c2."tenant_id" = cfg."tenant_id"
              AND c2."deleted_at" IS NULL
            ORDER BY c2."effective_date" DESC, c2."id" DESC
            LIMIT 1
          );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_kuaioa_min_wage_tenant_current";
        ALTER TABLE "apps_kuaioa_minimum_wage_configs" DROP COLUMN IF EXISTS "is_current";
        ALTER TABLE "apps_kuaioa_minimum_wage_configs" DROP COLUMN IF EXISTS "end_date";
    """
