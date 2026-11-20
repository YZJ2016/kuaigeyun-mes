"""采购发票审核通过后的业务状态为已开票。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE apps_kuaicaiwu_purchase_invoices
        SET status = '已开票', updated_at = NOW()
        WHERE status = '已审核'
          AND review_status IN ('已审核', 'approved')
          AND deleted_at IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE apps_kuaicaiwu_purchase_invoices
        SET status = '已审核', updated_at = NOW()
        WHERE status = '已开票'
          AND review_status IN ('已审核', 'approved')
          AND deleted_at IS NULL;
    """
