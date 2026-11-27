"""其他费用支出申请关联采购入库（上游 961 重映射）"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_other_expense_applications"
        ADD COLUMN IF NOT EXISTS "related_purchase_receipts" JSONB;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_other_expense_applications"
        DROP COLUMN IF EXISTS "related_purchase_receipts";
    """
