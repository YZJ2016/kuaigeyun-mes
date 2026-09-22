"""轻办公月度考勤表。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaioa_attendance_sheets" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "sheet_code" VARCHAR(50) NOT NULL,
            "year_month" VARCHAR(7) NOT NULL,
            "workshop_name" VARCHAR(100) NOT NULL,
            "production_line_name" VARCHAR(100),
            "has_night" BOOLEAN NOT NULL DEFAULT FALSE,
            "standard_hours" NUMERIC(6,2) NOT NULL DEFAULT 8,
            "status" VARCHAR(20) NOT NULL DEFAULT 'draft',
            "submitted_at" TIMESTAMPTZ,
            "submitted_by" INT,
            "submitted_by_name" VARCHAR(100),
            "notes" TEXT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaioa_att_sheet_code"
            ON "apps_kuaioa_attendance_sheets" ("tenant_id", "sheet_code")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_att_sheet_ym"
            ON "apps_kuaioa_attendance_sheets" ("tenant_id", "year_month");
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_att_sheet_ws"
            ON "apps_kuaioa_attendance_sheets" ("tenant_id", "workshop_name");

        CREATE TABLE IF NOT EXISTS "apps_kuaioa_attendance_days" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "sheet_id" INT NOT NULL,
            "employee_id" INT NOT NULL,
            "employee_code" VARCHAR(50),
            "employee_name" VARCHAR(100) NOT NULL,
            "work_date" DATE NOT NULL,
            "regular_hours" NUMERIC(6,2) NOT NULL DEFAULT 8,
            "ot_hours" NUMERIC(6,2) NOT NULL DEFAULT 0,
            "mark" VARCHAR(20) NOT NULL DEFAULT 'normal',
            "is_night" BOOLEAN NOT NULL DEFAULT FALSE,
            "leave_deduct_amount" NUMERIC(12,2),
            "leave_request_id" INT,
            "notes" TEXT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaioa_att_day_cell"
            ON "apps_kuaioa_attendance_days"
            ("tenant_id", "sheet_id", "employee_id", "work_date")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_att_day_sheet"
            ON "apps_kuaioa_attendance_days" ("tenant_id", "sheet_id");
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_att_day_emp"
            ON "apps_kuaioa_attendance_days" ("tenant_id", "employee_id", "work_date");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaioa_attendance_days";
        DROP TABLE IF EXISTS "apps_kuaioa_attendance_sheets";
    """
