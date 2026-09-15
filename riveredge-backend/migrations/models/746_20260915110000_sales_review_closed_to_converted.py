"""
订单评审：下推销售订单后的终态由 closed（已关闭）改为 converted（已转单）。

closed 仅表示成功下推，与全局「关闭/关停」语义冲突；对齐采购询价「已转单」。
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
UPDATE "apps_kuaizhizao_sales_reviews"
SET
    "status" = 'converted',
    "updated_at" = NOW()
WHERE "deleted_at" IS NULL
  AND "status" = 'closed';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
UPDATE "apps_kuaizhizao_sales_reviews"
SET
    "status" = 'closed',
    "updated_at" = NOW()
WHERE "deleted_at" IS NULL
  AND "status" = 'converted'
  AND "sales_order_id" IS NOT NULL;
    """
