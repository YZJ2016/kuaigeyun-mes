"""物料评审版次快照（L40 升版后可下载历史版）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaiplm_material_reviews"
            ADD COLUMN IF NOT EXISTS "revision_no" INT NOT NULL DEFAULT 1;

        CREATE TABLE IF NOT EXISTS "apps_kuaiplm_material_review_revisions" (
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL,
            "updated_at" TIMESTAMPTZ NOT NULL,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "id" SERIAL NOT NULL PRIMARY KEY,
            "review_id" INT NOT NULL,
            "revision_no" INT NOT NULL,
            "title" VARCHAR(200) NOT NULL,
            "remarks" TEXT,
            "lines_snapshot" JSONB NOT NULL,
            "approved_at" TIMESTAMPTZ NOT NULL,
            "approved_by" INT,
            "approved_by_name" VARCHAR(100),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiplm_mrr_rev"
            ON "apps_kuaiplm_material_review_revisions" ("tenant_id", "review_id", "revision_no")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_kuaiplm_mrr_review"
            ON "apps_kuaiplm_material_review_revisions" ("tenant_id", "review_id");
        CREATE INDEX IF NOT EXISTS "idx_kuaiplm_mrr_uuid"
            ON "apps_kuaiplm_material_review_revisions" ("uuid");
        COMMENT ON TABLE "apps_kuaiplm_material_review_revisions" IS '快研发 - 物料评审版次';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaiplm_material_review_revisions";
        ALTER TABLE "apps_kuaiplm_material_reviews"
            DROP COLUMN IF EXISTS "revision_no";
    """
