"""库存流水记录实际扣减/增加的库位，供无库位出库撤回按原库位加回。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_material_stock_movements"
            ADD COLUMN IF NOT EXISTS "location_id" INT;
        ALTER TABLE "apps_kuaizhizao_material_stock_movements"
            ADD COLUMN IF NOT EXISTS "location_code" VARCHAR(50);
        COMMENT ON COLUMN "apps_kuaizhizao_material_stock_movements"."location_id"
            IS '发生余额变动的库位ID';
        COMMENT ON COLUMN "apps_kuaizhizao_material_stock_movements"."location_code"
            IS '发生余额变动的库位编码（空串=未分库位键；空值=历史流水未记录库位）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_material_stock_movements" DROP COLUMN IF EXISTS "location_code";
        ALTER TABLE "apps_kuaizhizao_material_stock_movements" DROP COLUMN IF EXISTS "location_id";
    """
