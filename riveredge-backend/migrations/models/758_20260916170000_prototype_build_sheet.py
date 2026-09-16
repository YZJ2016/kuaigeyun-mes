"""样机制作书（研发项目 §2.15）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaiplm_prototype_build_sheets" (
            "id" SERIAL PRIMARY KEY,
            "uuid" UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "tenant_id" INT NOT NULL,
            "sheet_code" VARCHAR(50) NOT NULL,
            "project_id" INT NOT NULL,
            "project_code" VARCHAR(50) NOT NULL,
            "project_name" VARCHAR(200) NOT NULL,
            "round_key" VARCHAR(20) NOT NULL DEFAULT 't1',
            "title" VARCHAR(200) NOT NULL,
            "status" VARCHAR(20) NOT NULL DEFAULT 'draft',
            "project_requirements" TEXT,
            "project_attachments" JSONB NOT NULL DEFAULT '[]',
            "electronics_requirements" TEXT,
            "electronics_attachments" JSONB NOT NULL DEFAULT '[]',
            "electronics_status" VARCHAR(20) NOT NULL DEFAULT 'draft',
            "structure_requirements" TEXT,
            "structure_attachments" JSONB NOT NULL DEFAULT '[]',
            "structure_status" VARCHAR(20) NOT NULL DEFAULT 'draft',
            "manufacturing_opinion" TEXT,
            "quality_opinion" TEXT,
            "remarks" TEXT,
            "submitted_at" TIMESTAMPTZ,
            "approved_at" TIMESTAMPTZ,
            "issued_at" TIMESTAMPTZ,
            "closed_at" TIMESTAMPTZ,
            "deleted_at" TIMESTAMPTZ,
            CONSTRAINT "uid_apps_kuaiplm_prototype_build_sheets_tenant_code"
                UNIQUE ("tenant_id", "sheet_code")
        );
        CREATE INDEX IF NOT EXISTS "idx_prototype_build_sheets_tenant_project"
            ON "apps_kuaiplm_prototype_build_sheets" ("tenant_id", "project_id");
        CREATE INDEX IF NOT EXISTS "idx_prototype_build_sheets_tenant_status"
            ON "apps_kuaiplm_prototype_build_sheets" ("tenant_id", "status");
        CREATE INDEX IF NOT EXISTS "idx_prototype_build_sheets_tenant_round"
            ON "apps_kuaiplm_prototype_build_sheets" ("tenant_id", "round_key");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaiplm_prototype_build_sheets";
    """
