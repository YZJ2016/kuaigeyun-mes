"""ERP 适配器：金蝶等厂商行过滤与口径，供入站同步共用。"""

from core.services.integration.erp_adapters.kingdee_active_rows import (
    filter_kingdee_master_rows_active,
    stamp_kingdee_sync_is_active,
)

__all__ = [
    "filter_kingdee_master_rows_active",
    "stamp_kingdee_sync_is_active",
]
