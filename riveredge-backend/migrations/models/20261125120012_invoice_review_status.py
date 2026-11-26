"""发票表增加审核状态。销项已审核记已审核，未审核记草稿。（上游 1000_20261107194500 remap）"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_invoices"
            ADD COLUMN "review_status" VARCHAR(20) NOT NULL DEFAULT '草稿';
        UPDATE "apps_kuaicaiwu_invoices"
            SET "review_status" = '已审核'
            WHERE "status" IN ('已审核', '已开票');
        UPDATE "apps_kuaicaiwu_invoices"
            SET "review_status" = '已驳回'
            WHERE "status" = '已驳回';
        UPDATE "apps_kuaicaiwu_invoices"
            SET "review_status" = '已作废'
            WHERE "status" = '已作废';
        UPDATE "apps_kuaicaiwu_invoices"
            SET "review_status" = '已红冲'
            WHERE "status" = '已红冲';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_invoices"
            DROP COLUMN "review_status";
    """
