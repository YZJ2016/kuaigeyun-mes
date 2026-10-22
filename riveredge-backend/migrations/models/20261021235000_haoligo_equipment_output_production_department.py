"""设备产出单：制令单带出生产部门。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "haoligo_equipment_output_record"
            ADD COLUMN IF NOT EXISTS "production_department" VARCHAR(200);

        ALTER TABLE "haoligo_equipment_output_dataset_binding"
            ADD COLUMN IF NOT EXISTS "production_department_column" VARCHAR(128);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "haoligo_equipment_output_dataset_binding"
            DROP COLUMN IF EXISTS "production_department_column";

        ALTER TABLE "haoligo_equipment_output_record"
            DROP COLUMN IF EXISTS "production_department";
    """
