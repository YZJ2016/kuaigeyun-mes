"""其他费用收入服务"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from apps.common.base_service import AppBaseService
from apps.kuaicaiwu.models.other_voucher import OtherIncome, OtherIncomeLine
from apps.kuaicaiwu.schemas.other_voucher import (
    OtherIncomeCreate,
    OtherIncomeResponse,
    OtherIncomeUpdate,
    OtherVoucherLineInput,
    OtherVoucherLineResponse,
)
from apps.kuaicaiwu.services.document_action_policy.other_income import (
    assert_other_income_capability,
    derive_other_income_capabilities,
    is_other_income_confirmed_status,
)
from apps.kuaicaiwu.services.other_income_audit_service import (
    OtherIncomeAuditService,
    assert_other_income_review_editable,
)
from apps.kuaicaiwu.services.finance_misc_category_service import FinanceMiscCategoryService
from apps.kuaicaiwu.services.finance_voucher_codes import allocate_other_income_code
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import NotFoundError, ValidationError, BusinessLogicError
from infra.services.business_config_service import BusinessConfigService


class OtherIncomeService(AppBaseService[OtherIncome]):
    def __init__(self) -> None:
        super().__init__(OtherIncome)
        self._categories = FinanceMiscCategoryService()
        self._config = BusinessConfigService()

    async def _sum_and_validate_lines(
        self, tenant_id: int, lines: List[OtherVoucherLineInput]
    ) -> tuple[Decimal, List[dict]]:
        total = Decimal("0")
        normalized: List[dict] = []
        for idx, item in enumerate(lines, start=1):
            amt = Decimal(str(item.amount))
            if amt <= 0:
                raise ValidationError(f"第 {idx} 行金额须大于 0")
            code = str(item.category_code).strip()
            cat = await self._categories.get_active_by_code(tenant_id, "income", code)
            gl = item.gl_account_code
            if not gl and cat.default_gl_account_code:
                gl = cat.default_gl_account_code
            normalized.append(
                {
                    "line_no": idx,
                    "category_code": cat.code,
                    "category_name": cat.name,
                    "amount": amt,
                    "description": item.description,
                    "gl_account_code": gl,
                }
            )
            total += amt
        return total, normalized

    async def _to_response(self, head: OtherIncome) -> OtherIncomeResponse:
        lines = await OtherIncomeLine.filter(
            tenant_id=head.tenant_id, other_income_id=head.id
        ).order_by("line_no")
        from apps.kuaicaiwu.services.misc_voucher_finance_bridge import MiscVoucherFinanceBridge

        finance_links = await MiscVoucherFinanceBridge().finance_links_for_income(
            head.tenant_id, int(head.id)
        )
        caps = derive_other_income_capabilities(
            head,
            has_receivable=bool(finance_links.get("receivable_id")),
            has_receipt=bool(finance_links.get("receipt_id")),
        )
        base = OtherIncomeResponse.model_validate(head, from_attributes=True)
        return base.model_copy(
            update={
                "lines": [OtherVoucherLineResponse.model_validate(r) for r in lines],
                "capabilities": {k: v.model_dump() for k, v in caps.items()},
                **finance_links,
            }
        )

    async def create_income(
        self, tenant_id: int, data: OtherIncomeCreate, created_by: int
    ) -> OtherIncomeResponse:
        total, line_rows = await self._sum_and_validate_lines(tenant_id, data.lines)
        user = await self.get_user_info(created_by)
        code = (data.income_code or await allocate_other_income_code(tenant_id)).strip().upper()
        from apps.kuaizhizao.services.document_recognition import ensure_revenue_recognition_on_create

        customer_id = (
            int(data.counterparty_id)
            if (data.counterparty_kind or "").lower() == "customer" and data.counterparty_id
            else None
        )
        revenue_recognition = await ensure_revenue_recognition_on_create(
            tenant_id,
            customer_id,
            getattr(data, "revenue_recognition", None),
        )
        async with in_transaction():
            head = await OtherIncome.create(
                tenant_id=tenant_id,
                income_code=code,
                business_date=data.business_date,
                counterparty_kind=data.counterparty_kind or "none",
                counterparty_id=data.counterparty_id,
                counterparty_name=data.counterparty_name,
                total_amount=total,
                payment_method=data.payment_method,
                bank_account_id=data.bank_account_id,
                bank_account=data.bank_account,
                status="Draft",
                review_status="草稿",
                department_id=data.department_id,
                department_name=data.department_name,
                project_id=data.project_id,
                project_name=data.project_name,
                notes=data.notes,
                attachments=data.attachments,
                revenue_recognition=revenue_recognition,
                created_by=created_by,
                created_by_name=user["name"],
                updated_by=created_by,
                updated_by_name=user["name"],
            )
            for row in line_rows:
                await OtherIncomeLine.create(
                    tenant_id=tenant_id, other_income_id=head.id, **row
                )
            head_id = head.id
        from apps.kuaizhizao.services.manual_create_auto_lifecycle import (
            apply_manual_create_auto_submit,
        )

        await apply_manual_create_auto_submit(
            tenant_id=tenant_id,
            node_key="other_income",
            entity_id=head_id,
            operator_id=created_by,
        )
        return await self.get_by_id(tenant_id, head_id)

    async def get_by_id(
        self,
        tenant_id: int,
        income_id: int,
        *,
        viewer_id: Optional[int] = None,
    ) -> OtherIncomeResponse:
        head = await OtherIncome.get_or_none(
            tenant_id=tenant_id, id=income_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用收入单不存在: {income_id}")
        item = await self._to_response(head)
        from core.services.approval.audit_record_enricher import enrich_items

        enriched = await enrich_items(
            tenant_id, "other_income", [item], viewer_id=viewer_id
        )
        return enriched[0]

    async def list_incomes(
        self,
        tenant_id: int,
        *,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        review_status: Optional[str] = None,
        keyword: Optional[str] = None,
        viewer_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        q = OtherIncome.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if status:
            q = q.filter(status=status)
        if review_status:
            q = q.filter(review_status=review_status)
        kw = (keyword or "").strip()
        if kw:
            q = q.filter(
                Q(income_code__icontains=kw)
                | Q(counterparty_name__icontains=kw)
                | Q(notes__icontains=kw)
            )
        total = await q.count()
        rows = await q.offset(skip).limit(limit).order_by("-created_at")
        items = [await self._to_response(r) for r in rows]
        from core.services.approval.audit_record_enricher import enrich_items

        items = await enrich_items(
            tenant_id, "other_income", items, viewer_id=viewer_id
        )
        return {"items": items, "total": total}

    async def update_income(
        self,
        tenant_id: int,
        income_id: int,
        data: OtherIncomeUpdate,
        updated_by: int,
    ) -> OtherIncomeResponse:
        head = await OtherIncome.get_or_none(
            tenant_id=tenant_id, id=income_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用收入单不存在: {income_id}")
        assert_other_income_capability(head, "update")
        assert_other_income_review_editable(head)
        dump = data.model_dump(exclude_unset=True)
        # 明细须用 schema 实例校验；model_dump 后的 dict 无 .amount
        lines_provided = "lines" in dump
        dump.pop("lines", None)
        user = await self.get_user_info(updated_by)
        async with in_transaction():
            if lines_provided:
                if not data.lines:
                    raise ValidationError("至少一行明细")
                total, line_rows = await self._sum_and_validate_lines(tenant_id, data.lines)
                await OtherIncomeLine.filter(
                    tenant_id=tenant_id, other_income_id=income_id
                ).delete()
                for row in line_rows:
                    await OtherIncomeLine.create(
                        tenant_id=tenant_id, other_income_id=income_id, **row
                    )
                dump["total_amount"] = total
            dump["updated_by"] = updated_by
            dump["updated_by_name"] = user["name"]
            await head.update_from_dict(dump).save()
        return await self.get_by_id(tenant_id, income_id)

    async def delete_income(self, tenant_id: int, income_id: int) -> None:
        head = await OtherIncome.get_or_none(
            tenant_id=tenant_id, id=income_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用收入单不存在: {income_id}")
        assert_other_income_capability(head, "delete")
        assert_other_income_review_editable(head)
        head.deleted_at = resolve_business_datetime()
        await head.save()

    async def submit_income(
        self,
        tenant_id: int,
        income_id: int,
        user_id: int,
        *,
        selected_approver_user_ids: Optional[List[int]] = None,
        selected_approver_by_node: Optional[Dict[str, List[int]]] = None,
    ) -> OtherIncomeResponse:
        """内部一次性送审。页面提交请走 uni-audit commit。"""
        await OtherIncomeAuditService().submit_income(
            tenant_id,
            income_id,
            user_id,
            selected_approver_user_ids=selected_approver_user_ids,
            selected_approver_by_node=selected_approver_by_node,
        )
        return await self.get_by_id(tenant_id, income_id)

    async def _on_income_approved(
        self, tenant_id: int, head: OtherIncome, operator_id: int
    ) -> None:
        from apps.kuaicaiwu.services.misc_voucher_finance_bridge import MiscVoucherFinanceBridge

        await MiscVoucherFinanceBridge().ensure_receivable_on_income_approved(
            tenant_id, head, operator_id
        )

    async def approve_income(
        self,
        tenant_id: int,
        income_id: int,
        *,
        approved: bool,
        operator_id: int,
        review_remarks: Optional[str] = None,
    ) -> OtherIncomeResponse:
        await OtherIncomeAuditService().approve_income(
            tenant_id,
            income_id,
            operator_id,
            approved=approved,
            review_remarks=review_remarks,
        )
        return await self.get_by_id(tenant_id, income_id)

    async def withdraw_income_submit(
        self, tenant_id: int, income_id: int, user_id: int
    ) -> OtherIncomeResponse:
        await OtherIncomeAuditService().withdraw_income(tenant_id, income_id, user_id)
        return await self.get_by_id(tenant_id, income_id)

    async def revoke_income_approval(
        self, tenant_id: int, income_id: int, user_id: int
    ) -> OtherIncomeResponse:
        await OtherIncomeAuditService().revoke_income(tenant_id, income_id, user_id)
        return await self.get_by_id(tenant_id, income_id)

    async def cancel_income(
        self, tenant_id: int, income_id: int, operator_id: int
    ) -> OtherIncomeResponse:
        head = await OtherIncome.get_or_none(
            tenant_id=tenant_id, id=income_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用收入单不存在: {income_id}")
        assert_other_income_capability(head, "cancel")
        if is_other_income_confirmed_status(str(head.status or "")):
            from apps.kuaicaiwu.services.misc_voucher_posting_service import (
                MiscVoucherPostingService,
            )

            await MiscVoucherPostingService().unpost_other_income(
                tenant_id, income_id, operator_id=operator_id
            )
        user = await self.get_user_info(operator_id)
        head.status = "Cancelled"
        head.updated_by = operator_id
        head.updated_by_name = user["name"]
        await head.save()
        return await self.get_by_id(tenant_id, income_id)
