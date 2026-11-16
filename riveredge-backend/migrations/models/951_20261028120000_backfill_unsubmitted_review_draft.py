"""
回填未提交单据 review_status：误标待审核但无审核人/审核时刻的历史行改为草稿。

与采购询价、销售退货同类问题；采购退货对称处理。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_purchase_returns"
        SET
            "review_status" = '草稿',
            "updated_at" = CURRENT_TIMESTAMP
        WHERE "deleted_at" IS NULL
          AND "review_status" IN ('待审核', 'PENDING', 'pending', 'pending_review', 'PENDING_REVIEW')
          AND "status" IN ('待退货', '草稿')
          AND "reviewer_id" IS NULL
          AND "review_time" IS NULL;

        UPDATE "apps_kuaizhizao_sales_returns"
        SET
            "review_status" = '草稿',
            "updated_at" = CURRENT_TIMESTAMP
        WHERE "deleted_at" IS NULL
          AND "review_status" IN ('待审核', 'PENDING', 'pending', 'pending_review', 'PENDING_REVIEW')
          AND "status" IN ('待退货', '草稿')
          AND "reviewer_id" IS NULL
          AND "review_time" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        SELECT 1;
    """
