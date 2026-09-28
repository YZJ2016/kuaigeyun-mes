"""工单拆分关联：关系写入异常离开 split_work_order。_RecordingTx 不打开数据库事务，不证明行已回滚。按工序拆分保持拒绝。"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.kuaizhizao.schemas.work_order import WorkOrderSplitRequest
from apps.kuaizhizao.services import work_order_service as module
from infra.exceptions.exceptions import BusinessLogicError, ValidationError


class _RecordingTx:
    """in_transaction 替身：不打开数据库事务。记录离开上下文的异常且不吞掉它，不证明行已回滚。"""

    def __init__(self):
        self.exc_type = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.exc_type = exc_type
        return False


def _parent_work_order():
    return SimpleNamespace(
        id=10,
        status="draft",
        quantity=Decimal("10"),
        code="WO-1",
        name="主工单",
        product_id=1,
        product_code="P",
        product_name="产品",
        production_mode="mto",
        sales_order_id=None,
        sales_order_code=None,
        sales_order_name=None,
        workshop_id=None,
        workshop_name=None,
        work_center_id=None,
        work_center_name=None,
        priority=1,
        planned_start_date=None,
        planned_end_date=None,
        updated_by=None,
        updated_by_name=None,
        save=AsyncMock(),
    )


def _wire_split_prefix(monkeypatch, parent):
    tx = _RecordingTx()
    monkeypatch.setattr(module, "in_transaction", lambda *a, **k: tx)
    qs = MagicMock()
    qs.all = AsyncMock(return_value=[])
    monkeypatch.setattr(module.ReportingRecord, "filter", lambda *a, **k: qs)
    child = SimpleNamespace(
        id=21,
        uuid="child-uuid-1",
        tenant_id=1,
        code="WO-1-001",
        name="主工单-拆分1",
        product_id=1,
        product_code="P",
        product_name="产品",
        quantity=Decimal("5"),
        status="draft",
        created_by=7,
        created_by_name="op",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    monkeypatch.setattr(module.WorkOrder, "create", AsyncMock(return_value=child))
    svc = module.WorkOrderService()
    monkeypatch.setattr(svc, "_is_work_order_param_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(svc, "get_by_id", AsyncMock(return_value=parent))
    monkeypatch.setattr(svc, "get_user_info", AsyncMock(return_value={"name": "op"}))
    monkeypatch.setattr(svc, "_next_split_child_sequence", AsyncMock(return_value=1))
    monkeypatch.setattr(svc, "_provision_split_work_order_operations", AsyncMock())
    return svc, tx, child


def _quantity_request():
    return WorkOrderSplitRequest(split_type="quantity", split_quantities=[Decimal("10")])


@pytest.mark.asyncio
async def test_split_relation_already_exists_leaves_split_work_order(monkeypatch):
    """「关联关系已存在」离开 split_work_order，不作为拆分成功返回。_RecordingTx 不打开数据库事务，不证明行已回滚。"""
    parent = _parent_work_order()
    svc, tx, _child = _wire_split_prefix(monkeypatch, parent)

    async def _exists(*a, **k):
        raise BusinessLogicError("关联关系已存在")

    monkeypatch.setattr(
        "apps.kuaizhizao.services.document_relation_new_service.DocumentRelationNewService.create_relation",
        _exists,
    )

    with pytest.raises(BusinessLogicError, match="关联关系已存在"):
        await svc.split_work_order(
            tenant_id=1,
            work_order_id=10,
            split_data=_quantity_request(),
            created_by=7,
        )

    assert tx.exc_type is BusinessLogicError
    assert module.WorkOrder.create.await_count == 1
    parent.save.assert_awaited()
    assert parent.status == "split"


@pytest.mark.asyncio
async def test_split_relation_other_error_leaves_split_work_order(monkeypatch):
    """关系写入的其它异常同样离开 split_work_order，不记日志后当拆分成功。_RecordingTx 不证明行已回滚。"""
    parent = _parent_work_order()
    svc, tx, _child = _wire_split_prefix(monkeypatch, parent)

    async def _boom(*a, **k):
        raise RuntimeError("relation insert failed")

    monkeypatch.setattr(
        "apps.kuaizhizao.services.document_relation_new_service.DocumentRelationNewService.create_relation",
        _boom,
    )

    with pytest.raises(RuntimeError, match="relation insert failed"):
        await svc.split_work_order(
            tenant_id=1,
            work_order_id=10,
            split_data=_quantity_request(),
            created_by=7,
        )

    assert tx.exc_type is RuntimeError
    assert module.WorkOrder.create.await_count == 1
    parent.save.assert_awaited()


@pytest.mark.asyncio
async def test_split_relation_created_once_per_child_with_split_desc(monkeypatch):
    """成功路径：每个子工单各调一次 create_relation，业务键 source=父、target=子、
    relation_desc="工单拆分"——保护撤销/删除侧按键匹配（delete_relation 业务键）的回归。"""
    parent = _parent_work_order()
    svc, tx, _child = _wire_split_prefix(monkeypatch, parent)

    create_relation = AsyncMock()
    monkeypatch.setattr(
        "apps.kuaizhizao.services.document_relation_new_service.DocumentRelationNewService.create_relation",
        create_relation,
    )

    await svc.split_work_order(
        tenant_id=1,
        work_order_id=10,
        split_data=WorkOrderSplitRequest(
            split_type="quantity",
            split_quantities=[Decimal("5"), Decimal("5")],
        ),
        created_by=7,
    )

    assert create_relation.await_count == 2
    for awaited in create_relation.await_args_list:
        assert awaited.kwargs["tenant_id"] == 1
        assert awaited.kwargs["created_by"] == 7
        rel = awaited.kwargs["relation_data"]
        assert (rel.source_type, rel.source_id) == ("work_order", 10)
        assert (rel.target_type, rel.target_id) == ("work_order", 21)
        assert rel.relation_type == "source"
        assert rel.relation_mode == "push"
        assert rel.relation_desc == "工单拆分"
    assert tx.exc_type is None


def test_operation_split_schema_is_deprecated_never_but_still_parsed():
    """契约标明 operation 不可成功；schema 不把该值变成 422。"""
    req = WorkOrderSplitRequest(split_type="operation", operation_ids=[1])
    assert req.split_type == "operation"
    split_desc = WorkOrderSplitRequest.model_fields["split_type"].description
    op_ids_desc = WorkOrderSplitRequest.model_fields["operation_ids"].description
    assert "Deprecated-never" in split_desc
    assert "仅 quantity" in split_desc
    assert "或operation" not in split_desc
    assert "Deprecated-never" in op_ids_desc
    assert "要拆分到新工单" not in op_ids_desc


@pytest.mark.asyncio
async def test_operation_split_rejected_by_service(monkeypatch):
    """服务继续以 ValidationError 拒绝按工序拆分，且不创建子工单。"""
    parent = _parent_work_order()
    svc, tx, _child = _wire_split_prefix(monkeypatch, parent)

    with pytest.raises(ValidationError, match="按工序拆分功能暂未实现"):
        await svc.split_work_order(
            tenant_id=1,
            work_order_id=10,
            split_data=WorkOrderSplitRequest(split_type="operation"),
            created_by=7,
        )

    assert tx.exc_type is ValidationError
    module.WorkOrder.create.assert_not_awaited()
    parent.save.assert_not_awaited()
