"""其他费用支出申请服务"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from apps.common.base_service import AppBaseService
from apps.kuaicaiwu.models.other_expense_application import (
    OtherExpenseApplication,
    OtherExpenseApplicationLine,
)
from apps.kuaicaiwu.models.other_voucher import OtherExpense
from apps.kuaicaiwu.schemas.other_expense_application import (
    OtherExpenseApplicationCreate,
    OtherExpenseApplicationResponse,
    OtherExpenseApplicationUpdate,
)
from apps.kuaicaiwu.schemas.other_voucher import OtherVoucherLineInput, OtherVoucherLineResponse
from apps.kuaicaiwu.services.document_action_policy.other_expense_application import (
    assert_other_expense_application_capability,
    derive_other_expense_application_capabilities,
)
from apps.kuaicaiwu.services.finance_misc_category_service import FinanceMiscCategoryService
from apps.kuaicaiwu.services.other_expense_service import OtherExpenseService
from apps.kuaicaiwu.services.finance_voucher_codes import allocate_other_expense_application_code
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.services.business_config_service import BusinessConfigService


async def resolve_application_linked_expenses(
    tenant_id: int,
    expense_rels: List[Any],
) -> List[Dict[str, Any]]:
    from apps.kuaizhizao.models.document_relation import DocumentRelation

    ids = [int(r.target_id) for r in expense_rels if getattr(r, "target_id", None)]
    if not ids:
        return []
    rows = await OtherExpense.filter(
        tenant_id=tenant_id, id__in=ids, deleted_at__isnull=True
    ).all()
    by_id = {int(r.id): r for r in rows}
    linked: List[Dict[str, Any]] = []
    for rel in expense_rels:
        eid = int(rel.target_id) if rel.target_id else 0
        exp = by_id.get(eid)
        if not exp:
            continue
        linked.append(
            {
                "id": eid,
                "code": str(exp.expense_code or getattr(rel, "target_code", None) or ""),
            }
        )
    return linked


class OtherExpenseApplicationService(AppBaseService[OtherExpenseApplication]):
    def __init__(self) -> None:
        super().__init__(OtherExpenseApplication)
        self._categories = FinanceMiscCategoryService()
        self._config = BusinessConfigService()

    async def _sum_and_validate_lines(
        self,
        tenant_id: int,
        lines: List[OtherVoucherLineInput],
        *,
        payment_method: str,
    ) -> tuple[Decimal, List[dict]]:
        total = Decimal("0")
        normalized: List[dict] = []
        require_payee = str(payment_method or "").strip() == "员工垫付"
        for idx, item in enumerate(lines, start=1):
            amt = Decimal(str(item.amount))
            if amt <= 0:
                raise ValidationError(f"第 {idx} 行金额须大于 0")
            code = str(item.category_code).strip()
            cat = await self._categories.get_active_by_code(tenant_id, "expense", code)
            gl = item.gl_account_code
            if not gl and cat.default_gl_account_code:
                gl = cat.default_gl_account_code
            payee_id = int(item.payee_id) if item.payee_id else None
            payee_name = (str(item.payee_name).strip() if item.payee_name else "") or None
            if require_payee:
                if not payee_id or not payee_name:
                    raise ValidationError(f"第 {idx} 行须选择领款人（员工垫付）")
            else:
                payee_id = None
                payee_name = None
            normalized.append(
                {
                    "line_no": idx,
                    "category_code": cat.code,
                    "category_name": cat.name,
                    "amount": amt,
                    "pushed_amount": Decimal("0"),
                    "description": item.description,
                    "gl_account_code": gl,
                    "payee_id": payee_id,
                    "payee_name": payee_name,
                }
            )
            total += amt
        return total, normalized

    @staticmethod
    def _sync_head_totals(app: OtherExpenseApplication) -> None:
        total = Decimal(str(app.total_amount or 0))
        pushed = Decimal(str(app.pushed_amount or 0))
        app.remaining_amount = max(Decimal("0"), total - pushed)

    async def _to_response(
        self,
        app: OtherExpenseApplication,
        *,
        viewer_id: Optional[int] = None,
    ) -> OtherExpenseApplicationResponse:
        lines = await OtherExpenseApplicationLine.filter(
            tenant_id=app.tenant_id, application_id=app.id
        ).order_by("line_no")
        from apps.kuaizhizao.models.document_relation import DocumentRelation

        expense_rels = await DocumentRelation.filter(
            tenant_id=app.tenant_id,
            source_type="other_expense_application",
            source_id=int(app.id),
            target_type="other_expense",
        ).all()
        linked = await resolve_application_linked_expenses(app.tenant_id, expense_rels)
        caps = derive_other_expense_application_capabilities(
            app, has_linked_expense=bool(linked)
        )
        line_resp = []
        for row in lines:
            lr = OtherVoucherLineResponse.model_validate(row, from_attributes=True)
            line_resp.append(lr)
        resp = OtherExpenseApplicationResponse.model_validate(app, from_attributes=True)
        resp = resp.model_copy(
            update={
                "lines": line_resp,
                "capabilities": {k: v.model_dump() for k, v in caps.items()},
                "linked_expenses": linked,
            }
        )
        from core.services.approval.audit_record_enricher import enrich_record

        return await enrich_record(
            app.tenant_id,
            "other_expense_application",
            resp,
            audit_enabled=True,
            viewer_id=viewer_id,
        )

    async def _auto_submit_when_audit_disabled(
        self, tenant_id: int, application_id: int, user_id: int
    ) -> OtherExpenseApplicationResponse:
        """免审或开启「手动建单自动提交」时，保存后一次性提交（有审批流则待审）。"""
        from apps.kuaizhizao.services.manual_create_auto_lifecycle import (
            is_manual_create_auto_submit_enabled,
        )

        audit_required = await self._config.check_audit_required(
            tenant_id, "other_expense_application"
        )
        cfg_on = await is_manual_create_auto_submit_enabled(
            tenant_id, "other_expense_application"
        )
        if audit_required and not cfg_on:
            return await self.get_by_id(tenant_id, application_id)
        head = await OtherExpenseApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用支出申请不存在: {application_id}")
        review = str(head.review_status or "").strip()
        if review in {"", "草稿", "draft", "驳回", "rejected", "已驳回"}:
            return await self.submit_application(tenant_id, application_id, user_id)
        return await self.get_by_id(tenant_id, application_id)

    async def create_application(
        self, tenant_id: int, data: OtherExpenseApplicationCreate, created_by: int
    ) -> OtherExpenseApplicationResponse:
        total, line_rows = await self._sum_and_validate_lines(
            tenant_id, data.lines, payment_method=str(data.payment_method or "")
        )
        user = await self.get_user_info(created_by)
        code = (
            data.application_code or await allocate_other_expense_application_code(tenant_id)
        ).strip().upper()
        from apps.kuaizhizao.services.document_recognition import (
            ensure_payable_recognition_on_create,
            payable_recognition_for_misc_expense_counterparty,
        )

        supplier_id = (
            int(data.counterparty_id)
            if (data.counterparty_kind or "").lower() == "supplier" and data.counterparty_id
            else None
        )
        payable_resolved = await ensure_payable_recognition_on_create(
            tenant_id,
            supplier_id,
            getattr(data, "payable_recognition", None),
        )
        payable_recognition = payable_recognition_for_misc_expense_counterparty(
            str(data.counterparty_kind or "none"),
            payable_resolved,
        )
        expense_svc = OtherExpenseService()
        related_receipts = await expense_svc.normalize_related_purchase_receipts(
            tenant_id,
            counterparty_kind=data.counterparty_kind or "none",
            counterparty_id=supplier_id,
            related=data.related_purchase_receipts,
        )
        async with in_transaction():
            head = await OtherExpenseApplication.create(
                tenant_id=tenant_id,
                application_code=code,
                business_date=data.business_date,
                counterparty_kind=data.counterparty_kind or "none",
                counterparty_id=data.counterparty_id,
                counterparty_name=data.counterparty_name,
                counterparty_account_name=data.counterparty_account_name,
                counterparty_bank_name=data.counterparty_bank_name,
                counterparty_bank_account=data.counterparty_bank_account,
                total_amount=total,
                pushed_amount=Decimal("0"),
                remaining_amount=total,
                payment_method=str(data.payment_method or "银行转账"),
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
                related_purchase_receipts=related_receipts,
                payable_recognition=payable_recognition,
                created_by=created_by,
                created_by_name=user["name"],
                updated_by=created_by,
                updated_by_name=user["name"],
            )
            for row in line_rows:
                await OtherExpenseApplicationLine.create(
                    tenant_id=tenant_id, application_id=head.id, **row
                )
            head_id = head.id
        return await self._auto_submit_when_audit_disabled(tenant_id, head_id, created_by)

    async def get_by_id(
        self,
        tenant_id: int,
        application_id: int,
        *,
        viewer_id: Optional[int] = None,
    ) -> OtherExpenseApplicationResponse:
        head = await OtherExpenseApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用支出申请不存在: {application_id}")
        return await self._to_response(head, viewer_id=viewer_id)

    async def list_applications(
        self,
        tenant_id: int,
        *,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        review_status: Optional[str] = None,
        keyword: Optional[str] = None,
        approved_only: bool = False,
        with_remaining: bool = False,
        viewer_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        q = OtherExpenseApplication.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if status:
            q = q.filter(status=status)
        if review_status:
            q = q.filter(review_status=review_status)
        if approved_only:
            q = q.filter(status="Approved")
        if with_remaining:
            q = q.filter(remaining_amount__gt=0)
        kw = (keyword or "").strip()
        if kw:
            q = q.filter(
                Q(application_code__icontains=kw)
                | Q(counterparty_name__icontains=kw)
                | Q(notes__icontains=kw)
            )
        total = await q.count()
        rows = await q.offset(skip).limit(limit).order_by("-created_at")
        items = [await self._to_response(r, viewer_id=viewer_id) for r in rows]
        return {"items": items, "total": total}

    async def update_application(
        self,
        tenant_id: int,
        application_id: int,
        data: OtherExpenseApplicationUpdate,
        updated_by: int,
    ) -> OtherExpenseApplicationResponse:
        head = await OtherExpenseApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用支出申请不存在: {application_id}")
        assert_other_expense_application_capability(head, "update")
        if Decimal(str(head.pushed_amount or 0)) > 0:
            raise BusinessLogicError("已有下推占用，不可修改")
        dump = data.model_dump(exclude_unset=True)
        lines_provided = "lines" in dump
        dump.pop("lines", None)
        user = await self.get_user_info(updated_by)
        payment_method = str(dump.get("payment_method") or head.payment_method or "银行转账")
        if "related_purchase_receipts" in dump:
            cp_kind = str(
                dump.get("counterparty_kind") or head.counterparty_kind or "none"
            )
            cp_id = dump.get("counterparty_id")
            if cp_id is None:
                cp_id = head.counterparty_id
            supplier_id = (
                int(cp_id)
                if str(cp_kind).lower() == "supplier" and cp_id is not None
                else None
            )
            expense_svc = OtherExpenseService()
            dump["related_purchase_receipts"] = await expense_svc.normalize_related_purchase_receipts(
                tenant_id,
                counterparty_kind=cp_kind,
                counterparty_id=supplier_id,
                related=dump.get("related_purchase_receipts"),
            )
        cp_kind_final = str(
            dump.get("counterparty_kind") or head.counterparty_kind or "none"
        )
        if str(cp_kind_final).strip().lower() != "supplier":
            from apps.kuaizhizao.services.document_recognition import (
                payable_recognition_for_misc_expense_counterparty,
            )

            dump["payable_recognition"] = payable_recognition_for_misc_expense_counterparty(
                cp_kind_final,
                str(head.payable_recognition or "manual"),
            )
        async with in_transaction():
            if lines_provided and data.lines is not None:
                total, line_rows = await self._sum_and_validate_lines(
                    tenant_id, data.lines, payment_method=payment_method
                )
                await OtherExpenseApplicationLine.filter(
                    tenant_id=tenant_id, application_id=application_id
                ).delete()
                for row in line_rows:
                    await OtherExpenseApplicationLine.create(
                        tenant_id=tenant_id, application_id=application_id, **row
                    )
                dump["total_amount"] = total
                dump["remaining_amount"] = total - Decimal(str(head.pushed_amount or 0))
            dump["updated_by"] = updated_by
            dump["updated_by_name"] = user["name"]
            await head.update_from_dict(dump).save()
        return await self._auto_submit_when_audit_disabled(
            tenant_id, application_id, updated_by
        )

    async def delete_application(self, tenant_id: int, application_id: int) -> None:
        head = await OtherExpenseApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用支出申请不存在: {application_id}")
        assert_other_expense_application_capability(head, "delete")
        if Decimal(str(head.pushed_amount or 0)) > 0:
            raise BusinessLogicError("已有下推占用，不可删除")
        head.deleted_at = resolve_business_datetime()
        await head.save()

    async def commit_application(
        self, tenant_id: int, application_id: int, user_id: int
    ) -> OtherExpenseApplicationResponse:
        head = await OtherExpenseApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用支出申请不存在: {application_id}")
        assert_other_expense_application_capability(head, "submit")
        raw = str(head.review_status or "").strip()
        if raw == "SUBMITTED":
            return await self.get_by_id(tenant_id, application_id)
        user = await self.get_user_info(user_id)
        head.review_status = "SUBMITTED"
        head.status = "Draft"
        head.updated_by = user_id
        head.updated_by_name = user["name"]
        await head.save()
        return await self.get_by_id(tenant_id, application_id)

    async def submit_application_for_review(
        self,
        tenant_id: int,
        application_id: int,
        user_id: int,
        *,
        selected_approver_user_ids: Optional[List[int]] = None,
        selected_approver_by_node: Optional[Dict[str, List[int]]] = None,
    ) -> OtherExpenseApplicationResponse:
        head = await OtherExpenseApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用支出申请不存在: {application_id}")
        if str(head.review_status or "").strip() != "SUBMITTED":
            raise BusinessLogicError("请先提交其他费用支出申请，再提交审核")
        return await self._enter_review(
            tenant_id,
            head,
            user_id,
            selected_approver_user_ids=selected_approver_user_ids,
            selected_approver_by_node=selected_approver_by_node,
        )

    async def submit_application(
        self,
        tenant_id: int,
        application_id: int,
        user_id: int,
        *,
        selected_approver_user_ids: Optional[List[int]] = None,
        selected_approver_by_node: Optional[Dict[str, List[int]]] = None,
    ) -> OtherExpenseApplicationResponse:
        """内部一次性：草稿直接进入审核。页面提交请走 commit_application。"""
        head = await OtherExpenseApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用支出申请不存在: {application_id}")
        raw = str(head.review_status or "").strip()
        if raw in {"已审核", "approved", "待审核", "pending_review", "PENDING_REVIEW"}:
            return await self.get_by_id(tenant_id, application_id)
        if raw != "SUBMITTED":
            assert_other_expense_application_capability(head, "submit")
            user = await self.get_user_info(user_id)
            head.review_status = "SUBMITTED"
            head.status = "Draft"
            head.updated_by = user_id
            head.updated_by_name = user["name"]
            await head.save()
            head = await OtherExpenseApplication.get(
                tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
            )
        return await self._enter_review(
            tenant_id,
            head,
            user_id,
            selected_approver_user_ids=selected_approver_user_ids,
            selected_approver_by_node=selected_approver_by_node,
        )

    async def _enter_review(
        self,
        tenant_id: int,
        head: OtherExpenseApplication,
        user_id: int,
        *,
        selected_approver_user_ids: Optional[List[int]] = None,
        selected_approver_by_node: Optional[Dict[str, List[int]]] = None,
    ) -> OtherExpenseApplicationResponse:
        audit_required = await self._config.check_audit_required(
            tenant_id, "other_expense_application"
        )
        user = await self.get_user_info(user_id)
        if audit_required:
            from core.services.approval.audit_flow_guard import (
                approval_instance_finished_on_submit,
                start_document_approval_or_raise,
            )

            instance = await start_document_approval_or_raise(
                tenant_id=tenant_id,
                user_id=user_id,
                node_key="other_expense_application",
                entity_type="other_expense_application",
                entity_id=int(head.id),
                entity_uuid=str(head.uuid),
                title=f"其他费用支出申请审批: {head.application_code}",
                content=f"金额: {head.total_amount}",
                doc_label="其他费用支出申请",
                selected_approver_user_ids=selected_approver_user_ids,
                selected_approver_by_node=selected_approver_by_node,
            )
            head.review_status = "待审核"
            head.status = "Draft"
            head.updated_by = user_id
            head.updated_by_name = user["name"]
            await head.save()
            if approval_instance_finished_on_submit(instance):
                return await self.approve_application(
                    tenant_id,
                    int(head.id),
                    approved=True,
                    operator_id=user_id,
                    is_auto_approve=True,
                )
            return await self.get_by_id(tenant_id, int(head.id))
        head.review_status = "已审核"
        head.status = "Approved"
        head.reviewer_id = user_id
        head.reviewer_name = user["name"]
        head.review_time = resolve_business_datetime()
        head.updated_by = user_id
        head.updated_by_name = user["name"]
        await head.save()
        return await self.get_by_id(tenant_id, int(head.id))

    async def approve_application(
        self,
        tenant_id: int,
        application_id: int,
        *,
        approved: bool,
        operator_id: int,
        review_remarks: Optional[str] = None,
        is_auto_approve: bool = False,
    ) -> OtherExpenseApplicationResponse:
        head = await OtherExpenseApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用支出申请不存在: {application_id}")
        if not is_auto_approve:
            if approved:
                assert_other_expense_application_capability(head, "approve")
            else:
                assert_other_expense_application_capability(head, "reject")
        user = await self.get_user_info(operator_id)
        if approved:
            head.review_status = "已审核"
            head.status = "Approved"
        else:
            head.review_status = "已驳回"
            head.status = "Rejected"
        head.reviewer_id = operator_id
        head.reviewer_name = user["name"]
        head.review_time = resolve_business_datetime()
        head.review_remarks = review_remarks
        head.updated_by = operator_id
        head.updated_by_name = user["name"]
        await head.save()
        return await self.get_by_id(tenant_id, application_id)

    async def withdraw_application_submit(
        self, tenant_id: int, application_id: int, user_id: int
    ) -> OtherExpenseApplicationResponse:
        from apps.kuaicaiwu.services.finance_audit_workflow import (
            _PENDING_REVIEW,
            _norm_review,
        )
        from core.services.approval.approval_instance_service import ApprovalInstanceService

        head = await OtherExpenseApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用支出申请不存在: {application_id}")
        assert_other_expense_application_capability(head, "withdraw_submit")
        user = await self.get_user_info(user_id)
        raw = str(head.review_status or "").strip()
        if raw == "SUBMITTED":
            head.review_status = "草稿"
            head.status = "Draft"
            head.updated_by = user_id
            head.updated_by_name = user["name"]
            await head.save()
            return await self.get_by_id(tenant_id, application_id)
        if _norm_review(raw) in _PENDING_REVIEW:
            cancelled = await ApprovalInstanceService.cancel_approval(
                tenant_id=tenant_id,
                entity_type="other_expense_application",
                entity_id=application_id,
                operator_id=user_id,
            )
            if cancelled is False:
                raise BusinessLogicError("撤回失败：无法取消审批流程，请重试")
            head.review_status = "SUBMITTED"
            head.status = "Draft"
            head.reviewer_id = None
            head.reviewer_name = None
            head.review_time = None
            head.review_remarks = None
            head.updated_by = user_id
            head.updated_by_name = user["name"]
            await head.save()
            return await self.get_by_id(tenant_id, application_id)
        raise BusinessLogicError("仅已提交或待审核可撤回")

    async def revoke_application_approval(
        self, tenant_id: int, application_id: int, user_id: int
    ) -> OtherExpenseApplicationResponse:
        head = await OtherExpenseApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用支出申请不存在: {application_id}")
        from apps.kuaizhizao.models.document_relation import DocumentRelation

        expense_rels = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="other_expense_application",
            source_id=int(head.id),
            target_type="other_expense",
        ).all()
        linked = await resolve_application_linked_expenses(tenant_id, expense_rels)
        assert_other_expense_application_capability(
            head, "revoke_approval", has_linked_expense=bool(linked)
        )
        user = await self.get_user_info(user_id)
        head.review_status = "草稿"
        head.status = "Draft"
        head.reviewer_id = None
        head.reviewer_name = None
        head.review_time = None
        head.review_remarks = None
        head.updated_by = user_id
        head.updated_by_name = user["name"]
        await head.save()
        return await self.get_by_id(tenant_id, application_id)

    async def allocate_push_amount_to_lines(
        self,
        lines: List[OtherExpenseApplicationLine],
        push_total: Decimal,
        *,
        line_ids: Optional[List[int]] = None,
    ) -> List[tuple[OtherExpenseApplicationLine, Decimal]]:
        remaining = Decimal(str(push_total or 0))
        if remaining <= 0:
            return []
        selected = lines
        if line_ids:
            id_set = {int(i) for i in line_ids}
            selected = [ln for ln in lines if int(ln.id) in id_set]
        out: List[tuple[OtherExpenseApplicationLine, Decimal]] = []
        for line in sorted(selected, key=lambda x: int(x.line_no or 0)):
            if remaining <= 0:
                break
            open_amt = Decimal(str(line.amount or 0)) - Decimal(str(line.pushed_amount or 0))
            if open_amt <= 0:
                continue
            take = min(open_amt, remaining)
            out.append((line, take))
            remaining -= take
        if remaining > 0:
            raise BusinessLogicError("下推金额超过申请行可下推余额")
        return out

    async def record_line_pushed(
        self,
        tenant_id: int,
        application_id: int,
        line_pushes: List[tuple[int, Decimal]],
    ) -> None:
        if not line_pushes:
            return
        app = await OtherExpenseApplication.get(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        async with in_transaction():
            for line_id, amt in line_pushes:
                line = await OtherExpenseApplicationLine.get_or_none(
                    tenant_id=tenant_id, id=line_id, application_id=application_id
                )
                if not line:
                    continue
                line.pushed_amount = Decimal(str(line.pushed_amount or 0)) + Decimal(str(amt))
                await line.save()
            lines = await OtherExpenseApplicationLine.filter(
                tenant_id=tenant_id, application_id=application_id
            ).all()
            pushed = sum(Decimal(str(l.pushed_amount or 0)) for l in lines)
            app.pushed_amount = pushed
            self._sync_head_totals(app)
            await app.save()

    async def release_expense_occupancy(
        self, tenant_id: int, expense: OtherExpense
    ) -> None:
        if str(getattr(expense, "source_type", "") or "") != "other_expense_application":
            return
        app_id = int(getattr(expense, "source_id", 0) or 0)
        if not app_id:
            return
        amount = Decimal(str(expense.total_amount or 0))
        if amount <= 0:
            return
        lines = await OtherExpenseApplicationLine.filter(
            tenant_id=tenant_id, application_id=app_id
        ).order_by("line_no")
        release_plan: List[tuple[int, Decimal]] = []
        remaining = amount
        for line in lines:
            if remaining <= 0:
                break
            pushed = Decimal(str(line.pushed_amount or 0))
            if pushed <= 0:
                continue
            take = min(pushed, remaining)
            release_plan.append((int(line.id), take))
            remaining -= take
        if not release_plan:
            return
        app = await OtherExpenseApplication.get_or_none(
            tenant_id=tenant_id, id=app_id, deleted_at__isnull=True
        )
        if not app:
            return
        async with in_transaction():
            for line_id, amt in release_plan:
                line = await OtherExpenseApplicationLine.get(
                    tenant_id=tenant_id, id=line_id, application_id=app_id
                )
                line.pushed_amount = max(
                    Decimal("0"), Decimal(str(line.pushed_amount or 0)) - Decimal(str(amt))
                )
                await line.save()
            all_lines = await OtherExpenseApplicationLine.filter(
                tenant_id=tenant_id, application_id=app_id
            ).all()
            app.pushed_amount = sum(Decimal(str(l.pushed_amount or 0)) for l in all_lines)
            self._sync_head_totals(app)
            await app.save()
