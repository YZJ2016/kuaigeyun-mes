"""采购管理单据表头增加部门（id + 名称快照），供下推带入。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True

# (table, index_name)
_TABLES: tuple[tuple[str, str], ...] = (
    ("apps_kuaizhizao_purchase_requisitions", "idx_kz_pr_tenant_dept"),
    ("apps_kuaizhizao_purchase_inquiries", "idx_kz_pi_tenant_dept"),
    ("apps_kuaizhizao_purchase_orders", "idx_kz_po_tenant_dept"),
    ("apps_kuaizhizao_purchase_order_change_orders", "idx_kz_poc_tenant_dept"),
    ("apps_kuaizhizao_receipt_notices", "idx_kz_rn_tenant_dept"),
    ("apps_kuaizhizao_purchase_receipts", "idx_kz_prec_tenant_dept"),
    ("apps_kuaizhizao_purchase_returns", "idx_kz_pret_tenant_dept"),
)


async def upgrade(db: BaseDBAsyncClient) -> str:
    stmts: list[str] = []
    for table, idx in _TABLES:
        stmts.append(
            f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "department_id" INT'
        )
        stmts.append(
            f'ALTER TABLE "{table}"'
            f' ADD COLUMN IF NOT EXISTS "department_name" VARCHAR(100)'
        )
        stmts.append(
            f'CREATE INDEX IF NOT EXISTS "{idx}" ON "{table}" ("tenant_id", "department_id")'
        )
    return ";\n".join(stmts) + ";"


async def downgrade(db: BaseDBAsyncClient) -> str:
    stmts: list[str] = []
    for table, idx in _TABLES:
        stmts.append(f'DROP INDEX IF EXISTS "{idx}"')
        stmts.append(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS "department_name"')
        stmts.append(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS "department_id"')
    return ";\n".join(stmts) + ";"
