"""KU-AI Tool 目录合并改名（spec 190）：改写档案 ``enabled_tools`` 旧名→新名。

11 个存量 Tool 合并改名为 9 个：工单双视图并入 ``query_work_orders``，
两个采购查询并入 ``query_purchase_orders``，其余只读 Tool 改名。
本迁移为纯数据迁移（JSONB 列内容改写），无 DDL：

- 跨租户逐行改写 ``apps_kuaiai_agent_profiles.enabled_tools``；
- 去重保序（按新名首次出现位置）；无旧名的行不写；
- 只改 ``enabled_tools`` 列，不动 ``tenant_id`` 与
  ``updated_at`` / ``updated_by``——改写审计字段会伪造用户操作痕迹。

downgrade 为**有损回退**：合并组无法区分迁移前持有的是哪个旧名，
一律还原为各组第一个旧名（``query_work_orders`` → ``query_workorder``、
``query_purchase_orders`` → ``query_purchase_followup``）。
"""

from __future__ import annotations

import json

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True

# 旧名 → 新名（spec 190 Scope 表）
_UPGRADE_MAP = {
    "query_workorder": "query_work_orders",
    "list_workorder_tasks": "query_work_orders",
    "query_purchase_followup": "query_purchase_orders",
    "query_supplier_orders": "query_purchase_orders",
    "query_inventory_balance": "query_inventory",
    "query_delivery_risk": "analyze_delivery_risk",
    "query_published_schedule": "query_schedule",
    "query_quality_anomalies": "analyze_quality",
}

# 新名 → 旧名（有损：合并组还原为各组第一个旧名）
_DOWNGRADE_MAP = {
    "query_work_orders": "query_workorder",
    "query_purchase_orders": "query_purchase_followup",
    "query_inventory": "query_inventory_balance",
    "analyze_delivery_risk": "query_delivery_risk",
    "query_schedule": "query_published_schedule",
    "analyze_quality": "query_quality_anomalies",
}


def _remap_enabled_tools(raw, mapping):
    """映射 + 去重保序；无映射命中或结果不变返回 None（该行不改写）。"""
    if not isinstance(raw, list):
        return None
    out = []
    hit = False
    for item in raw:
        name = str(item or "").strip() if isinstance(item, str) else item
        new = mapping.get(name, name) if isinstance(name, str) else name
        if new != name:
            hit = True
        if isinstance(new, str) and not new:
            continue
        if new not in out:
            out.append(new)
    if not hit or out == raw:
        return None
    return out


async def _rewrite(db: BaseDBAsyncClient, mapping) -> None:
    rows = await db.execute_query_dict(
        """
        SELECT "id", "enabled_tools"
        FROM "apps_kuaiai_agent_profiles"
        """
    )
    for row in rows:
        new_tools = _remap_enabled_tools(row.get("enabled_tools"), mapping)
        if new_tools is None:
            continue
        await db.execute_query(
            """
            UPDATE "apps_kuaiai_agent_profiles"
            SET "enabled_tools" = $1::jsonb
            WHERE "id" = $2
            """,
            [json.dumps(new_tools, ensure_ascii=False), int(row["id"])],
        )


async def upgrade(db: BaseDBAsyncClient) -> str:
    await _rewrite(db, _UPGRADE_MAP)
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    await _rewrite(db, _DOWNGRADE_MAP)
    return "SELECT 1;"
