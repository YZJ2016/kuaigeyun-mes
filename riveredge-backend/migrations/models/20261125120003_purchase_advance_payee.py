from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_orders"
        ADD COLUMN IF NOT EXISTS "advance_payee_id" INT;
        ALTER TABLE "apps_kuaizhizao_purchase_orders"
        ADD COLUMN IF NOT EXISTS "advance_payee_name" VARCHAR(100);

        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
        ADD COLUMN IF NOT EXISTS "advance_payee_id" INT;
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
        ADD COLUMN IF NOT EXISTS "advance_payee_name" VARCHAR(100);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_orders" DROP COLUMN IF EXISTS "advance_payee_id";
        ALTER TABLE "apps_kuaizhizao_purchase_orders" DROP COLUMN IF EXISTS "advance_payee_name";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "advance_payee_id";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "advance_payee_name";
    """