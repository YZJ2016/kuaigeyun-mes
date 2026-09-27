"""其他入库/其他出库/借料/还料/半成品入库明细增加序列号字段（spec 141 撤回回冲链路补齐）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_other_inbound_items"
            ADD COLUMN IF NOT EXISTS "serial_numbers" JSONB;
        ALTER TABLE "apps_kuaizhizao_other_outbound_items"
            ADD COLUMN IF NOT EXISTS "serial_numbers" JSONB;
        ALTER TABLE "apps_kuaizhizao_material_borrow_items"
            ADD COLUMN IF NOT EXISTS "serial_numbers" JSONB;
        ALTER TABLE "apps_kuaizhizao_material_return_items"
            ADD COLUMN IF NOT EXISTS "serial_numbers" JSONB;
        ALTER TABLE "apps_kuaizhizao_semi_finished_goods_receipt_items"
            ADD COLUMN IF NOT EXISTS "serial_numbers" JSONB;
        ALTER TABLE "apps_kuaizhizao_production_return_items"
            ADD COLUMN IF NOT EXISTS "serial_numbers" JSONB;

        COMMENT ON COLUMN "apps_kuaizhizao_other_inbound_items"."serial_numbers"
            IS '序列号列表（JSON格式，存储多个序列号）';
        COMMENT ON COLUMN "apps_kuaizhizao_other_outbound_items"."serial_numbers"
            IS '序列号列表（JSON格式，存储多个序列号）';
        COMMENT ON COLUMN "apps_kuaizhizao_material_borrow_items"."serial_numbers"
            IS '序列号列表（JSON格式，存储多个序列号）';
        COMMENT ON COLUMN "apps_kuaizhizao_material_return_items"."serial_numbers"
            IS '序列号列表（JSON格式，存储多个序列号）';
        COMMENT ON COLUMN "apps_kuaizhizao_semi_finished_goods_receipt_items"."serial_numbers"
            IS '序列号列表（JSON格式，存储多个序列号）';
        COMMENT ON COLUMN "apps_kuaizhizao_production_return_items"."serial_numbers"
            IS '序列号列表（JSON格式，存储多个序列号）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_other_inbound_items"
            DROP COLUMN IF EXISTS "serial_numbers";
        ALTER TABLE "apps_kuaizhizao_other_outbound_items"
            DROP COLUMN IF EXISTS "serial_numbers";
        ALTER TABLE "apps_kuaizhizao_material_borrow_items"
            DROP COLUMN IF EXISTS "serial_numbers";
        ALTER TABLE "apps_kuaizhizao_material_return_items"
            DROP COLUMN IF EXISTS "serial_numbers";
        ALTER TABLE "apps_kuaizhizao_semi_finished_goods_receipt_items"
            DROP COLUMN IF EXISTS "serial_numbers";
        ALTER TABLE "apps_kuaizhizao_production_return_items"
            DROP COLUMN IF EXISTS "serial_numbers";
    """
