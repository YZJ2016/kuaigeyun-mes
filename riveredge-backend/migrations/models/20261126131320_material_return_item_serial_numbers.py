"""还料明细增加序列号列表（JSON），与借料出库序列号对齐。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_material_return_items"
        ADD COLUMN IF NOT EXISTS "serial_numbers" JSONB;
        COMMENT ON COLUMN "apps_kuaizhizao_material_return_items"."serial_numbers" IS '序列号列表（JSON数组）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_material_return_items"
        DROP COLUMN IF EXISTS "serial_numbers";
    """
