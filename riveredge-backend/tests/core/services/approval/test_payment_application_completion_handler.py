"""付款申请须注册审批完成写回，否则流程结束单据仍停在待审核。"""

from pathlib import Path


def test_payment_application_registered_in_completion_handlers():
    src = Path(__file__).resolve().parents[4] / (
        "src/core/services/approval/approval_instance_service.py"
    )
    text = src.read_text(encoding="utf-8")
    assert "async def _handle_payment_application()" in text
    assert '"payment_application": _handle_payment_application' in text
    assert "approve_application(" in text
    assert "is_auto_approve=True" in text
