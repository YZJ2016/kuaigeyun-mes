"""仓储单据金蝶操作员/领用人工号（真源 User.employee_number，禁止登录名）。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.services.integration.kingdee_bizuser_resolver import resolve_kingdee_bizuser_number

KINGDEE_PICKER_OPERATOR_CONFIG_KEYS = (
    "pickeroperator_operatornumber",
    "pickeroperator_number",
    "picker_number",
    "bizuser_number",
    "bizoperator_operatornumber",
    "consumer_number",
)

KINGDEE_INBOUND_OPERATOR_CONFIG_KEYS = (
    "operator_operatornumber",
    "bizoperator_operatornumber",
    "operator_number",
    "buyer_operatornumber",
)


def strip_kingdee_operator_config_keys(
    config: Dict[str, Any],
    *,
    keys: tuple[str, ...] = KINGDEE_PICKER_OPERATOR_CONFIG_KEYS,
) -> Dict[str, Any]:
    out = dict(config)
    for key in keys:
        out.pop(key, None)
    return out


async def resolve_document_operator_number(
    tenant_id: int,
    user_id: Optional[int],
    *,
    explicit: Optional[str] = None,
) -> Optional[str]:
    """解析单据操作员工号。

    真源是 ``User.employee_number``。有 ``user_id`` 时以该用户工号为准，
    **忽略**可能属于上一任选人的陈旧 ``explicit``（编辑采购员后隐藏字段未刷新的血泪）。
    仅在未选人时才回落到 ``explicit``。
    """
    uid = int(user_id or 0)
    if uid > 0:
        from_user = await resolve_kingdee_bizuser_number(tenant_id, uid)
        if from_user:
            return from_user
        # 用户无工号：清空，禁止继续沿用上一任采购员的工号
        return None
    text = str(explicit or "").strip()
    return text or None


async def sync_other_outbound_picker_operator_fields(
    tenant_id: int,
    fields: Dict[str, Any],
) -> None:
    """写入/更新其他出库表头时，按 picker_id 补齐 picker_operator_number。"""
    picker_id = fields.get("picker_id")
    if picker_id is None and "picker_operator_number" not in fields:
        return
    resolved = await resolve_document_operator_number(
        tenant_id,
        int(picker_id) if picker_id is not None and int(picker_id or 0) > 0 else None,
        explicit=fields.get("picker_operator_number"),
    )
    if resolved:
        fields["picker_operator_number"] = resolved
    elif picker_id is not None and int(picker_id or 0) > 0:
        fields["picker_operator_number"] = None
