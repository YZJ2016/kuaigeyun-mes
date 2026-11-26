"""采购入库审核状态默认改为草稿。未入库的历史「待审核」并未走过审批，回写成草稿。已入库的历史单记为审核通过。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ALTER COLUMN "review_status" SET DEFAULT '草稿';
        UPDATE "apps_kuaizhizao_purchase_receipts"
            SET "review_status" = '草稿'
            WHERE "deleted_at" IS NULL
              AND "review_status" = '待审核'
              AND "status" IN ('草稿', 'draft', 'DRAFT', '待入库');
        UPDATE "apps_kuaizhizao_purchase_receipts"
            SET "review_status" = '审核通过'
            WHERE "deleted_at" IS NULL
              AND "review_status" = '待审核'
              AND "status" IN ('已入库', 'completed');
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ALTER COLUMN "review_status" SET DEFAULT '待审核';
    """

# 对应上游 996_20261107163000_purchase_receipt_review_draft.py
