"""返工单头表与排位行 extension_payload（行业 profile 溢出字段）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_rework_orders"
            ADD COLUMN IF NOT EXISTS "extension_payload" JSONB;
        COMMENT ON COLUMN "apps_kuaizhizao_rework_orders"."extension_payload"
            IS '行业扩展载荷（form_sections / rework_path_type 等）';

        ALTER TABLE "apps_kuaizhizao_rework_order_position_plans"
            ADD COLUMN IF NOT EXISTS "extension_payload" JSONB;
        COMMENT ON COLUMN "apps_kuaizhizao_rework_order_position_plans"."extension_payload"
            IS '排位策划行行业扩展载荷';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_rework_order_position_plans"
            DROP COLUMN IF EXISTS "extension_payload";
        ALTER TABLE "apps_kuaizhizao_rework_orders"
            DROP COLUMN IF EXISTS "extension_payload";
    """
