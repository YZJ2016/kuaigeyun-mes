"""spec 141（KR-CL2）：库存过账幂等键失败关闭 + 序列号行锁。

- `idempotent_stock_change` / `_increase_stock_no_atomic` / `_decrease_stock_no_atomic`
  对空/缺 ``idempotency_key`` 失败关闭；
- 同键重试命中既有流水即返回、不再过账；
- 序列号台账读写走 ``select_for_update`` 行锁（与批次同事务、固定锁序）；
- 包装层 ``increase_stock``/``decrease_stock`` 缺键时按
  ``source_type + source_doc_id + 动作`` 合成确定性键（A 案），无法合成即拒绝；
- spec AC3 的全部直接调用点必须显式传键。
"""

import ast
from contextlib import ExitStack, asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaizhizao.services.inventory_service import (
    InventoryService,
    _synth_stock_key_counter,
)
from infra.exceptions.exceptions import ValidationError

_SRC = Path(__file__).resolve().parents[4] / "src"


@asynccontextmanager
async def _noop_tx():
    conn = MagicMock()
    conn.execute_query = AsyncMock(return_value=None)
    yield conn


def _dedup_queryset(keys):
    qs = MagicMock()
    qs.using_db = MagicMock(return_value=qs)
    qs.values_list = AsyncMock(return_value=list(keys))
    qs.exists = AsyncMock(return_value=False)
    return qs


def _patched_posting(keys=()):
    """替换事务边界与流水查重：``keys`` 为已落库幂等键（命中则不再过账）。"""
    return (
        patch(
            "apps.kuaizhizao.utils.stock_posting.reuse_or_begin_transaction",
            _noop_tx,
        ),
        patch(
            "apps.kuaizhizao.models.material_stock_movement.MaterialStockMovement.filter",
            MagicMock(return_value=_dedup_queryset(keys)),
        ),
    )


# ---------- 1. 空/缺幂等键失败关闭 ----------


@pytest.mark.asyncio
@pytest.mark.parametrize("key", [None, "", "   "])
@pytest.mark.parametrize(
    "fn", [InventoryService._increase_stock_no_atomic, InventoryService._decrease_stock_no_atomic]
)
async def test_no_atomic_entries_reject_missing_or_blank_key(fn, key):
    kwargs = dict(tenant_id=1, material_id=1, quantity=Decimal("1"), movement_type="t")
    if key is not None:
        kwargs["idempotency_key"] = key
    with pytest.raises(ValidationError, match="idempotency_key"):
        await fn(**kwargs)


@pytest.mark.asyncio
async def test_wrapped_bypass_still_rejects_empty_key():
    """直接调底层函数体（绕过装饰器）同样拒绝空键。"""
    with pytest.raises(ValidationError, match="idempotency_key"):
        await InventoryService._increase_stock_no_atomic.__wrapped__(
            tenant_id=1, material_id=1, quantity=Decimal("1")
        )
    with pytest.raises(ValidationError, match="idempotency_key"):
        await InventoryService._decrease_stock_no_atomic.__wrapped__(
            tenant_id=1, material_id=1, quantity=Decimal("1")
        )


# ---------- 2. 同键重试查重 ----------


@pytest.mark.asyncio
async def test_same_key_retry_returns_existing_without_posting():
    tx_patch, dedup_patch = _patched_posting(keys=["doc:1:inc"])
    with (
        tx_patch,
        dedup_patch,
        patch(
            "apps.master_data.models.material.Material.get_or_none",
            new=AsyncMock(),
        ) as material_get,
    ):
        ok = await InventoryService._increase_stock_no_atomic(
            tenant_id=1,
            material_id=1,
            quantity=Decimal("5"),
            movement_type="other_inbound",
            idempotency_key="doc:1:inc",
        )
    assert ok is True
    material_get.assert_not_called()  # 命中既有流水 → 不再进过账体


@pytest.mark.asyncio
async def test_same_key_retry_dedup_on_shard_suffix():
    """既有流水为分片键（key#p0）时，主键重试同样判重。"""
    tx_patch, dedup_patch = _patched_posting(keys=["doc:2:dec#p0"])
    with (
        tx_patch,
        dedup_patch,
        patch(
            "apps.master_data.models.warehouse.Warehouse.get_or_none",
            new=AsyncMock(),
        ) as wh_get,
    ):
        ok = await InventoryService._decrease_stock_no_atomic(
            tenant_id=1,
            material_id=1,
            quantity=Decimal("5"),
            movement_type="other_outbound",
            idempotency_key="doc:2:dec",
        )
    assert ok is True
    wh_get.assert_not_called()


