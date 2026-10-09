"""L52 例试委托：待提交实验室状态、结构/电子分区、经理指定、下发时刻。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaiplm_lab_requests"
    ADD COLUMN IF NOT EXISTS "structure_special_test" TEXT;
ALTER TABLE "apps_kuaiplm_lab_requests"
    ADD COLUMN IF NOT EXISTS "structure_section_attachments" JSONB;
ALTER TABLE "apps_kuaiplm_lab_requests"
    ADD COLUMN IF NOT EXISTS "structure_section_status" VARCHAR(20) NOT NULL DEFAULT 'draft';
ALTER TABLE "apps_kuaiplm_lab_requests"
    ADD COLUMN IF NOT EXISTS "electronics_special_test" TEXT;
ALTER TABLE "apps_kuaiplm_lab_requests"
    ADD COLUMN IF NOT EXISTS "electronics_section_attachments" JSONB;
ALTER TABLE "apps_kuaiplm_lab_requests"
    ADD COLUMN IF NOT EXISTS "electronics_section_status" VARCHAR(20) NOT NULL DEFAULT 'draft';
ALTER TABLE "apps_kuaiplm_lab_requests"
    ADD COLUMN IF NOT EXISTS "structure_manager_user_id" INT;
ALTER TABLE "apps_kuaiplm_lab_requests"
    ADD COLUMN IF NOT EXISTS "electronics_manager_user_id" INT;
ALTER TABLE "apps_kuaiplm_lab_requests"
    ADD COLUMN IF NOT EXISTS "notify_user_ids" JSONB;
ALTER TABLE "apps_kuaiplm_lab_requests"
    ADD COLUMN IF NOT EXISTS "dispatched_at" TIMESTAMPTZ;
ALTER TABLE "apps_kuaiplm_lab_requests"
    ADD COLUMN IF NOT EXISTS "dispatched_by" INT;
ALTER TABLE "apps_kuaiplm_lab_requests"
    ADD COLUMN IF NOT EXISTS "dispatched_by_name" VARCHAR(100);

UPDATE "apps_kuaiplm_lab_requests"
SET "structure_special_test" = COALESCE(
        "structure_special_test",
        NULLIF(TRIM("extension_payload"->>'structure_special_test'), '')
    ),
    "electronics_special_test" = COALESCE(
        "electronics_special_test",
        NULLIF(TRIM("extension_payload"->>'electronics_special_test'), '')
    )
WHERE "business_type" = 'project_product'
  AND "extension_payload" IS NOT NULL;
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaiplm_lab_requests" DROP COLUMN IF EXISTS "dispatched_by_name";
ALTER TABLE "apps_kuaiplm_lab_requests" DROP COLUMN IF EXISTS "dispatched_by";
ALTER TABLE "apps_kuaiplm_lab_requests" DROP COLUMN IF EXISTS "dispatched_at";
ALTER TABLE "apps_kuaiplm_lab_requests" DROP COLUMN IF EXISTS "notify_user_ids";
ALTER TABLE "apps_kuaiplm_lab_requests" DROP COLUMN IF EXISTS "electronics_manager_user_id";
ALTER TABLE "apps_kuaiplm_lab_requests" DROP COLUMN IF EXISTS "structure_manager_user_id";
ALTER TABLE "apps_kuaiplm_lab_requests" DROP COLUMN IF EXISTS "electronics_section_status";
ALTER TABLE "apps_kuaiplm_lab_requests" DROP COLUMN IF EXISTS "electronics_section_attachments";
ALTER TABLE "apps_kuaiplm_lab_requests" DROP COLUMN IF EXISTS "electronics_special_test";
ALTER TABLE "apps_kuaiplm_lab_requests" DROP COLUMN IF EXISTS "structure_section_status";
ALTER TABLE "apps_kuaiplm_lab_requests" DROP COLUMN IF EXISTS "structure_section_attachments";
ALTER TABLE "apps_kuaiplm_lab_requests" DROP COLUMN IF EXISTS "structure_special_test";
"""
