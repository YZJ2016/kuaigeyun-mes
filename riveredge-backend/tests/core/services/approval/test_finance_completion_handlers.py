"""应收应付审批完成回调须调用正确 Service，禁止虚构 FinanceService。"""

from pathlib import Path


def test_finance_completion_handlers_use_real_service_classes():
    src = Path(__file__).resolve().parents[4] / (
        "src/core/services/approval/approval_instance_service.py"
    )
    text = src.read_text(encoding="utf-8")
    assert "from apps.kuaicaiwu.services.finance_service import FinanceService" not in text
    assert "from apps.kuaicaiwu.services.finance_service import PayableService" in text
    assert "from apps.kuaicaiwu.services.finance_service import ReceivableService" in text
    assert "from apps.kuaicaiwu.services.finance_service import PurchaseInvoiceService" in text
    assert "is_auto_approve=True" in text


def test_completion_handlers_cover_writeback_dependent_entities():
    """依赖完成回调写回单据的实体必须在 completion_handlers 注册，
    否则审批中心/单据页审完流程后单据滞留「待审核」。"""
    src = Path(__file__).resolve().parents[4] / (
        "src/core/services/approval/approval_instance_service.py"
    )
    text = src.read_text(encoding="utf-8")
    assert '"payment_application": _handle_payment_application' in text
    assert '"other_income": _handle_other_income' in text
    assert '"other_expense": _handle_other_expense' in text
    assert "PaymentApplicationService" in text
    assert "OtherIncomeService" in text
    assert "OtherExpenseService" in text