# ---------- 3. 入库序列号走行锁 ----------


def _serial_lock_query(record):
    qs = MagicMock()
    qs.select_for_update = MagicMock(return_value=qs)
    qs.first = AsyncMock(return_value=record)
    return qs


@pytest.mark.asyncio
async def test_inbound_serial_update_uses_select_for_update():
    material = SimpleNamespace(
        id=5, main_code="M1", code="M1", name="m",
        batch_managed=False, serial_managed=True,
    )
    serial = SimpleNamespace(
        status="out_stock", material_id=None, production_date=None, save=AsyncMock()
    )
    serial_qs = _serial_lock_query(serial)
    tx_patch, dedup_patch = _patched_posting()
    with (
        tx_patch,
        dedup_patch,
        patch(
            "apps.kuaizhizao.services.inventory_service.InventoryService._get_warehouse_management_flags",
            new=AsyncMock(return_value=(False, True)),
        ),
        patch(
            "apps.master_data.models.material.Material.get_or_none",
            new=AsyncMock(return_value=material),
        ),
        patch(
            "apps.kuaizhizao.services.inventory_service.InventoryService._find_in_stock_material_batch",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "apps.kuaizhizao.services.inventory_service.InventoryService._material_batch_increase_or_restore",
            new=AsyncMock(),
        ),
        patch(
            "apps.kuaizhizao.services.inventory_service.InventoryService._record_stock_movement",
            new=AsyncMock(),
        ),
        patch(
            "apps.master_data.models.material_serial.MaterialSerial.filter",
            MagicMock(return_value=serial_qs),
        ),
        patch(
            "apps.kuaizhizao.services.work_order_readiness_service.notify_inventory_changed",
            return_value=None,
        ),
    ):
        ok = await InventoryService._increase_stock_no_atomic(
            tenant_id=1,
            material_id=5,
            quantity=Decimal("1"),
            serial_nos=["SN-9"],
            source_type="other_inbound",
            source_doc_id=3,
            ledger_production_date=date(2026, 1, 1),
            movement_type="other_inbound",
            operator_id=1,
            idempotency_key="other_inbound:3:inc:1",
        )
    assert ok is True
    serial_qs.select_for_update.assert_called_once()
    assert serial.status == "in_stock"
    serial.save.assert_awaited_once()


# ---------- 4. 包装层合成键（A 案） ----------


@pytest.mark.asyncio
async def test_wrapper_synthesizes_deterministic_key_and_dedups_retry():
    inner = AsyncMock(return_value=True)
    synth_calls = []

    async def capture(**kwargs):
        synth_calls.append(kwargs["idempotency_key"])
        return await inner(**kwargs)

    with (
        patch(
            "apps.kuaizhizao.utils.stock_posting.reuse_or_begin_transaction",
            _noop_tx,
        ),
        patch.object(
            InventoryService, "_increase_stock_no_atomic", new=AsyncMock(side_effect=capture)
        ),
    ):
        await InventoryService.increase_stock(
            tenant_id=1, material_id=7, quantity=Decimal("2"),
            source_type="other_outbound_revoke", source_doc_id=9,
        )
        # 同一调用上下文内内容相同的第二行明细 → 序号区分
        await InventoryService.increase_stock(
            tenant_id=1, material_id=7, quantity=Decimal("2"),
            source_type="other_outbound_revoke", source_doc_id=9,
        )
        # 不同明细 → 不同摘要
        await InventoryService.increase_stock(
            tenant_id=1, material_id=8, quantity=Decimal("2"),
            source_type="other_outbound_revoke", source_doc_id=9,
        )

    first, second, third = synth_calls
    assert first.startswith("other_outbound_revoke:9:increase:")
    assert second == f"{first}#s1"
    assert third.startswith("other_outbound_revoke:9:increase:")
    assert third != first and third != second

    # 新上下文（模拟重试请求）按相同顺序重放 → 得到同一组键
    _synth_stock_key_counter.set(None)
    with (
        patch(
            "apps.kuaizhizao.utils.stock_posting.reuse_or_begin_transaction",
            _noop_tx,
        ),
        patch.object(
            InventoryService, "_increase_stock_no_atomic", new=AsyncMock(side_effect=capture)
        ),
    ):
        await InventoryService.increase_stock(
            tenant_id=1, material_id=7, quantity=Decimal("2"),
            source_type="other_outbound_revoke", source_doc_id=9,
        )
    assert synth_calls[-1] == first


