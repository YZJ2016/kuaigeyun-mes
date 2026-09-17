"""交付：config_attrs spec_tier 与 duration_rules 键统一为 product_model。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
UPDATE "apps_kuaizhizao_delivery_process_template_nodes"
SET "duration_rules" = jsonb_set("duration_rules", '{attr_key}', '"product_model"')
WHERE "duration_rules" IS NOT NULL
  AND "duration_rules"->>'attr_key' = 'spec_tier';

UPDATE "apps_kuaizhizao_delivery_projects"
SET "config_attrs" = ("config_attrs" - 'spec_tier')
    || jsonb_build_object('product_model', "config_attrs"->'spec_tier')
WHERE "config_attrs" IS NOT NULL
  AND "config_attrs" ? 'spec_tier';
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
UPDATE "apps_kuaizhizao_delivery_process_template_nodes"
SET "duration_rules" = jsonb_set("duration_rules", '{attr_key}', '"spec_tier"')
WHERE "duration_rules" IS NOT NULL
  AND "duration_rules"->>'attr_key' = 'product_model';

UPDATE "apps_kuaizhizao_delivery_projects"
SET "config_attrs" = ("config_attrs" - 'product_model')
    || jsonb_build_object('spec_tier', "config_attrs"->'product_model')
WHERE "config_attrs" IS NOT NULL
  AND "config_attrs" ? 'product_model';
"""
