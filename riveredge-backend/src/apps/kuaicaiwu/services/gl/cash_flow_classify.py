"""现金流量项目归类：凭证现金行写入与报表汇总共用。"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from apps.kuaicaiwu.models.chart_of_account import ChartOfAccount
from apps.kuaicaiwu.models.gl_cash_flow_item import GlCashFlowItem
from apps.kuaicaiwu.services.gl.cash_flow_statement_template import DEFAULT_CASH_FLOW_SEED

# 业务事件模板 → 现金/银行分录默认现金流量项目
TEMPLATE_CASH_FLOW_ITEM: Dict[str, str] = {
    "receipt_confirmed": "CF01",
    "receipt_refund": "CF01",
    "payment_confirmed": "CF03",
    "payment_refund": "CF03",
    "customer_prepayment": "CF01",
    "supplier_prepayment": "CF03",
}

# 对方科目编码前缀 → 流入/流出项目（无显式 cash_flow_item_id 时按直接法推断）
_INFLOW_COUNTERPART_PREFIXES: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("1122", "6001", "6051"), "CF01"),
    (("2203",), "CF01"),
    (("1511", "1512", "1101"), "CF08"),
    (("1131", "1132"), "CF09"),
    (("1601", "1606", "1701"), "CF10"),
    (("2001",), "CF14"),
    (("4001",), "CF15"),
)

_OUTFLOW_COUNTERPART_PREFIXES: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("2202", "1123", "1403", "1405", "1401"), "CF03"),
    (("2211",), "CF04"),
    (("2221",), "CF05"),
    (("1601", "1606", "1701"), "CF12"),
    (("1511", "1512", "1101"), "CF11"),
    (("2001",), "CF16"),
    (("2231",), "CF17"),
    (("2232", "4104"), "CF18"),
)


async def ensure_cash_flow_items_seeded(tenant_id: int) -> None:
    """租户无现金流量项目字典时写入标准种子（幂等）。"""
    for item in DEFAULT_CASH_FLOW_SEED:
        exists = await GlCashFlowItem.filter(
            tenant_id=tenant_id, item_code=item["item_code"], deleted_at__isnull=True
        ).exists()
        if exists:
            continue
        await GlCashFlowItem.create(tenant_id=tenant_id, uuid=str(uuid.uuid4()), **item)


async def resolve_cash_flow_item_id(tenant_id: int, item_code: str) -> Optional[int]:
    code = str(item_code or "").strip()
    if not code:
        return None
    await ensure_cash_flow_items_seeded(tenant_id)
    row = await GlCashFlowItem.get_or_none(
        tenant_id=tenant_id, item_code=code, deleted_at__isnull=True, is_active=True
    )
    return int(row.id) if row else None


def is_monetary_account(
    account: ChartOfAccount,
    *,
    designated_ids: Optional[set[int]] = None,
) -> bool:
    """现金 / 银行 / 其他货币资金（含下级编码）或设置中指定科目。"""
    if bool(getattr(account, "is_cash_journal", False) or getattr(account, "is_bank_journal", False)):
        return True
    if designated_ids and int(account.id) in designated_ids:
        return True
    code = str(getattr(account, "account_code", "") or "")
    return code.startswith(("1001", "1002", "1012"))


def infer_cash_flow_item_code(
    *,
    cash_debit: Any,
    cash_credit: Any,
    counterpart_account_codes: Sequence[str],
) -> str:
    """按现金行借贷与对方科目推断 CF 编码。"""
    from decimal import Decimal

    debit = Decimal(str(cash_debit or 0))
    credit = Decimal(str(cash_credit or 0))
    is_inflow = debit > credit
    prefixes = _INFLOW_COUNTERPART_PREFIXES if is_inflow else _OUTFLOW_COUNTERPART_PREFIXES
    default_code = "CF02" if is_inflow else "CF06"
    for code in counterpart_account_codes:
        text = str(code or "").strip()
        if not text:
            continue
        for prefix_group, item_code in prefixes:
            if any(text.startswith(p) for p in prefix_group):
                return item_code
    return default_code


def template_cash_flow_item_code(template_key: str) -> Optional[str]:
    return TEMPLATE_CASH_FLOW_ITEM.get(str(template_key or "").strip())


def pick_counterpart_codes(
    cash_line_account_id: int,
    lines: List[Dict[str, Any]],
    account_code_by_id: Dict[int, str],
) -> List[str]:
    """同一凭证中非现金分录的科目编码（按金额降序）。"""
    from decimal import Decimal

    scored: List[Tuple[Decimal, str]] = []
    for line in lines:
        aid = int(line.get("account_id") or 0)
        if not aid or aid == cash_line_account_id:
            continue
        code = account_code_by_id.get(aid) or str(line.get("account_code") or "")
        if not code:
            continue
        amt = Decimal(str(line.get("debit_amount") or 0)) + Decimal(
            str(line.get("credit_amount") or 0)
        )
        scored.append((amt, code))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [code for _, code in scored]
