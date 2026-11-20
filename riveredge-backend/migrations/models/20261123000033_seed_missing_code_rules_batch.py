"""
补种缺失编码规则（跨租户）。

1) 主租户缺口：资金调拨 / 样机制作书
2) 设备维保主数据：点检项、保养方案/项、巡检路线、模具/工装保养维修方案与项目
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True

_RULES = [
    {
        "code": "FUND_TRANSFER_CODE",
        "name": "资金调拨编码规则",
        "description": "资金调拨编码规则，格式：ZD + 日期（YYYYMMDD）+ 4位序号，每日重置",
        "components": (
            '[{"type":"fixed_text","order":0,"text":"ZD"},'
            '{"type":"date","order":1,"format_type":"preset","preset_format":"YYYYMMDD"},'
            '{"type":"auto_counter","order":2,"digits":4,"fixed_width":true,'
            '"reset_cycle":"daily","initial_value":1}]'
        ),
        "seq_reset_rule": "daily",
    },
    {
        "code": "KUAI_PLM_PROTOTYPE_BUILD_SHEET_CODE",
        "name": "样机制作书编码规则",
        "description": "样机制作书编码规则，格式：YJZZ + 4位序号",
        "components": (
            '[{"type":"fixed_text","order":0,"text":"YJZZ"},'
            '{"type":"auto_counter","order":1,"digits":4,"fixed_width":true,'
            '"reset_cycle":"never","initial_value":1}]'
        ),
        "seq_reset_rule": "never",
    },
    {
        "code": "EQUIPMENT_INSPECTION_ITEM_CODE",
        "name": "点检项编码规则",
        "description": "点检项编码规则，格式：DJX + 4位序号",
        "components": (
            '[{"type":"fixed_text","order":0,"text":"DJX"},'
            '{"type":"auto_counter","order":1,"digits":4,"fixed_width":true,'
            '"reset_cycle":"never","initial_value":1}]'
        ),
        "seq_reset_rule": "never",
    },
    {
        "code": "EQUIPMENT_MAINTENANCE_ITEM_CODE",
        "name": "保养项编码规则",
        "description": "保养项编码规则，格式：BYX + 4位序号",
        "components": (
            '[{"type":"fixed_text","order":0,"text":"BYX"},'
            '{"type":"auto_counter","order":1,"digits":4,"fixed_width":true,'
            '"reset_cycle":"never","initial_value":1}]'
        ),
        "seq_reset_rule": "never",
    },
    {
        "code": "EQUIPMENT_MAINTENANCE_SCHEME_CODE",
        "name": "保养方案编码规则",
        "description": "保养方案编码规则，格式：BYFA + 4位序号",
        "components": (
            '[{"type":"fixed_text","order":0,"text":"BYFA"},'
            '{"type":"auto_counter","order":1,"digits":4,"fixed_width":true,'
            '"reset_cycle":"never","initial_value":1}]'
        ),
        "seq_reset_rule": "never",
    },
    {
        "code": "EQUIPMENT_PATROL_ROUTE_CODE",
        "name": "巡检路线编码规则",
        "description": "巡检路线编码规则，格式：XJLX + 4位序号",
        "components": (
            '[{"type":"fixed_text","order":0,"text":"XJLX"},'
            '{"type":"auto_counter","order":1,"digits":4,"fixed_width":true,'
            '"reset_cycle":"never","initial_value":1}]'
        ),
        "seq_reset_rule": "never",
    },
    {
        "code": "MOLD_MAINTENANCE_ITEM_CODE",
        "name": "模具保养项编码规则",
        "description": "模具保养项编码规则，格式：MJBYX + 4位序号",
        "components": (
            '[{"type":"fixed_text","order":0,"text":"MJBYX"},'
            '{"type":"auto_counter","order":1,"digits":4,"fixed_width":true,'
            '"reset_cycle":"never","initial_value":1}]'
        ),
        "seq_reset_rule": "never",
    },
    {
        "code": "MOLD_MAINTENANCE_SCHEME_CODE",
        "name": "模具保养方案编码规则",
        "description": "模具保养方案编码规则，格式：MJBYFA + 4位序号",
        "components": (
            '[{"type":"fixed_text","order":0,"text":"MJBYFA"},'
            '{"type":"auto_counter","order":1,"digits":4,"fixed_width":true,'
            '"reset_cycle":"never","initial_value":1}]'
        ),
        "seq_reset_rule": "never",
    },
    {
        "code": "MOLD_REPAIR_ITEM_CODE",
        "name": "模具维修项编码规则",
        "description": "模具维修项编码规则，格式：MJWXX + 4位序号",
        "components": (
            '[{"type":"fixed_text","order":0,"text":"MJWXX"},'
            '{"type":"auto_counter","order":1,"digits":4,"fixed_width":true,'
            '"reset_cycle":"never","initial_value":1}]'
        ),
        "seq_reset_rule": "never",
    },
    {
        "code": "MOLD_REPAIR_SCHEME_CODE",
        "name": "模具维修方案编码规则",
        "description": "模具维修方案编码规则，格式：MJWXFA + 4位序号",
        "components": (
            '[{"type":"fixed_text","order":0,"text":"MJWXFA"},'
            '{"type":"auto_counter","order":1,"digits":4,"fixed_width":true,'
            '"reset_cycle":"never","initial_value":1}]'
        ),
        "seq_reset_rule": "never",
    },
    {
        "code": "TOOL_MAINTENANCE_ITEM_CODE",
        "name": "工装保养项编码规则",
        "description": "工装保养项编码规则，格式：GZBYX + 4位序号",
        "components": (
            '[{"type":"fixed_text","order":0,"text":"GZBYX"},'
            '{"type":"auto_counter","order":1,"digits":4,"fixed_width":true,'
            '"reset_cycle":"never","initial_value":1}]'
        ),
        "seq_reset_rule": "never",
    },
    {
        "code": "TOOL_MAINTENANCE_SCHEME_CODE",
        "name": "工装保养方案编码规则",
        "description": "工装保养方案编码规则，格式：GZBYFA + 4位序号",
        "components": (
            '[{"type":"fixed_text","order":0,"text":"GZBYFA"},'
            '{"type":"auto_counter","order":1,"digits":4,"fixed_width":true,'
            '"reset_cycle":"never","initial_value":1}]'
        ),
        "seq_reset_rule": "never",
    },
    {
        "code": "TOOL_REPAIR_ITEM_CODE",
        "name": "工装修修项编码规则",
        "description": "工装修修项编码规则，格式：GZWXX + 4位序号",
        "components": (
            '[{"type":"fixed_text","order":0,"text":"GZWXX"},'
            '{"type":"auto_counter","order":1,"digits":4,"fixed_width":true,'
            '"reset_cycle":"never","initial_value":1}]'
        ),
        "seq_reset_rule": "never",
    },
    {
        "code": "TOOL_REPAIR_SCHEME_CODE",
        "name": "工装修修方案编码规则",
        "description": "工装修修方案编码规则，格式：GZWXFA + 4位序号",
        "components": (
            '[{"type":"fixed_text","order":0,"text":"GZWXFA"},'
            '{"type":"auto_counter","order":1,"digits":4,"fixed_width":true,'
            '"reset_cycle":"never","initial_value":1}]'
        ),
        "seq_reset_rule": "never",
    },
]


def _insert_rule_sql(rule: dict) -> str:
    components = rule["components"].replace("'", "''")
    desc = rule["description"].replace("'", "''")
    rule_name = rule["name"].replace("'", "''")
    rule_code = rule["code"]
    reset = rule["seq_reset_rule"]
    return f"""
        INSERT INTO "core_code_rules" (
            "uuid", "tenant_id", "name", "code", "rule_components", "description",
            "seq_start", "seq_step", "seq_reset_rule", "is_system", "is_active",
            "allow_manual_edit", "created_at", "updated_at"
        )
        SELECT
            gen_random_uuid()::text,
            t."tenant_id",
            '{rule_name}',
            '{rule_code}',
            '{components}'::jsonb,
            '{desc}',
            1, 1, '{reset}', TRUE, TRUE, TRUE, NOW(), NOW()
        FROM (
            SELECT DISTINCT "tenant_id"
            FROM "core_code_rules"
            WHERE "tenant_id" IS NOT NULL AND "deleted_at" IS NULL
        ) t
        WHERE NOT EXISTS (
            SELECT 1 FROM "core_code_rules" r
            WHERE r."tenant_id" = t."tenant_id"
              AND r."code" = '{rule_code}'
              AND r."deleted_at" IS NULL
        );
    """


async def upgrade(db: BaseDBAsyncClient) -> str:
    return "\n".join(_insert_rule_sql(rule) for rule in _RULES)


async def downgrade(db: BaseDBAsyncClient) -> str:
    codes = ", ".join(f"'{r['code']}'" for r in _RULES)
    return f"""
        DELETE FROM "core_code_rules"
        WHERE "code" IN ({codes})
          AND "is_system" = TRUE
          AND "deleted_at" IS NULL;
    """
