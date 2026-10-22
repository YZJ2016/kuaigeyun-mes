"""
质检检验单：物料型号快照；OQC 补规格/型号字段。
"""
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True

_INSPECTION_TABLES_WITH_SPEC = (
    "apps_kuaizhizao_incoming_inspections",
    "apps_kuaizhizao_process_inspections",
    "apps_kuaizhizao_finished_goods_inspections",
    "apps_kuaizhizao_outsource_inspections",
    "apps_kuaizhizao_quality_patrols",
)


def _add_model_column_sql() -> str:
    parts = []
    for table in _INSPECTION_TABLES_WITH_SPEC:
        parts.append(
            f"""
        ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS material_model VARCHAR(200) NULL;
        """
        )
    parts.append(
        """
        ALTER TABLE apps_kuaizhizao_oqc_inspections
            ADD COLUMN IF NOT EXISTS material_spec VARCHAR(200) NULL,
            ADD COLUMN IF NOT EXISTS material_model VARCHAR(200) NULL;
        """
    )
    return "\n".join(parts)


def _backfill_from_materials_sql() -> str:
    parts = []
    all_tables = _INSPECTION_TABLES_WITH_SPEC + ("apps_kuaizhizao_oqc_inspections",)
    for table in all_tables:
        parts.append(
            f"""
        UPDATE {table} qi
        SET material_spec = NULLIF(TRIM(m.specification), '')
        FROM apps_master_data_materials m
        WHERE m.id = qi.material_id
          AND qi.material_spec IS NULL;

        UPDATE {table} qi
        SET material_model = NULLIF(TRIM(m.model), '')
        FROM apps_master_data_materials m
        WHERE m.id = qi.material_id
          AND qi.material_model IS NULL;
        """
        )
    return "\n".join(parts)


async def upgrade(db: BaseDBAsyncClient) -> str:
    return _add_model_column_sql() + _backfill_from_materials_sql()


async def downgrade(db: BaseDBAsyncClient) -> str:
    parts = []
    for table in _INSPECTION_TABLES_WITH_SPEC:
        parts.append(f"ALTER TABLE {table} DROP COLUMN IF EXISTS material_model;")
    parts.append(
        """
        ALTER TABLE apps_kuaizhizao_oqc_inspections
            DROP COLUMN IF EXISTS material_spec,
            DROP COLUMN IF EXISTS material_model;
        """
    )
    return "\n".join(parts)
