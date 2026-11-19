"""Declare the personnel number already consumed by document push services."""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "core_users"
            ADD COLUMN IF NOT EXISTS "employee_number" VARCHAR(50);
        COMMENT ON COLUMN "core_users"."employee_number"
            IS '人员工号（租户内唯一，外推人员标识真源）';
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_core_users_tenant_employee_number"
            ON "core_users" ("tenant_id", "employee_number")
            WHERE "employee_number" IS NOT NULL AND "deleted_at" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uid_core_users_tenant_employee_number";
        ALTER TABLE "core_users" DROP COLUMN IF EXISTS "employee_number";
    """
