"""Spec 223 Batch 1B: CW-P1 / CW-P2 / CW-P3 总账 L1 修复单元测试。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaicaiwu.services.gl.balance_service import BalanceService
from apps.kuaicaiwu.services.gl.period_service import GlPeriodService
from apps.kuaicaiwu.services.gl.transfer_service import GlTransferService
from apps.kuaicaiwu.services.posting_service import (
    PostingService,
    VOUCHER_SOURCE_DOC_TYPE_GL_AUTO_TRANSFER,
    voucher_requires_aux,
)
from infra.exceptions.exceptions import BusinessLogicError


def _fake_tx():
    return MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False))


# ---------- CW-P1 ----------


@pytest.mark.asyncio
async def test_opening_balance_diagnostics_returns_only_non_leaf_plain_residuals():
    accounts = {
        1: SimpleNamespace(id=1, account_code="2221", account_name="应交税费", is_leaf=False),
        2: SimpleNamespace(id=2, account_code="222101", account_name="应交增值税", is_leaf=True),
        3: SimpleNamespace(id=3, account_code="1002", account_name="银行存款", is_leaf=False),
    }
    rows = [
        # 非末级 plain 有残留 -> 应返回
        {
            "account_id": 1,
            "customer_id": None,
            "supplier_id": None,
            "department_id": None,
            "employee_id": None,
            "project_id": None,
            "opening_debit": 0.0,
            "opening_credit": 90775.74,
            "period_debit": 0.0,
            "period_credit": 0.0,
            "ending_debit": 0.0,
            "ending_credit": 90775.74,
        },
        # 非末级辅助行 -> 忽略
        {
            "account_id": 1,
            "customer_id": 99,
            "opening_debit": 100.0,
            "opening_credit": 0.0,
            "ending_debit": 100.0,
            "ending_credit": 0.0,
        },
        # 末级科目 -> 忽略
        {
            "account_id": 2,
            "opening_debit": 0.0,
            "opening_credit": 500.0,
            "ending_debit": 0.0,
            "ending_credit": 500.0,
        },
        # 非末级 plain 全零 -> 忽略
        {
            "account_id": 3,
            "opening_debit": 0.0,
            "opening_credit": 0.0,
            "period_debit": 0.0,
            "period_credit": 0.0,
            "ending_debit": 0.0,
            "ending_credit": 0.0,
        },
    ]
    svc = BalanceService()
    with patch.object(svc, "_load_accounts_by_id", AsyncMock(return_value=accounts)), patch.object(
        svc, "account_balance_sheet", AsyncMock(return_value=rows)
    ):
        diag = await svc.opening_balance_diagnostics(10, 2026, 5)

    assert diag["count"] == 1
    assert diag["items"][0]["account_code"] == "2221"
    assert diag["items"][0]["opening_credit"] == pytest.approx(90775.74, abs=0.01)


@pytest.mark.asyncio
async def test_clear_non_leaf_opening_residual_zeroes_only_non_leaf_plain_rows():
    accounts = {
        1: SimpleNamespace(id=1, account_code="2221", is_leaf=False),
        2: SimpleNamespace(id=2, account_code="222101", is_leaf=True),
    }
    non_leaf_row = SimpleNamespace(
        account_id=1,
        opening_debit=Decimal("0"),
        opening_credit=Decimal("90775.74"),
        period_debit=Decimal("0"),
        period_credit=Decimal("0"),
        year_debit=Decimal("0"),
        year_credit=Decimal("90775.74"),
        ending_debit=Decimal("0"),
        ending_credit=Decimal("90775.74"),
        save=AsyncMock(),
    )
    leaf_row = SimpleNamespace(
        account_id=2,
        opening_debit=Decimal("0"),
        opening_credit=Decimal("500"),
        period_debit=Decimal("0"),
        period_credit=Decimal("0"),
        year_debit=Decimal("0"),
        year_credit=Decimal("500"),
        ending_debit=Decimal("0"),
        ending_credit=Decimal("500"),
        save=AsyncMock(),
    )
    qs = MagicMock()
    qs.all = AsyncMock(return_value=[non_leaf_row, leaf_row])
    svc = BalanceService()
    trial_payload = {"balanced": True, "opening_debit": 0.0, "opening_credit": 500.0}

    with patch.object(svc, "_load_accounts_by_id", AsyncMock(return_value=accounts)), patch(
        "apps.kuaicaiwu.services.gl.balance_service.in_transaction",
        return_value=_fake_tx(),
    ), patch(
        "apps.kuaicaiwu.services.gl.balance_service.AccountBalance.filter",
        return_value=qs,
    ), patch.object(
        svc, "trial_balance", AsyncMock(return_value=trial_payload)
    ):
        res = await svc.clear_non_leaf_opening_residual(10, 2026, 5)

    assert res["cleared"] == 1
    assert res["trial"] == trial_payload
    assert non_leaf_row.opening_credit == Decimal("0")
    assert non_leaf_row.ending_credit == Decimal("0")
    assert non_leaf_row.year_credit == Decimal("0")
    non_leaf_row.save.assert_awaited_once()
    assert leaf_row.opening_credit == Decimal("500")
    leaf_row.save.assert_not_awaited()


# ---------- CW-P2 ----------


@pytest.mark.asyncio
async def test_ensure_period_activates_not_open_row():
    row = SimpleNamespace(period_year=2026, period_month=6, status="not_open", save=AsyncMock())
    svc = GlPeriodService()
    with patch(
        "apps.kuaicaiwu.services.gl.period_service.AccountingPeriod.get_or_none",
        AsyncMock(return_value=row),
    ):
        res = await svc.ensure_period(1, 2026, 6, status="open")
    assert res is row
    assert row.status == "open"
    row.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_assert_period_open_for_posting_rejects_multiple_open_periods():
    settings = SimpleNamespace(initialized=True, current_year=2026, current_month=6)
    p5 = SimpleNamespace(period_year=2026, period_month=5, status="open")
    p6 = SimpleNamespace(period_year=2026, period_month=6, status="open")
    svc = GlPeriodService()
    with patch(
        "apps.kuaicaiwu.services.gl.period_service.GlSettingsService.get_or_create",
        AsyncMock(return_value=settings),
    ), patch(
        "apps.kuaicaiwu.services.gl.period_service.AccountingPeriod.get_or_none",
        AsyncMock(side_effect=[p5, p6]),
    ), patch.object(
        svc, "_open_periods", AsyncMock(return_value=[p5, p6])
    ):
        with pytest.raises(BusinessLogicError, match="存在多个打开的会计期间"):
            await svc.assert_period_open_for_posting(1, 2026, 6)


@pytest.mark.asyncio
async def test_prepare_period_for_posting_rolls_forward_months():
    p5 = SimpleNamespace(period_year=2026, period_month=5, status="open")
    p6 = SimpleNamespace(period_year=2026, period_month=6, status="open")
    p7 = SimpleNamespace(period_year=2026, period_month=7, status="open")
    svc = GlPeriodService()
    with patch.object(
        svc, "_open_periods", AsyncMock(side_effect=[[p5], [p6], [p7]])
    ), patch.object(
        svc, "close_period", AsyncMock()
    ) as close_mock, patch.object(
        svc, "assert_period_open_for_posting", AsyncMock()
    ) as assert_mock:
        await svc.prepare_period_for_posting(1, 2026, 7, operator_id=42)

    assert close_mock.await_count == 2
    close_mock.assert_any_await(1, 2026, 5, 42)
    close_mock.assert_any_await(1, 2026, 6, 42)
    assert_mock.assert_awaited_once_with(1, 2026, 7)


@pytest.mark.asyncio
async def test_close_period_idempotent_opens_next_when_no_later_active():
    period = SimpleNamespace(period_year=2026, period_month=5, status="closed")
    settings = SimpleNamespace(current_year=2026, current_month=5, save=AsyncMock())
    svc = GlPeriodService()
    with patch(
        "apps.kuaicaiwu.services.gl.period_service.AccountingPeriod.get_or_none",
        AsyncMock(return_value=period),
    ), patch.object(
        svc, "_has_later_active_period", AsyncMock(return_value=False)
    ), patch.object(
        svc, "ensure_period", AsyncMock()
    ) as ensure_mock, patch(
        "apps.kuaicaiwu.services.gl.period_service.GlSettingsService.get_or_create",
        AsyncMock(return_value=settings),
    ):
        res = await svc.close_period(1, 2026, 5, operator_id=42)

    assert res["status"] == "already_closed"
    ensure_mock.assert_awaited_once_with(1, 2026, 6, status="open")
    assert settings.current_year == 2026
    assert settings.current_month == 6
    settings.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_voucher_calls_prepare_period_for_posting_inside_transaction():
    voucher = SimpleNamespace(
        id=9,
        status="reviewed",
        period_year=2026,
        period_month=7,
        posted_at=None,
        posted_by=None,
        save=AsyncMock(),
    )
    line_qs = MagicMock()
    line_qs.all = AsyncMock(return_value=[])
    svc = PostingService()
    with patch.object(svc, "_get", AsyncMock(return_value=voucher)), patch(
        "apps.kuaicaiwu.services.posting_service.VoucherLine.filter",
        return_value=line_qs,
    ), patch.object(
        svc, "_assert_deficit_control", AsyncMock()
    ), patch(
        "apps.kuaicaiwu.services.posting_service.in_transaction",
        return_value=_fake_tx(),
    ), patch.object(
        svc.period_service, "prepare_period_for_posting", AsyncMock()
    ) as prep_mock, patch.object(
        svc.balance_service, "apply_voucher_lines", AsyncMock()
    ):
        res = await svc.post_voucher(1, 9, posted_by=7)

    assert res.status == "posted"
    prep_mock.assert_awaited_once_with(1, 2026, 7, 7)


# ---------- CW-P3 ----------


def test_voucher_requires_aux_rules():
    assert voucher_requires_aux(SimpleNamespace(source_event_id=None, source_doc_type=None)) is True
    assert voucher_requires_aux(SimpleNamespace(source_event_id=123, source_doc_type=None)) is False
    assert (
        voucher_requires_aux(
            SimpleNamespace(
                source_event_id=None,
                source_doc_type=VOUCHER_SOURCE_DOC_TYPE_GL_AUTO_TRANSFER,
            )
        )
        is False
    )


@pytest.mark.asyncio
async def test_transfer_service_profit_loss_exempts_aux():
    target = SimpleNamespace(id=100, account_code="4103", account_name="本年利润")
    income_acc = SimpleNamespace(id=101, account_code="6001", account_name="主营业务收入")
    bal_row = SimpleNamespace(period_debit=Decimal("0"), period_credit=Decimal("1000"))

    target_qs = MagicMock()
    target_qs.first = AsyncMock(return_value=target)
    pl_qs = MagicMock()
    pl_qs.all = AsyncMock(return_value=[income_acc])
    bal_qs = MagicMock()
    bal_qs.all = AsyncMock(return_value=[bal_row])

    def coa_filter_side_effect(*_args, **kwargs):
        if kwargs.get("account_code") == "4103":
            return target_qs
        return pl_qs

    created_voucher = SimpleNamespace(id=55)
    posting_instance = MagicMock()
    posting_instance.create_manual_voucher = AsyncMock(return_value=created_voucher)
    posting_instance.voucher_to_dict = MagicMock(return_value={"id": 55})

    svc = GlTransferService()
    with patch.object(svc, "ensure_profit_loss_template", AsyncMock()), patch(
        "apps.kuaicaiwu.services.gl.transfer_service.ChartOfAccount.filter",
        side_effect=coa_filter_side_effect,
    ), patch(
        "apps.kuaicaiwu.services.gl.transfer_service.AccountBalance.filter",
        return_value=bal_qs,
    ), patch(
        "apps.kuaicaiwu.services.gl.transfer_service.PostingService",
        return_value=posting_instance,
    ):
        res = await svc.run_profit_loss_transfer(1, 2026, 5, operator_id=9)

    assert res["created"] is True
    call_args = posting_instance.create_manual_voucher.await_args
    assert call_args.args[2]["source_doc_type"] == VOUCHER_SOURCE_DOC_TYPE_GL_AUTO_TRANSFER
    assert call_args.kwargs["allow_controlled"] is True
    assert call_args.kwargs["require_aux"] is False
