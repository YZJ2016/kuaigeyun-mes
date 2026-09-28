"""好力 GO — 设备验收单头：合同约定产能。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "haoligo_equipment_acceptance_sheet"
            ADD COLUMN IF NOT EXISTS "contract_capacity" NUMERIC(20,4);
        COMMENT ON COLUMN "haoligo_equipment_acceptance_sheet"."contract_capacity"
            IS '合同约定产能（个/小时）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "haoligo_equipment_acceptance_sheet"
            DROP COLUMN IF EXISTS "contract_capacity";
    """
