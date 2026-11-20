"""往来对账单接入审核流程：增加 review_status 与审核人字段。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_partner_statements"
            ADD COLUMN IF NOT EXISTS "review_status" VARCHAR(20) DEFAULT '草稿';
        ALTER TABLE "apps_kuaicaiwu_partner_statements"
            ADD COLUMN IF NOT EXISTS "reviewer_id" INT;
        ALTER TABLE "apps_kuaicaiwu_partner_statements"
            ADD COLUMN IF NOT EXISTS "reviewer_name" VARCHAR(100);
        ALTER TABLE "apps_kuaicaiwu_partner_statements"
            ADD COLUMN IF NOT EXISTS "review_time" TIMESTAMPTZ;
        ALTER TABLE "apps_kuaicaiwu_partner_statements"
            ADD COLUMN IF NOT EXISTS "review_remarks" TEXT;
        UPDATE "apps_kuaicaiwu_partner_statements"
           SET "review_status" = '已审核'
         WHERE "deleted_at" IS NULL
           AND "status" IN ('Confirmed', 'Sent', 'LedgerPosted', 'Disputed')
           AND COALESCE("review_status", '') IN ('', '草稿');
        UPDATE "apps_kuaicaiwu_partner_statements"
           SET "review_status" = '草稿'
         WHERE "deleted_at" IS NULL
           AND ("review_status" IS NULL OR "review_status" = '');
        CREATE INDEX IF NOT EXISTS "idx_kz_ps_tenant_review"
            ON "apps_kuaicaiwu_partner_statements" ("tenant_id", "review_status");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_kz_ps_tenant_review";
        ALTER TABLE "apps_kuaicaiwu_partner_statements" DROP COLUMN IF EXISTS "review_remarks";
        ALTER TABLE "apps_kuaicaiwu_partner_statements" DROP COLUMN IF EXISTS "review_time";
        ALTER TABLE "apps_kuaicaiwu_partner_statements" DROP COLUMN IF EXISTS "reviewer_name";
        ALTER TABLE "apps_kuaicaiwu_partner_statements" DROP COLUMN IF EXISTS "reviewer_id";
        ALTER TABLE "apps_kuaicaiwu_partner_statements" DROP COLUMN IF EXISTS "review_status";
    """
