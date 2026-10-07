"""研发交付物：project_id 可空 + project_code 快照（无项目直管）。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaiplm_rd_project_deliverables"
    ADD COLUMN IF NOT EXISTS "project_code" VARCHAR(50);
ALTER TABLE "apps_kuaiplm_rd_project_deliverables"
    ALTER COLUMN "project_id" DROP NOT NULL;
ALTER TABLE "apps_kuaiplm_rd_project_deliverable_versions"
    ALTER COLUMN "project_id" DROP NOT NULL;
UPDATE "apps_kuaiplm_rd_project_deliverables" AS d
SET "project_code" = p."project_code"
FROM "apps_kuaiplm_rd_projects" AS p
WHERE d."project_id" = p."id"
  AND (d."project_code" IS NULL OR d."project_code" = '');
CREATE INDEX IF NOT EXISTS "idx_apps_kuaiplm_rd_project_deliverables_tenant_id_deliverable_type"
    ON "apps_kuaiplm_rd_project_deliverables" ("tenant_id", "deliverable_type");
CREATE INDEX IF NOT EXISTS "idx_apps_kuaiplm_rd_project_deliverables_tenant_id_material_code"
    ON "apps_kuaiplm_rd_project_deliverables" ("tenant_id", "material_code");
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP INDEX IF EXISTS "idx_apps_kuaiplm_rd_project_deliverables_tenant_id_material_code";
DROP INDEX IF EXISTS "idx_apps_kuaiplm_rd_project_deliverables_tenant_id_deliverable_type";
ALTER TABLE "apps_kuaiplm_rd_project_deliverables"
    DROP COLUMN IF EXISTS "project_code";
"""
