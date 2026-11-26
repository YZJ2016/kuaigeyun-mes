"""需求计划审核状态规范化。草稿业务态的 PENDING 审核改为草稿。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_demands"
            SET "review_status" = 'DRAFT'
            WHERE "deleted_at" IS NULL
              AND "demand_type" = 'demand_plan'
              AND "status" IN ('DRAFT', '草稿', 'draft')
              AND (
                "review_status" IS NULL
                OR TRIM("review_status") = ''
                OR "review_status" IN ('PENDING', 'pending', 'Pending', '待审核')
              );
        ALTER TABLE "apps_kuaizhizao_demands"
            ALTER COLUMN "review_status" SET DEFAULT 'DRAFT';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_demands"
            ALTER COLUMN "review_status" SET DEFAULT 'PENDING';
    """

# 对应上游 1013_20261107235500_demand_review_draft.py
