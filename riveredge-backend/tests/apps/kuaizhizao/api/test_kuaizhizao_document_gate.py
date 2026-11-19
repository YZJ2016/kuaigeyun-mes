"""系统内下推 / 外推权限码映射回归（纯函数，无 DB）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from apps.kuaizhizao.api.document_push_pull import document_push_pull as routes

from apps.kuaizhizao.api._kuaizhizao_document_gate import (
    all_reverse_permission_codes,
    resolve_external_push_permission,
    resolve_internal_pull_permissions,
    resolve_internal_push_permissions,
    resolve_reverse_permission,
)


def test_external_push_maps_known_sources():
    assert resolve_external_push_permission("sales_order") == "kuaizhizao:sales-order:push"
    assert resolve_external_push_permission("work_order") == "kuaizhizao:work-order:push"
    assert resolve_external_push_permission("material") == "master-data:material:push"


def test_external_push_rejects_unknown_source():
    with pytest.raises(HTTPException) as exc:
        resolve_external_push_permission("unknown_type")
    assert exc.value.status_code == 403


def test_sales_and_purchase_external_push_permission_codes():
    assert resolve_external_push_permission("sales_order") == "kuaizhizao:sales-order:push"
    assert resolve_external_push_permission("purchase_order") == "kuaizhizao:purchase-order:push"
    assert resolve_external_push_permission("sales_delivery") == "kuaizhizao:outbound:push"


def test_sales_order_reverse_is_revoke_code():
    assert resolve_reverse_permission("sales_order") == "kuaizhizao:sales-order:revoke"
    assert resolve_reverse_permission("work_order") == "kuaizhizao:work-order:revoke"


def test_unknown_reverse_type_is_403():
    with pytest.raises(HTTPException) as exc:
        resolve_reverse_permission("purchase_order")
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "REVERSE_TYPE_NOT_ALLOWED"


def test_internal_push_rejects_unknown_pair_is_403():
    with pytest.raises(HTTPException) as exc:
        resolve_internal_push_permissions("sales_order", "unknown_target")
    assert exc.value.status_code == 403


def test_internal_push_pairs():
    assert resolve_internal_push_permissions("demand_computation", "work_order") == (
        "kuaizhizao:work-order:create",
    )
    assert resolve_internal_push_permissions("purchase_receipt", "incoming_inspection") == (
        "kuaizhizao:quality-management-incoming-inspection:create",
    )


def test_internal_push_rejects_unknown_pair():
    with pytest.raises(HTTPException):
        resolve_internal_push_permissions("sales_order", "work_order")


def test_internal_pull_and_reverse():
    assert resolve_internal_pull_permissions("demand_computation", "work_order") == (
        "kuaizhizao:plan-management-demand-computation:update",
    )
    assert resolve_reverse_permission("sales_order") == "kuaizhizao:sales-order:revoke"
    assert "kuaizhizao:work-order:revoke" in all_reverse_permission_codes()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,body,code",
    [
        ("push", {"source_type": "demand_computation", "source_id": 1, "target_type": "work_order"},
         "kuaizhizao:work-order:create"),
        ("pull", {"source_type": "demand_computation", "source_id": 1, "target_type": "work_order", "target_id": 2},
         "kuaizhizao:plan-management-demand-computation:update"),
        ("reverse", {"document_type": "work_order", "document_id": 1, "reverse_type": "revoke_state"},
         "kuaizhizao:work-order:revoke"),
    ],
)
async def test_permission_denial_prevents_document_mutation(monkeypatch, action, body, code):
    guard = AsyncMock(side_effect=HTTPException(status_code=403, detail="denied"))
    service = MagicMock()
    engine = MagicMock()
    monkeypatch.setattr(routes, "ensure_permission_codes", guard)
    monkeypatch.setattr(routes, "DocumentPushPullService", service)
    monkeypatch.setattr(routes, "DocumentStateEngine", engine)
    auth = SimpleNamespace()
    http_request = SimpleNamespace()
    with pytest.raises(HTTPException) as exc:
        await getattr(routes, f"{action}_document")(
            request=SimpleNamespace(**body), http_request=http_request,
            auth=auth, current_user=SimpleNamespace(id=7), tenant_id=11,
        )
    assert exc.value.status_code == 403
    guard.assert_awaited_once_with(
        auth, 11, http_request, [code], require_all=True, check_abac=False,
    )
    service.assert_not_called()
    engine.assert_not_called()
