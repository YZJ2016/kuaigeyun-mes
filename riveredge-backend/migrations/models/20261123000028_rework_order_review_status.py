"""返工单增加审核状态。历史 pending/approved 审计态迁入 review_status；业务 status 保持草稿至下达。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_rework_orders"
            ADD COLUMN IF NOT EXISTS "review_status" VARCHAR(20) NOT NULL DEFAULT '草稿';
        UPDATE "apps_kuaizhizao_rework_orders"
            SET "review_status" = '待审核',
                "status" = 'draft'
            WHERE "deleted_at" IS NULL
              AND "status" IN ('pending', 'pending_review', 'pending_approval', '待审核');
        UPDATE "apps_kuaizhizao_rework_orders"
            SET "review_status" = '已通过',
                "status" = 'draft'
            WHERE "deleted_at" IS NULL
              AND "status" IN ('approved', '已审核', '审核通过', '已通过');
        UPDATE "apps_kuaizhizao_rework_orders"
            SET "review_status" = '已通过'
            WHERE "deleted_at" IS NULL
              AND "status" NOT IN ('draft', '草稿', 'DRAFT', 'cancelled', '已取消')
              AND ("review_status" IS NULL OR TRIM("review_status") = '' OR "review_status" = '草稿');
        UPDATE "apps_kuaizhizao_rework_orders"
            SET "review_status" = '草稿'
            WHERE "deleted_at" IS NULL
              AND "status" IN ('draft', '草稿', 'DRAFT')
              AND ("review_status" IS NULL OR TRIM("review_status") = '' OR "review_status" = '草稿');
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_rework_orders"
            SET "status" = 'pending'
            WHERE "deleted_at" IS NULL
              AND "status" = 'draft'
              AND "review_status" = '待审核';
        UPDATE "apps_kuaizhizao_rework_orders"
            SET "status" = 'approved'
            WHERE "deleted_at" IS NULL
              AND "status" = 'draft'
              AND "review_status" IN ('已通过', '审核通过', '已审核');
        ALTER TABLE "apps_kuaizhizao_rework_orders"
            DROP COLUMN IF EXISTS "review_status";
    """
