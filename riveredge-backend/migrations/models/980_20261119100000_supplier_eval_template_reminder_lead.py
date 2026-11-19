"""评价模板：到期预警提前天数（R-03）。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_supplier_eval_templates"
            ADD COLUMN IF NOT EXISTS "reminder_lead_days" INT NOT NULL DEFAULT 7;
        COMMENT ON COLUMN "apps_kuaizhizao_supplier_eval_templates"."reminder_lead_days"
            IS '到期前提醒提前天数（模板默认；评价计划可覆盖）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_supplier_eval_templates"
            DROP COLUMN IF EXISTS "reminder_lead_days";
    """