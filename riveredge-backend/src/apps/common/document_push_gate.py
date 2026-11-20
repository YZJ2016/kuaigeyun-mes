"""宿主外推 DocumentPush 薄代理：仅快连接 ORM 就绪时加载 kuaiconnect.document_push。"""

from __future__ import annotations

from typing import Any, TypeVar

from apps.common.optional_pro import import_pro_attr, require_pro_orm

T = TypeVar("T")


def load_document_push_attr(module_leaf: str, attr: str) -> Any:
    """例：load_document_push_attr('document_push_service', 'DocumentPushService')"""
    require_pro_orm("kuaiconnect")
    return import_pro_attr(
        f"apps.kuaiconnect.services.document_push.{module_leaf}",
        attr,
    )


def document_push_service() -> Any:
    cls = load_document_push_attr("document_push_service", "DocumentPushService")
    return cls()