@pytest.mark.asyncio
async def test_wrapper_keeps_explicit_key():
    seen = []

    async def capture(**kwargs):
        seen.append(kwargs["idempotency_key"])
        return True

    with (
        patch(
            "apps.kuaizhizao.utils.stock_posting.reuse_or_begin_transaction",
            _noop_tx,
        ),
        patch.object(
            InventoryService, "_decrease_stock_no_atomic", new=AsyncMock(side_effect=capture)
        ),
    ):
        await InventoryService.decrease_stock(
            tenant_id=1, material_id=7, quantity=Decimal("2"),
            source_type="inventory_transfer", source_doc_id=4,
            idempotency_key="inventory_transfer:4:dec:11",
        )
    assert seen == ["inventory_transfer:4:dec:11"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fn", [InventoryService.increase_stock, InventoryService.decrease_stock]
)
async def test_wrapper_rejects_when_key_unsynthesizable(fn):
    with (
        patch(
            "apps.kuaizhizao.utils.stock_posting.reuse_or_begin_transaction",
            _noop_tx,
        ),
        pytest.raises(ValidationError, match="source_type|source_doc_id|幂等键"),
    ):
        await fn(
            tenant_id=1, material_id=7, quantity=Decimal("2"),
            source_type="assembly_order",  # 缺 source_doc_id → 无法合成 → 拒绝
        )


# ---------- 5. 直接调用点必须传键（spec AC3） ----------


_STOCK_CALL_FILES = [
    "apps/kuaizhizao/services/warehouse_service.py",
    "apps/kuaizhizao/services/semi_finished_goods_receipt_service.py",
    "apps/kuaizhizao/services/scrap_record_service.py",
    "apps/kuaizhizao/services/material_binding_service.py",
    "apps/kuaizhizao/services/backflush_service.py",
    "apps/kuaizhizao/services/customer_material_registration_service.py",
    "apps/kuaizhizao/services/inventory_service.py",
]

_ATOMIC_NAMES = {"_increase_stock_no_atomic", "_decrease_stock_no_atomic"}
_WRAPPER_NAMES = {"increase_stock", "decrease_stock"}


def _calls(tree, names):
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in names
    ]


def _has_kwarg(call, name):
    return any(k.arg == name for k in call.keywords)


def _has_splat(call):
    return any(k.arg is None for k in call.keywords)


def _enclosing_function_source(source: str, call):
    best = None
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= call.lineno <= (node.end_lineno or 0):
                if best is None or node.lineno > best.lineno:
                    best = node
    if best is None:
        return ""
    return ast.get_source_segment(source, best) or ""


def test_direct_atomic_calls_all_pass_idempotency_key():
    for rel in _STOCK_CALL_FILES:
        source = (_SRC / rel).read_text()
        tree = ast.parse(source)
        for call in _calls(tree, _ATOMIC_NAMES):
            loc = f"{rel}:{call.lineno}"
            if _has_kwarg(call, "idempotency_key"):
                continue
            # **kwargs 透传（如 material_binding 的 common/dec_kwargs）：
            # 其所在函数体内必须能检索到幂等键赋值
            if _has_splat(call) and "idempotency_key" in _enclosing_function_source(
                source, call
            ):
                continue
            pytest.fail(f"直接过账调用缺少 idempotency_key: {loc}")


def test_wrapper_calls_pass_key_or_synthesizable_fields():
    for rel in _STOCK_CALL_FILES + [
        "apps/kuaizhizao/services/material_call_service.py",
        "apps/kuaizhizao/services/outsource_material_issue_service.py",
        "apps/kuaizhizao/services/outsource_material_receipt_service.py",
        "apps/kuaizhizao/services/outsource_material_return_service.py",
        "apps/kuaizhizao/services/outsource_product_return_service.py",
        "apps/kuaizhizao/services/defect_record_service.py",
        "apps/kuaizhizao/services/disassembly_order_service.py",
        "apps/kuaizhizao/services/batching_order_service.py",
        "apps/kuaizhizao/services/assembly_order_service.py",
        "apps/kuaizhizao/services/inventory_transfer_service.py",
    ]:
        source = (_SRC / rel).read_text()
        tree = ast.parse(source)
        for call in _calls(tree, _WRAPPER_NAMES):
            loc = f"{rel}:{call.lineno}"
            ok = _has_kwarg(call, "idempotency_key") or (
                _has_kwarg(call, "source_type") and _has_kwarg(call, "source_doc_id")
            )
            if not ok:
                pytest.fail(
                    f"包装层调用既无 idempotency_key 也无法合成（缺 source_type/source_doc_id）: {loc}"
                )


