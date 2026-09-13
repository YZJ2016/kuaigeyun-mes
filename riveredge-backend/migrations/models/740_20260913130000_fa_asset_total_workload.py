"""固定资产卡片：工作量法预计总工作量。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_fa_assets"
        ADD COLUMN IF NOT EXISTS "total_workload" DECIMAL(20,4);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_fa_assets"
        DROP COLUMN IF EXISTS "total_workload";
    """
