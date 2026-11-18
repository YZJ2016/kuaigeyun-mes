"""付款单列表读侧 enrichment（关联应付总额等）。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Sequence, Set

from apps.kuaicaiwu.models.payable import Payable
from apps.kuaicaiwu.models.payment_pull_line import PaymentPullLine

_MONEY = Decimal("0.01")


def _money(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value)).quantize(_MONEY)


async def enrich_payment_list_linked_payable_totals(
    tenant_id: int,
    items: Sequence[Any],
) -> None:
    """
    为列表项填充关联应付单总额与剩余（来自 pull_lines.source_type=payable）。
    无关联应付时不写字段（前端展示 —）。
    """
    if not items:
        return
    payment_ids: List[int] = []
    for row in items:
        pid = getattr(row, "id", None)
        if pid is None and isinstance(row, dict):
            pid = row.get("id")
        if pid is not None and int(pid) > 0:
            payment_ids.append(int(pid))
    if not payment_ids:
        return

    pull_rows = await PaymentPullLine.filter(
        tenant_id=tenant_id,
        payment_id__in=payment_ids,
        source_type="payable",
        deleted_at__isnull=True,
    ).values("payment_id", "source_id")

    payable_ids_by_payment: Dict[int, Set[int]] = {}
    all_payable_ids: Set[int] = set()
    for ln in pull_rows:
        pay_id = int(ln["payment_id"])
        src_id = int(ln["source_id"])
        if src_id <= 0:
            continue
        payable_ids_by_payment.setdefault(pay_id, set()).add(src_id)
        all_payable_ids.add(src_id)

    if not all_payable_ids:
        return

    payable_rows = await Payable.filter(
        tenant_id=tenant_id,
        id__in=list(all_payable_ids),
        deleted_at__isnull=True,
    ).values("id", "total_amount", "remaining_amount")
    payable_by_id = {int(r["id"]): r for r in payable_rows}

    for row in items:
        pid = int(getattr(row, "id", None) or (row.get("id") if isinstance(row, dict) else 0) or 0)
        ids = payable_ids_by_payment.get(pid)
        if not ids:
            continue
        total_sum = Decimal("0")
        remaining_sum = Decimal("0")
        for payable_id in ids:
            rec = payable_by_id.get(payable_id)
            if not rec:
                continue
            total_sum += _money(rec.get("total_amount"))
            remaining_sum += _money(rec.get("remaining_amount"))
        if total_sum <= 0:
            continue
        payload = {
            "linked_payable_total_amount": total_sum,
            "linked_payable_remaining_amount": remaining_sum,
        }
        if isinstance(row, dict):
            row.update(payload)
        else:
            for key, val in payload.items():
                setattr(row, key, val)
