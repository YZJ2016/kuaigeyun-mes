"""
采购入库单增加苍穹推送编码字段：组织、单据类型、业务类型、库存事务。
单据可改；空时回落接口管理默认值。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "org_number" VARCHAR(64);
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "bizorg_number" VARCHAR(64);
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "billtype_number" VARCHAR(64);
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "biztype_number" VARCHAR(64) DEFAULT '110';
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "invscheme_number" VARCHAR(64) DEFAULT '110';

        COMMENT ON COLUMN "apps_kuaizhizao_purchase_receipts"."org_number"
            IS '库存组织编码（推送 org_number）';
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_receipts"."bizorg_number"
            IS '采购组织编码（推送 bizorg_number）';
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_receipts"."billtype_number"
            IS '单据类型编码（推送 billtype_number）';
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_receipts"."biztype_number"
            IS '业务类型编码（推送 biztype_number，默认物料类采购 110）';
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_receipts"."invscheme_number"
            IS '库存事务编码（推送 invscheme_number，默认普通采购入库 110）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "org_number";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "bizorg_number";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "billtype_number";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "biztype_number";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "invscheme_number";
    """
