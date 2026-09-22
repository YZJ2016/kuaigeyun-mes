"""
调拨明细物料编码/名称快照回填。

根因：创建/更新明细时前端未稳定写入 material_code/material_name，
列表「明细」列与详情表依赖行上快照，空值导致不展示。
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
UPDATE "apps_kuaizhizao_inventory_transfer_items" AS i
SET
  "material_code" = COALESCE(NULLIF(TRIM(m."main_code"), ''), NULLIF(TRIM(m."code"), ''), i."material_code"),
  "material_name" = COALESCE(NULLIF(TRIM(m."name"), ''), i."material_name"),
  "material_unit" = COALESCE(NULLIF(TRIM(i."material_unit"), ''), NULLIF(TRIM(m."base_unit"), ''), i."material_unit")
FROM "apps_master_data_materials" AS m
WHERE i."deleted_at" IS NULL
  AND i."material_id" = m."id"
  AND i."tenant_id" = m."tenant_id"
  AND m."deleted_at" IS NULL
  AND (
    TRIM(COALESCE(i."material_code", '')) = ''
    OR TRIM(COALESCE(i."material_name", '')) = ''
    OR TRIM(COALESCE(i."material_unit", '')) = ''
  );
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return "-- noop: inventory transfer item material snapshot backfill is irreversible"
