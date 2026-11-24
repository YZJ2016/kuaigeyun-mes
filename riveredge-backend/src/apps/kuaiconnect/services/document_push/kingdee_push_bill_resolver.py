"""兼容 re-export：真源在 apps.kuaizhizao.services.kingdee_push_bill_resolver。"""

from apps.kuaizhizao.services.kingdee_push_bill_resolver import (  # noqa: F401
    KINGDEE_DEFICIT_TARGET,
    KINGDEE_SURPLUS_TARGET,
    KingdeeStocktakingPushBills,
    resolve_kingdee_push_bill_no,
    resolve_kingdee_stocktaking_push_bills,
)