"""需方表补齐 BaseModel.uuid（899 建表时遗漏，ORM 查询会选该列）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_demand_parties"
            ADD COLUMN IF NOT EXISTS "uuid" VARCHAR(36);
        UPDATE "apps_kuaizhizao_purchase_demand_parties"
            SET "uuid" = gen_random_uuid()::text
            WHERE "uuid" IS NULL OR "uuid" = '';
        ALTER TABLE "apps_kuaizhizao_purchase_demand_parties"
            ALTER COLUMN "uuid" SET NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_purchase_demand_parties_uuid"
            ON "apps_kuaizhizao_purchase_demand_parties" ("uuid");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uid_purchase_demand_parties_uuid";
        ALTER TABLE "apps_kuaizhizao_purchase_demand_parties"
            DROP COLUMN IF EXISTS "uuid";
    """
