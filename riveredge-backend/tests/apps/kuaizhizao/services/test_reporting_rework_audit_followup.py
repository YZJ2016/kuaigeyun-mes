"""报工待审撤回落点，以及报工/返工列表打印门禁。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.kuaizhizao.schemas.rework_order import ReworkOrderListResponse
from apps.kuaizhizao.services.document_action_policy.print_unaudited_gate import (
    push_allow_print_unaudited,
)
from infra.services.business_config_service import _TENANT_ALLOW_PRINT_UNAUDITED


def _clear_print_cache() -> None:
    _TENANT_ALLOW_PRINT_UNAUDITED.clear()


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    async def count(self):
        return len(self.rows)

    def offset(self, n):
        return self

    def limit(self, n):
        return self

    def order_by(self, *args):
        return self

    async def all(self):
        return self.rows

    def __await__(self):
        async def _inner():
            return self.rows

        return _inner().__await__()


def _reporting_row(**kwargs):
    now = datetime(2026, 11, 22, 8, 0, 0)
    data = dict(
        id=1,
        uuid="rpt-1",
        tenant_id=1,
        work_order_id=1,
        work_order_code="WO-1",
        work_order_name="工单",
        operation_id=2,
        operation_code="OP",
        operation_name="工序",
        reported_quantity=Decimal("3"),
        qualified_quantity=Decimal("3"),
        unqualified_quantity=Decimal("0"),
        work_hours=Decimal("1"),
        reported_at=now,
        status="draft",
        review_status="草稿",
        created_at=now,
        updated_at=now,
        completed_quantity=Decimal("9"),
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_withdraw_pending_reporting_returns_both_fields_to_draft(monkeypatch):
    from apps.kuaizhizao.models.reporting_record import ReportingRecord
    from apps.kuaizhizao.services.reporting_service import ReportingService

    record = _reporting_row(review_status="待审核", rejection_reason="旧原因")
    saved = {"n": 0}

    async def save():
        saved["n"] += 1

    record.save = save

    async def get_or_none(**kwargs):
        return record

    async def cancel_approval(**kwargs):
        return True

    monkeypatch.setattr(ReportingRecord, "get_or_none", get_or_none)
    monkeypatch.setattr(
        "core.services.approval.approval_instance_service.ApprovalInstanceService.cancel_approval",
        cancel_approval,
    )
    svc = ReportingService()
    progress = {"n": 0}

    async def update_progress(*args, **kwargs):
        progress["n"] += 1

    svc._update_work_order_progress = update_progress
    result = await svc.withdraw_reporting_submit(1, 1, 2)
    assert record.status == "draft"
    assert record.review_status == "draft"
    assert record.rejection_reason is None
    assert record.completed_quantity == Decimal("9")
    assert saved["n"] == 1
    assert progress["n"] == 0
    assert result.status == "draft"
    assert result.review_status == "draft"


@pytest.mark.asyncio
async def test_reporting_list_print_uses_real_allow_flag(monkeypatch):
    from apps.kuaizhizao.models.reporting_record import ReportingRecord
    from apps.kuaizhizao.models.work_order import WorkOrder
    from apps.kuaizhizao.services.defect_record_service import DefectRecordService
    from apps.kuaizhizao.services.reporting_service import ReportingService
    from infra.services.business_config_service import BusinessConfigService

    draft = _reporting_row(id=1, review_status="草稿")
    approved = _reporting_row(id=2, uuid="rpt-2", review_status="已通过")

    class _WorkOrders:
        def only(self, *args):
            return self

        def __await__(self):
            async def _inner():
                return []

            return _inner().__await__()

    async def remaining(self, tenant_id, mapping):
        return {}

    async def enrich_items(tenant_id, entity_type, rows, **kwargs):
        return rows

    allow = {"value": False}

    async def get_allow(self, tenant_id):
        return allow["value"]

    monkeypatch.setattr(ReportingRecord, "filter", lambda **kwargs: _Rows([draft, approved]))
    monkeypatch.setattr(WorkOrder, "filter", lambda **kwargs: _WorkOrders())
    monkeypatch.setattr(
        DefectRecordService,
        "batch_reporting_unqualified_remaining",
        remaining,
        raising=False,
    )
    monkeypatch.setattr(
        "core.services.approval.audit_record_enricher.enrich_items",
        enrich_items,
    )
    monkeypatch.setattr(BusinessConfigService, "get_allow_print_unaudited", get_allow)
    svc = ReportingService()
    svc.batch_work_orders_have_posted_sales_outbound = _async_return({})
    svc.batch_reporting_have_approved_inbound_downstream = _async_return({})

    _clear_print_cache()
    denied = await svc.list_reporting_records(1)
    by_id = {row["id"]: row for row in denied["data"]}
    assert by_id[1]["capabilities"]["print"]["allowed"] is False
    assert by_id[2]["capabilities"]["print"]["allowed"] is True

    allow["value"] = True
    _clear_print_cache()
    opened = await svc.list_reporting_records(1)
    opened_by_id = {row["id"]: row for row in opened["data"]}
    assert opened_by_id[1]["capabilities"]["print"]["allowed"] is True


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner


def _rework_order(**kwargs):
    now = datetime(2026, 11, 22, 8, 0, 0)
    data = dict(
        id=1,
        uuid="rw-1",
        code="RW-1",
        tenant_id=1,
        original_work_order_id=None,
        original_work_order_uuid=None,
        product_id=1,
        product_code="P",
        product_name="产品",
        quantity=Decimal("1"),
        rework_reason="原因",
        rework_type="工艺",
        status="draft",
        review_status="草稿",
        planned_start_date=None,
        planned_end_date=None,
        work_center_name=None,
        operator_name=None,
        cost=Decimal("0"),
        created_at=now,
        updated_at=now,
        start_work_order_operation_id=None,
        extension_payload={},
        business_type="simple_exec",
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_rework_list_pushes_real_allow_flag(monkeypatch):
    from apps.kuaizhizao.models.rework_order import ReworkOrder
    from apps.kuaizhizao.services.rework_order_service import ReworkOrderService
    from apps.kuaizhizao.services.document_action_policy.print_unaudited_gate import (
        resolve_allow_print_unaudited_for_attach,
    )

    seen = {}

    async def enrich(self, tenant_id, resp, rework_order):
        seen["allow"] = resolve_allow_print_unaudited_for_attach(
            rework_order, explicit=None
        )

    async def scope(query, **kwargs):
        return query

    async def get_allow(self, tenant_id):
        return False

    monkeypatch.setattr(ReworkOrder, "filter", lambda **kwargs: _Rows([_rework_order()]))
    monkeypatch.setattr(
        "apps.kuaizhizao.services.kuaizhizao_data_scope.apply_kuaizhizao_list_scope",
        scope,
    )
    monkeypatch.setattr(ReworkOrderService, "_enrich_rework_order_response", enrich)
    monkeypatch.setattr(
        "infra.services.business_config_service.BusinessConfigService.get_allow_print_unaudited",
        get_allow,
    )
    _clear_print_cache()
    svc = ReworkOrderService()
    await svc.list_rework_orders(1)
    assert seen["allow"] is False


@pytest.mark.asyncio
async def test_rework_enrich_print_gate_matches_param(monkeypatch):
    from apps.kuaizhizao.services.rework_order_service import ReworkOrderService

    async def ctx(*args, **kwargs):
        return {}

    monkeypatch.setattr(
        "apps.kuaizhizao.services.rework_order_service.compute_capability_context",
        ctx,
    )
    svc = ReworkOrderService()
    now = datetime(2026, 11, 22, 8, 0, 0)

    def response(status: str, review: str) -> ReworkOrderListResponse:
        return ReworkOrderListResponse.model_construct(
            id=1,
            uuid="rw-1",
            code="RW-1",
            status=status,
            review_status=review,
            product_id=1,
            product_code="P",
            product_name="产品",
            quantity=Decimal("1"),
            rework_reason="原因",
            rework_type="工艺",
            cost=Decimal("0"),
            created_at=now,
            updated_at=now,
            original_work_order_id=None,
            original_work_order_uuid=None,
            planned_start_date=None,
            planned_end_date=None,
            work_center_name=None,
            operator_name=None,
        )

    draft = _rework_order()
    draft_resp = response("draft", "草稿")
    _clear_print_cache()
    with push_allow_print_unaudited(False):
        await svc._enrich_rework_order_response(1, draft_resp, draft)
    assert draft_resp.capabilities.print.allowed is False

    approved = _rework_order(review_status="已通过")
    approved_resp = response("draft", "已通过")
    with push_allow_print_unaudited(False):
        await svc._enrich_rework_order_response(1, approved_resp, approved)
    assert approved_resp.capabilities.print.allowed is True

    closed = _rework_order(status="cancelled", review_status="草稿")
    closed_resp = response("cancelled", "草稿")
    with push_allow_print_unaudited(True):
        await svc._enrich_rework_order_response(1, closed_resp, closed)
    assert closed_resp.capabilities.print.allowed is False
