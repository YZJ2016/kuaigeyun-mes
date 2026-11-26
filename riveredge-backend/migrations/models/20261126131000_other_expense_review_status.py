"""其他支出单补 review_status 镜像列。

与 20261126130900_other_income_review_status 对称：上游 other_voucher 模型
收入/支出单均含 review_status；本地服务以 status 承载审核态，此列仅作镜像，
由 MiscVoucherService 随 status 同步写入。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_other_expenses"
            ADD COLUMN IF NOT EXISTS "review_status" VARCHAR(20) NOT NULL DEFAULT '草稿';
        UPDATE "apps_kuaicaiwu_other_expenses"
            SET "review_status" = '已审核'
            WHERE "status" IN ('Approved', 'Confirmed', '已审核', '已确认');
        UPDATE "apps_kuaicaiwu_other_expenses"
            SET "review_status" = '待审核'
            WHERE "status" IN ('PendingReview', '待审核');
        UPDATE "apps_kuaicaiwu_other_expenses"
            SET "review_status" = '已驳回'
            WHERE "status" IN ('Rejected', '已驳回');
        UPDATE "apps_kuaicaiwu_other_expenses"
            SET "review_status" = '已取消'
            WHERE "status" IN ('Cancelled', '已取消');
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_other_expenses"
            DROP COLUMN IF EXISTS "review_status";
    """
