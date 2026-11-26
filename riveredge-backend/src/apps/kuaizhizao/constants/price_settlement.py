"""月结定价常量（开源真源；轻财务包 re-export）。"""

from enum import Enum


class PriceSettlementStatus(str, Enum):
    PROVISIONAL = "PROVISIONAL"
    SETTLED = "SETTLED"


class PriceSettlementSide(str, Enum):
    SALES = "sales"
    PURCHASE = "purchase"


class PriceSettlementBatchStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    APPLIED = "applied"
    CANCELLED = "cancelled"


class PriceSettlementPriceSource(str, Enum):
    MANUAL = "manual"
    PARTNER_BOOK = "partner_book"
    MARKET = "market"
    HISTORY = "history"


# 账期类结算（具体天数见客商 payment_terms_days）；含历史 monthly 等库值
MONTHLY_SETTLEMENT_METHOD_CODES = frozenset(
    {
        "net_terms",
        "monthly",
        "bimonthly",
        "quarterly",
        "月结",
        "双月结",
        "季结",
        "账期",
        "账期结算",
    }
)
