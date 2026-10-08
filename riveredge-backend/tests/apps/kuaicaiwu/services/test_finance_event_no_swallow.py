"""spec 142 业财与库存同一成败：会计事件/关联失败不得吞掉、工资基数不得回退常数、
金蝶推送失败须留下可查询的 source 维度、既有会计护栏不回归。"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

SRC_ROOT = Path(__file__).resolve().parents[4] / "src"


# ---------------------------------------------------------------------------
# T1: record_finance_accounting_event / link_finance_document_relation 改抛
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_finance_accounting_event_propagates_failure(monkeypatch):
    """record_event 抛错时不得返回成功，应包装为 BusinessLogicError 上抛。"""
    from apps.kuaicaiwu.services import finance_integration_hooks
    from infra.exceptions.exceptions import BusinessLogicError

    async def _boom(**kwargs):
        raise RuntimeError("accounting event store down")

    monkeypatch.setattr(
        finance_integration_hooks.AccountingEventService, "record_event", _boom
    )

    with pytest.raises(BusinessLogicError) as exc_info:
        await finance_integration_hooks.record_finance_accounting_event(
            tenant_id=1,
            event_type="WAREHOUSE_INBOUND",
            business_type="inventory",
            source_doc_type="other_inbound",
            source_doc_id=7,
            source_doc_code="QTRK-1",
            target_doc_type="other_inbound",
            target_doc_id=7,
            target_doc_code="QTRK-1",
            amount=Decimal("10"),
            operator_id=1,
        )
    msg = str(exc_info.value)
    # 错误信息须带单据标识与事件类型，便于定位
    assert "WAREHOUSE_INBOUND" in msg
    assert "other_inbound" in msg
    assert "7" in msg


@pytest.mark.asyncio
async def test_link_finance_document_relation_propagates_failure(monkeypatch):
    """单据关联写库失败时不得只记日志当成功。"""
    from apps.kuaicaiwu.services.finance_integration_hooks import (
        link_finance_document_relation,
    )
    from apps.kuaizhizao.services.document_relation_new_service import (
        DocumentRelationNewService,
    )
    from infra.exceptions.exceptions import BusinessLogicError

    async def _boom(self, **kwargs):
        raise RuntimeError("relation insert conflict")

    monkeypatch.setattr(DocumentRelationNewService, "create_relation", _boom)

    with pytest.raises(BusinessLogicError):
        await link_finance_document_relation(
            tenant_id=1,
            source_type="sales_delivery",
            source_id=3,
            source_code="XSCK-3",
            target_type="receivable",
            target_id=9,
            target_code="YS-9",
            relation_desc="销售出库确认自动生成应收单",
            created_by=1,
        )


@pytest.mark.asyncio
async def test_record_event_success_still_passes_payload(monkeypatch):
    """正常路径仍透传参数到 record_event（不回归）。"""
    from apps.kuaicaiwu.services import finance_integration_hooks

    captured: dict = {}

    async def _ok(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        finance_integration_hooks.AccountingEventService, "record_event", _ok
    )

    await finance_integration_hooks.record_finance_accounting_event(
        tenant_id=2,
        event_type="FINISHED_GOODS_RECEIPT_TO_INVENTORY",
        business_type="inventory",
        source_doc_type="finished_goods_receipt",
        source_doc_id=11,
        source_doc_code="CPRK-11",
        target_doc_type="finished_goods_receipt",
        target_doc_id=11,
        target_doc_code="CPRK-11",
        amount=Decimal("99.50"),
        operator_id=5,
    )
    assert captured["event_type"] == "FINISHED_GOODS_RECEIPT_TO_INVENTORY"
    assert captured["amount"] == Decimal("99.50")


# ---------------------------------------------------------------------------
# T3: 成品/半成品入库会计事件接线
# ---------------------------------------------------------------------------


def test_finished_goods_receipt_event_alias_and_template():
    """FINISHED_GOODS_RECEIPT_TO_INVENTORY 须映射到借贷平衡的生产入库模板。"""
    from apps.kuaicaiwu.services.voucher_template_service import VoucherTemplateService

    key = VoucherTemplateService.EVENT_ALIASES.get("FINISHED_GOODS_RECEIPT_TO_INVENTORY")
    assert key, "缺少生产入库事件别名"
    lines = VoucherTemplateService.DEFAULT_TEMPLATES[key]
    sides = {line["side"] for line in lines}
    assert sides == {"debit", "credit"}
    codes = {line["account_code"] for line in lines}
    # 借库存商品 1405、贷生产成本 5001
    assert "1405" in codes
    assert "5001" in codes


def test_finished_and_semi_finished_receipt_emit_event_in_source():
    """成品/半成品确认路径源码内必须实际调用该事件（同事务）。"""
    wh = (SRC_ROOT / "apps/kuaizhizao/services/warehouse_service.py").read_text(encoding="utf-8")
    sfg = (
        SRC_ROOT / "apps/kuaizhizao/services/semi_finished_goods_receipt_service.py"
    ).read_text(encoding="utf-8")
    for name, text in (("warehouse_service", wh), ("semi_finished", sfg)):
        assert 'event_type="FINISHED_GOODS_RECEIPT_TO_INVENTORY"' in text, name


# ---------------------------------------------------------------------------
# T4: 预估工资基数缺配置 → None + 「未配置」，禁止回退 30
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_wage_rate_returns_none_when_unconfigured(monkeypatch):
    from apps.kuaizhizao.services.reporting_service import ReportingService
    from infra.services.business_config_service import BusinessConfigService

    async def _cfg(self, tenant_id):
        return {}

    monkeypatch.setattr(BusinessConfigService, "get_business_config", _cfg)
    rate = await ReportingService()._get_reporting_estimated_wage_rate(1)
    assert rate is None


@pytest.mark.asyncio
async def test_api_wage_rate_returns_none_when_unconfigured(monkeypatch):
    from apps.kuaizhizao.api.productions import reporting as reporting_api
    from infra.services.business_config_service import BusinessConfigService

    async def _cfg(self, tenant_id):
        return {"parameters": {"reporting": {}}}

    monkeypatch.setattr(BusinessConfigService, "get_business_config", _cfg)
    rate = await reporting_api._get_reporting_estimated_wage_rate(1)
    assert rate is None


@pytest.mark.asyncio
async def test_wage_rate_configured_still_works(monkeypatch):
    from apps.kuaizhizao.services.reporting_service import ReportingService
    from infra.services.business_config_service import BusinessConfigService

    async def _cfg(self, tenant_id):
        return {"parameters": {"reporting": {"estimated_wage_rate": "25.5"}}}

    monkeypatch.setattr(BusinessConfigService, "get_business_config", _cfg)
    assert await ReportingService()._get_reporting_estimated_wage_rate(1) == Decimal("25.5")


def test_no_decimal_30_wage_fallback_left():
    """源码中不得残留 Decimal(\"30\") 工资回退。"""
    for rel in (
        "apps/kuaizhizao/services/reporting_service.py",
        "apps/kuaizhizao/api/productions/reporting.py",
    ):
        text = (SRC_ROOT / rel).read_text(encoding="utf-8")
        assert 'Decimal("30")' not in text, rel
        # estimated_wages 缺配置须为 null 并带「未配置」标记
        assert "estimated_wages_note" in text, rel
        assert "未配置" in text, rel


def test_reporting_schemas_allow_null_estimated_wages():
    from apps.kuaizhizao.schemas.reporting_record import (
        ReportingDetailedStatisticsResponse,
        ReportingOverviewStatisticsResponse,
    )

    overview = ReportingOverviewStatisticsResponse.model_validate(
        {
            "cumulative_hours": 1.5,
            "estimated_wages": None,
            "estimated_wages_note": "未配置",
            "downtime_records": 0,
            "exception_reports": 0,
            "efficiency": 0.0,
            "trends": {"hours": [0], "wages": [None], "efficiency": [0.0]},
        }
    )
    assert overview.estimated_wages is None
    assert overview.estimated_wages_note == "未配置"

    detailed = ReportingDetailedStatisticsResponse.model_validate(
        {
            "cumulative_hours": 2.0,
            "estimated_wages": None,
            "estimated_wages_note": "未配置",
            "qualification_rate": 0.0,
            "trends": {"hours": [], "wages": [], "efficiency": []},
        }
    )
    assert detailed.estimated_wages is None


# ---------------------------------------------------------------------------
# T5: 金蝶/外推失败 → SyncRunLog 携带 source_type/source_id，可查未推送态
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_run_log_records_source_dimensions(monkeypatch):
    from core.models.sync_run_log import SyncRunLog
    from core.services.integration.document_push_pipeline import DocumentPushPipeline
    from core.utils.timezone_utils import resolve_business_datetime

    captured: dict = {}

    async def _create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(SyncRunLog, "create", _create)

    pipeline = DocumentPushPipeline()
    await pipeline._record_push_run_log(
        tenant_id=1,
        source_type="work_order",
        source_id=42,
        target_profile="kingdee_erp",
        connector_type="kingdee",
        started_at=resolve_business_datetime(),
        success=False,
        error="K3 API 500",
    )
    assert captured["status"] == "failed"
    assert captured["source_type"] == "work_order"
    assert captured["source_id"] == 42
    assert captured["entity_type"] == "document_push"


def test_push_status_query_endpoint_exists():
    text = (SRC_ROOT / "apps/kuaizhizao/api/document_push/document_push.py").read_text(encoding="utf-8")
    assert '"/status"' in text
    assert "source_type" in text and "source_id" in text
    # 失败行须透出 pushed=False / status=failed；顶层须给出汇总布尔
    assert '"pushed"' in text
    assert '"ever_pushed"' in text


def test_sync_run_log_model_has_source_columns():
    from core.models.sync_run_log import SyncRunLog

    assert "source_type" in SyncRunLog._meta.fields_map
    assert "source_id" in SyncRunLog._meta.fields_map


def test_sync_run_log_source_migration_exists():
    mig_dir = Path(__file__).resolve().parents[4] / "migrations" / "models"
    hits = [
        p for p in mig_dir.glob("*.py")
        if "core_sync_run_logs" in p.read_text(encoding="utf-8")
        and "source_type" in p.read_text(encoding="utf-8")
        and "source_id" in p.read_text(encoding="utf-8")
    ]
    assert hits, "缺少 core_sync_run_logs source_type/source_id 迁移"
    # aerich 排序键 = 文件名首段；按仓库约定须为 14 位时间戳且大于既有最大时间戳
    for p in hits:
        stem = p.name.split("_", 1)[0]
        assert len(stem) == 14 and stem.isdigit(), p.name


# ---------------------------------------------------------------------------
# T6: 既有会计护栏不回归
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# T7: 行为级失败传播——成本/预付款/折旧路径任一步失败必须上抛（同事务回滚由
# in_transaction 保证；mock 层验证异常不被吞、冒泡到调用方）
# ---------------------------------------------------------------------------


class _PassthroughTx:
    """in_transaction 的 mock 替身：不连库，只验证内部异常会冒泡出 with 块。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_cost_hook_propagates_per_line_failure(monkeypatch):
    """行级移动平均成本更新失败必须抛出，不得 warning 后继续（RA-H2 回归）。"""
    from apps.kuaicaiwu.services.inventory_cost_service import InventoryCostService
    from apps.kuaizhizao.models.sales_return_item import SalesReturnItem

    item = SimpleNamespace(material_id=5, return_quantity=Decimal("2"), unit_price=Decimal("10"))

    class _QS:
        async def all(self):
            return [item]

    monkeypatch.setattr(SalesReturnItem, "filter", lambda *a, **k: _QS())
    svc = InventoryCostService()

    async def _boom(self, **kwargs):
        raise RuntimeError("cost write conflict")

    monkeypatch.setattr(InventoryCostService, "update_moving_average_cost", _boom)

    with pytest.raises(RuntimeError, match="cost write conflict"):
        await svc.on_sales_return_confirmed(tenant_id=1, return_id=9)


@pytest.mark.asyncio
async def test_prepayment_payment_propagates_relation_failure(monkeypatch):
    """付款单已建但关联失败 → 整体抛错（事务内回滚），不得产出孤立付款单。"""
    from apps.kuaicaiwu.services import finance_integration_hooks as hooks
    from infra.exceptions.exceptions import BusinessLogicError

    async def _no_relation(*a, **k):
        return False

    async def _user(self, uid):
        return {"name": "op"}

    async def _bank(tenant_id, bank_id):
        return (None, None, "cash")

    async def _code(tenant_id):
        return "FK-1"

    async def _payment_create(**kwargs):
        return SimpleNamespace(id=77, payment_code="FK-1")

    async def _boom(**kwargs):
        raise RuntimeError("relation insert failed")

    monkeypatch.setattr(hooks, "_existing_order_prepayment_relation", _no_relation)
    monkeypatch.setattr(
        "apps.common.base_service.AppBaseService.get_user_info", _user
    )
    monkeypatch.setattr(hooks, "_resolve_bank_account_for_voucher", _bank)
    monkeypatch.setattr(
        "apps.kuaicaiwu.services.finance_voucher_codes.allocate_payment_code", _code
    )
    monkeypatch.setattr("apps.kuaicaiwu.models.payment.Payment.create", _payment_create)
    monkeypatch.setattr(hooks, "link_finance_document_relation", _boom)
    monkeypatch.setattr(
        "tortoise.transactions.in_transaction", lambda *a, **k: _PassthroughTx()
    )

    with pytest.raises(BusinessLogicError, match="预付付款单失败"):
        await hooks.ensure_prepayment_payment_for_purchase_order(
            tenant_id=1,
            order_id=3,
            order_code="PO-3",
            supplier_id=2,
            supplier_name="供应商",
            prepayment_amount=Decimal("100"),
            prepayment_bank_account_id=None,
            operator_id=1,
        )


@pytest.mark.asyncio
async def test_fa_depreciation_confirm_run_propagates_event_failure(monkeypatch):
    """折旧确认：事件记录失败必须抛出（同事务回滚，重试不重复累计折旧）。"""
    from apps.kuaicaiwu.services import fa_depreciation_service as fa_dep

    run = SimpleNamespace(
        id=1, status="draft", run_code="ZJ-1", period_year=2026, period_month=9
    )
    line = SimpleNamespace(id=8, asset_id=4, final_amount=Decimal("100"))
    asset = SimpleNamespace(
        id=4,
        asset_code="FA-4",
        asset_name="设备",
        accumulated_depreciation=Decimal("0"),
        depreciated_periods=0,
        expense_account_code="6602",
        accumulated_depreciation_account_code="1602",
        asset_account_code="1601",
        department_id=None,
        department_name=None,
        save=lambda: _awaitable(None),
    )

    async def _boom(**kwargs):
        raise RuntimeError("event store down")

    class _RunQS:
        async def all(self):
            return [line]

    monkeypatch.setattr(
        fa_dep.FaDepreciationRun, "get_or_none",
        lambda **k: _awaitable(run),
    )
    monkeypatch.setattr(
        fa_dep.FaDepreciationRunLine, "filter", lambda *a, **k: _RunQS()
    )
    monkeypatch.setattr(
        fa_dep.FaAsset, "get_or_none", lambda **k: _awaitable(asset)
    )
    monkeypatch.setattr(
        fa_dep.AccountingEventService, "record_event", _boom
    )
    monkeypatch.setattr(
        fa_dep.FaDepreciationService, "_ensure_period_open",
        lambda self, *a: _awaitable(None),
    )
    monkeypatch.setattr(
        "tortoise.transactions.in_transaction", lambda *a, **k: _PassthroughTx()
    )

    with pytest.raises(RuntimeError, match="event store down"):
        await fa_dep.FaDepreciationService().confirm_run(
            1, 1, SimpleNamespace(id=1, name="op")
        )


async def _awaitable(value):
    return value


def test_posting_rejects_unbalanced_voucher():
    text = (SRC_ROOT / "apps/kuaicaiwu/services/posting_service.py").read_text(encoding="utf-8")
    assert "total_debit != total_credit" in text
    assert "凭证借贷不平衡" in text


def test_close_period_prechecks_default_on():
    text = (SRC_ROOT / "apps/kuaicaiwu/services/gl/period_service.py").read_text(encoding="utf-8")
    assert "skip_checks: bool = False" in text
    assert "if not skip_checks:" in text
    assert "pre_close_checks" in text


def test_no_skip_checks_true_callers():
    offenders = []
    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"skip_checks\s*=\s*True", text):
            offenders.append(str(path.relative_to(SRC_ROOT)))
    assert offenders == [], f"出现 skip_checks=True 调用: {offenders}"
