"""物料分组产品工艺表补齐 BaseModel 审计列。

1033 建表时未含 created_by / updated_by，保存时会 SELECT updated_by 失败。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_material_group_product_process"
            ADD COLUMN IF NOT EXISTS "created_by" INT,
            ADD COLUMN IF NOT EXISTS "created_by_name" VARCHAR(100),
            ADD COLUMN IF NOT EXISTS "updated_by" INT,
            ADD COLUMN IF NOT EXISTS "updated_by_name" VARCHAR(100);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_material_group_product_process"
            DROP COLUMN IF EXISTS "created_by",
            DROP COLUMN IF EXISTS "created_by_name",
            DROP COLUMN IF EXISTS "updated_by",
            DROP COLUMN IF EXISTS "updated_by_name";
    """

# 对应上游 1034_20261115150000_material_group_product_process_audit_cols.py
