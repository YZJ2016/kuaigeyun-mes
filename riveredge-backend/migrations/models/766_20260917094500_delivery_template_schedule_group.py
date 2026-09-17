"""交付流程模板节点：schedule_group 支持并行排程（如一类～四类采购）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_delivery_process_template_nodes"
    ADD COLUMN IF NOT EXISTS "schedule_group" VARCHAR(50);

UPDATE "apps_kuaizhizao_delivery_process_template_nodes"
SET "schedule_group" = 'procurement'
WHERE "node_key" IN ('buy_cat1', 'buy_cat2', 'buy_cat3', 'buy_cat4')
  AND ("schedule_group" IS NULL OR "schedule_group" = '');
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_delivery_process_template_nodes"
    DROP COLUMN IF EXISTS "schedule_group";
"""
