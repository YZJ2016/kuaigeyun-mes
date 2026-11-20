"""字段权限细字段收敛为两大类：amount / party_name。

先软删同键多余行（取最严），再改名，避免 unique(tenant,role,resource,field_name) 冲突。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True

_AMOUNT_COLS = (
    "amount",
    "total_amount",
    "tax_amount",
    "untaxed_amount",
    "unit_price",
    "price",
    "amount_with_tax",
    "amount_without_tax",
)
_PARTY_COLS = (
    "customer_name",
    "supplier_name",
    "default_supplier_id",
    "default_supplier_name",
)


async def upgrade(db: BaseDBAsyncClient) -> str:
    amount_in = ", ".join(f"'{c}'" for c in _AMOUNT_COLS)
    party_in = ", ".join(f"'{c}'" for c in _PARTY_COLS)
    return f"""
        WITH mapped AS (
          SELECT id,
                 tenant_id,
                 role_uuid,
                 lower(trim(resource)) AS res,
                 CASE
                   WHEN lower(trim(field_name)) IN ({amount_in}) THEN 'amount'
                   WHEN lower(trim(field_name)) = 'amount' THEN 'amount'
                   WHEN lower(trim(field_name)) IN ({party_in}) THEN 'party_name'
                   WHEN lower(trim(field_name)) = 'party_name' THEN 'party_name'
                   ELSE NULL
                 END AS kind,
                 mask_level,
                 updated_at
            FROM core_field_permission_policies
           WHERE deleted_at IS NULL
        ),
        ranked AS (
          SELECT id,
                 kind,
                 ROW_NUMBER() OVER (
                   PARTITION BY tenant_id, role_uuid, res, kind
                   ORDER BY
                     CASE lower(mask_level)
                       WHEN 'hidden' THEN 2
                       WHEN 'masked' THEN 1
                       ELSE 0
                     END DESC,
                     updated_at DESC,
                     id DESC
                 ) AS rn
            FROM mapped
           WHERE kind IS NOT NULL
        )
        UPDATE core_field_permission_policies AS p
           SET deleted_at = NOW(),
               updated_at = NOW()
         WHERE p.deleted_at IS NULL
           AND (
             p.id IN (SELECT id FROM ranked WHERE rn > 1)
             OR p.id IN (SELECT id FROM mapped WHERE kind IS NULL)
           );

        -- 软删行若已占用目标 (resource, field_name) 唯一键，改名腾位
        UPDATE core_field_permission_policies
           SET field_name = field_name || '__archived_' || id::text,
               updated_at = NOW()
         WHERE deleted_at IS NOT NULL
           AND lower(field_name) IN ('amount', 'party_name');

        WITH keepers AS (
          SELECT id,
                 CASE
                   WHEN lower(trim(field_name)) IN ({amount_in}) THEN 'amount'
                   WHEN lower(trim(field_name)) = 'amount' THEN 'amount'
                   WHEN lower(trim(field_name)) IN ({party_in}) THEN 'party_name'
                   WHEN lower(trim(field_name)) = 'party_name' THEN 'party_name'
                   ELSE lower(trim(field_name))
                 END AS kind,
                 lower(trim(resource)) AS res
            FROM core_field_permission_policies
           WHERE deleted_at IS NULL
        )
        UPDATE core_field_permission_policies AS p
           SET field_name = k.kind,
               resource = k.res,
               updated_at = NOW()
          FROM keepers AS k
         WHERE p.id = k.id
           AND (p.field_name <> k.kind OR p.resource <> k.res);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    # 策略类不可无损还原为细字段
    return """
        SELECT 1;
    """
