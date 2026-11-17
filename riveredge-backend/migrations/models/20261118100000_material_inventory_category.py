"""物料主数据：存货类别字段。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_materials"
            ADD COLUMN IF NOT EXISTS "inventory_category" VARCHAR(32);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_materials"
            DROP COLUMN IF EXISTS "inventory_category";
    """
