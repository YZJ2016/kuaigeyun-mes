"""
账户组织字段：工号、直接上级、人员类型/使用状态；兼职部门关联表。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "core_users"
        ADD COLUMN IF NOT EXISTS "employee_number" VARCHAR(50);
        COMMENT ON COLUMN "core_users"."employee_number"
            IS '金蝶人员工号（租户内唯一，外推 bizuser_number 真源）';

        ALTER TABLE "core_users"
        ADD COLUMN IF NOT EXISTS "supervisor_id" INT;
        COMMENT ON COLUMN "core_users"."supervisor_id"
            IS '直接上级用户 ID';

        ALTER TABLE "core_users"
        ADD COLUMN IF NOT EXISTS "person_category" VARCHAR(32);
        COMMENT ON COLUMN "core_users"."person_category"
            IS '人员类型（字典 user_person_category）';

        ALTER TABLE "core_users"
        ADD COLUMN IF NOT EXISTS "employment_status" VARCHAR(32);
        COMMENT ON COLUMN "core_users"."employment_status"
            IS '人员使用状态（字典 user_employment_status）';

        CREATE UNIQUE INDEX IF NOT EXISTS "uid_core_users_tenant_employee_number"
            ON "core_users" ("tenant_id", "employee_number")
            WHERE "employee_number" IS NOT NULL
              AND "deleted_at" IS NULL;

        CREATE INDEX IF NOT EXISTS "idx_core_users_supervisor_id"
            ON "core_users" ("supervisor_id");

        CREATE TABLE IF NOT EXISTS "core_user_department_assignments" (
            "id" SERIAL PRIMARY KEY,
            "uuid" UUID NOT NULL,
            "tenant_id" INT NOT NULL,
            "user_id" INT NOT NULL,
            "department_id" INT NOT NULL,
            "is_primary" BOOL NOT NULL DEFAULT FALSE,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "created_by" INT,
            "updated_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by_name" VARCHAR(100)
        );
        COMMENT ON TABLE "core_user_department_assignments" IS '用户部门任职（含兼职）';

        CREATE UNIQUE INDEX IF NOT EXISTS "uid_core_user_dept_assign_user_dept"
            ON "core_user_department_assignments" ("tenant_id", "user_id", "department_id");

        CREATE INDEX IF NOT EXISTS "idx_core_user_dept_assign_tenant_user"
            ON "core_user_department_assignments" ("tenant_id", "user_id");
        """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "core_user_department_assignments";
        DROP INDEX IF EXISTS "idx_core_users_supervisor_id";
        DROP INDEX IF EXISTS "uid_core_users_tenant_employee_number";
        ALTER TABLE "core_users" DROP COLUMN IF EXISTS "employment_status";
        ALTER TABLE "core_users" DROP COLUMN IF EXISTS "person_category";
        ALTER TABLE "core_users" DROP COLUMN IF EXISTS "supervisor_id";
        ALTER TABLE "core_users" DROP COLUMN IF EXISTS "employee_number";
        """
