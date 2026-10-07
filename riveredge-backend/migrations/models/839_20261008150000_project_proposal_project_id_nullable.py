"""项目建议书为立项前置单据：新建时尚未有正式研发项目，project_id 可空。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaiplm_project_proposals"
    ALTER COLUMN "project_id" DROP NOT NULL;
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
UPDATE "apps_kuaiplm_project_proposals"
SET "project_id" = 0
WHERE "project_id" IS NULL;
ALTER TABLE "apps_kuaiplm_project_proposals"
    ALTER COLUMN "project_id" SET NOT NULL;
"""
