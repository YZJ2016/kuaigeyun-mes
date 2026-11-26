"""其他出库、借料明细增加序列号列表（JSON），对齐销售出库等单据。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_other_outbound_items"
        ADD COLUMN IF NOT EXISTS "serial_numbers" JSONB;
        COMMENT ON COLUMN "apps_kuaizhizao_other_outbound_items"."serial_numbers" IS '序列号列表（JSON数组）';

        ALTER TABLE "apps_kuaizhizao_material_borrow_items"
        ADD COLUMN IF NOT EXISTS "serial_numbers" JSONB;
        COMMENT ON COLUMN "apps_kuaizhizao_material_borrow_items"."serial_numbers" IS '序列号列表（JSON数组）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_other_outbound_items"
        DROP COLUMN IF EXISTS "serial_numbers";
        ALTER TABLE "apps_kuaizhizao_material_borrow_items"
        DROP COLUMN IF EXISTS "serial_numbers";
    """
