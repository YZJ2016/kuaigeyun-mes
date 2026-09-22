"""科目余额汇总：辅助核算合并、上下级科目轧卷。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional

BALANCE_AMOUNT_FIELDS = (
    "opening_debit",
    "opening_credit",
    "period_debit",
    "period_credit",
    "year_debit",
    "year_credit",
    "ending_debit",
    "ending_credit",
)


def _d(v: Any) -> Decimal:
    return Decimal(str(v or 0))


def recompute_ending_fields(row: Dict[str, Any]) -> None:
    """期初 + 本期发生额轧差到期末借/贷。"""
    debit = _d(row.get("opening_debit")) + _d(row.get("period_debit"))
    credit = _d(row.get("opening_credit")) + _d(row.get("period_credit"))
    if debit >= credit:
        row["ending_debit"] = float(debit - credit)
        row["ending_credit"] = 0.0
    else:
        row["ending_credit"] = float(credit - debit)
        row["ending_debit"] = 0.0


def aggregate_balances_by_account(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按科目汇总，合并辅助核算拆行。"""
    by_account: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        account_id = int(row.get("account_id") or 0)
        if not account_id:
            continue
        item = by_account.get(account_id)
        if not item:
            item = {
                "account_id": account_id,
                "account_code": row.get("account_code"),
                "account_name": row.get("account_name") or "",
                "account_type": row.get("account_type") or "",
                **{field: 0.0 for field in BALANCE_AMOUNT_FIELDS},
            }
            by_account[account_id] = item
        for field in BALANCE_AMOUNT_FIELDS:
            item[field] = float(_d(item[field]) + _d(row.get(field)))
    result = list(by_account.values())
    for item in result:
        recompute_ending_fields(item)
    result.sort(key=lambda x: str(x.get("account_code") or ""))
    return result


def _empty_account_bucket(account: Any) -> Dict[str, Any]:
    return {
        "account_id": int(account.id),
        "account_code": account.account_code,
        "account_name": account.account_name,
        "account_type": account.account_type,
        **{field: 0.0 for field in BALANCE_AMOUNT_FIELDS},
    }


def _row_has_activity(row: Mapping[str, Any]) -> bool:
    return any(_d(row.get(field)) != 0 for field in BALANCE_AMOUNT_FIELDS)


def rollup_balances_to_ancestors(
    rows: List[Dict[str, Any]],
    accounts_by_id: Dict[int, Any],
) -> List[Dict[str, Any]]:
    """
    将下级科目余额逐层累加到上级科目（科目余额表/总账展示口径）。
    输入须已按 account_id 合并辅助核算。
    """
    if not rows:
        return []

    buckets: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        account_id = int(row.get("account_id") or 0)
        if not account_id:
            continue
        bucket = buckets.get(account_id)
        if not bucket:
            account = accounts_by_id.get(account_id)
            bucket = dict(row)
            if account:
                bucket["account_code"] = account.account_code
                bucket["account_name"] = account.account_name
                bucket["account_type"] = account.account_type
            buckets[account_id] = bucket
        else:
            for field in BALANCE_AMOUNT_FIELDS:
                bucket[field] = float(_d(bucket[field]) + _d(row.get(field)))

    for row in list(buckets.values()):
        account_id = int(row.get("account_id") or 0)
        account = accounts_by_id.get(account_id)
        if not account:
            continue
        parent_id = int(getattr(account, "parent_id", 0) or 0)
        while parent_id > 0:
            parent = accounts_by_id.get(parent_id)
            if not parent:
                break
            parent_bucket = buckets.get(parent_id)
            if not parent_bucket:
                parent_bucket = _empty_account_bucket(parent)
                buckets[parent_id] = parent_bucket
            for field in BALANCE_AMOUNT_FIELDS:
                parent_bucket[field] = float(
                    _d(parent_bucket[field]) + _d(row.get(field))
                )
            parent_id = int(getattr(parent, "parent_id", 0) or 0)

    result = [row for row in buckets.values() if _row_has_activity(row)]
    for row in result:
        recompute_ending_fields(row)
    result.sort(key=lambda x: str(x.get("account_code") or ""))
    return result
