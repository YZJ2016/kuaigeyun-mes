"""spec 140 / KR-CL1：检验门禁按 source 判定与状态契约。

- default_none（无策略）→ 成品/采购来料/客供料入库必检，与三个全局开关存值无关
- material 且 eff=none → 物料级显式免检放行
- stage_disabled / module_disabled → 环节/模块未启用跳过
- simple / plan → 必检
- 成品入库 work_order_id 为空不得绕开 FQC
- 检验单中文「合格/不合格/待判定」 ↔ 批次账英文 qualified/pending_qc/quarantine/unqualified
- 半成品一键入库工单态白名单同时收英文 in_progress/completed 与中文「进行中」「已完成」
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaizhizao.services.inspection_policy_service import (
    assert_fqc_for_finished_goods_receipt,
    assert_iqc_for_customer_material_registration_lines,
    assert_iqc_for_purchase_receipt_lines,
    inbound_inspection_required,
    resolve_inspection_policy,
    resolve_material_stage_policy_from_rows,
)
from infra.exceptions.exceptions import BusinessLogicError


def _cfg(**over):
    cfg = {
        "stage_enabled": {"iqc": True, "ipqc": True, "fqc": True, "oqc": True},
        "module_enabled": {
            "incoming": True,
            "process": True,
            "finished": True,
            "defect_handling": True,
        },
        "auto_create": {},
        "gate": {},
        "fai": {},
    }
    for k, v in over.items():
        cfg[k] = v
    return cfg


def _material(**kw):
    defaults = {
        "inspection_stages": None,
        "inspection_mode": None,
        "default_inspection_plan_id": None,
        "group_id": None,
    }
    defaults.update(kw)
    return MagicMock(**defaults)


def _line(**kw):
    defaults = {"material_id": 1, "receipt_quantity": 10, "qualified_quantity": None, "quantity": 10}
    defaults.update(kw)
    return MagicMock(**defaults)


class _EmptyQuery:
    def filter(self, *_args, **_kwargs):
        return self

    async def all(self):
        return []


# ---------- resolve_material_stage_policy_from_rows：source 矩阵 ----------


def test_policy_source_default_none_when_no_material():
    eff, plan_id, source = resolve_material_stage_policy_from_rows(_cfg(), "iqc", None, None)
    assert (eff, plan_id, source) == ("none", None, "default_none")


def test_policy_source_default_none_when_all_stages_none():
    mat = _material(inspection_stages={"iqc": {"mode": "none"}, "fqc": {"mode": "none"}, "oqc": {"mode": "none"}})
    eff, _, source = resolve_material_stage_policy_from_rows(_cfg(), "iqc", mat, None)
    assert (eff, source) == ("none", "default_none")


def test_policy_source_material_none_is_explicit_exempt():
    """inspection_stages 非空且任一环节 mode≠none，但当前环节 mode=none → material+none 显式免检。"""
    mat = _material(
        inspection_stages={
            "iqc": {"mode": "none"},
            "fqc": {"mode": "simple"},
            "oqc": {"mode": "none"},
        }
    )
    eff, _, source = resolve_material_stage_policy_from_rows(_cfg(), "iqc", mat, None)
    assert (eff, source) == ("none", "material")
    eff, _, source = resolve_material_stage_policy_from_rows(_cfg(), "fqc", mat, None)
    assert (eff, source) == ("simple", "material")


def test_policy_source_material_legacy_and_group():
    mat = _material(inspection_mode="simple")
    eff, _, source = resolve_material_stage_policy_from_rows(_cfg(), "iqc", mat, None)
    assert (eff, source) == ("simple", "material_legacy")

    mat = _material(group_id=7)
    grp = {"iqc": {"mode": "plan", "plan_id": 3, "plan_ids": [3]}}
    eff, plan_id, source = resolve_material_stage_policy_from_rows(_cfg(), "iqc", mat, grp)
    assert (eff, plan_id, source) == ("plan", 3, "material_group")


def test_policy_source_stage_and_module_disabled():
    cfg = _cfg(stage_enabled={"iqc": False})
    eff, _, source = resolve_material_stage_policy_from_rows(cfg, "iqc", _material(), None)
    assert (eff, source) == ("none", "stage_disabled")

    cfg = _cfg(module_enabled={"incoming": False})
    eff, _, source = resolve_material_stage_policy_from_rows(cfg, "iqc", _material(), None)
    assert (eff, source) == ("none", "module_disabled")


# ---------- resolve_inspection_policy：eff=none 时透传内层 source ----------


def test_resolve_inspection_policy_preserves_material_none_source():
    """material 级显式免检不得再被收成 default_none。"""
    mat = _material(
        inspection_stages={
            "iqc": {"mode": "none"},
            "fqc": {"mode": "simple"},
            "oqc": {"mode": "none"},
        }
    )
    with patch(
        "apps.kuaizhizao.services.inspection_policy_service.get_quality_effective_config",
        new=AsyncMock(return_value=_cfg()),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.batch_get_materials_for_policy",
        new=AsyncMock(return_value=({1: mat}, {})),
    ):
        eff, plan_id, source = asyncio.run(
            resolve_inspection_policy(1, "iqc", material_id=1)
        )
    assert (eff, plan_id, source) == ("none", None, "material")


def test_resolve_inspection_policy_default_none_stays_default_none():
    mat = _material()
    with patch(
        "apps.kuaizhizao.services.inspection_policy_service.get_quality_effective_config",
        new=AsyncMock(return_value=_cfg()),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.batch_get_materials_for_policy",
        new=AsyncMock(return_value=({1: mat}, {})),
    ):
        _, _, source = asyncio.run(resolve_inspection_policy(1, "iqc", material_id=1))
    assert source == "default_none"


# ---------- inbound_inspection_required 真值表 ----------


@pytest.mark.parametrize(
    "eff,source,required",
    [
        ("none", "default_none", True),
        ("none", "material", False),
        ("none", "stage_disabled", False),
        ("none", "module_disabled", False),
        ("simple", "material", True),
        ("plan", "material", True),
        ("simple", "material_legacy", True),
        ("plan", "material_group", True),
        ("simple", "work_order_override", True),
    ],
)
def test_inbound_inspection_required_truth_table(eff, source, required):
    assert inbound_inspection_required(eff, source) is required


# ---------- FQC 门禁 ----------


def _fqc_mocks(policy, *, qualified=Decimal("0"), remaining=Decimal("0"), concession=Decimal("0")):
    return (
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.get_quality_effective_config",
            new=AsyncMock(return_value=_cfg(gate={"require_fqc_before_finished_goods_receipt": False})),
        ),
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.sum_defect_accept_quantity_for_finished_goods_receipt",
            new=AsyncMock(return_value=concession),
        ),
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
            new=AsyncMock(return_value=policy),
        ),
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.sum_fqc_inbound_qualified_quantity",
            new=AsyncMock(return_value=qualified),
        ),
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.get_fqc_inbound_remaining_quantity",
            new=AsyncMock(return_value=remaining),
        ),
    )


def test_fqc_gate_blocks_default_none_even_with_work_order():
    """无策略（default_none）必检：合格数 0 即拒绝。"""
    mocks = _fqc_mocks(("none", None, "default_none"))
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
        with pytest.raises(BusinessLogicError, match="成品检验"):
            asyncio.run(assert_fqc_for_finished_goods_receipt(1, 99, 10, [_line()]))


def test_fqc_gate_blocks_default_none_when_work_order_id_empty():
    """空 work_order_id 不得绕开 FQC；default_none 行照样拒绝。"""
    mocks = _fqc_mocks(("none", None, "default_none"))
    with mocks[0], mocks[1], mocks[2], mocks[3] as cap_mock, mocks[4]:
        with pytest.raises(BusinessLogicError, match="成品检验"):
            asyncio.run(assert_fqc_for_finished_goods_receipt(1, 99, None, [_line()]))
        cap_mock.assert_not_called()


def test_fqc_gate_allows_material_exempt_without_work_order():
    """material+none 物料级显式免检：空工单也放行。"""
    mocks = _fqc_mocks(("none", None, "material"))
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
        asyncio.run(assert_fqc_for_finished_goods_receipt(1, 99, None, [_line()]))


@pytest.mark.parametrize("source", ["stage_disabled", "module_disabled"])
def test_fqc_gate_skips_stage_or_module_disabled(source):
    mocks = _fqc_mocks(("none", None, source))
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
        asyncio.run(assert_fqc_for_finished_goods_receipt(1, 99, 10, [_line()]))


def test_fqc_gate_blocks_simple_mode_without_qualified_qty():
    mocks = _fqc_mocks(("simple", None, "material"))
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
        with pytest.raises(BusinessLogicError, match="成品检验"):
            asyncio.run(assert_fqc_for_finished_goods_receipt(1, 99, 10, [_line()]))


def test_fqc_gate_allows_when_qualified_remaining_covers_qty():
    mocks = _fqc_mocks(
        ("plan", 5, "material"), qualified=Decimal("60"), remaining=Decimal("60")
    )
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
        asyncio.run(
            assert_fqc_for_finished_goods_receipt(1, 99, 10, [_line(receipt_quantity=10)])
        )


# ---------- IQC 门禁：采购入库 ----------


def _iqc_mocks(policy, *, inspections=None, concessions=frozenset()):
    class _Query:
        def filter(self, *_a, **_k):
            return self

        async def all(self):
            return list(inspections or [])

    return (
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.get_quality_effective_config",
            new=AsyncMock(
                return_value=_cfg(gate={"require_iqc_before_receipt_confirm": False})
            ),
        ),
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
            new=AsyncMock(return_value=policy),
        ),
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.defect_accept_material_ids_for_purchase_receipt",
            new=AsyncMock(return_value=concessions),
        ),
        patch(
            "apps.kuaizhizao.models.incoming_inspection.IncomingInspection.filter",
            return_value=_Query(),
        ),
    )


def test_iqc_purchase_gate_blocks_default_none_regardless_of_switch():
    """开关存 False 时，无策略（default_none）行仍被拒。"""
    cfg_mock, policy_mock, concession_mock, insp_mock = _iqc_mocks(("none", None, "default_none"))
    with cfg_mock as gate_cfg, policy_mock, concession_mock, insp_mock:
        with pytest.raises(BusinessLogicError, match="来料检验"):
            asyncio.run(assert_iqc_for_purchase_receipt_lines(1, 88, [_line()]))
        gate_cfg.assert_not_called()


def test_iqc_purchase_gate_allows_material_exempt():
    cfg_mock, policy_mock, concession_mock, insp_mock = _iqc_mocks(("none", None, "material"))
    with cfg_mock as gate_cfg, policy_mock, concession_mock, insp_mock:
        asyncio.run(assert_iqc_for_purchase_receipt_lines(1, 88, [_line()]))
        gate_cfg.assert_not_called()


@pytest.mark.parametrize("source", ["stage_disabled", "module_disabled"])
def test_iqc_purchase_gate_skips_disabled_stage_or_module(source):
    cfg_mock, policy_mock, concession_mock, insp_mock = _iqc_mocks(("none", None, source))
    with cfg_mock, policy_mock, concession_mock, insp_mock:
        asyncio.run(assert_iqc_for_purchase_receipt_lines(1, 88, [_line()]))


def test_iqc_purchase_gate_blocks_simple_mode_without_inspection():
    cfg_mock, policy_mock, concession_mock, insp_mock = _iqc_mocks(("simple", None, "material"))
    with cfg_mock, policy_mock, concession_mock, insp_mock:
        with pytest.raises(BusinessLogicError, match="来料检验"):
            asyncio.run(assert_iqc_for_purchase_receipt_lines(1, 88, [_line()]))


def test_iqc_purchase_gate_passes_with_qualified_inspection():
    insp = MagicMock(material_id=1)
    cfg_mock, policy_mock, concession_mock, insp_mock = _iqc_mocks(
        ("simple", None, "material"), inspections=[insp]
    )
    with cfg_mock, policy_mock, concession_mock, insp_mock, patch(
        "apps.kuaizhizao.services.inspection_policy_service.iqc_inspection_passed_for_inbound",
        new=AsyncMock(return_value=True),
    ):
        asyncio.run(assert_iqc_for_purchase_receipt_lines(1, 88, [_line()]))


# ---------- IQC 门禁：客供料登记（与采购来料同一规则） ----------


def _cm_iqc_mocks(policy, *, inspections=None):
    class _Query:
        def filter(self, *_a, **_k):
            return self

        async def all(self):
            return list(inspections or [])

    return (
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.get_quality_effective_config",
            new=AsyncMock(
                return_value=_cfg(gate={"require_iqc_before_customer_material_confirm": False})
            ),
        ),
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
            new=AsyncMock(return_value=policy),
        ),
        patch(
            "apps.kuaizhizao.models.incoming_inspection.IncomingInspection.filter",
            return_value=_Query(),
        ),
    )


def test_iqc_customer_material_gate_blocks_default_none_regardless_of_switch():
    cfg_mock, policy_mock, insp_mock = _cm_iqc_mocks(("none", None, "default_none"))
    with cfg_mock as gate_cfg, policy_mock, insp_mock:
        with pytest.raises(BusinessLogicError, match="来料检验"):
            asyncio.run(
                assert_iqc_for_customer_material_registration_lines(1, 77, [_line()])
            )
        gate_cfg.assert_not_called()


def test_iqc_customer_material_gate_allows_material_exempt():
    cfg_mock, policy_mock, insp_mock = _cm_iqc_mocks(("none", None, "material"))
    with cfg_mock as gate_cfg, policy_mock, insp_mock:
        asyncio.run(assert_iqc_for_customer_material_registration_lines(1, 77, [_line()]))
        gate_cfg.assert_not_called()


def test_iqc_customer_material_gate_passes_with_qualified_reviewed_inspection():
    insp = MagicMock(material_id=1, quality_status="合格", review_status="已审核")
    cfg_mock, policy_mock, insp_mock = _cm_iqc_mocks(
        ("simple", None, "material"), inspections=[insp]
    )
    with cfg_mock, policy_mock, insp_mock:
        asyncio.run(assert_iqc_for_customer_material_registration_lines(1, 77, [_line()]))


# ---------- 评审拍板：全环节 none 保存校验 / 行级展示口径 / 预览判定同源 ----------


def test_save_rejects_all_none_inspection_stages():
    """spec 140 规则 8：inspection_stages 非空 dict 但三环节全 none → 保存拒绝。"""
    from apps.kuaizhizao.services.inspection_policy_service import (
        assert_master_data_inspection_stages_allowed,
    )
    from infra.exceptions.exceptions import ConflictError

    with patch(
        "apps.kuaizhizao.services.inspection_policy_service.get_quality_effective_config",
        new=AsyncMock(return_value=_cfg()),
    ):
        with pytest.raises(ConflictError, match="全部设为"):
            asyncio.run(
                assert_master_data_inspection_stages_allowed(
                    1,
                    material_stages={
                        "iqc": {"mode": "none"},
                        "fqc": {"mode": "none"},
                        "oqc": {"mode": "none"},
                    },
                )
            )
        # 至少一个环节非 none → 放行
        asyncio.run(
            assert_master_data_inspection_stages_allowed(
                1,
                material_stages={"iqc": {"mode": "none"}, "fqc": {"mode": "simple"}},
            )
        )
        # 空配置/未配置不拦（清配置路径）
        asyncio.run(assert_master_data_inspection_stages_allowed(1, material_stages={}))
        asyncio.run(assert_master_data_inspection_stages_allowed(1, material_stages=None))


def test_inbound_line_qc_mode_display_contract():
    """spec 140 规则 10：必检但无策略时 mode 置 None；免检行仍为 'none'。"""
    from apps.kuaizhizao.services.quality_service import _inbound_line_qc_mode

    assert _inbound_line_qc_mode("simple", True) == "simple"
    assert _inbound_line_qc_mode("plan", True) == "plan"
    assert _inbound_line_qc_mode("none", True) is None
    assert _inbound_line_qc_mode("none", False) == "none"


def test_inbound_preview_quantities_default_none_capped_by_fqc():
    """spec 140 规则 9：入库预览对 default_none 物料按必检口径——FQC 余量封顶。"""
    from apps.kuaizhizao.services.warehouse_service import FinishedGoodsReceiptService

    svc = FinishedGoodsReceiptService()
    wo = MagicMock(product_id=9, quantity=10)
    quota = {"received": 0.0, "pending": 5.0, "fqc_qualified_remaining": 0.0}
    with patch(
        "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
        new=AsyncMock(return_value=("none", None, "default_none")),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.sum_fqc_inbound_qualified_quantity",
        new=AsyncMock(return_value=Decimal("0")),
    ):
        _, _, pending, receipt_qty = asyncio.run(
            svc._resolve_work_order_inbound_preview_quantities(1, 1, wo, quota, 5.0)
        )
    assert (pending, receipt_qty) == (0.0, 0.0)


def test_inbound_preview_quantities_material_exempt_not_capped():
    """物料级显式免检（material+none）不进入 FQC 封顶分支。"""
    from apps.kuaizhizao.services.warehouse_service import FinishedGoodsReceiptService

    svc = FinishedGoodsReceiptService()
    wo = MagicMock(product_id=9, quantity=10)
    quota = {"received": 0.0, "pending": 5.0, "fqc_qualified_remaining": None}
    with patch(
        "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
        new=AsyncMock(return_value=("none", None, "material")),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.sum_fqc_inbound_qualified_quantity",
        new=AsyncMock(return_value=Decimal("0")),
    ) as sum_mock:
        _, _, pending, receipt_qty = asyncio.run(
            svc._resolve_work_order_inbound_preview_quantities(1, 1, wo, quota, 5.0)
        )
    assert (pending, receipt_qty) == (5.0, 5.0)
    sum_mock.assert_not_called()