# ---------- 6. 单据守卫：确认→撤回→再确认是新过账尝试（KR-CL2 回归） ----------

from apps.kuaizhizao.utils.stock_posting import stock_document_guard


def _patched_connections():
    """`stock_document_guard` 直接走 ``connections.get`` 取当前事务连接。

    mock 连接须通过 ``BaseTransactionWrapper`` 判定（守卫对非事务连接失败关闭）。
    """
    from tortoise.backends.base.client import BaseTransactionWrapper

    conn = MagicMock(spec=BaseTransactionWrapper)
    conn.execute_query = AsyncMock(return_value=None)
    conns = MagicMock()
    conns.get = MagicMock(return_value=conn)
    return patch("apps.kuaizhizao.utils.stock_posting.connections", conns)


@pytest.mark.asyncio
async def test_stock_document_guard_rejects_outside_transaction():
    """守卫落在非事务连接上时锁随语句结束即失效——失败关闭拒绝。"""
    conns = MagicMock()
    conns.get = MagicMock(return_value=MagicMock())  # 非 BaseTransactionWrapper
    with patch("apps.kuaizhizao.utils.stock_posting.connections", conns):
        with pytest.raises(ValidationError, match="活动事务"):
            async with stock_document_guard("sales_return", 1, 1):
                pass


def _increase_body_patches(material_get):
    material = SimpleNamespace(
        id=7, main_code="M7", code="M7", name="m", batch_managed=False, serial_managed=False
    )
    material_get.return_value = material
    return (
        patch(
            "apps.kuaizhizao.services.inventory_service.InventoryService._get_warehouse_management_flags",
            new=AsyncMock(return_value=(False, True)),
        ),
        patch("apps.master_data.models.material.Material.get_or_none", material_get),
        patch(
            "apps.kuaizhizao.services.inventory_service.InventoryService._find_in_stock_material_batch",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "apps.kuaizhizao.services.inventory_service.InventoryService._material_batch_increase_or_restore",
            new=AsyncMock(),
        ),
        patch(
            "apps.kuaizhizao.services.inventory_service.InventoryService._record_stock_movement",
            new=AsyncMock(),
        ),
        patch(
            "apps.kuaizhizao.services.work_order_readiness_service.notify_inventory_changed",
            return_value=None,
        ),
    )


@pytest.mark.asyncio
async def test_bare_key_reconfirm_is_deduped_and_swallowed():
    """修复前缺陷形态（回归基线）：无守卫时确认→撤回→再确认复用原键，被流水查重吞掉。"""
    tx_patch, dedup_patch = _patched_posting(keys=["sales_return:1:inc:7"])
    material_get = AsyncMock()
    with tx_patch, dedup_patch, patch(
        "apps.master_data.models.material.Material.get_or_none", material_get
    ):
        ok = await InventoryService._increase_stock_no_atomic(
            tenant_id=1,
            material_id=7,
            quantity=Decimal("2"),
            movement_type="sales_return",
            idempotency_key="sales_return:1:inc:7",
        )
    assert ok is True
    material_get.assert_not_called()  # 查重命中 → 过账体被跳过


@pytest.mark.asyncio
async def test_guarded_reconfirm_reposts_with_fresh_scope():
    """守卫内再确认：明细键带新 @scope 后缀、流水查重不中，过账体正常执行。"""
    # 空表模拟「新 scope 键无既有流水」：上一周期键是 …@attempt1，本次键 …@新uuid 必然不同
    tx_patch, dedup_patch = _patched_posting()
    material_get = AsyncMock()
    with ExitStack() as stack:
        for p in (tx_patch, dedup_patch, _patched_connections(), *_increase_body_patches(material_get)):
            stack.enter_context(p)
        async with stock_document_guard("sales_return", 1, 1):
            ok = await InventoryService._increase_stock_no_atomic(
                tenant_id=1,
                material_id=7,
                quantity=Decimal("2"),
                movement_type="sales_return",
                idempotency_key="sales_return:1:inc:7",
            )
    assert ok is True
    material_get.assert_awaited()  # 过账体执行 → 未被查重吞掉


