"""8D 协同：阶段指派、行动项、coordination_mode。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_quality_8d_reports"
        ADD COLUMN IF NOT EXISTS "coordination_mode" VARCHAR(20) NOT NULL DEFAULT 'legacy';

        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_quality_8d_stage_assignments" (
            "id" SERIAL PRIMARY KEY,
            "uuid" UUID NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "report_id" INT NOT NULL,
            "stage_key" VARCHAR(30) NOT NULL,
            "assignee_user_id" INT,
            "assignee_name" VARCHAR(100),
            "due_date" TIMESTAMPTZ,
            "status" VARCHAR(20) NOT NULL DEFAULT 'pending',
            "submitted_at" TIMESTAMPTZ,
            "approved_at" TIMESTAMPTZ,
            "approved_by" INT,
            "approved_by_name" VARCHAR(100),
            CONSTRAINT "uid_8d_stage_assign_t_r_s" UNIQUE ("tenant_id", "report_id", "stage_key")
        );
        CREATE INDEX IF NOT EXISTS "idx_8d_stage_assign_tenant" ON "apps_kuaizhizao_quality_8d_stage_assignments" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_8d_stage_assign_report" ON "apps_kuaizhizao_quality_8d_stage_assignments" ("report_id");
        CREATE INDEX IF NOT EXISTS "idx_8d_stage_assign_user" ON "apps_kuaizhizao_quality_8d_stage_assignments" ("assignee_user_id");

        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_quality_8d_action_items" (
            "id" SERIAL PRIMARY KEY,
            "uuid" UUID NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "report_id" INT NOT NULL,
            "discipline" VARCHAR(30) NOT NULL,
            "title" VARCHAR(200) NOT NULL,
            "description" TEXT,
            "assignee_user_id" INT,
            "assignee_name" VARCHAR(100),
            "due_date" TIMESTAMPTZ,
            "status" VARCHAR(20) NOT NULL DEFAULT 'open',
            "sort_order" INT NOT NULL DEFAULT 0,
            "evidence_attachments" JSONB,
            "completed_at" TIMESTAMPTZ,
            "verified_by" INT,
            "verified_by_name" VARCHAR(100),
            "verified_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_8d_action_tenant" ON "apps_kuaizhizao_quality_8d_action_items" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_8d_action_report" ON "apps_kuaizhizao_quality_8d_action_items" ("report_id");
        CREATE INDEX IF NOT EXISTS "idx_8d_action_user" ON "apps_kuaizhizao_quality_8d_action_items" ("assignee_user_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaizhizao_quality_8d_action_items";
        DROP TABLE IF EXISTS "apps_kuaizhizao_quality_8d_stage_assignments";
        ALTER TABLE "apps_kuaizhizao_quality_8d_reports" DROP COLUMN IF EXISTS "coordination_mode";
    """
