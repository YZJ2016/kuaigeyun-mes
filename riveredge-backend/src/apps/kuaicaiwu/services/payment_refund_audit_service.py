"""付款退款审核。业务状态仍是 Draft/Confirmed/Cancelled。确认退款是过账，不在这里改名。"""

from __future__ import annotations

from typing import Any

from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

from apps.kuaicaiwu.models.payment import Payment

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


def assert_payment_refund_review_editable(payment: Payment) -> None:
    raw = str(getattr(payment, "review_status", "") or "").strip()
    if raw not in _EDITABLE_REVIEW:
        raise BusinessLogicError("仅草稿或已驳回的付款退款可修改或作废")


class PaymentRefundAuditService:
    async def _get(self, tenant_id: int, payment_id: int) -> Payment:
        payment = await Payment.get_or_none(
            tenant_id=tenant_id,
            id=payment_id,
            deleted_at__isnull=True,
            settlement_type="refund",
        )
        if not payment:
            raise NotFoundError(f"付款退款单不存在: {payment_id}")
        return payment

    def _assert_draft_voucher(self, payment: Payment) -> None:
        if str(payment.status or "") != "Draft":
            raise BusinessLogicError("仅草稿付款退款可提交或审核")

    async def commit_payment_refund(
        self, tenant_id: int, payment_id: int, user_id: int
    ) -> dict[str, Any]:
        payment = await self._get(tenant_id, payment_id)
        self._assert_draft_voucher(payment)
        raw = str(payment.review_status or "").strip()
        if raw == "SUBMITTED":
            return self._payload(payment)
        if raw not in _EDITABLE_REVIEW:
            raise BusinessLogicError("仅草稿或已驳回的付款退款可提交")
        await Payment.filter(tenant_id=tenant_id, id=payment_id).update(review_status="SUBMITTED")
        payment.review_status = "SUBMITTED"
        return self._payload(payment)

    async def submit_payment_refund_for_review(
        self,
        tenant_id: int,
        payment_id: int,
        user_id: int,
        *,
        selected_approver_user_ids: list[int] | None = None,
        selected_approver_by_node: dict[str, list[int]] | None = None,
    ) -> dict[str, Any]:
        payment = await self._get(tenant_id, payment_id)
        self._assert_draft_voucher(payment)
        if str(payment.review_status or "").strip() != "SUBMITTED":
            raise BusinessLogicError("请先提交付款退款，再提交审核")
        await self._enter_review(
            tenant_id,
            payment,
            user_id,
            selected_approver_user_ids=selected_approver_user_ids,
            selected_approver_by_node=selected_approver_by_node,
        )
        return self._payload(await self._get(tenant_id, payment_id))

    async def submit_payment_refund(
        self, tenant_id: int, payment_id: int, user_id: int
    ) -> dict[str, Any]:
        """内部一次性：草稿直接进入审核。页面提交请走 commit_payment_refund。"""
        payment = await self._get(tenant_id, payment_id)
        raw = str(payment.review_status or "").strip()
        if raw in _APPROVED_REVIEW or raw in _PENDING_REVIEW:
            return self._payload(payment)
        if str(payment.status or "") != "Draft":
            raise BusinessLogicError("仅草稿付款退款可提交审核")
        if raw != "SUBMITTED":
            if raw not in _EDITABLE_REVIEW:
                raise BusinessLogicError("当前审核状态不可提交")
            await Payment.filter(tenant_id=tenant_id, id=payment_id).update(review_status="SUBMITTED")
            payment.review_status = "SUBMITTED"
        await self._enter_review(tenant_id, payment, user_id)
        return self._payload(await self._get(tenant_id, payment_id))

    async def withdraw_payment_refund(
        self, tenant_id: int, payment_id: int, user_id: int
    ) -> dict[str, Any]:
        from apps.kuaicaiwu.services.finance_audit_workflow import _norm_review
        from core.services.approval.approval_instance_service import ApprovalInstanceService

        payment = await self._get(tenant_id, payment_id)
        raw = str(payment.review_status or "").strip()
        if raw == "SUBMITTED":
            await Payment.filter(tenant_id=tenant_id, id=payment_id).update(review_status="草稿")
            payment.review_status = "草稿"
            return self._payload(payment)
        if _norm_review(raw) in _PENDING_REVIEW:
            cancelled = await ApprovalInstanceService.cancel_approval(
                tenant_id=tenant_id,
                entity_type="payment_refund",
                entity_id=payment_id,
                operator_id=user_id,
            )
            if cancelled is False:
                raise BusinessLogicError("撤回失败：无法取消审批流程，请重试")
            await Payment.filter(tenant_id=tenant_id, id=payment_id).update(review_status="SUBMITTED")
            payment.review_status = "SUBMITTED"
            return self._payload(payment)
        raise BusinessLogicError("仅已提交或待审核可撤回")

    async def approve_payment_refund(
        self,
        tenant_id: int,
        payment_id: int,
        user_id: int,
        rejection_reason: str | None = None,
    ) -> dict[str, Any]:
        from apps.kuaicaiwu.services.finance_audit_workflow import (
            _PENDING_REVIEW,
            _norm_review,
            assert_finance_pending_approval_flow,
        )
        from core.services.approval.uni_audit_service import UniAuditService

        payment = await self._get(tenant_id, payment_id)
        self._assert_draft_voucher(payment)

        async def _write() -> dict[str, Any]:
            current = await self._get(tenant_id, payment_id)
            if _norm_review(current.review_status) not in _PENDING_REVIEW:
                raise BusinessLogicError(
                    f"付款退款审核状态不是待审核，当前: {current.review_status!r}"
                )
            review_status = "驳回" if rejection_reason else "已审核"
            await Payment.filter(tenant_id=tenant_id, id=payment_id).update(
                review_status=review_status
            )
            current.review_status = review_status
            return self._payload(current)

        await assert_finance_pending_approval_flow(
            tenant_id=tenant_id,
            doc_id=payment_id,
            node_key="payment_refund",
            doc_label="付款退款",
            verb="驳回" if rejection_reason else "审核",
        )
        if rejection_reason:
            result = await UniAuditService.reject_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="payment_refund",
                entity_id=payment_id,
                approver_id=user_id,
                reason=rejection_reason,
                flow_reject=lambda _reason=None: _write(),
            )
        else:
            result = await UniAuditService.approve_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="payment_refund",
                entity_id=payment_id,
                approver_id=user_id,
                flow_approve=_write,
            )
        return result if result is not None else await _write()

    async def revoke_payment_refund(
        self, tenant_id: int, payment_id: int, user_id: int
    ) -> dict[str, Any]:
        payment = await self._get(tenant_id, payment_id)
        if str(payment.status or "") == "Confirmed":
            raise BusinessLogicError("已确认退款，请先撤回确认")
        raw = str(payment.review_status or "").strip()
        if raw not in _APPROVED_REVIEW:
            raise BusinessLogicError("付款退款未审核通过，无法反审核")
        await Payment.filter(tenant_id=tenant_id, id=payment_id).update(review_status="草稿")
        payment.review_status = "草稿"
        return self._payload(payment)

    async def _enter_review(
        self,
        tenant_id: int,
        payment: Payment,
        user_id: int,
        *,
        selected_approver_user_ids: list[int] | None = None,
        selected_approver_by_node: dict[str, list[int]] | None = None,
    ) -> None:
        from core.services.approval.approval_instance_service import ApprovalInstanceService
        from core.services.approval.audit_flow_guard import approval_instance_finished_on_submit
        from infra.services.business_config_service import BusinessConfigService

        audit_required = await BusinessConfigService().check_audit_required(
            tenant_id, "payment_refund"
        )
        if not audit_required:
            await Payment.filter(tenant_id=tenant_id, id=payment.id).update(review_status="已审核")
            return

        content = f"付款退款 {payment.payment_code}"
        if payment.supplier_name:
            content = f"{content}, 往来单位: {payment.supplier_name}"
        if payment.total_amount is not None:
            content = f"{content}, 金额: {payment.total_amount}"
        instance = await ApprovalInstanceService.start_approval_for_node(
            tenant_id=tenant_id,
            user_id=user_id,
            node_key="payment_refund",
            entity_type="payment_refund",
            entity_id=int(payment.id),
            entity_uuid=str(payment.uuid),
            title=f"付款退款审核: {payment.payment_code}",
            content=content,
            selected_approver_user_ids=selected_approver_user_ids,
            selected_approver_by_node=selected_approver_by_node,
        )
        if not instance:
            raise BusinessLogicError(
                "付款退款审核已开启但未找到可用的审批流程，请在配置中心检查 payment_refund 审批流程是否已激活"
            )
        await Payment.filter(tenant_id=tenant_id, id=payment.id).update(review_status="待审核")
        if approval_instance_finished_on_submit(instance):
            await Payment.filter(tenant_id=tenant_id, id=payment.id).update(review_status="已审核")

    @staticmethod
    def _payload(payment: Payment) -> dict[str, Any]:
        return {
            "id": int(payment.id),
            "payment_code": payment.payment_code,
            "status": payment.status,
            "review_status": payment.review_status,
        }
