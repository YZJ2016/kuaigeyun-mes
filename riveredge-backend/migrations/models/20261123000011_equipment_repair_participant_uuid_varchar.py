"""参与人 uuid 与 BaseModel CharField 对齐：PG UUID → VARCHAR(36)。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_equipment_repair_participants"
            ALTER COLUMN "uuid" TYPE VARCHAR(36)
            USING "uuid"::text;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_equipment_repair_participants"
            ALTER COLUMN "uuid" TYPE UUID
            USING "uuid"::uuid;
    """