@pytest.mark.asyncio
async def test_guard_scope_suffix_unique_per_attempt_and_reset_on_exit():
    """两次守卫进入 → 明细键后缀不同；退出守卫后恢复裸键。"""
    posting_keys = []

    async def capture_lock(conn, key):
        posting_keys.append(key)

    tx_patch, dedup_patch = _patched_posting()
    with ExitStack() as stack:
        for p in (
            tx_patch,
            dedup_patch,
            _patched_connections(),
            patch(
                "apps.kuaizhizao.utils.stock_posting._lock",
                new=AsyncMock(side_effect=capture_lock),
            ),
            *_increase_body_patches(AsyncMock()),
        ):
            stack.enter_context(p)
        for _ in range(2):
            async with stock_document_guard("sales_return", 1, 1):
                await InventoryService._increase_stock_no_atomic(
                    tenant_id=1, material_id=7, quantity=Decimal("2"),
                    movement_type="sales_return", idempotency_key="sales_return:1:inc:7",
                )
        await InventoryService._increase_stock_no_atomic(
            tenant_id=1, material_id=7, quantity=Decimal("2"),
            movement_type="sales_return", idempotency_key="sales_return:1:inc:7",
        )

    posting = [k for k in posting_keys if k.startswith("stock-posting:")]
    doc_locks = [k for k in posting_keys if k.startswith("stock-document:sales_return:")]
    assert len(doc_locks) == 2  # 两次守卫各取一次单据锁
    first, second = posting[0].rsplit("@", 1)
    assert first == "stock-posting:1:sales_return:1:inc:7"
    assert posting[1] != posting[0]  # 新尝试新后缀
    assert posting[1].startswith("stock-posting:1:sales_return:1:inc:7@")
    assert posting[2] == "stock-posting:1:sales_return:1:inc:7"  # 出守卫恢复裸键


# ---------- 7. 可撤回再确认单据流必须有守卫（结构防回归） ----------

_GUARDED_DOCUMENT_FLOWS = {
    "apps/kuaizhizao/services/warehouse_service.py": [
        ("SalesReturnService", "confirm_return"),
        ("SalesReturnService", "withdraw_confirmation"),
        ("PurchaseReturnService", "confirm_return"),
        ("PurchaseReturnService", "withdraw_confirmation"),
        ("OtherInboundService", "confirm_inbound"),
        ("OtherInboundService", "withdraw_confirmation"),
        ("OtherInboundService", "repair_deleted_other_inbound_inventory"),
        ("OtherOutboundService", "confirm_outbound"),
        ("OtherOutboundService", "withdraw_confirmation"),
        ("MaterialBorrowService", "confirm_borrow"),
        ("MaterialBorrowService", "withdraw_confirmation"),
        ("MaterialReturnService", "confirm_return"),
    ],
    "apps/kuaizhizao/services/customer_material_registration_service.py": [
        ("CustomerMaterialRegistrationService", "process_registration"),
        ("CustomerMaterialRegistrationService", "withdraw_registration"),
    ],
}


def test_reconfirmable_document_flows_have_stock_document_guard():
    """可「确认→撤回→再确认」的过账入口必须有单据守卫。

    `serialize_stock_document` 装饰器或函数体内 `stock_document_guard(...)` 二选一；
    两者都给明细幂等键注入单次尝试 scope，防止再确认被流水查重吞掉。
    """
    for rel, targets in _GUARDED_DOCUMENT_FLOWS.items():
        source = (_SRC / rel).read_text()
        tree = ast.parse(source)
        class_map = {
            n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)
        }
        for class_name, fn_name in targets:
            cls = class_map.get(class_name)
            assert cls is not None, f"{rel} 缺类 {class_name}"
            fn = next(
                (
                    n
                    for n in cls.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name == fn_name
                ),
                None,
            )
            assert fn is not None, f"{class_name} 缺方法 {fn_name}"
            decorated = any(
                "serialize_stock_document" in ast.dump(d) for d in fn.decorator_list
            )
            segment = ast.get_source_segment(source, fn) or ""
            assert decorated or "stock_document_guard(" in segment, (
                f"{class_name}.{fn_name} 缺少单据守卫"
                "（serialize_stock_document 装饰器或 stock_document_guard 上下文）"
            )


