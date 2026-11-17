"""客商默认付款方式与结算方式码表（由原 settlement_method_code 拆分）。"""

from __future__ import annotations

from typing import Optional, Tuple

PARTNER_PAYMENT_METHOD_CODES = frozenset(
    {
        "cash",
        "bank_transfer",
        "bank_acceptance",
        "commercial_acceptance",
        "other",
    }
)

# 结算方式（付款节点；周期类账期用 net_terms + payment_terms_days）
PARTNER_SETTLEMENT_TERMS_CODES = frozenset(
    {
        "prepaid",
        "pay_before_ship",
        "spot",
        "cod",
        "net_terms",
        "installment",
        "progress",
        "pay_on_invoice",
    }
)

# 历史库值 / 旧导入，读入时归并为 net_terms
_LEGACY_PERIOD_SETTLEMENT_TERMS = frozenset({"monthly", "bimonthly", "quarterly"})

_SETTLEMENT_TERMS_CN_ALIASES = {
    "月结": "net_terms",
    "双月结": "net_terms",
    "季结": "net_terms",
    "季度结": "net_terms",
    "预付款": "prepaid",
    "预付": "prepaid",
    "款到发货": "pay_before_ship",
    "先款后货": "pay_before_ship",
    "现款现货": "spot",
    "货到付款": "cod",
    "账期结算": "net_terms",
    "账期": "net_terms",
    "分期付款": "installment",
    "分期": "installment",
    "进度款": "progress",
    "按进度": "progress",
    "票到付款": "pay_on_invoice",
    "见票付款": "pay_on_invoice",
    "票到付": "pay_on_invoice",
}

_LEGACY_PAYMENT_METHOD_CODES = PARTNER_PAYMENT_METHOD_CODES
_LEGACY_SETTLEMENT_TERMS_CODES = (
    PARTNER_SETTLEMENT_TERMS_CODES | _LEGACY_PERIOD_SETTLEMENT_TERMS | frozenset(_SETTLEMENT_TERMS_CN_ALIASES.keys())
)


def coerce_partner_payment_method_code(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s if s in PARTNER_PAYMENT_METHOD_CODES else None


def normalize_purchase_receipt_pay_mode(value: Optional[str]) -> Optional[str]:
    """采购入库付款方式落库：客商付款方式码；历史金蝶 CREDIT/CASH 原样保留直至用户改选。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    partner = coerce_partner_payment_method_code(s)
    if partner is not None:
        return partner
    upper = s.upper()
    if upper in {"CREDIT", "CASH"}:
        return upper
    return None


def kingdee_paymode_from_receipt_pay_mode(value: Optional[str]) -> str:
    """外推苍穹 paymode：现金→CASH；其余（含历史赊购 CREDIT、银行类客商码）→CREDIT。"""
    s = str(value or "").strip()
    if not s:
        return "CREDIT"
    upper = s.upper()
    if upper == "CASH":
        return "CASH"
    if upper == "CREDIT":
        return "CREDIT"
    code = coerce_partner_payment_method_code(s)
    if code == "cash":
        return "CASH"
    return "CREDIT"


def coerce_partner_settlement_terms_code(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s in _SETTLEMENT_TERMS_CN_ALIASES:
        return _SETTLEMENT_TERMS_CN_ALIASES[s]
    lowered = s.lower()
    if lowered in _LEGACY_PERIOD_SETTLEMENT_TERMS:
        return "net_terms"
    if lowered in PARTNER_SETTLEMENT_TERMS_CODES:
        return lowered
    return None


def split_legacy_settlement_method_code(
    legacy: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """将旧 settlement_method_code 拆为 (default_payment_method_code, settlement_terms_code)。"""
    if legacy is None:
        return None, None
    s = str(legacy).strip()
    if not s:
        return None, None
    terms = coerce_partner_settlement_terms_code(s)
    if terms is not None and (
        s in _LEGACY_SETTLEMENT_TERMS_CODES or s.lower() in PARTNER_SETTLEMENT_TERMS_CODES | _LEGACY_PERIOD_SETTLEMENT_TERMS
    ):
        return None, terms
    if s in _LEGACY_PAYMENT_METHOD_CODES:
        return s, None
    return None, None


def partner_settlement_terms_for_pricing(partner: object) -> Optional[str]:
    """月结暂估价等：只读结算方式，不再读付款方式。"""
    raw = getattr(partner, "settlement_terms_code", None)
    return coerce_partner_settlement_terms_code(raw)
