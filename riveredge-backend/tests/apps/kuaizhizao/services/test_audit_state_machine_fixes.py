"""审核状态机缺口：发货通知、报工/返工相位、打印门禁、收货通知更新。"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from pydantic import BaseModel

from apps.kuaizhizao.schemas.receipt_notice import ReceiptNoticeResponse
from apps.kuaizhizao.schemas.shipment_notice import ShipmentNoticeResponse
from apps.kuaizhizao.services.document_action_policy.enricher import (
    _attach_capabilities_to_response,
)
from apps.kuaizhizao.services.document_action_policy.print_unaudited_gate import (
    apply_print_unaudited_gate_to_capabilities,
    is_document_review_approved_for_print,
    push_allow_print_unaudited,
)
from apps.kuaizhizao.services.document_action_policy.receipt_notice import (
    assert_receipt_notice_capability,
)
from apps.kuaizhizao.services.document_action_policy.rework_order import (
    derive_rework_order_capabilities,
)
from apps.kuaizhizao.services.document_action_policy.shipment_notice import (
    derive_shipment_notice_capabilities,
)
from apps.kuaizhizao.services.document_action_policy.types import ActionCapability
from core.services.approval.audit_phase import derive_audit_phase
from infra.exceptions.exceptions import BusinessLogicError, ValidationError


class _PrintDoc(BaseModel):
    status: str
    review_status: Optional[str] = None
    tenant_id: int = 1
    audit: Optional[dict] = None
    capabilities: Any = None


class _NoReviewDoc(BaseModel):
    status: str = "待发货"
    tenant_id: int = 1
    capabilities: Any = None


def _phase(entity_type: str, status: str, review_status: str, **kwargs):
    return derive_audit_phase(
        entity_type,
        status,
        review_status,
        enabled=True,
        **kwargs,
    )


def test_shipment_response_exposes_review_status():
    assert "review_status" in ShipmentNoticeResponse.model_fields
    assert "review_status" in ReceiptNoticeResponse.model_fields


def test_shipment_audit_phase_follows_review_status():
    pending = _phase("shipment_notice", "待审核", "待审核")
    assert pending["phase"] == "pending"
    assert "approve" in pending["allowed_actions"]
    assert "reject" in pending["allowed_actions"]

    legacy = _phase("shipment_notice", "待审核", "草稿")
    assert legacy["phase"] == "draft"

    approved = _phase("shipment_notice", "待发货", "已通过")
    assert approved["phase"] == "approved"

    draft = _phase("shipment_notice", "草稿", "草稿")
    assert draft["phase"] == "draft"
    assert "submit" in draft["allowed_actions"]

    rejected = _phase("shipment_notice", "草稿", "已驳回")
    assert rejected["phase"] == "rejected"
    assert "submit" in rejected["allowed_actions"]


def test_reporting_and_rework_draft_pending_review_phase():
    for entity_type in ("reporting_record", "rework_order"):
        pending = _phase(entity_type, "draft", "待审核")
        assert pending["phase"] == "pending"
        assert "approve" in pending["allowed_actions"]
        assert "reject" in pending["allowed_actions"]

        held = _phase(entity_type, "draft", "待审核", review_submitted=False)
        assert held["phase"] == "draft"


def test_inventory_verify_rework_release_waits_for_approval():
    pending = SimpleNamespace(
        status="draft",
        review_status="待审核",
        business_type="inventory_verify",
        routing_mode="fixed",
    )
    caps = derive_rework_order_capabilities(pending, has_operation_links=True)
    assert caps.approve.allowed
    assert not caps.release.allowed
    assert caps.release.reason == "rework_order.release.awaiting_approval"

    approved = SimpleNamespace(
        status="draft",
        review_status="已通过",
        business_type="inventory_verify",
        routing_mode="fixed",
    )
    released = derive_rework_order_capabilities(approved, has_operation_links=True)
    assert released.release.allowed


def test_print_capability_matches_print_gate():
    draft = _PrintDoc(status="待发货", review_status="草稿")
    caps = derive_shipment_notice_capabilities(draft)
    assert caps.print.allowed
    assert is_document_review_approved_for_print(draft) is False
    with push_allow_print_unaudited(False):
        gated = _attach_capabilities_to_response(draft, caps)
    assert gated.capabilities.print.allowed is False

    approved_draft_status = _PrintDoc(status="草稿", review_status="已通过")
    approved_caps = derive_shipment_notice_capabilities(
        SimpleNamespace(status="待发货", review_status="已通过")
    )
    assert is_document_review_approved_for_print(approved_draft_status) is True
    with push_allow_print_unaudited(False):
        still = _attach_capabilities_to_response(approved_draft_status, approved_caps)
    assert still.capabilities.print.allowed is True

    with push_allow_print_unaudited(True):
        opened = _attach_capabilities_to_response(draft, caps)
    assert opened.capabilities.print.allowed is True

    denied = SimpleNamespace(
        print=ActionCapability(allowed=False, reason="sales_order.print.requires_audit")
    )
    kept = apply_print_unaudited_gate_to_capabilities(
        denied,
        SimpleNamespace(status="草稿", review_status="草稿"),
        allow_print_unaudited=True,
    )
    assert kept.print.allowed is False
    assert kept.print.reason == "sales_order.print.requires_audit"

    untouched = _NoReviewDoc()
    with push_allow_print_unaudited(False):
        skipped = _attach_capabilities_to_response(untouched, caps)
    assert skipped.capabilities.print.allowed is True


def test_submitted_receipt_notice_cannot_update():
    submitted = SimpleNamespace(status="待收货", review_status="SUBMITTED")
    pending = SimpleNamespace(status="待收货", review_status="待审核")
    with pytest.raises(BusinessLogicError):
        assert_receipt_notice_capability(submitted, "update")
    with pytest.raises(BusinessLogicError):
        assert_receipt_notice_capability(pending, "update")
    with pytest.raises(BusinessLogicError):
        assert_receipt_notice_capability(pending, "delete")


class _UpdateQuery:
    def __init__(self, sink: dict):
        self.sink = sink

    async def update(self, **kwargs):
        self.sink.update(kwargs)


def _patch_notice_io(monkeypatch, model, notice, sink: dict):
    async def get_or_none(**kwargs):
        return notice

    def filter(**kwargs):
        return _UpdateQuery(sink)

    monkeypatch.setattr(model, "get_or_none", get_or_none)
    monkeypatch.setattr(model, "filter", filter)


@pytest.mark.asyncio
async def test_shipment_submit_approve_withdraw_revoke_write_both_fields(monkeypatch):
    from apps.kuaizhizao.models.shipment_notice import ShipmentNotice
    from apps.kuaizhizao.services.shipment_notice_service import ShipmentNoticeService

    sink: dict = {}
    notice = SimpleNamespace(
        id=1,
        uuid="u",
        notice_code="SN1",
        customer_name="c",
        total_amount=1,
        status="草稿",
        review_status="草稿",
    )
    _patch_notice_io(monkeypatch, ShipmentNotice, notice, sink)
    svc = ShipmentNoticeService()
    svc.get_user_info = _async_return({"name": "u"})
    svc.get_shipment_notice_by_id = _async_return("ok")
    svc.business_config_service.check_audit_required = _async_return(False)

    await svc.submit_shipment_notice(1, 1, 2)
    assert sink["status"] == "待发货"
    assert sink["review_status"] == "已通过"

    sink.clear()
    notice.status = "草稿"
    notice.review_status = "草稿"
    svc.business_config_service.check_audit_required = _async_return(True)

    async def start_approval(**kwargs):
        return SimpleNamespace(id=9)

    monkeypatch.setattr(
        "core.services.approval.approval_instance_service.ApprovalInstanceService.start_approval_for_node",
        start_approval,
    )
    monkeypatch.setattr(
        "core.services.approval.audit_flow_guard.approval_instance_finished_on_submit",
        lambda instance: False,
    )
    await svc.submit_shipment_notice(1, 1, 2)
    assert sink["status"] == "待审核"
    assert sink["review_status"] == "待审核"

    sink.clear()
    notice.status = "待审核"
    notice.review_status = "待审核"
    svc.business_config_service.check_audit_required = _async_return(False)
    await svc.approve_shipment_notice(1, 1, 2)
    assert sink["status"] == "待发货"
    assert sink["review_status"] == "已通过"

    sink.clear()
    notice.status = "待审核"
    notice.review_status = "待审核"
    await svc.reject_shipment_notice(1, 1, 2)
    assert sink["status"] == "草稿"
    assert sink["review_status"] == "已驳回"

    sink.clear()
    notice.status = "待审核"
    notice.review_status = "待审核"

    async def cancel_approval(**kwargs):
        return True

    monkeypatch.setattr(
        "core.services.approval.approval_instance_service.ApprovalInstanceService.cancel_approval",
        cancel_approval,
    )
    await svc.withdraw_shipment_notice_submit(1, 1, 2)
    assert sink["status"] == "草稿"
    assert sink["review_status"] == "草稿"

    sink.clear()
    notice.status = "待发货"
    notice.review_status = "已通过"
    svc.business_config_service.check_audit_required = _async_return(True)
    reopened = {"value": False}

    async def revoke_with_flow_fallback(*, flow_revoke, **kwargs):
        return await flow_revoke(reopened=reopened["value"])

    monkeypatch.setattr(
        "core.services.approval.uni_audit_service.UniAuditService.revoke_with_flow_fallback",
        revoke_with_flow_fallback,
    )
    await svc.revoke_shipment_notice_approval(1, 1, 2)
    assert sink["status"] == "草稿"
    assert sink["review_status"] == "草稿"
    assert sink["status"] != "待发货"

    sink.clear()
    notice.status = "待发货"
    notice.review_status = "已通过"
    reopened["value"] = True
    await svc.revoke_shipment_notice_approval(1, 1, 2)
    assert sink["status"] == "待审核"
    assert sink["review_status"] == "待审核"


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner


@pytest.mark.asyncio
async def test_notify_rejected_until_review_approved(monkeypatch):
    from apps.kuaizhizao.models.shipment_notice import ShipmentNotice
    from apps.kuaizhizao.services.shipment_notice_service import ShipmentNoticeService

    notice = SimpleNamespace(id=1, status="待发货", review_status="草稿")

    async def get_or_none(**kwargs):
        return notice

    monkeypatch.setattr(ShipmentNotice, "get_or_none", get_or_none)
    svc = ShipmentNoticeService()
    svc.business_config_service.check_audit_required = _async_return(True)
    submitted = {"n": 0}

    async def submit(*args, **kwargs):
        submitted["n"] += 1

    svc.submit_shipment_notice = submit
    with pytest.raises(BusinessLogicError):
        await svc.notify_warehouse(1, 1, 2)
    assert submitted["n"] == 0

    notice.status = "草稿"
    notice.review_status = "草稿"
    with pytest.raises(BusinessLogicError):
        await svc.notify_warehouse(1, 1, 2)
    assert submitted["n"] == 0


@pytest.mark.asyncio
async def test_notify_line_location_required_when_warehouse_has_locations(monkeypatch):
    from apps.kuaizhizao.services import shipment_notice_service as mod

    item = SimpleNamespace(
        id=7,
        notice_quantity=Decimal("1"),
        material_code="M1",
        material_name="物料",
        warehouse_id=3,
        warehouse_name="主仓",
    )

    class _QS:
        def order_by(self, *args, **kwargs):
            return self

        def __await__(self):
            async def _rows():
                return [item]

            return _rows().__await__()

    monkeypatch.setattr(mod.ShipmentNoticeItem, "filter", lambda **kwargs: _QS())

    async def find_first(tenant_id, warehouse_id):
        return 9, "L1"

    async def get_or_none(**kwargs):
        return SimpleNamespace(id=9, name="A-01", storage_area_id=None)

    monkeypatch.setattr(
        "apps.master_data.services.warehouse_service.WarehouseService.find_first_storage_location_for_warehouse",
        find_first,
    )
    monkeypatch.setattr(
        "apps.master_data.models.warehouse.StorageLocation.get_or_none",
        get_or_none,
    )
    resolved = {"n": 0}

    async def resolve(**kwargs):
        resolved["n"] += 1
        return 1, "X"

    monkeypatch.setattr(
        "apps.kuaizhizao.services.warehouse_service._resolve_line_location_pair",
        resolve,
    )
    notice = SimpleNamespace(id=1, warehouse_id=3, warehouse_name="主仓")
    svc = mod.ShipmentNoticeService()
    with pytest.raises(ValidationError, match="请指定库位"):
        await svc._apply_notify_line_warehouses(
            tenant_id=1,
            notice=notice,
            notified_by=1,
            notify_data=None,
        )
    assert resolved["n"] == 0


@pytest.mark.asyncio
async def test_notify_line_without_locations_still_resolves(monkeypatch):
    from apps.kuaizhizao.services import shipment_notice_service as mod

    item = SimpleNamespace(
        id=7,
        notice_quantity=Decimal("1"),
        material_code="M1",
        material_name="物料",
        warehouse_id=3,
        warehouse_name="主仓",
    )

    class _QS:
        def order_by(self, *args, **kwargs):
            return self

        def __await__(self):
            async def _rows():
                return [item]

            return _rows().__await__()

    monkeypatch.setattr(mod.ShipmentNoticeItem, "filter", lambda **kwargs: _QS())

    async def find_first(tenant_id, warehouse_id):
        return None, None

    monkeypatch.setattr(
        "apps.master_data.services.warehouse_service.WarehouseService.find_first_storage_location_for_warehouse",
        find_first,
    )

    async def resolve(*args, **kwargs):
        raise RuntimeError("resolved")

    monkeypatch.setattr(
        "apps.kuaizhizao.services.warehouse_service._resolve_line_location_pair",
        resolve,
    )
    notice = SimpleNamespace(id=1, warehouse_id=3, warehouse_name="主仓")
    svc = mod.ShipmentNoticeService()
    with pytest.raises(RuntimeError, match="resolved"):
        await svc._apply_notify_line_warehouses(
            tenant_id=1,
            notice=notice,
            notified_by=1,
            notify_data=None,
        )


def _notify_line_item_qs(item):
    class _QS:
        def order_by(self, *args, **kwargs):
            return self

        def __await__(self):
            async def _rows():
                return [item]

            return _rows().__await__()

    return _QS()


def _location_rows_qs(rows):
    class _QS:
        def __await__(self):
            async def _rows():
                return rows

            return _rows().__await__()

    return _QS()


@pytest.mark.asyncio
async def test_notify_line_whole_warehouse_placeholder_still_resolves(monkeypatch):
    """只有系统占位「整仓」时，不传库位不报错，继续走原库位解析。"""
    from apps.kuaizhizao.services import shipment_notice_service as mod

    item = SimpleNamespace(
        id=7,
        notice_quantity=Decimal("1"),
        material_code="M1",
        material_name="物料",
        warehouse_id=3,
        warehouse_name="主仓",
    )
    placeholder = SimpleNamespace(id=9, name="整仓", storage_area_id=None)
    monkeypatch.setattr(
        mod.ShipmentNoticeItem, "filter", lambda **kwargs: _notify_line_item_qs(item)
    )

    async def find_first(tenant_id, warehouse_id):
        return 9, "WH-整仓"

    async def get_or_none(**kwargs):
        return placeholder

    monkeypatch.setattr(
        "apps.master_data.services.warehouse_service.WarehouseService.find_first_storage_location_for_warehouse",
        find_first,
    )
    monkeypatch.setattr(
        "apps.master_data.models.warehouse.StorageLocation.get_or_none",
        get_or_none,
    )
    monkeypatch.setattr(
        "apps.master_data.models.warehouse.StorageLocation.filter",
        lambda **kwargs: _location_rows_qs([placeholder]),
    )

    async def resolve(*args, **kwargs):
        raise RuntimeError("resolved")

    monkeypatch.setattr(
        "apps.kuaizhizao.services.warehouse_service._resolve_line_location_pair",
        resolve,
    )
    notice = SimpleNamespace(id=1, warehouse_id=3, warehouse_name="主仓")
    svc = mod.ShipmentNoticeService()
    with pytest.raises(RuntimeError, match="resolved"):
        await svc._apply_notify_line_warehouses(
            tenant_id=1,
            notice=notice,
            notified_by=1,
            notify_data=None,
        )


@pytest.mark.asyncio
async def test_notify_line_placeholder_plus_real_location_requires_location(monkeypatch):
    """find_first 命中「整仓」但本仓另有真实货位时，不传库位仍报错。"""
    from apps.kuaizhizao.services import shipment_notice_service as mod

    item = SimpleNamespace(
        id=7,
        notice_quantity=Decimal("1"),
        material_code="M1",
        material_name="物料",
        warehouse_id=3,
        warehouse_name="主仓",
    )
    placeholder = SimpleNamespace(id=9, name="整仓", storage_area_id=None)
    real = SimpleNamespace(id=10, name="A-01", storage_area_id=None)
    monkeypatch.setattr(
        mod.ShipmentNoticeItem, "filter", lambda **kwargs: _notify_line_item_qs(item)
    )

    async def find_first(tenant_id, warehouse_id):
        return 9, "WH-整仓"

    async def get_or_none(**kwargs):
        return placeholder

    monkeypatch.setattr(
        "apps.master_data.services.warehouse_service.WarehouseService.find_first_storage_location_for_warehouse",
        find_first,
    )
    monkeypatch.setattr(
        "apps.master_data.models.warehouse.StorageLocation.get_or_none",
        get_or_none,
    )
    monkeypatch.setattr(
        "apps.master_data.models.warehouse.StorageLocation.filter",
        lambda **kwargs: _location_rows_qs([placeholder, real]),
    )
    resolved = {"n": 0}

    async def resolve(**kwargs):
        resolved["n"] += 1
        return 1, "X"

    monkeypatch.setattr(
        "apps.kuaizhizao.services.warehouse_service._resolve_line_location_pair",
        resolve,
    )
    notice = SimpleNamespace(id=1, warehouse_id=3, warehouse_name="主仓")
    svc = mod.ShipmentNoticeService()
    with pytest.raises(ValidationError, match="请指定库位"):
        await svc._apply_notify_line_warehouses(
            tenant_id=1,
            notice=notice,
            notified_by=1,
            notify_data=None,
        )
    assert resolved["n"] == 0


@pytest.mark.asyncio
async def test_update_receipt_notice_rejects_submitted(monkeypatch):
    from apps.kuaizhizao.models.receipt_notice import ReceiptNotice
    from apps.kuaizhizao.services.receipt_notice_service import ReceiptNoticeService

    notice = SimpleNamespace(id=1, status="待收货", review_status="SUBMITTED")
    writes = {"n": 0}

    async def get_or_none(**kwargs):
        return notice

    class _Q:
        async def update(self, **kwargs):
            writes["n"] += 1

    monkeypatch.setattr(ReceiptNotice, "get_or_none", get_or_none)
    monkeypatch.setattr(ReceiptNotice, "filter", lambda **kwargs: _Q())
    svc = ReceiptNoticeService()
    with pytest.raises(BusinessLogicError):
        await svc.update_receipt_notice(1, 1, None, 2)
    with pytest.raises(BusinessLogicError):
        await svc.delete_receipt_notice(1, 1)
    assert writes["n"] == 0
