"""销售发票（销项）审核。业务 status 仍保留未审核/已审核/已驳回/已作废/已红冲。"""

from __future__ import annotations

from typing import Any

from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

from apps.kuaicaiwu.models.invoice import Invoice

_EDITABLE_REVIEW = frozenset({"", "草稿", "draft", "驳回", "rejected", "已驳回"})
_APPROVED_REVIEW = frozenset({"approved", "已审核", "审核通过", "已通过", "通过"})
_PENDING_REVIEW = frozenset({
    "待审核",
    "pending_review",
    "PENDING_REVIEW",
    "pending_approval",
    "已提交",
    "pending",
})
_TERMINAL_STATUS = frozenset({"已作废", "已红冲"})


def assert_sales_invoice_review_editable(invoice: Invoice) -> None:
    if str(invoice.status or "").strip() in _TERMINAL_STATUS:
        raise BusinessLogicError("已作废或已红冲的发票不可修改或删除")
    raw = str(getattr(invoice, "review_status", "") or "").strip()
    if raw not in _EDITABLE_REVIEW:
        raise BusinessLogicError("仅草稿或已驳回的销售发票可修改或删除")


class SalesInvoiceAuditService:
    async def _get(self, tenant_id: int, invoice_id: int) -> Invoice:
        invoice = await Invoice.get_or_none(
            tenant_id=tenant_id,
            id=invoice_id,
            category="OUT",
            deleted_at__isnull=True,
        )
        if not invoice:
            raise NotFoundError(f"销售发票不存在: {invoice_id}")
        return invoice

    def _assert_open(self, invoice: Invoice) -> None:
        st = str(invoice.status or "").strip()
        if st in _TERMINAL_STATUS:
            raise BusinessLogicError("已作废或已红冲的发票不可提交或审核")
        if st == "已审核":
            raise BusinessLogicError("已审核发票不可再提交")

    async def commit_sales_invoice(
        self, tenant_id: int, invoice_id: int, user_id: int
    ) -> dict[str, Any]:
        invoice = await self._get(tenant_id, invoice_id)
        self._assert_open(invoice)
        raw = str(invoice.review_status or "").strip()
        if raw == "SUBMITTED":
            return self._payload(invoice)
        if raw not in _EDITABLE_REVIEW:
            raise BusinessLogicError("仅草稿或已驳回的销售发票可提交")
        await Invoice.filter(tenant_id=tenant_id, id=invoice_id).update(
            review_status="SUBMITTED",
            status="未审核",
        )
        invoice.review_status = "SUBMITTED"
        invoice.status = "未审核"
        return self._payload(invoice)

    async def submit_sales_invoice_for_review(
        self, tenant_id: int, invoice_id: int, user_id: int
    ) -> dict[str, Any]:
        invoice = await self._get(tenant_id, invoice_id)
        self._assert_open(invoice)
        if str(invoice.review_status or "").strip() != "SUBMITTED":
            raise BusinessLogicError("请先提交销售发票，再提交审核")
        await self._enter_review(tenant_id, invoice, user_id)
        return self._payload(await self._get(tenant_id, invoice_id))

    async def submit_sales_invoice(
        self, tenant_id: int, invoice_id: int, user_id: int
    ) -> dict[str, Any]:
        """内部一次性：草稿直接进入审核。页面提交请走 commit_sales_invoice。"""
        invoice = await self._get(tenant_id, invoice_id)
        raw = str(invoice.review_status or "").strip()
        if raw in _APPROVED_REVIEW or raw in _PENDING_REVIEW:
            return self._payload(invoice)
        self._assert_open(invoice)
        if raw != "SUBMITTED":
            if raw not in _EDITABLE_REVIEW:
                raise BusinessLogicError("当前审核状态不可提交")
            await Invoice.filter(tenant_id=tenant_id, id=invoice_id).update(
                review_status="SUBMITTED",
                status="未审核",
            )
            invoice.review_status = "SUBMITTED"
        await self._enter_review(tenant_id, invoice, user_id)
        return self._payload(await self._get(tenant_id, invoice_id))

    async def withdraw_sales_invoice(
        self, tenant_id: int, invoice_id: int, user_id: int
    ) -> dict[str, Any]:
        from apps.kuaicaiwu.services.finance_audit_workflow import _norm_review
        from core.services.approval.approval_instance_service import ApprovalInstanceService

        invoice = await self._get(tenant_id, invoice_id)
        self._assert_open(invoice)
        raw = str(invoice.review_status or "").strip()
        if raw == "SUBMITTED":
            await Invoice.filter(tenant_id=tenant_id, id=invoice_id).update(
                review_status="草稿",
                status="未审核",
            )
            invoice.review_status = "草稿"
            return self._payload(invoice)
        if _norm_review(raw) in _PENDING_REVIEW:
            cancelled = await ApprovalInstanceService.cancel_approval(
                tenant_id=tenant_id,
                entity_type="sales_invoice",
                entity_id=invoice_id,
                operator_id=user_id,
            )
            if cancelled is False:
                raise BusinessLogicError("撤回失败：无法取消审批流程，请重试")
            await Invoice.filter(tenant_id=tenant_id, id=invoice_id).update(
                review_status="SUBMITTED",
                status="未审核",
            )
            invoice.review_status = "SUBMITTED"
            return self._payload(invoice)
        raise BusinessLogicError("仅已提交或待审核可撤回")

    async def approve_sales_invoice(
        self,
        tenant_id: int,
        invoice_id: int,
        user_id: int,
        rejection_reason: str | None = None,
    ) -> dict[str, Any]:
        from apps.kuaicaiwu.services.finance_audit_workflow import (
            _PENDING_REVIEW,
            _norm_review,
            assert_finance_pending_approval_flow,
        )
        from core.services.approval.uni_audit_service import UniAuditService

        invoice = await self._get(tenant_id, invoice_id)
        self._assert_open(invoice)

        async def _write() -> dict[str, Any]:
            current = await self._get(tenant_id, invoice_id)
            if _norm_review(current.review_status) not in _PENDING_REVIEW:
                raise BusinessLogicError(
                    f"销售发票审核状态不是待审核，当前: {current.review_status!r}"
                )
            if rejection_reason:
                patch = {"review_status": "已驳回", "status": "已驳回"}
            else:
                patch = {"review_status": "已审核", "status": "已审核"}
            await Invoice.filter(tenant_id=tenant_id, id=invoice_id).update(**patch)
            current.review_status = patch["review_status"]
            current.status = patch["status"]
            return self._payload(current)

        await assert_finance_pending_approval_flow(
            tenant_id=tenant_id,
            doc_id=invoice_id,
            node_key="sales_invoice",
            doc_label="销售发票",
            verb="驳回" if rejection_reason else "审核",
        )
        if rejection_reason:
            result = await UniAuditService.reject_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="sales_invoice",
                entity_id=invoice_id,
                approver_id=user_id,
                reason=rejection_reason,
                flow_reject=lambda _reason=None: _write(),
            )
        else:
            result = await UniAuditService.approve_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="sales_invoice",
                entity_id=invoice_id,
                approver_id=user_id,
                flow_approve=_write,
            )
        out = result if result is not None else await _write()
        if not rejection_reason:
            invoice_row = await self._record_detail_occupancy_if_approved(tenant_id, invoice_id)
            if str(invoice_row.status or "").strip() == "已审核":
                from apps.kuaicaiwu.models.receivable import Receivable
                from apps.kuaicaiwu.services.finance_audit_workflow import submit_finance_review
                from apps.kuaicaiwu.services.sales_invoice_receivable_auto import (
                    maybe_auto_generate_receivable_for_sales_invoice,
                )
                auto_receivable_id, _ = await maybe_auto_generate_receivable_for_sales_invoice(
                    tenant_id=tenant_id,
                    invoice=invoice_row,
                    created_by=user_id,
                )
                if auto_receivable_id:
                    await submit_finance_review(
                        model=Receivable,
                        tenant_id=tenant_id,
                        doc_id=int(auto_receivable_id),
                        updated_by=user_id,
                        doc_label="应收单",
                        node_key="receivable",
                    )
        return out

    async def _record_detail_occupancy_if_approved(
        self, tenant_id: int, invoice_id: int
    ) -> Invoice:
        from apps.kuaicaiwu.config.finance_settlement_contract import SETTLEMENT_MODE_DETAIL
        from apps.kuaicaiwu.services.sales_invoice_detail_occupancy import (
            record_detail_sales_invoice_occupancy_on_approve,
        )

        invoice_row = await Invoice.get(tenant_id=tenant_id, id=invoice_id)
        if (
            str(invoice_row.status or "").strip() == "已审核"
            and str(invoice_row.settlement_mode or "") == SETTLEMENT_MODE_DETAIL
        ):
            await record_detail_sales_invoice_occupancy_on_approve(tenant_id, invoice_id)
        return invoice_row

    async def revoke_sales_invoice(
        self, tenant_id: int, invoice_id: int, user_id: int
    ) -> dict[str, Any]:
        from tortoise.transactions import in_transaction
        from apps.kuaicaiwu.config.finance_settlement_contract import SETTLEMENT_MODE_DETAIL
        from apps.kuaicaiwu.services.sales_delivery_line_finance_occupancy_service import (
            release_sales_delivery_invoice_occupancy,
        )

        invoice = await self._get(tenant_id, invoice_id)
        if str(invoice.status or "").strip() in _TERMINAL_STATUS:
            raise BusinessLogicError("已作废或已红冲的发票不可反审核")
        raw = str(invoice.review_status or "").strip()
        if raw not in _APPROVED_REVIEW and str(invoice.status or "").strip() != "已审核":
            raise BusinessLogicError("销售发票未审核通过，无法反审核")
        async with in_transaction():
            await Invoice.filter(tenant_id=tenant_id, id=invoice_id).update(
                review_status="草稿",
                status="未审核",
            )
            if str(getattr(invoice, "settlement_mode", None) or "") == SETTLEMENT_MODE_DETAIL:
                await release_sales_delivery_invoice_occupancy(tenant_id, invoice_id)
        invoice.review_status = "草稿"
        invoice.status = "未审核"
        return self._payload(invoice)

    async def _enter_review(self, tenant_id: int, invoice: Invoice, user_id: int) -> None:
        from core.services.approval.approval_instance_service import ApprovalInstanceService
        from core.services.approval.audit_flow_guard import approval_instance_finished_on_submit
        from infra.services.business_config_service import BusinessConfigService

        audit_required = await BusinessConfigService().check_audit_required(
            tenant_id, "sales_invoice"
        )
        if not audit_required:
            await Invoice.filter(tenant_id=tenant_id, id=invoice.id).update(
                review_status="已审核",
                status="已审核",
            )
            await self._record_detail_occupancy_if_approved(tenant_id, int(invoice.id))
            return

        content = f"销售发票 {invoice.invoice_code}"
        if invoice.partner_name:
            content = f"{content}, 往来单位: {invoice.partner_name}"
        if invoice.total_amount is not None:
            content = f"{content}, 金额: {invoice.total_amount}"
        instance = await ApprovalInstanceService.start_approval_for_node(
            tenant_id=tenant_id,
            user_id=user_id,
            node_key="sales_invoice",
            entity_type="sales_invoice",
            entity_id=int(invoice.id),
            entity_uuid=str(invoice.uuid),
            title=f"销售发票审核: {invoice.invoice_code}",
            content=content,
        )
        if not instance:
            raise BusinessLogicError(
                "销售发票审核已开启但未找到可用的审批流程，请在配置中心检查 sales_invoice 审批流程是否已激活"
            )
        await Invoice.filter(tenant_id=tenant_id, id=invoice.id).update(
            review_status="待审核",
            status="未审核",
        )
        if approval_instance_finished_on_submit(instance):
            await Invoice.filter(tenant_id=tenant_id, id=invoice.id).update(
                review_status="已审核",
                status="已审核",
            )
            await self._record_detail_occupancy_if_approved(tenant_id, int(invoice.id))

    @staticmethod
    def _payload(invoice: Invoice) -> dict[str, Any]:
        return {
            "id": int(invoice.id),
            "invoice_code": invoice.invoice_code,
            "status": invoice.status,
            "review_status": invoice.review_status,
        }
