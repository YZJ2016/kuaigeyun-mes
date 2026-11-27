"""其他费用支出申请下推支出单"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from apps.kuaicaiwu.models.other_expense_application import (
    OtherExpenseApplication,
    OtherExpenseApplicationLine,
)
from apps.kuaicaiwu.schemas.other_expense_application import PushOtherExpenseApplicationRequest
from apps.kuaicaiwu.schemas.other_voucher import OtherExpenseCreate, OtherVoucherLineInput
from apps.kuaicaiwu.services.document_action_policy.other_expense_application import (
    assert_other_expense_application_capability,
)
from apps.kuaicaiwu.services.other_expense_application_service import OtherExpenseApplicationService
from apps.kuaicaiwu.services.other_expense_service import OtherExpenseService
from core.utils.timezone_utils import resolve_business_datetime, to_site_date
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.user import User


class OtherExpenseApplicationPushService:
    def __init__(self) -> None:
        self._app_svc = OtherExpenseApplicationService()
        self._expense_svc = OtherExpenseService()

    async def push_to_other_expense(
        self,
        tenant_id: int,
        application_id: int,
        data: PushOtherExpenseApplicationRequest,
        current_user: User,
    ) -> dict:
        app = await OtherExpenseApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not app:
            raise NotFoundError(f"其他费用支出申请不存在: {application_id}")
        assert_other_expense_application_capability(app, "push_other_expense")

        line_query = OtherExpenseApplicationLine.filter(
            tenant_id=tenant_id, application_id=application_id
        ).order_by("line_no")
        lines = await line_query.all()
        if not lines:
            raise ValidationError("无可用申请行")

        remaining_head = Decimal(str(app.remaining_amount or 0))
        if remaining_head <= 0:
            raise BusinessLogicError("申请单已无待下推金额")

        if data.total_amount is not None:
            push_total = Decimal(str(data.total_amount))
        else:
            push_total = remaining_head

        if push_total <= 0:
            raise ValidationError("下推金额须大于 0")
        if push_total > remaining_head:
            raise BusinessLogicError(
                f"下推金额 {push_total} 超过待下推余额 {remaining_head}"
            )

        allocations = await self._app_svc.allocate_push_amount_to_lines(
            list(lines), push_total, line_ids=data.line_ids
        )
        if not allocations:
            raise BusinessLogicError("所选行已无待下推金额")

        expense_lines: List[OtherVoucherLineInput] = []
        line_pushes: List[tuple[int, Decimal]] = []
        for line, amt in allocations:
            expense_lines.append(
                OtherVoucherLineInput(
                    category_code=str(line.category_code),
                    amount=amt,
                    description=line.description,
                    gl_account_code=line.gl_account_code,
                    payee_id=line.payee_id,
                    payee_name=line.payee_name,
                )
            )
            line_pushes.append((int(line.id), amt))

        biz_date = data.business_date or to_site_date(resolve_business_datetime())
        notes = (data.notes or "").strip() or f"由申请 {app.application_code} 下推"

        create_payload = OtherExpenseCreate(
            business_date=biz_date,
            counterparty_kind=str(app.counterparty_kind or "none"),
            counterparty_id=app.counterparty_id,
            counterparty_name=app.counterparty_name,
            counterparty_account_name=getattr(app, "counterparty_account_name", None),
            counterparty_bank_name=getattr(app, "counterparty_bank_name", None),
            counterparty_bank_account=getattr(app, "counterparty_bank_account", None),
            payment_method=str(app.payment_method or ""),
            bank_account_id=app.bank_account_id,
            bank_account=app.bank_account,
            department_id=app.department_id,
            department_name=app.department_name,
            project_id=app.project_id,
            project_name=app.project_name,
            notes=notes,
            attachments=app.attachments,
            payable_recognition=app.payable_recognition,
            related_purchase_receipts=app.related_purchase_receipts,
            lines=expense_lines,
            source_type="other_expense_application",
            source_id=int(app.id),
            source_code=str(app.application_code),
        )

        expense = await self._expense_svc.create_expense_from_application(
            tenant_id, create_payload, current_user.id, line_pushes=line_pushes
        )

        return {
            "application_id": application_id,
            "application_code": app.application_code,
            "expense_id": expense.id,
            "expense_code": expense.expense_code,
            "total_amount": float(push_total),
        }
