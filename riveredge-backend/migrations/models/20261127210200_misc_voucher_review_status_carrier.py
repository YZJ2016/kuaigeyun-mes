"""其他费用收支/申请单审核态收敛：review_status 升为审核承载列（上游 1001/1003/1004 合并重映射）。

- 申请表补 review_status 列并按历史 status 回填；历史 PendingReview/Rejected 业务 status 归 Draft，
  Approved 保留以便下推。
- 其他费用支出/收入：review_status 镜像列升承载列，历史 PendingReview/Approved/Rejected
  回填后业务 status 归 Draft（Confirmed/Cancelled 保留）。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_other_expense_applications"
            ADD COLUMN IF NOT EXISTS "review_status" VARCHAR(20) NOT NULL DEFAULT '草稿';
        UPDATE "apps_kuaicaiwu_other_expense_applications"
            SET "review_status" = '已审核'
            WHERE "status" IN ('Approved', '已审核');
        UPDATE "apps_kuaicaiwu_other_expense_applications"
            SET "review_status" = '待审核'
            WHERE "status" IN ('PendingReview', '待审核');
        UPDATE "apps_kuaicaiwu_other_expense_applications"
            SET "review_status" = '已驳回'
            WHERE "status" IN ('Rejected', '已驳回');
        UPDATE "apps_kuaicaiwu_other_expense_applications"
            SET "status" = 'Draft'
            WHERE "status" IN ('PendingReview', 'Rejected', '待审核', '已驳回');

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
            SET "status" = 'Draft'
            WHERE "status" IN ('PendingReview', 'Approved', 'Rejected', '待审核', '已审核', '已驳回');

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
        ALTER TABLE "apps_kuaicaiwu_other_expense_applications"
            DROP COLUMN IF EXISTS "review_status";
    """
