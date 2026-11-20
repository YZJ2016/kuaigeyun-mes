"""宿主入站同步薄代理：仅快连接 ORM 就绪时加载 kuaiconnect.inbound_sync。"""

from __future__ import annotations

from typing import Any, TypeVar

from apps.common.optional_pro import import_pro_attr, require_pro_orm

T = TypeVar("T")


def load_inbound_sync_attr(module_leaf: str, attr: str) -> Any:
    """例：load_inbound_sync_attr('sales_order_sync_service', 'SalesOrderSyncService')"""
    require_pro_orm("kuaiconnect")
    return import_pro_attr(
        f"apps.kuaiconnect.services.inbound_sync.{module_leaf}",
        attr,
    )


def inbound_sync_service(module_leaf: str, class_name: str) -> Any:
    cls = load_inbound_sync_attr(module_leaf, class_name)
    return cls()
