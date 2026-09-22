"""物料主数据：超收/超发容差（空则继承组织默认）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_master_data_materials"
    ADD COLUMN IF NOT EXISTS "over_receipt_tolerance_pct" DECIMAL(8,4),
    ADD COLUMN IF NOT EXISTS "over_issue_tolerance_pct" DECIMAL(8,4);

COMMENT ON COLUMN "apps_master_data_materials"."over_receipt_tolerance_pct" IS '超收容差百分数(0-100)，空则继承组织采购容差';
COMMENT ON COLUMN "apps_master_data_materials"."over_issue_tolerance_pct" IS '超发容差百分数(0-100)，空则继承组织仓储超发比例';
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_master_data_materials"
    DROP COLUMN IF EXISTS "over_issue_tolerance_pct",
    DROP COLUMN IF EXISTS "over_receipt_tolerance_pct";
"""
