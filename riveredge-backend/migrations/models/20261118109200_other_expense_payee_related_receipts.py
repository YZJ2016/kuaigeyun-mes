"""其他费用支出：明细行员工垫付领款人 + 头表关联采购入库单快照。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_other_expense_lines"
            ADD COLUMN IF NOT EXISTS "payee_id" INT;
        ALTER TABLE "apps_kuaicaiwu_other_expense_lines"
            ADD COLUMN IF NOT EXISTS "payee_name" VARCHAR(100);
        COMMENT ON COLUMN "apps_kuaicaiwu_other_expense_lines"."payee_id"
            IS '领款人用户ID（员工垫付必填）';
        COMMENT ON COLUMN "apps_kuaicaiwu_other_expense_lines"."payee_name"
            IS '领款人姓名快照';
        ALTER TABLE "apps_kuaicaiwu_other_expenses"
            ADD COLUMN IF NOT EXISTS "related_purchase_receipts" JSONB;
        COMMENT ON COLUMN "apps_kuaicaiwu_other_expenses"."related_purchase_receipts"
            IS '关联采购入库单 [{id, code}]（往来类型=供应商时可用）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_other_expense_lines"
            DROP COLUMN IF EXISTS "payee_id";
        ALTER TABLE "apps_kuaicaiwu_other_expense_lines"
            DROP COLUMN IF EXISTS "payee_name";
        ALTER TABLE "apps_kuaicaiwu_other_expenses"
            DROP COLUMN IF EXISTS "related_purchase_receipts";
    """
