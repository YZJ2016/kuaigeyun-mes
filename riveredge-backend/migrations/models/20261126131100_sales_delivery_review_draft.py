"""销售出库审核状态规范化。待审核迁出业务 status；历史 PENDING 改为草稿；已出库记审核通过。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_sales_deliveries"
            SET "status" = '待出库'
            WHERE "deleted_at" IS NULL
              AND "status" = '待审核';
        UPDATE "apps_kuaizhizao_sales_deliveries"
            SET "review_status" = '草稿'
            WHERE "deleted_at" IS NULL
              AND "status" IN ('待出库', '草稿')
              AND (
                "review_status" IS NULL
                OR TRIM("review_status") = ''
                OR "review_status" IN ('PENDING', 'pending', 'Pending')
              );
        UPDATE "apps_kuaizhizao_sales_deliveries"
            SET "review_status" = '已通过'
            WHERE "deleted_at" IS NULL
              AND "status" = '已出库'
              AND (
                "review_status" IS NULL
                OR TRIM("review_status") = ''
                OR "review_status" IN ('PENDING', 'pending', '草稿', 'draft', 'DRAFT')
              );
        ALTER TABLE "apps_kuaizhizao_sales_deliveries"
            ALTER COLUMN "review_status" SET DEFAULT '草稿';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_deliveries"
            ALTER COLUMN "review_status" SET DEFAULT 'PENDING';
        UPDATE "apps_kuaizhizao_sales_deliveries"
            SET "status" = '待审核'
            WHERE "deleted_at" IS NULL
              AND "status" = '待出库'
              AND "review_status" = '待审核';
    """

# 对应上游 1011_20261107235000_sales_delivery_review_draft.py
