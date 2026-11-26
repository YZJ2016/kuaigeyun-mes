"""
返工单编码规则改为 FR + 产品线码 + 两位年 + 3 位流水（按产品线隔离）。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True

_REWORK_COMPONENTS = (
    "["
    '{"type":"fixed_text","order":0,"text":"FR"},'
    '{"type":"form_field","order":1,"field_name":"product_line_code"},'
    '{"type":"date","order":2,"format_type":"preset","preset_format":"YY"},'
    '{"type":"auto_counter","order":3,"digits":3,"fixed_width":true,'
    '"reset_cycle":"never","initial_value":1,"scope_fields":["product_line_code"]}'
    "]"
)


async def upgrade(db: BaseDBAsyncClient) -> str:
    return f"""
        UPDATE "core_code_rules"
        SET
            "expression" = 'FR{{product_line_code}}{{YY}}{{SEQ:3}}',
            "rule_components" = '{_REWORK_COMPONENTS}'::jsonb,
            "description" = '返工单编码规则，格式：FR + 产品线码 + 两位年 + 3位流水（按产品线隔离）',
            "updated_at" = NOW()
        WHERE "code" = 'REWORK_ORDER_CODE'
          AND "deleted_at" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "core_code_rules"
        SET
            "expression" = 'FGD{YYYY}{MM}{DD}{SEQ:4}',
            "rule_components" = '[
              {"text":"FGD","type":"fixed_text","order":0},
              {"type":"date","order":1,"format_type":"preset","preset_format":"YYYYMMDD"},
              {"type":"auto_counter","order":2,"digits":4,"fixed_width":true,"reset_cycle":"daily","initial_value":1}
            ]'::jsonb,
            "description" = '返工单编码规则，格式：FGD + 日期（YYYYMMDD）+ 4位序号，每日重置',
            "updated_at" = NOW()
        WHERE "code" = 'REWORK_ORDER_CODE'
          AND "deleted_at" IS NULL;
    """
