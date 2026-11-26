"""其他费用收入增加审核状态；历史 PendingReview/Approved/Rejected 回填后业务 status 归 Draft。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    # 本地 MiscVoucherService 仍以 status 承载审核态（上游为 status/review_status 拆分模型），
    # 故不搬上游末段 status 归 Draft；review_status 仅作镜像列，由服务层同步写入。
    return """
        ALTER TABLE "apps_kuaicaiwu_other_incomes"
            ADD COLUMN IF NOT EXISTS "review_status" VARCHAR(20) NOT NULL DEFAULT '草稿';
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
            SET "review_status" = '已取消'
            WHERE "status" IN ('Cancelled', '已取消');
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_other_incomes"
            DROP COLUMN "review_status";
    """

# 对应上游 1001_20261107183000_other_income_review_status.py
