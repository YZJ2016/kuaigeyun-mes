"""收货通知单增加审核状态。未通知的历史单记草稿。已通知或已入库记审核通过。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_receipt_notices"
            ADD COLUMN "review_status" VARCHAR(20) NOT NULL DEFAULT '草稿';
        UPDATE "apps_kuaizhizao_receipt_notices"
            SET "review_status" = '审核通过'
            WHERE "deleted_at" IS NULL
              AND "status" IN ('已通知', '已入库');
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_receipt_notices"
            DROP COLUMN "review_status";
    """
