"""spec 140 / KR-CL1 状态契约钉死：

- 检验单质量态为中文「合格 / 不合格 / 待判定」
- 批次账质量态为 qualified / pending_qc / quarantine / unqualified
- 入库门禁查检验单用中文「合格」；成品/半成品入库过账写批次 qualified
- 半成品一键入库工单态白名单同时收英文 in_progress/completed 与中文「进行中」「已完成」
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.master_data.constants.batch_quality_status import (
    ALL_BATCH_QUALITY_STATUSES,
    PENDING_QC,
    QUALIFIED,
    QUARANTINE,
    UNQUALIFIED,
)
from apps.kuaizhizao.services.inspection_policy_service import (
    fqc_inspection_passed_for_inbound,
    iqc_inspection_passed_for_inbound,
)
from apps.kuaizhizao.services.semi_finished_goods_receipt_service import (
    SemiFinishedGoodsReceiptService,
    WORK_ORDER_INBOUND_ALLOWED_STATUSES,
)
from apps.kuaizhizao.services.warehouse_service import FinishedGoodsReceiptService
from infra.exceptions.exceptions import BusinessLogicError


def test_batch_quality_status_literals():
    assert QUALIFIED == "qualified"
    assert PENDING_QC == "pending_qc"
    assert QUARANTINE == "quarantine"
    assert UNQUALIFIED == "unqualified"
    assert ALL_BATCH_QUALITY_STATUSES == {QUALIFIED, PENDING_QC, QUARANTINE, UNQUALIFIED}


def test_inbound_posting_writes_batch_qualified_literal():
    """成品/半成品入库过账到库存的批次质量态必须是契约字面 qualified。"""
    import inspect

    from apps.kuaizhizao.services import warehouse_service, semi_finished_goods_receipt_service

    assert 'quality_status="qualified"' in inspect.getsource(
        warehouse_service.FinishedGoodsReceiptService.confirm_receipt
    )
    assert 'quality_status="qualified"' in inspect.getsource(
        semi_finished_goods_receipt_service.SemiFinishedGoodsReceiptService.confirm_receipt
    )


def _insp(**kw):
    defaults = {
        "status": "已检验",
        "review_status": "已审核",
        "qualified_quantity": 5,
        "quality_status": "合格",
    }
    defaults.update(kw)
    return MagicMock(**defaults)


def test_iqc_passed_requires_chinese_qualified():
    """门禁匹配检验单中文质量态「合格」，批次英文字面不算合格。"""
    with patch(
        "infra.services.business_config_service.BusinessConfigService.check_audit_required",
        new=AsyncMock(return_value=False),
    ):
        assert asyncio.run(
            iqc_inspection_passed_for_inbound(1, _insp(quality_status="合格"))
        ) is True
        for bad in ("不合格", "待判定", "qualified", "pending_qc"):
            assert asyncio.run(
                iqc_inspection_passed_for_inbound(1, _insp(quality_status=bad))
            ) is False


def test_fqc_passed_requires_conducted_status_and_positive_qualified_qty():
    """成品检验合格口径：已检验/已审核且合格数>0（部分不合格仍放行合格数）。"""
    with patch(
        "infra.services.business_config_service.BusinessConfigService.check_audit_required",
        new=AsyncMock(return_value=False),
    ):
        assert asyncio.run(
            fqc_inspection_passed_for_inbound(1, _insp(quality_status="不合格"))
        ) is True
        assert asyncio.run(
            fqc_inspection_passed_for_inbound(1, _insp(status="待检验"))
        ) is False
        assert asyncio.run(
            fqc_inspection_passed_for_inbound(1, _insp(qualified_quantity=0))
        ) is False


@pytest.mark.parametrize("status", ["in_progress", "completed", "进行中", "已完成"])
def test_semi_finished_inbound_whitelist_accepts_en_and_cn(status):
    assert status in WORK_ORDER_INBOUND_ALLOWED_STATUSES


def test_semi_finished_inbound_whitelist_rejects_illegal_status():
    for status in ("draft", "released", "cancelled", "split", "草稿", "已取消"):
        assert status not in WORK_ORDER_INBOUND_ALLOWED_STATUSES


def _preview_mocks(work_order):
    return (
        patch(
            "apps.kuaizhizao.models.work_order.WorkOrder.get_or_none",
            new=AsyncMock(return_value=work_order),
        ),
        patch.object(
            FinishedGoodsReceiptService,
            "_get_work_order_inbound_quota",
            new=AsyncMock(
                return_value={"pending": 0.0, "fqc_qualified_remaining": None}
            ),
        ),
        patch.object(
            FinishedGoodsReceiptService,
            "_resolve_work_order_suggested_receipt_quantity",
            new=AsyncMock(return_value=0.0),
        ),
        patch.object(
            FinishedGoodsReceiptService,
            "_resolve_work_order_inbound_preview_quantities",
            new=AsyncMock(return_value=(0.0, 0.0, 0.0, 0.0)),
        ),
        patch(
            "apps.master_data.models.material.Material.get_or_none",
            new=AsyncMock(return_value=None),
        ),
    )


def _wo(status: str):
    return MagicMock(
        id=10,
        status=status,
        product_id=9,
        code="WO-1",
        product_code="M-9",
        product_name="半成品9",
        product_spec=None,
        sales_order_code=None,
    )


@pytest.mark.parametrize("status", ["in_progress", "completed", "进行中", "已完成"])
def test_semi_finished_preview_accepts_bilingual_statuses(status):
    wo = _wo(status)
    m = _preview_mocks(wo)
    with m[0], m[1], m[2], m[3], m[4]:
        resp = asyncio.run(
            SemiFinishedGoodsReceiptService().get_work_order_inbound_preview(1, 10)
        )
    assert resp.inbound_doc_kind == "semi_finished_goods"


@pytest.mark.parametrize("status", ["draft", "released", "cancelled"])
def test_semi_finished_preview_rejects_illegal_statuses(status):
    wo = _wo(status)
    with patch(
        "apps.kuaizhizao.models.work_order.WorkOrder.get_or_none",
        new=AsyncMock(return_value=wo),
    ):
        with pytest.raises(BusinessLogicError, match="无法预览入库明细"):
            asyncio.run(
                SemiFinishedGoodsReceiptService().get_work_order_inbound_preview(1, 10)
            )
