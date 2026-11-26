"""到货延期草稿的审核状态从默认待审改为草稿。已进入审核的单据不动。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_purchase_arrival_delay_reports"
            SET "review_status" = 'DRAFT'
            WHERE "deleted_at" IS NULL
              AND "status" = 'DRAFT'
              AND "review_status" = 'PENDING';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_purchase_arrival_delay_reports"
            SET "review_status" = 'PENDING'
            WHERE "deleted_at" IS NULL
              AND "status" = 'DRAFT'
              AND "review_status" = 'DRAFT';
    """

# 对应上游 998_20261107180000_arrival_delay_review_draft.py
