"""轻办公每日考勤登记记录。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaioa_daily_attendance_records" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "employee_id" INT,
            "employee_code" VARCHAR(50),
            "employee_name" VARCHAR(100) NOT NULL,
            "department_name" VARCHAR(100),
            "work_date" DATE NOT NULL,
            "clock_in_1" VARCHAR(16),
            "clock_out_1" VARCHAR(16),
            "clock_in_2" VARCHAR(16),
            "clock_out_2" VARCHAR(16),
            "clock_in_3" VARCHAR(16),
            "clock_out_3" VARCHAR(16),
            "result" VARCHAR(50),
            "expected_hours" NUMERIC(8,2),
            "paid_hours" NUMERIC(8,2),
            "actual_hours" NUMERIC(8,2),
            "late_minutes" INT,
            "early_leave_minutes" INT,
            "ot_hours" NUMERIC(8,2),
            "notes" TEXT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaioa_daily_att_emp_date"
            ON "apps_kuaioa_daily_attendance_records" ("tenant_id", "employee_id", "work_date")
            WHERE "deleted_at" IS NULL AND "employee_id" IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaioa_daily_att_code_date"
            ON "apps_kuaioa_daily_attendance_records" ("tenant_id", "employee_code", "work_date")
            WHERE "deleted_at" IS NULL AND "employee_code" IS NOT NULL AND "employee_id" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_daily_att_date"
            ON "apps_kuaioa_daily_attendance_records" ("tenant_id", "work_date");
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_daily_att_dept"
            ON "apps_kuaioa_daily_attendance_records" ("tenant_id", "department_name");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaioa_daily_attendance_records";
    """
