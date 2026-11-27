"""从其他费用支出申请取单创建支出"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from apps.kuaicaiwu.models.other_expense_application import (
    OtherExpenseApplication,
    OtherExpenseApplicationLine,
)
from apps.kuaicaiwu.services.document_action_policy.other_expense import (
    is_other_expense_approved_status,
)
from apps.kuaicaiwu.services.document_action_policy.other_expense_application import (
    derive_other_expense_application_capabilities,
)
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError


class OtherExpenseApplicationPullService:
    async def list_for_expense_pull(
        self,
        tenant_id: int,
        *,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        q = OtherExpenseApplication.filter(
            tenant_id=tenant_id, deleted_at__isnull=True, status="Approved", remaining_amount__gt=0
        )
        kw = (keyword or "").strip()
        if kw:
            from tortoise.expressions import Q

            q = q.filter(
                Q(application_code__icontains=kw) | Q(counterparty_name__icontains=kw)
            )
        total = await q.count()
        apps = await q.offset(skip).limit(limit).order_by("-business_date", "-id")
        rows: List[Dict[str, Any]] = []
        for app in apps:
            remaining = Decimal(str(app.remaining_amount or 0))
            caps = derive_other_expense_application_capabilities(app)
            pull_cap = caps.get("push_other_expense")
            allowed = bool(pull_cap and pull_cap.allowed) and remaining > 0
            rows.append(
                {
                    "id": int(app.id),
                    "application_code": app.application_code,
                    "business_date": app.business_date,
                    "counterparty_name": app.counterparty_name,
                    "total_amount": float(app.total_amount or 0),
                    "remaining_amount": float(remaining),
                    "payment_method": app.payment_method,
                    "capabilities": {
                        "pull_other_expense": {
                            "allowed": allowed,
                            "reason": pull_cap.reason if pull_cap and not allowed else None,
                        }
                    },
                }
            )
        return {"data": rows, "total": total, "success": True}

    async def preview_pull_for_expense(
        self, tenant_id: int, application_id: int
    ) -> Dict[str, Any]:
        app = await OtherExpenseApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not app:
            raise NotFoundError(f"其他费用支出申请不存在: {application_id}")
        if not is_other_expense_approved_status(str(app.status or "")):
            return {
                "has_blocking_issues": True,
                "blocking_reason": "申请单未审核通过",
                "source_type": "other_expense_application",
                "source_id": application_id,
                "source_code": app.application_code,
            }
        remaining = Decimal(str(app.remaining_amount or 0))
        if remaining <= 0:
            return {
                "has_blocking_issues": True,
                "blocking_reason": "申请单已无待下推金额",
                "source_type": "other_expense_application",
                "source_id": application_id,
                "source_code": app.application_code,
            }
        lines = await OtherExpenseApplicationLine.filter(
            tenant_id=tenant_id, application_id=application_id
        ).order_by("line_no")
        items = []
        for line in lines:
            open_amt = Decimal(str(line.amount or 0)) - Decimal(str(line.pushed_amount or 0))
            if open_amt <= 0:
                continue
            items.append(
                {
                    "line_id": int(line.id),
                    "line_no": int(line.line_no or 0),
                    "category_code": line.category_code,
                    "category_name": line.category_name,
                    "max_push_quantity": float(open_amt),
                    "description": line.description,
                    "payee_id": line.payee_id,
                    "payee_name": line.payee_name,
                    "gl_account_code": line.gl_account_code,
                }
            )
        return {
            "has_blocking_issues": False,
            "source_type": "other_expense_application",
            "source_id": application_id,
            "source_code": app.application_code,
            "max_push_total": float(remaining),
            "header": {
                "business_date": app.business_date,
                "counterparty_kind": app.counterparty_kind,
                "counterparty_id": app.counterparty_id,
                "counterparty_name": app.counterparty_name,
                "payment_method": app.payment_method,
                "bank_account_id": app.bank_account_id,
                "bank_account": app.bank_account,
                "department_id": app.department_id,
                "department_name": app.department_name,
                "project_id": app.project_id,
                "project_name": app.project_name,
                "payable_recognition": app.payable_recognition,
                "notes": app.notes,
            },
            "items": items,
        }

    async def assert_pull_create_allowed(
        self,
        tenant_id: int,
        *,
        application_id: int,
        total_amount: Decimal,
    ) -> Dict[str, Any]:
        preview = await self.preview_pull_for_expense(tenant_id, application_id)
        if preview.get("has_blocking_issues"):
            reason = preview.get("blocking_reason") or "当前不可加载支出单"
            raise BusinessLogicError(reason)
        max_push = Decimal(str(preview.get("max_push_total") or 0))
        if max_push <= 0:
            raise BusinessLogicError("无可下推金额")
        if total_amount > max_push:
            raise BusinessLogicError(f"支出金额 {total_amount} 超过可下推金额 {max_push}")
        return preview
