"""会计科目编码规则、级次解析、辅助核算切换与父科目末级同步。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaicaiwu.services.gl.coa_service import (
    CoaService,
    allows_account_field_change_with_activity,
)


def test_allows_turn_off_aux_with_activity_not_turn_on_or_code():
    assert allows_account_field_change_with_activity("aux_customer", True, False) is True
    assert allows_account_field_change_with_activity("aux_supplier", True, False) is True
    assert allows_account_field_change_with_activity("aux_customer", False, True) is False
    assert allows_account_field_change_with_activity("account_code", "6001", "6002") is False
    assert allows_account_field_change_with_activity("account_type", "asset", "liability") is False


def test_code_lengths_from_rule_default():
    assert CoaService.code_lengths_from_rule("4-2-2-2") == [4, 6, 8, 10]


def test_code_lengths_from_rule_custom():
    assert CoaService.code_lengths_from_rule("4-3-3") == [4, 7, 10]


def test_cas_manufacturing_cost_accounts_sequential():
    from apps.kuaicaiwu.services.gl.coa_templates import COA_TEMPLATES

    codes = [
        row["account_code"]
        for row in COA_TEMPLATES["cas_manufacturing"]["accounts"]
        if row.get("account_type") == "cost"
    ]
    assert codes == ["5001", "5101", "5201", "5301", "5401", "5402", "5403"]


def test_cas_core_includes_1001_cash():
    from apps.kuaicaiwu.services.gl.coa_templates import COA_TEMPLATES

    codes = [row["account_code"] for row in COA_TEMPLATES["cas_manufacturing"]["accounts"]]
    assert codes[0] == "1001"
    assert COA_TEMPLATES["cas_manufacturing"]["accounts"][0]["account_name"] == "库存现金"


def test_cas_core_equity_includes_4102():
    from apps.kuaicaiwu.services.gl.coa_templates import COA_TEMPLATES

    equity_codes = [
        row["account_code"]
        for row in COA_TEMPLATES["cas_manufacturing"]["accounts"]
        if row.get("account_type") == "equity"
    ]
    assert "4102" in equity_codes
    idx_4101 = equity_codes.index("4101")
    idx_4102 = equity_codes.index("4102")
    idx_4103 = equity_codes.index("4103")
    assert idx_4101 < idx_4102 < idx_4103


@pytest.mark.asyncio
async def test_sync_parent_leaf_flag_restores_parent_when_no_children():
    parent = SimpleNamespace(id=10, is_leaf=False, save=AsyncMock())
    filter_mock = MagicMock()
    filter_mock.exists = AsyncMock(return_value=False)
    svc = CoaService()
    with patch(
        "apps.kuaicaiwu.services.gl.coa_service.ChartOfAccount.get_or_none",
        AsyncMock(return_value=parent),
    ), patch(
        "apps.kuaicaiwu.services.gl.coa_service.ChartOfAccount.filter",
        return_value=filter_mock,
    ):
        await svc.sync_parent_leaf_flag(1, 10)
    assert parent.is_leaf is True
    parent.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_parent_leaf_flag_keeps_non_leaf_when_siblings_remain():
    parent = SimpleNamespace(id=10, is_leaf=False, save=AsyncMock())
    filter_mock = MagicMock()
    filter_mock.exists = AsyncMock(return_value=True)
    svc = CoaService()
    with patch(
        "apps.kuaicaiwu.services.gl.coa_service.ChartOfAccount.get_or_none",
        AsyncMock(return_value=parent),
    ), patch(
        "apps.kuaicaiwu.services.gl.coa_service.ChartOfAccount.filter",
        return_value=filter_mock,
    ):
        await svc.sync_parent_leaf_flag(1, 10)
    assert parent.is_leaf is False
    parent.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_account_syncs_parent_leaf_flag():
    child = SimpleNamespace(id=20, parent_id=10, deleted_at=None, is_active=True, save=AsyncMock())
    children_qs = MagicMock()
    children_qs.exists = AsyncMock(return_value=False)
    svc = CoaService()
    with patch(
        "apps.kuaicaiwu.services.gl.coa_service.ChartOfAccount.get_or_none",
        AsyncMock(return_value=child),
    ), patch.object(
        svc, "_has_activity", AsyncMock(return_value=False)
    ), patch(
        "apps.kuaicaiwu.services.gl.coa_service.ChartOfAccount.filter",
        return_value=children_qs,
    ), patch.object(
        svc, "sync_parent_leaf_flag", AsyncMock()
    ) as sync_mock:
        await svc.delete_account(1, 20)
    child.save.assert_awaited_once()
    sync_mock.assert_awaited_once_with(1, 10)


@pytest.mark.asyncio
async def test_repair_orphan_non_leaf_flags_repairs_only_orphans():
    orphan = SimpleNamespace(id=10, is_leaf=False, save=AsyncMock())
    valid_parent = SimpleNamespace(id=11, is_leaf=False, save=AsyncMock())

    non_leaf_qs = MagicMock()
    non_leaf_qs.all = AsyncMock(return_value=[orphan, valid_parent])

    def filter_side_effect(*_args, **kwargs):
        if kwargs.get("is_leaf") is False:
            return non_leaf_qs
        child_qs = MagicMock()
        child_qs.exists = AsyncMock(return_value=(kwargs.get("parent_id") == 11))
        return child_qs

    svc = CoaService()
    with patch(
        "apps.kuaicaiwu.services.gl.coa_service.ChartOfAccount.filter",
        side_effect=filter_side_effect,
    ):
        fixed = await svc.repair_orphan_non_leaf_flags(1)

    assert fixed == 1
    assert orphan.is_leaf is True
    orphan.save.assert_awaited_once()
    assert valid_parent.is_leaf is False
    valid_parent.save.assert_not_awaited()
