"""票据台账增加审核状态；历史在手/开出票据视为已审核。（上游 1002_20261107190000 remap）"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_notes"
            ADD COLUMN "review_status" VARCHAR(20) NOT NULL DEFAULT '草稿';
        UPDATE "apps_kuaicaiwu_notes"
            SET "review_status" = '已审核';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_notes"
            DROP COLUMN "review_status";
    """
