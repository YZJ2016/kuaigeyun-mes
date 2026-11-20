"""报工记录增加审核状态。历史 pending/rejected 迁出业务 status；已通过记审核通过。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_reporting_records"
            ADD COLUMN IF NOT EXISTS "review_status" VARCHAR(20) NOT NULL DEFAULT '草稿';
        UPDATE "apps_kuaizhizao_reporting_records"
            SET "review_status" = '审核通过'
            WHERE "deleted_at" IS NULL
              AND "status" IN ('approved', '已审核', '审核通过');
        UPDATE "apps_kuaizhizao_reporting_records"
            SET "review_status" = '待审核',
                "status" = 'draft'
            WHERE "deleted_at" IS NULL
              AND "status" IN ('pending', 'pending_review', 'pending_approval', '待审核');
        UPDATE "apps_kuaizhizao_reporting_records"
            SET "review_status" = '审核驳回',
                "status" = 'draft'
            WHERE "deleted_at" IS NULL
              AND "status" IN ('rejected', '已驳回', '审核驳回');
        UPDATE "apps_kuaizhizao_reporting_records"
            SET "review_status" = '草稿'
            WHERE "deleted_at" IS NULL
              AND "status" IN ('draft', '草稿', 'DRAFT')
              AND ("review_status" IS NULL OR TRIM("review_status") = '' OR "review_status" = '草稿');
        ALTER TABLE "apps_kuaizhizao_reporting_records"
            ALTER COLUMN "status" SET DEFAULT 'draft';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_reporting_records"
            SET "status" = 'pending'
            WHERE "deleted_at" IS NULL
              AND "status" = 'draft'
              AND "review_status" = '待审核';
        UPDATE "apps_kuaizhizao_reporting_records"
            SET "status" = 'rejected'
            WHERE "deleted_at" IS NULL
              AND "status" = 'draft'
              AND "review_status" IN ('审核驳回', '已驳回');
        ALTER TABLE "apps_kuaizhizao_reporting_records"
            ALTER COLUMN "status" SET DEFAULT 'pending';
        ALTER TABLE "apps_kuaizhizao_reporting_records"
            DROP COLUMN IF EXISTS "review_status";
    """
