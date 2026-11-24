"""
销售订单/销售出库：客户订单号（表头+明细快照）。
"""
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE apps_kuaizhizao_sales_orders
            ADD COLUMN IF NOT EXISTS customer_order_no VARCHAR(100) NULL;
        COMMENT ON COLUMN apps_kuaizhizao_sales_orders.customer_order_no IS '客户订单号';

        ALTER TABLE apps_kuaizhizao_sales_order_items
            ADD COLUMN IF NOT EXISTS customer_order_no VARCHAR(100) NULL;
        COMMENT ON COLUMN apps_kuaizhizao_sales_order_items.customer_order_no IS '客户订单号（与表头同步快照）';

        ALTER TABLE apps_kuaizhizao_sales_deliveries
            ADD COLUMN IF NOT EXISTS customer_order_no VARCHAR(100) NULL;
        COMMENT ON COLUMN apps_kuaizhizao_sales_deliveries.customer_order_no IS '客户订单号（来源销售订单，不可改）';

        ALTER TABLE apps_kuaizhizao_sales_delivery_items
            ADD COLUMN IF NOT EXISTS customer_order_no VARCHAR(100) NULL;
        COMMENT ON COLUMN apps_kuaizhizao_sales_delivery_items.customer_order_no IS '客户订单号（来源销售订单行，不可改）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE apps_kuaizhizao_sales_delivery_items
            DROP COLUMN IF EXISTS customer_order_no;
        ALTER TABLE apps_kuaizhizao_sales_deliveries
            DROP COLUMN IF EXISTS customer_order_no;
        ALTER TABLE apps_kuaizhizao_sales_order_items
            DROP COLUMN IF EXISTS customer_order_no;
        ALTER TABLE apps_kuaizhizao_sales_orders
            DROP COLUMN IF EXISTS customer_order_no;
    """