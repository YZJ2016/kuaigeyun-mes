"""BOM 子件行增加安装位置字段，用于区分重复子物料。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_bom"
            ADD COLUMN IF NOT EXISTS "install_position" VARCHAR(100);
        COMMENT ON COLUMN "apps_master_data_bom"."install_position"
            IS '安装位置（重复子件时手工区分）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_bom"
            DROP COLUMN IF EXISTS "install_position";
    """

# 对应上游 1035_20261115160000_bom_install_position.py
