"""CURRENCY 系统字典补齐港币、新加坡元。

汇率设置预置常见货币含 HKD/SGD，但 SYSTEM_DICTIONARIES 原先无这两项，
列表币种名称空白。本迁移为各租户已有 CURRENCY 字典写入缺失项。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True

_ITEMS = [
    (6, "港币 (HKD)", "HKD", "香港港币"),
    (7, "新加坡元 (SGD)", "SGD", "新加坡元"),
]


async def upgrade(db: BaseDBAsyncClient) -> str:
    item_inserts = []
    for sort_order, label, value, description in _ITEMS:
        item_inserts.append(
            f"""
        INSERT INTO core_dictionary_items (
            uuid, tenant_id, dictionary_id, label, value, description, sort_order, is_active, created_at, updated_at
        )
        SELECT
            gen_random_uuid()::text,
            d.tenant_id,
            d.id,
            '{label}',
            '{value}',
            '{description}',
            {sort_order},
            TRUE,
            NOW(),
            NOW()
        FROM core_data_dictionaries d
        WHERE d.code = 'CURRENCY'
          AND d.deleted_at IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM core_dictionary_items i
            WHERE i.tenant_id = d.tenant_id
              AND i.dictionary_id = d.id
              AND i.value = '{value}'
              AND i.deleted_at IS NULL
          );
        """
        )
    return "\n".join(item_inserts)


async def downgrade(db: BaseDBAsyncClient) -> str:
    values = ", ".join(f"'{v}'" for _, _, v, _ in _ITEMS)
    return f"""
        DELETE FROM core_dictionary_items i
        USING core_data_dictionaries d
        WHERE i.dictionary_id = d.id
          AND d.code = 'CURRENCY'
          AND i.value IN ({values});
    """
