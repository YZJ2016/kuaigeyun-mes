"""
回填销售/采购类单据：主状态草稿且 review 误为 PENDING/待审核、无审核人时刻 → review 草稿。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_sales_orders"
        SET "review_status" = 'DRAFT', "updated_at" = CURRENT_TIMESTAMP
        WHERE "deleted_at" IS NULL
          AND "status" IN ('DRAFT', '草稿')
          AND "review_status" IN ('PENDING', '待审核', 'pending_review', 'PENDING_REVIEW')
          AND "reviewer_id" IS NULL
          AND "review_time" IS NULL;

        UPDATE "apps_kuaizhizao_purchase_orders"
        SET "review_status" = 'DRAFT', "updated_at" = CURRENT_TIMESTAMP
        WHERE "deleted_at" IS NULL
          AND "status" IN ('DRAFT', '草稿')
          AND "review_status" IN ('PENDING', '待审核', 'pending_review', 'PENDING_REVIEW')
          AND "reviewer_id" IS NULL
          AND "review_time" IS NULL;

        UPDATE "apps_kuaizhizao_purchase_requisitions"
        SET "review_status" = 'DRAFT', "updated_at" = CURRENT_TIMESTAMP
        WHERE "deleted_at" IS NULL
          AND "status" IN ('DRAFT', '草稿')
          AND "review_status" IN ('PENDING', '待审核', 'pending_review', 'PENDING_REVIEW')
          AND "reviewer_id" IS NULL
          AND "review_time" IS NULL;

        UPDATE "apps_kuaizhizao_sales_forecasts"
        SET "review_status" = 'DRAFT', "updated_at" = CURRENT_TIMESTAMP
        WHERE "deleted_at" IS NULL
          AND "status" IN ('DRAFT', '草稿')
          AND "review_status" IN ('PENDING', '待审核', 'pending_review', 'PENDING_REVIEW')
          AND "reviewer_id" IS NULL
          AND "review_time" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        SELECT 1;
    """
