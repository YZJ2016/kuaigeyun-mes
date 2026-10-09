"""产品固件：软件12位编码（nullable，定制页录入）。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaiplm_product_firmwares"
    ADD COLUMN IF NOT EXISTS "software_item_code" VARCHAR(12);
COMMENT ON COLUMN "apps_kuaiplm_product_firmwares"."software_item_code"
    IS '软件料号/12位编码（定制页展示）';
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaiplm_product_firmwares"
    DROP COLUMN IF EXISTS "software_item_code";
"""
