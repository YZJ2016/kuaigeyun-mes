"""
订单评审：头表评审部门计划 + 部门意见指定评审人。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_reviews"
            ADD COLUMN IF NOT EXISTS "review_dept_plan" JSONB;
        COMMENT ON COLUMN "apps_kuaizhizao_sales_reviews"."review_dept_plan"
            IS '下达前评审部门与指定评审人计划';

        ALTER TABLE "apps_kuaizhizao_sales_review_dept_opinions"
            ADD COLUMN IF NOT EXISTS "assigned_reviewer_id" INT;
        ALTER TABLE "apps_kuaizhizao_sales_review_dept_opinions"
            ADD COLUMN IF NOT EXISTS "assigned_reviewer_name" VARCHAR(100);
        COMMENT ON COLUMN "apps_kuaizhizao_sales_review_dept_opinions"."assigned_reviewer_id"
            IS '下达时指定的评审人';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_review_dept_opinions"
            DROP COLUMN IF EXISTS "assigned_reviewer_name";
        ALTER TABLE "apps_kuaizhizao_sales_review_dept_opinions"
            DROP COLUMN IF EXISTS "assigned_reviewer_id";
        ALTER TABLE "apps_kuaizhizao_sales_reviews"
            DROP COLUMN IF EXISTS "review_dept_plan";
    """
