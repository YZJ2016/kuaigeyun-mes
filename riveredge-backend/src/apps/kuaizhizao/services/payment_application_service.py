"""
付款申请单服务
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from apps.common.base_service import AppBaseService
from apps.kuaicaiwu.models.payable import Payable
from apps.kuaizhizao.constants import ReviewStatus, is_draft_status, is_pending_review_status
from apps.kuaizhizao.models.payment_application import PaymentApplication, PaymentApplicationLine
from apps.kuaizhizao.schemas.payment_application import (
    PaymentApplicationCreate,
    PaymentApplicationUpdate,
    PaymentApplicationResponse,
    PaymentApplicationLineResponse,
    PaymentApplicationPurchaseOrderSource,
)
from apps.kuaizhizao.services.document_action_policy.payment_application import (
    assert_payment_application_capability,
    derive_payment_application_capabilities,
)
from apps.kuaizhizao.services.payable_open_amount_service import PayableOpenAmountService
from core.utils.timezone_utils import resolve_business_datetime, to_site_date
from infra.exceptions.exceptions import NotFoundError, ValidationError, BusinessLogicError
from infra.services.business_config_service import BusinessConfigService
from loguru import logger


PAYMENT_APPLICATION_INVOICE_STATUSES = frozenset({"有发票", "无发票", "发票后补"})

PAYMENT_APPLICATION_SORTABLE = frozenset({
    "application_code",
    "application_date",
    "status",
    "supplier_name",
    "total_request_amount",
    "created_at",
    "updated_at",
})


def _assert_payment_application_department(
    department_id: Any, department_name: Any
) -> tuple[int, str]:
    did = int(department_id or 0)
    name = str(department_name or "").strip()
    if did <= 0 or not name:
        raise ValidationError("请选择申请部门")
    return did, name


def _apply_payment_application_approval_filter(query, approval_phase: Optional[str]):
    phase = str(approval_phase or "").strip().lower()
    if not phase:
        return query
    if phase == "draft":
        return query.filter(status="草稿")
    if phase == "submitted":
        return query.filter(status="已提交")
    if phase == "pending_review":
        return query.filter(status="待审核")
    if phase == "approved":
        return query.filter(review_status=ReviewStatus.APPROVED.value)
    if phase == "rejected":
        return query.filter(
            Q(status="已驳回") | Q(review_status=ReviewStatus.REJECTED.value)
        )
    return query


def _apply_payment_application_settlement_filter(query, payment_settlement: Optional[str]):
    settlement = str(payment_settlement or "").strip().lower()
    if not settlement:
        return query
    if settlement == "unpaid":
        return query.filter(status="已批准")
    if settlement == "partial":
        return query.filter(status="部分付款")
    if settlement == "paid":
        return query.filter(status="已付款")
    return query


async def resolve_payment_application_linked_payments(
    tenant_id: int,
    payment_rels: List[Any],
) -> List[Dict[str, Any]]:
    """付款申请 → 付款单关联：仅返回仍存在的付款单（避免已删单留下 DocumentRelation 幽灵链接）。"""
    from apps.kuaicaiwu.models.payment import Payment

    ids = [int(r.target_id) for r in payment_rels if getattr(r, "target_id", None)]
    if not ids:
        return []
    rows = await Payment.filter(
        tenant_id=tenant_id, id__in=ids, deleted_at__isnull=True
    ).all()
    by_id = {int(p.id): p for p in rows}
    linked: List[Dict[str, Any]] = []
    for rel in payment_rels:
        pid = int(rel.target_id) if rel.target_id else 0
        pay = by_id.get(pid)
        if not pay:
            continue
        linked.append(
            {
                "id": pid,
                "code": str(pay.payment_code or getattr(rel, "target_code", None) or ""),
            }
        )
    return linked


class PaymentApplicationService(AppBaseService[PaymentApplication]):
    def __init__(self) -> None:
        super().__init__(PaymentApplication)
        self._open_amount = PayableOpenAmountService()
        self.business_config_service = BusinessConfigService()

    @staticmethod
    def _coerce_invoice_status(raw: Any, *, allow_default: bool) -> str:
        text = str(raw or "").strip()
        if not text:
            if allow_default:
                return "无发票"
            raise ValidationError("请选择发票情况")
        if text not in PAYMENT_APPLICATION_INVOICE_STATUSES:
            raise ValidationError("发票情况无效")
        return text

    @classmethod
    def _assert_application_invoice_status(cls, app: PaymentApplication) -> None:
        cls._coerce_invoice_status(app.invoice_status, allow_default=False)

    async def _generate_code(self, tenant_id: int) -> str:
        return await self.generate_code(tenant_id, "PAYMENT_APPLICATION_CODE", prefix="FKSQ")

    @staticmethod
    def _line_value(item: Any, key: str) -> Any:
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    async def _validate_lines(
        self,
        tenant_id: int,
        supplier_id: int,
        items: List[Any],
        *,
        exclude_application_id: Optional[int] = None,
    ) -> Decimal:
        total = Decimal("0")
        for idx, item in enumerate(items, start=1):
            req = Decimal(str(self._line_value(item, "request_amount") or 0))
            if req <= 0:
                raise ValidationError(f"第 {idx} 行申请金额须大于 0")
            line_kind = str(self._line_value(item, "line_kind") or "goods")
            payable_id = self._line_value(item, "payable_id")
            if line_kind != "prepayment":
                if not payable_id:
                    raise ValidationError(f"第 {idx} 行须关联应付单")
                payable = await Payable.get_or_none(
                    tenant_id=tenant_id, id=int(payable_id), deleted_at__isnull=True
                )
                if not payable:
                    raise NotFoundError(f"应付单不存在: {payable_id}")
                if int(payable.supplier_id) != int(supplier_id):
                    raise ValidationError("应付单供应商与申请头不一致")
                review = str(payable.review_status or "").strip()
                if review not in ("已审核", "APPROVED", "审核通过"):
                    raise ValidationError(f"应付单 {payable.payable_code} 未审核")
                max_req = await self._open_amount.max_request_for_payable(
                    tenant_id, payable, exclude_application_id=exclude_application_id
                )
                if req > max_req:
                    raise ValidationError(
                        f"第 {idx} 行申请金额 {req} 超过可请款 {max_req}（应付 {payable.payable_code}）"
                    )
            total += req
        return total

    async def _to_response(self, app: PaymentApplication) -> PaymentApplicationResponse:
        lines = await PaymentApplicationLine.filter(
            tenant_id=app.tenant_id, application_id=app.id
        ).order_by("line_no")
        from apps.kuaizhizao.models.document_relation import DocumentRelation

        payment_rels = await DocumentRelation.filter(
            tenant_id=app.tenant_id,
            source_type="payment_application",
            source_id=int(app.id),
            target_type="payment",
        ).all()
        linked_payments = await resolve_payment_application_linked_payments(
            app.tenant_id, payment_rels
        )
        caps = derive_payment_application_capabilities(
            app, has_linked_payment=bool(linked_payments)
        )
        from apps.kuaizhizao.services.payment_application_purchase_order_sources import (
            load_payment_application_purchase_order_sources,
        )

        po_sources_raw = await load_payment_application_purchase_order_sources(
            app.tenant_id, lines
        )
        po_sources = (
            [PaymentApplicationPurchaseOrderSource.model_validate(row) for row in po_sources_raw]
            if po_sources_raw
            else None
        )
        resp = PaymentApplicationResponse.model_validate(app, from_attributes=True)
        resp = resp.model_copy(
            update={
                "items": [PaymentApplicationLineResponse.model_validate(row) for row in lines],
                "capabilities": {k: v.model_dump() for k, v in caps.items()},
                "linked_payments": linked_payments,
                "purchase_order_sources": po_sources,
            }
        )
        from core.services.approval.audit_record_enricher import enrich_record

        return await enrich_record(
            app.tenant_id,
            "payment_application",
            resp,
            audit_enabled=True,
        )

    async def create_application(
        self,
        tenant_id: int,
        data: PaymentApplicationCreate,
        created_by: int,
        *,
        skip_manual_create_auto_submit: bool = False,
    ) -> PaymentApplicationResponse:
        if not data.items:
            raise ValidationError("至少一行申请明细")
        from apps.kuaicaiwu.constants.payment_method import (
            assert_payment_application_payee_fields,
        )

        assert_payment_application_payee_fields(
            payment_method=data.payment_method,
            advance_payee_id=data.advance_payee_id,
            advance_payee_name=data.advance_payee_name,
        )
        total = await self._validate_lines(tenant_id, data.supplier_id, data.items)
        dept_id, dept_name = _assert_payment_application_department(
            data.department_id, data.department_name
        )
        async with in_transaction():
            code = data.application_code or await self._generate_code(tenant_id)
            user = await self.get_user_info(created_by)
            app = await PaymentApplication.create(
                tenant_id=tenant_id,
                application_code=code.strip().upper(),
                supplier_id=data.supplier_id,
                supplier_name=data.supplier_name.strip(),
                application_kind=data.application_kind or "goods",
                application_date=data.application_date or to_site_date(resolve_business_datetime()),
                expected_payment_date=data.expected_payment_date,
                applicant_id=data.applicant_id or created_by,
                applicant_name=data.applicant_name or user["name"],
                department_id=dept_id,
                department_name=dept_name,
                total_request_amount=total,
                paid_amount=Decimal("0"),
                remaining_amount=total,
                status="草稿",
                review_status=ReviewStatus.PENDING.value,
                supplier_account_name=data.supplier_account_name,
                supplier_bank_name=data.supplier_bank_name,
                supplier_bank_account=data.supplier_bank_account,
                payment_reason=data.payment_reason,
                payment_method=data.payment_method,
                advance_payee_id=data.advance_payee_id,
                advance_payee_name=data.advance_payee_name,
                invoice_status=self._coerce_invoice_status(
                    data.invoice_status, allow_default=True
                ),
                payment_terms=data.payment_terms,
                notes=data.notes,
                require_payment_voucher=bool(data.require_payment_voucher),
                attachments=data.attachments,
                created_by=created_by,
                created_by_name=user["name"],
                updated_by=created_by,
                updated_by_name=user["name"],
            )
            for idx, item in enumerate(data.items, start=1):
                max_amt = item.request_amount
                if item.payable_id:
                    payable = await Payable.get(
                        id=int(item.payable_id), tenant_id=tenant_id, deleted_at__isnull=True
                    )
                    max_amt = await self._open_amount.max_request_for_payable(tenant_id, payable)
                await PaymentApplicationLine.create(
                    tenant_id=tenant_id,
                    application_id=app.id,
                    line_no=idx,
                    source_type=item.source_type,
                    source_id=item.source_id,
                    source_code=item.source_code,
                    payable_id=item.payable_id,
                    payable_code=item.payable_code,
                    line_kind=item.line_kind or "goods",
                    request_amount=item.request_amount,
                    paid_amount=Decimal("0"),
                    max_request_amount=max_amt,
                    notes=item.notes,
                )
            app_id = app.id
        from apps.kuaizhizao.services.manual_create_auto_lifecycle import (
            apply_manual_create_auto_submit,
        )

        await apply_manual_create_auto_submit(
            tenant_id=tenant_id,
            node_key="payment_application",
            entity_id=app_id,
            operator_id=created_by,
            skip=skip_manual_create_auto_submit,
        )
        return await self.get_by_id(tenant_id, app_id)

    async def get_by_id(
        self,
        tenant_id: int,
        application_id: int,
        *,
        viewer_id: Optional[int] = None,
    ) -> PaymentApplicationResponse:
        app = await PaymentApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not app:
            raise NotFoundError(f"付款申请单不存在: {application_id}")
        resp = await self._to_response(app)
        if viewer_id is not None:
            from core.services.approval.audit_record_enricher import (
                apply_viewer_flow_gate_after_capabilities,
            )

            resp = (
                await apply_viewer_flow_gate_after_capabilities(
                    tenant_id,
                    "payment_application",
                    [resp],
                    viewer_id,
                )
            )[0]
        return resp

    async def list_applications(
        self,
        tenant_id: int,
        *,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        supplier_id: Optional[int] = None,
        keyword: Optional[str] = None,
        sort_field: Optional[str] = None,
        sort_order: Optional[str] = None,
        approved_only: bool = False,
        with_remaining: bool = False,
        approval_phase: Optional[str] = None,
        payment_settlement: Optional[str] = None,
        viewer_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        query = PaymentApplication.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if status:
            query = query.filter(status=status)
        query = _apply_payment_application_approval_filter(query, approval_phase)
        query = _apply_payment_application_settlement_filter(query, payment_settlement)
        if supplier_id:
            query = query.filter(supplier_id=supplier_id)
        if approved_only:
            query = query.filter(status__in=["已批准", "部分付款"])
        if with_remaining:
            query = query.filter(remaining_amount__gt=0)
        kw = str(keyword or "").strip()
        if kw:
            query = query.filter(
                Q(application_code__icontains=kw) | Q(supplier_name__icontains=kw)
            )
        sf = sort_field if sort_field in PAYMENT_APPLICATION_SORTABLE else "created_at"
        order = sf if (sort_order or "desc").lower() == "asc" else f"-{sf}"
        total = await query.count()
        rows = await query.offset(skip).limit(limit).order_by(order)
        data = [await self._to_response(row) for row in rows]
        if viewer_id is not None:
            from core.services.approval.audit_record_enricher import (
                apply_viewer_flow_gate_after_capabilities,
            )

            data = await apply_viewer_flow_gate_after_capabilities(
                tenant_id,
                "payment_application",
                data,
                viewer_id,
            )
        return {"data": data, "total": total}

    async def update_application(
        self,
        tenant_id: int,
        application_id: int,
        data: PaymentApplicationUpdate,
        updated_by: int,
    ) -> PaymentApplicationResponse:
        app = await PaymentApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not app:
            raise NotFoundError(f"付款申请单不存在: {application_id}")
        assert_payment_application_capability(app, "update")

        dump = data.model_dump(exclude_unset=True, by_alias=False)
        from apps.kuaicaiwu.constants.payment_method import (
            assert_payment_application_payee_fields,
        )

        merged_method = dump.get("payment_method", app.payment_method)
        merged_payee_id = dump.get("advance_payee_id", app.advance_payee_id)
        merged_payee_name = dump.get("advance_payee_name", app.advance_payee_name)
        assert_payment_application_payee_fields(
            payment_method=merged_method,
            advance_payee_id=merged_payee_id,
            advance_payee_name=merged_payee_name,
        )
        items = dump.pop("items", None)
        if items is not None:
            supplier_id = int(dump.get("supplier_id") or app.supplier_id)
            total = await self._validate_lines(
                tenant_id, supplier_id, items, exclude_application_id=application_id
            )
            async with in_transaction():
                await PaymentApplicationLine.filter(
                    tenant_id=tenant_id, application_id=application_id
                ).delete()
                for idx, item in enumerate(items, start=1):
                    max_amt = item["request_amount"]
                    if item.get("payable_id"):
                        payable = await Payable.get(
                            id=int(item["payable_id"]),
                            tenant_id=tenant_id,
                            deleted_at__isnull=True,
                        )
                        max_amt = await self._open_amount.max_request_for_payable(
                            tenant_id, payable, exclude_application_id=application_id
                        )
                    await PaymentApplicationLine.create(
                        tenant_id=tenant_id,
                        application_id=application_id,
                        line_no=idx,
                        source_type=item["source_type"],
                        source_id=item.get("source_id"),
                        source_code=item.get("source_code"),
                        payable_id=item.get("payable_id"),
                        payable_code=item.get("payable_code"),
                        line_kind=item.get("line_kind") or "goods",
                        request_amount=item["request_amount"],
                        paid_amount=Decimal("0"),
                        max_request_amount=max_amt,
                        notes=item.get("notes"),
                    )
                dump["total_request_amount"] = total
                dump["remaining_amount"] = total - Decimal(str(app.paid_amount or 0))
        if "invoice_status" in dump:
            dump["invoice_status"] = self._coerce_invoice_status(
                dump["invoice_status"], allow_default=False
            )
        merged_dept_id = dump.get("department_id", app.department_id)
        merged_dept_name = dump.get("department_name", app.department_name)
        dept_id, dept_name = _assert_payment_application_department(
            merged_dept_id, merged_dept_name
        )
        dump["department_id"] = dept_id
        dump["department_name"] = dept_name
        user = await self.get_user_info(updated_by)
        dump["updated_by"] = updated_by
        dump["updated_by_name"] = user["name"]
        await app.update_from_dict(dump).save()
        return await self.get_by_id(tenant_id, application_id)

    async def delete_application(self, tenant_id: int, application_id: int) -> None:
        app = await PaymentApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not app:
            raise NotFoundError(f"付款申请单不存在: {application_id}")
        assert_payment_application_capability(app, "delete")
        app.deleted_at = resolve_business_datetime()
        await app.save()

    async def submit_application(
        self,
        tenant_id: int,
        application_id: int,
        submitted_by: int,
        *,
        selected_approver_user_ids: Optional[List[int]] = None,
        selected_approver_by_node: Optional[Dict[str, List[int]]] = None,
    ) -> PaymentApplicationResponse:
        app = await PaymentApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not app:
            raise NotFoundError(f"付款申请单不存在: {application_id}")
        assert_payment_application_capability(app, "submit")
        self._assert_application_invoice_status(app)

        audit_required = await self.business_config_service.check_audit_required(
            tenant_id, "payment_application"
        )
        user = await self.get_user_info(submitted_by)

        if audit_required:
            from core.services.approval.audit_flow_guard import (
                approval_instance_finished_on_submit,
                start_document_approval_or_raise,
            )

            instance = await start_document_approval_or_raise(
                tenant_id=tenant_id,
                user_id=submitted_by,
                node_key="payment_application",
                entity_type="payment_application",
                entity_id=int(app.id),
                entity_uuid=str(app.uuid),
                title=f"付款申请审批: {app.application_code}",
                content=f"供应商: {app.supplier_name or '—'}",
                doc_label="付款申请",
                selected_approver_user_ids=selected_approver_user_ids,
                selected_approver_by_node=selected_approver_by_node,
            )
            app.status = "待审核"
            app.review_status = ReviewStatus.PENDING.value
            app.updated_by = submitted_by
            app.updated_by_name = user["name"]
            await app.save()
            if approval_instance_finished_on_submit(instance):
                return await self.approve_application(
                    tenant_id,
                    application_id,
                    approved=True,
                    approved_by=submitted_by,
                    is_auto_approve=True,
                )
            return await self.get_by_id(tenant_id, application_id)

        app.status = "已批准"
        app.review_status = ReviewStatus.APPROVED.value
        app.updated_by = submitted_by
        app.updated_by_name = user["name"]
        await app.save()
        return await self.get_by_id(tenant_id, application_id)

    async def withdraw_application(
        self, tenant_id: int, application_id: int, withdrawn_by: int
    ) -> PaymentApplicationResponse:
        app = await PaymentApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not app:
            raise NotFoundError(f"付款申请单不存在: {application_id}")
        if not is_pending_review_status(app.status or ""):
            raise BusinessLogicError("payment_application.withdraw.not_allowed")
        try:
            from core.services.approval.approval_instance_service import ApprovalInstanceService

            await ApprovalInstanceService.cancel_approval(
                tenant_id=tenant_id,
                entity_type="payment_application",
                entity_id=application_id,
                operator_id=withdrawn_by,
            )
        except Exception as e:
            logger.warning("取消付款申请审批流程失败或无需取消: {}", e)
        user = await self.get_user_info(withdrawn_by)
        app.status = "草稿"
        app.review_status = ReviewStatus.PENDING.value
        app.updated_by = withdrawn_by
        app.updated_by_name = user["name"]
        await app.save()
        return await self.get_by_id(tenant_id, application_id)

    async def approve_application(
        self,
        tenant_id: int,
        application_id: int,
        *,
        approved: bool,
        approved_by: int,
        review_remarks: Optional[str] = None,
        is_auto_approve: bool = False,
    ) -> PaymentApplicationResponse:
        app = await PaymentApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not app:
            raise NotFoundError(f"付款申请单不存在: {application_id}")
        assert_payment_application_capability(app, "approve")

        audit_required = await self.business_config_service.check_audit_required(
            tenant_id, "payment_application"
        )
        if not is_auto_approve:
            from core.services.approval.audit_flow_guard import assert_pending_approval_instance

            await assert_pending_approval_instance(
                tenant_id=tenant_id,
                entity_type="payment_application",
                entity_id=application_id,
                audit_required=audit_required,
                doc_label="付款申请",
                verb="审核" if approved else "驳回",
            )

        from core.services.approval.uni_audit_service import UniAuditService

        async def _do_decide() -> PaymentApplicationResponse:
            row = await PaymentApplication.get_or_none(
                tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
            )
            if not row:
                raise NotFoundError(f"付款申请单不存在: {application_id}")
            user = await self.get_user_info(approved_by)
            row.reviewer_id = approved_by
            row.reviewer_name = user["name"]
            row.review_time = resolve_business_datetime()
            row.review_remarks = review_remarks
            if approved:
                row.status = "已批准"
                row.review_status = ReviewStatus.APPROVED.value
            else:
                row.status = "已驳回"
                row.review_status = ReviewStatus.REJECTED.value
            row.updated_by = approved_by
            row.updated_by_name = user["name"]
            await row.save()
            return await self.get_by_id(tenant_id, application_id)

        sync_after_flow = False
        if audit_required and approved_by and not is_auto_approve:
            from core.services.approval.audit_flow_guard import (
                get_approval_gate_status,
                should_sync_doc_after_flow_completed,
            )

            gate = await get_approval_gate_status(
                tenant_id=tenant_id,
                entity_type="payment_application",
                entity_id=application_id,
            )
            sync_after_flow = should_sync_doc_after_flow_completed(gate, approve=approved)

        if is_auto_approve or not approved_by or sync_after_flow:
            return await _do_decide()

        if approved:
            result = await UniAuditService.approve_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="payment_application",
                entity_id=application_id,
                approver_id=approved_by,
                flow_approve=_do_decide,
            )
        else:
            result = await UniAuditService.reject_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="payment_application",
                entity_id=application_id,
                approver_id=approved_by,
                reason=review_remarks,
                flow_reject=lambda _reason: _do_decide(),
            )
        return result if result is not None else await self.get_by_id(tenant_id, application_id)

    async def revoke_application_approval(
        self,
        tenant_id: int,
        application_id: int,
        operator_id: int,
    ) -> PaymentApplicationResponse:
        """撤销审核：有流程则按流程策略重开；否则回草稿或待审核。"""
        from apps.kuaizhizao.constants import ReviewStatus
        from apps.kuaizhizao.models.document_relation import DocumentRelation
        from core.services.approval.audit_transition import resolve_revoke_to_draft_landing_phase
        from core.services.approval.uni_audit_service import UniAuditService

        app = await PaymentApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not app:
            raise NotFoundError(f"付款申请单不存在: {application_id}")
        payment_rels = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="payment_application",
            source_id=int(application_id),
            target_type="payment",
        ).all()
        linked_payments = await resolve_payment_application_linked_payments(
            tenant_id, payment_rels
        )
        assert_payment_application_capability(
            app, "revoke_approval", has_linked_payment=bool(linked_payments)
        )

        audit_required = await self.business_config_service.check_audit_required(
            tenant_id, "payment_application"
        )
        op_id = int(operator_id)

        async def _do_revoke(*, reopened: bool = False) -> PaymentApplicationResponse:
            landing = resolve_revoke_to_draft_landing_phase(
                manual_audit_enabled=audit_required,
                flow_reopened=reopened,
            )
            row = await PaymentApplication.get_or_none(
                tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
            )
            if not row:
                raise NotFoundError(f"付款申请单不存在: {application_id}")
            if landing == "pending":
                row.status = "待审核"
            else:
                row.status = "草稿"
            row.review_status = ReviewStatus.PENDING.value
            row.reviewer_id = None
            row.reviewer_name = None
            row.review_time = None
            row.review_remarks = None
            user = await self.get_user_info(op_id)
            row.updated_by = op_id
            row.updated_by_name = user["name"]
            await row.save()
            return await self.get_by_id(tenant_id, application_id)

        return await UniAuditService.revoke_with_flow_fallback(
            tenant_id=tenant_id,
            entity_type="payment_application",
            entity_id=application_id,
            operator_id=op_id,
            flow_revoke=_do_revoke,
        )

    @staticmethod
    def _refresh_application_payment_status(app: PaymentApplication) -> None:
        total = Decimal(str(app.total_request_amount or 0))
        paid = max(Decimal("0"), Decimal(str(app.paid_amount or 0)))
        app.paid_amount = paid
        app.remaining_amount = max(Decimal("0"), total - paid)
        if app.remaining_amount <= 0 and paid > 0:
            app.status = "已付款"
        elif paid > 0:
            app.status = "部分付款"
        else:
            # 无已付时回到可再次下推付款的已批准态
            app.status = "已批准"

    async def record_line_paid(
        self,
        tenant_id: int,
        application_id: int,
        line_payments: List[tuple[int, Decimal]],
    ) -> None:
        """付款确认后回写申请行与头表已付金额。"""
        app = await PaymentApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not app:
            return
        total_paid_delta = Decimal("0")
        for line_id, amount in line_payments:
            line = await PaymentApplicationLine.get_or_none(
                tenant_id=tenant_id, id=line_id, application_id=application_id
            )
            if not line or amount <= 0:
                continue
            line.paid_amount = Decimal(str(line.paid_amount or 0)) + amount
            await line.save()
            total_paid_delta += amount
        if total_paid_delta <= 0:
            return
        app.paid_amount = Decimal(str(app.paid_amount or 0)) + total_paid_delta
        self._refresh_application_payment_status(app)
        await app.save()

    async def record_line_unpaid(
        self,
        tenant_id: int,
        application_id: int,
        line_payments: List[tuple[int, Decimal]],
    ) -> None:
        """付款单撤回确认/作废/删除后，冲回申请行与头表已付金额。"""
        app = await PaymentApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not app:
            return
        total_unpaid_delta = Decimal("0")
        for line_id, amount in line_payments:
            line = await PaymentApplicationLine.get_or_none(
                tenant_id=tenant_id, id=line_id, application_id=application_id
            )
            if not line or amount <= 0:
                continue
            current = Decimal(str(line.paid_amount or 0))
            take = min(current, amount)
            if take <= 0:
                continue
            line.paid_amount = current - take
            await line.save()
            total_unpaid_delta += take
        if total_unpaid_delta <= 0:
            return
        app.paid_amount = max(
            Decimal("0"),
            Decimal(str(app.paid_amount or 0)) - total_unpaid_delta,
        )
        self._refresh_application_payment_status(app)
        await app.save()

    async def repair_paid_from_confirmed_payments(
        self,
        tenant_id: int,
        application_id: int,
        *,
        exclude_payment_ids: Optional[set[int]] = None,
    ) -> None:
        """按仍存在的已确认付款单重算申请已付（修复删除/撤回后未冲回的脏数据）。

        分摊语义与 apply_payment_confirmed 一致：prepayment 单只摊到
        prepayment 行；普通单只摊到已下推（payable→payment 关联）的应付行。
        """
        from apps.kuaicaiwu.models.payment import Payment
        from apps.kuaizhizao.models.document_relation import DocumentRelation

        app = await PaymentApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not app:
            return
        exclude = exclude_payment_ids or set()
        rels = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="payment_application",
            source_id=application_id,
            target_type="payment",
        ).all()
        payment_ids = [
            int(r.target_id)
            for r in rels
            if r.target_id and int(r.target_id) not in exclude
        ]
        payments = []
        if payment_ids:
            payments = await Payment.filter(
                tenant_id=tenant_id,
                id__in=payment_ids,
                deleted_at__isnull=True,
                status="Confirmed",
            ).order_by("id").all()

        lines = await PaymentApplicationLine.filter(
            tenant_id=tenant_id, application_id=application_id
        ).order_by("line_no")
        paid_by_line: Dict[int, Decimal] = {int(l.id): Decimal("0") for l in lines}

        for pay in payments:
            remaining = Decimal(str(pay.total_amount or 0))
            if remaining <= 0:
                continue
            if str(pay.settlement_type or "") == "prepayment":
                eligible = {
                    int(l.id) for l in lines
                    if str(l.line_kind) == "prepayment"
                }
            else:
                eligible = set(
                    await DocumentRelation.filter(
                        tenant_id=tenant_id,
                        source_type="payable",
                        target_type="payment",
                        target_id=int(pay.id),
                    ).values_list("source_id", flat=True)
                )
            for line in lines:
                if remaining <= 0:
                    break
                line_id = int(line.id)
                if str(pay.settlement_type or "") == "prepayment":
                    if line_id not in eligible:
                        continue
                elif not line.payable_id or int(line.payable_id) not in eligible:
                    continue
                open_amt = (
                    Decimal(str(line.request_amount or 0)) - paid_by_line[line_id]
                )
                if open_amt <= 0:
                    continue
                take = min(open_amt, remaining)
                paid_by_line[line_id] += take
                remaining -= take

        for line in lines:
            new_paid = paid_by_line.get(int(line.id), Decimal("0"))
            if Decimal(str(line.paid_amount or 0)) != new_paid:
                line.paid_amount = new_paid
                await line.save()

        app.paid_amount = min(
            sum(paid_by_line.values(), Decimal("0")),
            Decimal(str(app.total_request_amount or 0)),
        )
        self._refresh_application_payment_status(app)
        await app.save()
