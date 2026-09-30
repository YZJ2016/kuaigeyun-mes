"""KR-PG5 序列号出入库留痕。不连开发库，用内存模型替身。"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from tortoise.exceptions import IntegrityError

from apps.kuaizhizao.services import material_serial_document_ledger_service as ledger_svc
from apps.kuaizhizao.services.inventory_service import InventoryService
from apps.kuaizhizao.services.material_serial_document_ledger_service import (
    current_document_from_rows,
    record_serial_document_ledger,
)
from apps.master_data.services.material_serial_service import MaterialSerialService
from infra.exceptions.exceptions import ValidationError


class _LedgerMemory:
    def __init__(self):
        self.rows = []
        self.next_id = 1
        self.fail = None
        self._t = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)

    def now(self):
        self._t += timedelta(seconds=1)
        return self._t

    def install(self, monkeypatch):
        mem = self

        class Query:
            def __init__(self, kwargs):
                self.kwargs = dict(kwargs)
                self.fields = ()

            def filter(self, **kwargs):
                merged = dict(self.kwargs)
                merged.update(kwargs)
                query = Query(merged)
                query.fields = self.fields
                return query

            def order_by(self, *fields):
                self.fields = fields
                return self

            def _matched(self):
                found = []
                for row in mem.rows:
                    if _row_matches(row, self.kwargs):
                        found.append(row)
                if self.fields:
                    found.sort(key=lambda row: tuple(getattr(row, field) for field in self.fields))
                return found

            def __await__(self):
                async def _all():
                    return self._matched()

                return _all().__await__()

            async def first(self):
                found = self._matched()
                return found[0] if found else None

            async def values_list(self, field, flat=False):
                return [getattr(row, field) for row in self._matched()]

        async def create(**kwargs):
            if mem.fail is not None:
                raise mem.fail
            for row in mem.rows:
                if (
                    row.tenant_id == kwargs.get("tenant_id")
                    and row.idempotency_key == kwargs.get("idempotency_key")
                    and row.serial_no == kwargs.get("serial_no")
                ):
                    raise IntegrityError("duplicate ledger")
            row = SimpleNamespace(id=mem.next_id, **kwargs)
            mem.next_id += 1
            mem.rows.append(row)
            return row

        monkeypatch.setattr(ledger_svc.MaterialSerialDocumentLedger, "filter", lambda **kw: Query(kw))
        monkeypatch.setattr(ledger_svc.MaterialSerialDocumentLedger, "create", create)
        monkeypatch.setattr(ledger_svc, "now_utc", mem.now)


def _row_matches(row, kwargs) -> bool:
    for key, expected in kwargs.items():
        if key.endswith("__isnull"):
            field = key[: -len("__isnull")]
            is_null = getattr(row, field) is None
            if bool(expected) != is_null:
                return False
            continue
        if getattr(row, key) != expected:
            return False
    return True


def _post(**overrides):
    payload = dict(
        tenant_id=1,
        serial_no="SN-1",
        material_id=7,
        direction="in",
        movement_type="purchase_receipt",
        source_type="purchase_receipt",
        source_doc_id=11,
        source_doc_code="PR-11",
        idempotency_key="purchase_receipt:11:confirm:1",
        operator_id=3,
        operator_name="仓管",
    )
    payload.update(overrides)
    return payload


@pytest.fixture
def ledger(monkeypatch):
    mem = _LedgerMemory()
    mem.install(monkeypatch)
    return mem


@pytest.mark.asyncio
async def test_same_idempotency_key_does_not_insert_second_row(ledger):
    await record_serial_document_ledger(**_post())
    await record_serial_document_ledger(**_post())
    assert len(ledger.rows) == 1


@pytest.mark.asyncio
async def test_revoke_appends_reverse_row_and_does_not_change_original(ledger):
    await record_serial_document_ledger(**_post())
    original = ledger.rows[0]
    snapshot = (
        original.direction,
        original.source_type,
        original.source_doc_id,
        original.reverses_id,
        original.movement_type,
    )
    await record_serial_document_ledger(
        **_post(
            direction="out",
            movement_type="purchase_receipt_withdraw",
            source_type="purchase_receipt_revoke",
            idempotency_key="purchase_receipt:11:revoke:1",
        )
    )
    assert len(ledger.rows) == 2
    assert (
        original.direction,
        original.source_type,
        original.source_doc_id,
        original.reverses_id,
        original.movement_type,
    ) == snapshot
    reversal = ledger.rows[1]
    assert reversal.reverses_id == original.id
    assert reversal.direction == "out"
    assert reversal.direction != original.direction
    assert current_document_from_rows(ledger.rows) is None


@pytest.mark.asyncio
async def test_unmatched_revoke_stays_in_history_but_is_not_current_document(ledger):
    await record_serial_document_ledger(**_post())
    await record_serial_document_ledger(
        **_post(
            direction="out",
            movement_type="sales_delivery_withdraw",
            source_type="sales_delivery_withdraw",
            source_doc_id=99,
            source_doc_code="SD-99",
            idempotency_key="sales_delivery:99:withdraw:1",
        )
    )
    assert len(ledger.rows) == 2
    reversal = ledger.rows[1]
    assert reversal.reverses_id is None
    assert reversal.source_type == "sales_delivery_withdraw"
    current = current_document_from_rows(ledger.rows)
    assert current["source_type"] == "purchase_receipt"
    assert current["source_doc_id"] == 11
    traced = await ledger_svc.serial_document_trace(1, "SN-1")
    assert [row["source_type"] for row in traced["serial_document_ledger"]] == [
        "purchase_receipt",
        "sales_delivery_withdraw",
    ]
    assert traced["current_document"]["source_type"] == "purchase_receipt"
    assert traced["current_document"]["source_doc_id"] == 11


@pytest.mark.asyncio
async def test_orphan_revoke_is_history_and_not_the_current_document(ledger):
    await record_serial_document_ledger(
        **_post(
            direction="out",
            movement_type="purchase_receipt_withdraw",
            source_type="purchase_receipt_revoke",
            idempotency_key="purchase_receipt:11:revoke:orphan",
        )
    )
    assert len(ledger.rows) == 1
    assert ledger.rows[0].reverses_id is None
    assert current_document_from_rows(ledger.rows) is None
    traced = await ledger_svc.serial_document_trace(1, "SN-1")
    assert traced["serial_document_ledger"][0]["source_type"] == "purchase_receipt_revoke"
    assert traced["current_document"] is None


@pytest.mark.asyncio
async def test_outbound_then_withdraw_current_document_is_no_longer_the_reversed_one(ledger):
    await record_serial_document_ledger(**_post())
    await record_serial_document_ledger(
        **_post(
            direction="out",
            movement_type="sales_delivery",
            source_type="sales_delivery",
            source_doc_id=22,
            source_doc_code="SD-22",
            idempotency_key="sales_delivery:22:confirm:1",
        )
    )
    assert current_document_from_rows(ledger.rows)["source_type"] == "sales_delivery"
    await record_serial_document_ledger(
        **_post(
            direction="in",
            movement_type="sales_delivery_withdraw",
            source_type="sales_delivery_withdraw",
            source_doc_id=22,
            source_doc_code="SD-22",
            idempotency_key="sales_delivery:22:withdraw:1",
        )
    )
    current = current_document_from_rows(ledger.rows)
    assert current["source_type"] == "purchase_receipt"
    assert current["source_doc_id"] == 11
    assert len(ledger.rows) == 3
    assert ledger.rows[1].reverses_id is None
    assert ledger.rows[2].reverses_id == ledger.rows[1].id


@pytest.mark.asyncio
async def test_issue_withdraw_points_at_original_even_if_movement_type_is_unchanged(ledger):
    await record_serial_document_ledger(
        **_post(
            direction="out",
            movement_type="production_issue",
            source_type="production_picking",
            source_doc_id=5,
            source_doc_code="PK-5",
            idempotency_key="production_picking:5:confirm:1",
        )
    )
    original = ledger.rows[0]
    await record_serial_document_ledger(
        **_post(
            direction="in",
            movement_type="production_issue",
            source_type="production_picking_withdraw",
            source_doc_id=5,
            source_doc_code="PK-5",
            idempotency_key="production_picking:5:withdraw:1",
        )
    )
    assert ledger.rows[1].reverses_id == original.id
    assert ledger.rows[1].direction == "in"
    assert original.direction == "out"
    assert original.reverses_id is None


@pytest.mark.asyncio
async def test_reconfirm_does_not_append_when_forward_row_exists(ledger):
    await record_serial_document_ledger(**_post())
    await record_serial_document_ledger(
        **_post(
            idempotency_key="purchase_receipt:11:confirm:1@scope2",
            reconfirm_tolerant=True,
        )
    )
    assert len(ledger.rows) == 1


@pytest.mark.asyncio
async def test_reconfirm_appends_when_no_forward_row(ledger):
    await record_serial_document_ledger(**_post(reconfirm_tolerant=True, idempotency_key="k-reconfirm"))
    await record_serial_document_ledger(**_post(reconfirm_tolerant=True, idempotency_key="k-reconfirm"))
    assert len(ledger.rows) == 1
    assert ledger.rows[0].source_type == "purchase_receipt"
    assert ledger.rows[0].reverses_id is None


@pytest.mark.asyncio
async def test_missing_idempotency_key_rejects(ledger):
    with pytest.raises(ValidationError):
        await record_serial_document_ledger(**_post(idempotency_key="  "))
    assert ledger.rows == []


def _patch_increase(monkeypatch, *, serial_row=None, revoke_exists=False):
    async def get_material(**kwargs):
        return SimpleNamespace(
            id=7,
            batch_managed=False,
            serial_managed=False,
            name="物料",
            main_code="M1",
            code="M1",
        )

    monkeypatch.setattr(
        "apps.master_data.models.material.Material.get_or_none",
        get_material,
    )
    monkeypatch.setattr(
        "apps.master_data.services.material_batch_service.MaterialBatchService.coerce_optional_date",
        lambda value: value,
    )
    monkeypatch.setattr(
        InventoryService,
        "_get_warehouse_management_flags",
        AsyncMock(return_value=(False, False)),
    )
    monkeypatch.setattr(InventoryService, "_find_in_stock_material_batch", AsyncMock(return_value=None))
    monkeypatch.setattr(InventoryService, "_material_batch_increase_or_restore", AsyncMock())
    monkeypatch.setattr(InventoryService, "_record_stock_movement", AsyncMock())
    monkeypatch.setattr(
        "apps.kuaizhizao.services.work_order_readiness_service.notify_inventory_changed",
        MagicMock(),
    )

    class SerialQuery:
        def select_for_update(self):
            return self

        async def first(self):
            return serial_row

    async def create_serial(**kwargs):
        return SimpleNamespace(save=AsyncMock(), **kwargs)

    monkeypatch.setattr(
        "apps.master_data.models.material_serial.MaterialSerial.filter",
        lambda **kw: SerialQuery(),
    )
    monkeypatch.setattr(
        "apps.master_data.models.material_serial.MaterialSerial.create",
        create_serial,
    )

    class MoveQuery:
        async def exists(self):
            return revoke_exists

    monkeypatch.setattr(
        "apps.kuaizhizao.models.material_stock_movement.MaterialStockMovement.filter",
        lambda **kw: MoveQuery(),
    )


def _patch_decrease(monkeypatch, *, serial_row):
    async def get_material(**kwargs):
        return SimpleNamespace(
            id=7,
            batch_managed=False,
            serial_managed=False,
            name="物料",
            main_code="M1",
            code="M1",
        )

    class ConfigService:
        async def get_business_config(self, tenant_id):
            return {"parameters": {"warehouse": {}}}

    monkeypatch.setattr(
        "apps.kuaizhizao.services.inventory_service.BusinessConfigService",
        ConfigService,
    )
    monkeypatch.setattr(
        "apps.master_data.models.material.Material.get_or_none",
        get_material,
    )
    monkeypatch.setattr(
        InventoryService,
        "_get_allow_negative_inventory",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        InventoryService,
        "_get_warehouse_management_flags",
        AsyncMock(return_value=(False, False)),
    )
    batch = SimpleNamespace(
        id=4,
        quantity=Decimal("5"),
        warehouse_id=0,
        batch_no="LOT",
        status="in_stock",
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        InventoryService,
        "_find_in_stock_material_batch",
        AsyncMock(return_value=batch),
    )
    monkeypatch.setattr(InventoryService, "_record_stock_movement", AsyncMock())
    monkeypatch.setattr(
        "apps.kuaizhizao.services.work_order_readiness_service.notify_inventory_changed",
        MagicMock(),
    )

    class SerialQuery:
        def select_for_update(self):
            return self

        async def first(self):
            return serial_row

    monkeypatch.setattr(
        "apps.master_data.models.material_serial.MaterialSerial.filter",
        lambda **kw: SerialQuery(),
    )
    return batch


@pytest.mark.asyncio
async def test_quantity_posting_without_serial_writes_no_ledger(ledger, monkeypatch):
    _patch_increase(monkeypatch)
    ok = await InventoryService._increase_stock_no_atomic.__wrapped__(
        tenant_id=1,
        material_id=7,
        quantity=Decimal("3"),
        idempotency_key="qty-only",
        movement_type="adjust",
        source_type="other_inbound",
        source_doc_id=1,
        operator_id=3,
        operator_name="仓管",
    )
    assert ok is True
    assert ledger.rows == []

    serial = SimpleNamespace(material_id=7, status="in_stock", save=AsyncMock())
    _patch_decrease(monkeypatch, serial_row=serial)
    ok = await InventoryService._decrease_stock_no_atomic.__wrapped__(
        tenant_id=1,
        material_id=7,
        quantity=Decimal("1"),
        batch_no="LOT",
        serial_nos=None,
        idempotency_key="qty-out",
        movement_type="other_outbound",
        source_type="other_outbound",
        source_doc_id=2,
        operator_id=3,
        operator_name="仓管",
    )
    assert ok is True
    assert ledger.rows == []
    assert serial.status == "in_stock"


@pytest.mark.asyncio
async def test_increase_and_ledger_commit_together(ledger, monkeypatch):
    _patch_increase(monkeypatch)
    ok = await InventoryService._increase_stock_no_atomic.__wrapped__(
        tenant_id=1,
        material_id=7,
        quantity=Decimal("1"),
        serial_nos=["SN-1"],
        ledger_production_date=date(2026, 9, 30),
        idempotency_key="in-1",
        movement_type="purchase_receipt",
        source_type="purchase_receipt",
        source_doc_id=11,
        source_doc_code="PR-11",
        operator_id=3,
        operator_name="仓管",
    )
    assert ok is True
    assert len(ledger.rows) == 1
    assert ledger.rows[0].serial_no == "SN-1"
    assert ledger.rows[0].direction == "in"
    assert ledger.rows[0].reverses_id is None


@pytest.mark.asyncio
async def test_increase_ledger_failure_fails_the_posting(ledger, monkeypatch):
    _patch_increase(monkeypatch)
    ledger.fail = RuntimeError("ledger down")
    with pytest.raises(RuntimeError, match="ledger down"):
        await InventoryService._increase_stock_no_atomic.__wrapped__(
            tenant_id=1,
            material_id=7,
            quantity=Decimal("1"),
            serial_nos=["SN-1"],
            ledger_production_date=date(2026, 9, 30),
            idempotency_key="in-fail",
            movement_type="purchase_receipt",
            source_type="purchase_receipt",
            source_doc_id=11,
            operator_id=3,
            operator_name="仓管",
        )
    assert ledger.rows == []


@pytest.mark.asyncio
async def test_decrease_ledger_failure_fails_the_posting(ledger, monkeypatch):
    serial = SimpleNamespace(material_id=7, status="in_stock", save=AsyncMock())
    _patch_decrease(monkeypatch, serial_row=serial)
    ledger.fail = RuntimeError("ledger down")
    with pytest.raises(RuntimeError, match="ledger down"):
        await InventoryService._decrease_stock_no_atomic.__wrapped__(
            tenant_id=1,
            material_id=7,
            quantity=Decimal("1"),
            batch_no="LOT",
            serial_nos=["SN-1"],
            idempotency_key="out-fail",
            movement_type="sales_delivery",
            source_type="sales_delivery",
            source_doc_id=22,
            operator_id=3,
            operator_name="仓管",
        )
    assert ledger.rows == []
    serial.save.assert_awaited()


@pytest.mark.asyncio
async def test_reconfirm_inbound_uses_tolerant_path_without_second_row(ledger, monkeypatch):
    await record_serial_document_ledger(**_post())
    serial = SimpleNamespace(
        status="in_stock",
        material_id=7,
        production_date=date(2026, 9, 30),
        save=AsyncMock(),
    )
    _patch_increase(monkeypatch, serial_row=serial, revoke_exists=True)
    ok = await InventoryService._increase_stock_no_atomic.__wrapped__(
        tenant_id=1,
        material_id=7,
        quantity=Decimal("1"),
        serial_nos=["SN-1"],
        ledger_production_date=date(2026, 9, 30),
        idempotency_key="purchase_receipt:11:confirm:1@scope2",
        movement_type="purchase_receipt",
        source_type="purchase_receipt",
        source_doc_id=11,
        source_doc_code="PR-11",
        operator_id=3,
        operator_name="仓管",
    )
    assert ok is True
    assert len(ledger.rows) == 1
    serial.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_trace_adds_ledger_without_changing_serial_identity(ledger, monkeypatch):
    await record_serial_document_ledger(**_post())
    serial = SimpleNamespace(serial_no="SN-1", uuid="serial-uuid")

    class SerialQuery:
        def prefetch_related(self, *args):
            return self

        async def first(self):
            return serial

    class Profile:
        events = []

        def model_dump(self, by_alias=True):
            return {"events": []}

    class TraceSvc:
        async def build_profile_by_serial_uuid(self, *args, **kwargs):
            return Profile()

    class SerialResp:
        def model_dump(self, by_alias=True):
            return {"uuid": "serial-uuid", "serialNo": "SN-1", "status": "in_stock"}

    monkeypatch.setattr(
        "apps.master_data.models.material_serial.MaterialSerial.filter",
        lambda **kw: SerialQuery(),
    )
    monkeypatch.setattr(
        "apps.kuaizhizao.services.traceability.TraceabilityService",
        TraceSvc,
    )
    monkeypatch.setattr(MaterialSerialService, "_to_response", lambda item: SerialResp())

    traced = await MaterialSerialService.trace_serial(1, "serial-uuid")
    assert traced["serial"]["uuid"] == "serial-uuid"
    assert traced["serial_document_ledger"][0]["source_type"] == "purchase_receipt"
    assert traced["serial_document_ledger"][0]["source_doc_code"] == "PR-11"
    assert traced["current_document"]["source_doc_id"] == 11
    blob = str(traced["serial_document_ledger"]) + str(traced["current_document"])
    assert "password" not in blob
    assert "/Users/" not in blob
    assert "secret" not in blob
