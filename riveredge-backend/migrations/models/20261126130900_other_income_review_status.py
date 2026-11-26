"""其他费用收入增加审核状态；历史 PendingReview/Approved/Rejected 回填后业务 status 归 Draft。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_other_incomes"
            ADD COLUMN "review_status" VARCHAR(20) NOT NULL DEFAULT '草稿';
        UPDATE "apps_kuaicaiwu_other_incomes"
            SET "review_status" = '已审核'
            WHERE "status" IN ('Approved', 'Confirmed', '已审核', '已确认');
        UPDATE "apps_kuaicaiwu_other_incomes"
            SET "review_status" = '待审核'
            WHERE "status" IN ('PendingReview', '待审核');
        UPDATE "apps_kuaicaiwu_other_incomes"
            SET "review_status" = '已驳回'
            WHERE "status" IN ('Rejected', '已驳回');
        UPDATE "apps_kuaicaiwu_other_incomes"
            SET "status" = 'Draft'
            WHERE "status" IN ('PendingReview', 'Approved', 'Rejected', '待审核', '已审核', '已驳回');
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_other_incomes"
            DROP COLUMN "review_status";
    """

# 对应上游 1001_20261107183000_other_income_review_status.py
