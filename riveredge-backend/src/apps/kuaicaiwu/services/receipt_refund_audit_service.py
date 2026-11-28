"""收款退款审核。业务状态仍是 Draft/Confirmed/Cancelled。确认退款是过账，不在这里改名。"""

from __future__ import annotations

from typing import Any

from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

from apps.kuaicaiwu.models.receipt import Receipt

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


def assert_receipt_refund_review_editable(receipt: Receipt) -> None:
    raw = str(getattr(receipt, "review_status", "") or "").strip()
    if raw not in _EDITABLE_REVIEW:
        raise BusinessLogicError("仅草稿或已驳回的收款退款可修改或作废")


class ReceiptRefundAuditService:
    async def _get(self, tenant_id: int, receipt_id: int) -> Receipt:
        receipt = await Receipt.get_or_none(
            tenant_id=tenant_id,
            id=receipt_id,
            deleted_at__isnull=True,
            settlement_type="refund",
        )
        if not receipt:
            raise NotFoundError(f"收款退款单不存在: {receipt_id}")
        return receipt

    def _assert_draft_voucher(self, receipt: Receipt) -> None:
        if str(receipt.status or "") != "Draft":
            raise BusinessLogicError("仅草稿收款退款可提交或审核")

    async def commit_receipt_refund(
        self, tenant_id: int, receipt_id: int, user_id: int
    ) -> dict[str, Any]:
        receipt = await self._get(tenant_id, receipt_id)
        self._assert_draft_voucher(receipt)
        raw = str(receipt.review_status or "").strip()
        if raw == "SUBMITTED":
            return self._payload(receipt)
        if raw not in _EDITABLE_REVIEW:
            raise BusinessLogicError("仅草稿或已驳回的收款退款可提交")
        await Receipt.filter(tenant_id=tenant_id, id=receipt_id).update(review_status="SUBMITTED")
        receipt.review_status = "SUBMITTED"
        return self._payload(receipt)

    async def submit_receipt_refund_for_review(
        self,
        tenant_id: int,
        receipt_id: int,
        user_id: int,
        *,
        selected_approver_user_ids: list[int] | None = None,
        selected_approver_by_node: dict[str, list[int]] | None = None,
    ) -> dict[str, Any]:
        receipt = await self._get(tenant_id, receipt_id)
        self._assert_draft_voucher(receipt)
        if str(receipt.review_status or "").strip() != "SUBMITTED":
            raise BusinessLogicError("请先提交收款退款，再提交审核")
        await self._enter_review(
            tenant_id,
            receipt,
            user_id,
            selected_approver_user_ids=selected_approver_user_ids,
            selected_approver_by_node=selected_approver_by_node,
        )
        return self._payload(await self._get(tenant_id, receipt_id))

    async def submit_receipt_refund(
        self, tenant_id: int, receipt_id: int, user_id: int
    ) -> dict[str, Any]:
        """内部一次性：草稿直接进入审核。页面提交请走 commit_receipt_refund。"""
        receipt = await self._get(tenant_id, receipt_id)
        raw = str(receipt.review_status or "").strip()
        if raw in _APPROVED_REVIEW or raw in _PENDING_REVIEW:
            return self._payload(receipt)
        if str(receipt.status or "") != "Draft":
            raise BusinessLogicError("仅草稿收款退款可提交审核")
        if raw != "SUBMITTED":
            if raw not in _EDITABLE_REVIEW:
                raise BusinessLogicError("当前审核状态不可提交")
            await Receipt.filter(tenant_id=tenant_id, id=receipt_id).update(review_status="SUBMITTED")
            receipt.review_status = "SUBMITTED"
        await self._enter_review(tenant_id, receipt, user_id)
        return self._payload(await self._get(tenant_id, receipt_id))

    async def withdraw_receipt_refund(
        self, tenant_id: int, receipt_id: int, user_id: int
    ) -> dict[str, Any]:
        from apps.kuaicaiwu.services.finance_audit_workflow import _norm_review
        from core.services.approval.approval_instance_service import ApprovalInstanceService

        receipt = await self._get(tenant_id, receipt_id)
        raw = str(receipt.review_status or "").strip()
        if raw == "SUBMITTED":
            await Receipt.filter(tenant_id=tenant_id, id=receipt_id).update(review_status="草稿")
            receipt.review_status = "草稿"
            return self._payload(receipt)
        if _norm_review(raw) in _PENDING_REVIEW:
            cancelled = await ApprovalInstanceService.cancel_approval(
                tenant_id=tenant_id,
                entity_type="receipt_refund",
                entity_id=receipt_id,
                operator_id=user_id,
            )
            if cancelled is False:
                raise BusinessLogicError("撤回失败：无法取消审批流程，请重试")
            await Receipt.filter(tenant_id=tenant_id, id=receipt_id).update(review_status="SUBMITTED")
            receipt.review_status = "SUBMITTED"
            return self._payload(receipt)
        raise BusinessLogicError("仅已提交或待审核可撤回")

    async def approve_receipt_refund(
        self,
        tenant_id: int,
        receipt_id: int,
        user_id: int,
        rejection_reason: str | None = None,
    ) -> dict[str, Any]:
        from apps.kuaicaiwu.services.finance_audit_workflow import (
            _PENDING_REVIEW,
            _norm_review,
            assert_finance_pending_approval_flow,
        )
        from core.services.approval.uni_audit_service import UniAuditService

        receipt = await self._get(tenant_id, receipt_id)
        self._assert_draft_voucher(receipt)

        async def _write() -> dict[str, Any]:
            current = await self._get(tenant_id, receipt_id)
            if _norm_review(current.review_status) not in _PENDING_REVIEW:
                raise BusinessLogicError(
                    f"收款退款审核状态不是待审核，当前: {current.review_status!r}"
                )
            review_status = "驳回" if rejection_reason else "已审核"
            await Receipt.filter(tenant_id=tenant_id, id=receipt_id).update(
                review_status=review_status
            )
            current.review_status = review_status
            return self._payload(current)

        await assert_finance_pending_approval_flow(
            tenant_id=tenant_id,
            doc_id=receipt_id,
            node_key="receipt_refund",
            doc_label="收款退款",
            verb="驳回" if rejection_reason else "审核",
        )
        if rejection_reason:
            result = await UniAuditService.reject_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="receipt_refund",
                entity_id=receipt_id,
                approver_id=user_id,
                reason=rejection_reason,
                flow_reject=lambda _reason=None: _write(),
            )
        else:
            result = await UniAuditService.approve_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="receipt_refund",
                entity_id=receipt_id,
                approver_id=user_id,
                flow_approve=_write,
            )
        return result if result is not None else await _write()

    async def revoke_receipt_refund(
        self, tenant_id: int, receipt_id: int, user_id: int
    ) -> dict[str, Any]:
        receipt = await self._get(tenant_id, receipt_id)
        if str(receipt.status or "") == "Confirmed":
            raise BusinessLogicError("已确认退款，请先撤回确认")
        raw = str(receipt.review_status or "").strip()
        if raw not in _APPROVED_REVIEW:
            raise BusinessLogicError("收款退款未审核通过，无法反审核")
        await Receipt.filter(tenant_id=tenant_id, id=receipt_id).update(review_status="草稿")
        receipt.review_status = "草稿"
        return self._payload(receipt)

    async def _enter_review(
        self,
        tenant_id: int,
        receipt: Receipt,
        user_id: int,
        *,
        selected_approver_user_ids: list[int] | None = None,
        selected_approver_by_node: dict[str, list[int]] | None = None,
    ) -> None:
        from core.services.approval.approval_instance_service import ApprovalInstanceService
        from core.services.approval.audit_flow_guard import approval_instance_finished_on_submit
        from infra.services.business_config_service import BusinessConfigService

        audit_required = await BusinessConfigService().check_audit_required(
            tenant_id, "receipt_refund"
        )
        if not audit_required:
            await Receipt.filter(tenant_id=tenant_id, id=receipt.id).update(review_status="已审核")
            return

        content = f"收款退款 {receipt.receipt_code}"
        if receipt.customer_name:
            content = f"{content}, 往来单位: {receipt.customer_name}"
        if receipt.total_amount is not None:
            content = f"{content}, 金额: {receipt.total_amount}"
        instance = await ApprovalInstanceService.start_approval_for_node(
            tenant_id=tenant_id,
            user_id=user_id,
            node_key="receipt_refund",
            entity_type="receipt_refund",
            entity_id=int(receipt.id),
            entity_uuid=str(receipt.uuid),
            title=f"收款退款审核: {receipt.receipt_code}",
            content=content,
            selected_approver_user_ids=selected_approver_user_ids,
            selected_approver_by_node=selected_approver_by_node,
        )
        if not instance:
            raise BusinessLogicError(
                "收款退款审核已开启但未找到可用的审批流程，请在配置中心检查 receipt_refund 审批流程是否已激活"
            )
        await Receipt.filter(tenant_id=tenant_id, id=receipt.id).update(review_status="待审核")
        if approval_instance_finished_on_submit(instance):
            await Receipt.filter(tenant_id=tenant_id, id=receipt.id).update(review_status="已审核")

    @staticmethod
    def _payload(receipt: Receipt) -> dict[str, Any]:
        return {
            "id": int(receipt.id),
            "receipt_code": receipt.receipt_code,
            "status": receipt.status,
            "review_status": receipt.review_status,
        }
