"""研发交付物：下发时间与下发对象 grant（L53 #59）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaiplm_rd_project_deliverables"
    ADD COLUMN IF NOT EXISTS "issued_at" TIMESTAMPTZ;
ALTER TABLE "apps_kuaiplm_rd_project_deliverables"
    ADD COLUMN IF NOT EXISTS "issued_by" INT;
ALTER TABLE "apps_kuaiplm_rd_project_deliverables"
    ADD COLUMN IF NOT EXISTS "issued_by_name" VARCHAR(100);

CREATE TABLE IF NOT EXISTS "apps_kuaiplm_rd_project_deliverable_issue_grants" (
    "id" SERIAL PRIMARY KEY,
    "uuid" VARCHAR(36) NOT NULL UNIQUE,
    "tenant_id" INT NOT NULL,
    "deliverable_id" INT NOT NULL,
    "target_type" VARCHAR(20) NOT NULL,
    "target_id" INT NOT NULL,
    "target_label" VARCHAR(200),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "deleted_at" TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS "idx_rd_deliv_issue_grants_tenant_deliverable"
    ON "apps_kuaiplm_rd_project_deliverable_issue_grants" ("tenant_id", "deliverable_id");
CREATE INDEX IF NOT EXISTS "idx_rd_deliv_issue_grants_tenant_target"
    ON "apps_kuaiplm_rd_project_deliverable_issue_grants" ("tenant_id", "target_type", "target_id");
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP TABLE IF EXISTS "apps_kuaiplm_rd_project_deliverable_issue_grants";
ALTER TABLE "apps_kuaiplm_rd_project_deliverables"
    DROP COLUMN IF EXISTS "issued_by_name";
ALTER TABLE "apps_kuaiplm_rd_project_deliverables"
    DROP COLUMN IF EXISTS "issued_by";
ALTER TABLE "apps_kuaiplm_rd_project_deliverables"
    DROP COLUMN IF EXISTS "issued_at";
"""