# ---------------------------------------------------------------------------
# 7. 序列号持久化接线：序列号单据行的过账调用必须传 serial_nos
# ---------------------------------------------------------------------------

_SERIAL_PERSISTED_FLOWS = {
    "apps/kuaizhizao/services/warehouse_service.py": [
        ("ProductionPickingService", "confirm_picking"),
        ("ProductionPickingService", "withdraw_picking_confirmation"),
        ("ProductionReturnService", "confirm_return"),
        ("ProductionReturnService", "withdraw_return_confirmation"),
        ("FinishedGoodsReceiptService", "confirm_receipt"),
        ("FinishedGoodsReceiptService", "withdraw_receipt_confirmation"),
        ("SalesDeliveryService", "withdraw_delivery_confirmation"),
        ("SalesDeliveryService", "_confirm_delivery_locked"),
        ("PurchaseReceiptService", "_confirm_receipt_posting"),
        ("PurchaseReceiptService", "withdraw_receipt_confirmation"),
        ("SalesReturnService", "confirm_return"),
        ("SalesReturnService", "withdraw_confirmation"),
        ("PurchaseReturnService", "confirm_return"),
        ("PurchaseReturnService", "withdraw_confirmation"),
        ("OtherInboundService", "confirm_inbound"),
        ("OtherInboundService", "withdraw_confirmation"),
        ("OtherInboundService", "repair_deleted_other_inbound_inventory"),
        ("OtherOutboundService", "confirm_outbound"),
        ("OtherOutboundService", "withdraw_confirmation"),
        ("MaterialBorrowService", "confirm_borrow"),
        ("MaterialBorrowService", "withdraw_confirmation"),
        ("MaterialReturnService", "confirm_return"),
    ],
    "apps/kuaizhizao/services/semi_finished_goods_receipt_service.py": [
        ("SemiFinishedGoodsReceiptService", "confirm_receipt"),
        ("SemiFinishedGoodsReceiptService", "withdraw_receipt_confirmation"),
    ],
    "apps/kuaizhizao/services/customer_material_registration_service.py": [
        ("CustomerMaterialRegistrationService", "_post_inventory_for_registration"),
        ("CustomerMaterialRegistrationService", "withdraw_registration"),
    ],
}

_STOCK_POSTING_NAMES = _ATOMIC_NAMES | _WRAPPER_NAMES


def test_serial_persisted_flows_pass_serial_nos_to_posting():
    """明细行持久化了序列号的单据流，过账调用必须带 serial_nos。

    serial_managed 物料的入库方向缺 serials 会被「入库必须提供序列号」拒死；
    出库方向缺 serials 则让 MaterialSerial 台账漂移。结构性断言防止接线回退。
    """
    for rel, targets in _SERIAL_PERSISTED_FLOWS.items():
        source = (_SRC / rel).read_text()
        tree = ast.parse(source)
        class_map = {
            n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)
        }
        for class_name, fn_name in targets:
            cls = class_map.get(class_name)
            assert cls is not None, f"{rel} 缺类 {class_name}"
            fn = next(
                (
                    n
                    for n in cls.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name == fn_name
                ),
                None,
            )
            assert fn is not None, f"{class_name} 缺方法 {fn_name}"
            posting_calls = [
                c
                for c in ast.walk(fn)
                if isinstance(c, ast.Call)
                and isinstance(c.func, ast.Attribute)
                and c.func.attr in _STOCK_POSTING_NAMES
            ]
            assert posting_calls, (
                f"{class_name}.{fn_name} 内未找到过账调用，接线目标漂移"
            )
            for call in posting_calls:
                has_serials = any(
                    kw.arg == "serial_nos" for kw in call.keywords
                )
                assert has_serials, (
                    f"{class_name}.{fn_name} 第 {call.lineno} 行过账调用"
                    "缺 serial_nos 关键字参数"
                )
                if call.func.attr in ("_increase_stock_no_atomic", "increase_stock"):
                    has_prod_date = any(
                        kw.arg == "ledger_production_date" for kw in call.keywords
                    )
                    assert has_prod_date, (
                        f"{class_name}.{fn_name} 第 {call.lineno} 行入库调用"
                        "缺 ledger_production_date（序列号入库必填，缺失会被拒死）"
                    )
