from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_defect_records"
            ADD COLUMN IF NOT EXISTS "finished_goods_receipt_id" INT;
        ALTER TABLE "apps_kuaizhizao_defect_records"
            ADD COLUMN IF NOT EXISTS "accept_purchase_receipt_id" INT;
        CREATE INDEX IF NOT EXISTS "idx_apps_kuaizh_defect_records_fg_receipt_id"
            ON "apps_kuaizhizao_defect_records" ("finished_goods_receipt_id");
        CREATE INDEX IF NOT EXISTS "idx_apps_kuaizh_defect_records_accept_pr_id"
            ON "apps_kuaizhizao_defect_records" ("accept_purchase_receipt_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_apps_kuaizh_defect_records_accept_pr_id";
        DROP INDEX IF EXISTS "idx_apps_kuaizh_defect_records_fg_receipt_id";
        ALTER TABLE "apps_kuaizhizao_defect_records"
            DROP COLUMN IF EXISTS "accept_purchase_receipt_id";
        ALTER TABLE "apps_kuaizhizao_defect_records"
            DROP COLUMN IF EXISTS "finished_goods_receipt_id";
    """
