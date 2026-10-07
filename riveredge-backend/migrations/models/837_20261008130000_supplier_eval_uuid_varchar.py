"""供方评价相关表 uuid：PG UUID → VARCHAR(36)。

BaseModel.uuid 为 CharField(36)；PG UUID 经 asyncpg 读出为 uuid.UUID，
导致 SupplierEvalTemplateListItem 等 schema.model_validate 失败。
对齐迁移 502（售后单）做法。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


_TABLES = (
    "apps_kuaizhizao_supplier_evaluations",
    "apps_kuaizhizao_supplier_eval_env_docs",
    "apps_kuaizhizao_supplier_eval_templates",
    "apps_kuaizhizao_supplier_eval_template_clauses",
    "apps_kuaizhizao_supplier_evaluation_lines",
    "apps_kuaizhizao_supplier_eval_plans",
    "apps_kuaizhizao_supplier_eval_plan_lines",
)


async def upgrade(db: BaseDBAsyncClient) -> str:
    alters = "\n".join(
        f'ALTER TABLE "{table}" ALTER COLUMN "uuid" TYPE VARCHAR(36) USING "uuid"::text;'
        for table in _TABLES
    )
    return f"""
        {alters}
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    alters = "\n".join(
        f'ALTER TABLE "{table}" ALTER COLUMN "uuid" TYPE UUID USING "uuid"::uuid;'
        for table in _TABLES
    )
    return f"""
        {alters}
    """
