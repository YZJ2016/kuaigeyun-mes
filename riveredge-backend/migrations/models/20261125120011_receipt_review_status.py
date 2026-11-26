"""收款单增加审核状态。已确认的历史单记已审核，其余记草稿。（上游 999_20261107193000 remap）"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_receipts"
            ADD COLUMN "review_status" VARCHAR(20) NOT NULL DEFAULT '草稿';
        UPDATE "apps_kuaicaiwu_receipts"
            SET "review_status" = '已审核'
            WHERE "status" = 'Confirmed';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_receipts"
            DROP COLUMN "review_status";
    """
