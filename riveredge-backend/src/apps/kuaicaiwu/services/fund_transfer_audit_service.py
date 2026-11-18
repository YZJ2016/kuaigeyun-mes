"""资金调拨审核。业务状态仍是 Draft/Confirmed/Cancelled。确认调拨是过账，不在这里改名。"""

from __future__ import annotations

from typing import Any

from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

from apps.kuaicaiwu.models.fund_transfer import FundTransfer

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


def assert_fund_transfer_review_editable(row: FundTransfer) -> None:
    raw = str(getattr(row, "review_status", "") or "").strip()
    if raw not in _EDITABLE_REVIEW:
        raise BusinessLogicError("仅草稿或已驳回的资金调拨单可修改或删除")


def assert_fund_transfer_review_approved(row: FundTransfer) -> None:
    raw = str(getattr(row, "review_status", "") or "").strip()
    if raw not in _APPROVED_REVIEW:
        raise BusinessLogicError("资金调拨单须审核通过后才能确认")


class FundTransferAuditService:
    async def _get(self, tenant_id: int, transfer_id: int) -> FundTransfer:
        row = await FundTransfer.get_or_none(
            tenant_id=tenant_id, id=transfer_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError(f"资金调拨单不存在: {transfer_id}")
        return row

    def _assert_draft_voucher(self, row: FundTransfer) -> None:
        if str(row.status or "") != "Draft":
            raise BusinessLogicError("仅草稿资金调拨单可提交或审核")

    async def commit_transfer(
        self, tenant_id: int, transfer_id: int, user_id: int
    ) -> dict[str, Any]:
        row = await self._get(tenant_id, transfer_id)
        self._assert_draft_voucher(row)
        raw = str(row.review_status or "").strip()
        if raw == "SUBMITTED":
            return self._payload(row)
        if raw not in _EDITABLE_REVIEW:
            raise BusinessLogicError("仅草稿或已驳回的资金调拨单可提交")
        await FundTransfer.filter(tenant_id=tenant_id, id=transfer_id).update(
            review_status="SUBMITTED"
        )
        row.review_status = "SUBMITTED"
        return self._payload(row)

    async def submit_transfer_for_review(
        self, tenant_id: int, transfer_id: int, user_id: int
    ) -> dict[str, Any]:
        row = await self._get(tenant_id, transfer_id)
        self._assert_draft_voucher(row)
        if str(row.review_status or "").strip() != "SUBMITTED":
            raise BusinessLogicError("请先提交资金调拨单，再提交审核")
        await self._enter_review(tenant_id, row, user_id)
        return self._payload(await self._get(tenant_id, transfer_id))

    async def submit_transfer(
        self, tenant_id: int, transfer_id: int, user_id: int
    ) -> dict[str, Any]:
        """内部一次性：草稿直接进入审核。页面提交请走 commit_transfer。"""
        row = await self._get(tenant_id, transfer_id)
        raw = str(row.review_status or "").strip()
        if raw in _APPROVED_REVIEW or raw in _PENDING_REVIEW:
            return self._payload(row)
        if str(row.status or "") != "Draft":
            raise BusinessLogicError("仅草稿资金调拨单可提交审核")
        if raw != "SUBMITTED":
            if raw not in _EDITABLE_REVIEW:
                raise BusinessLogicError("当前审核状态不可提交")
            await FundTransfer.filter(tenant_id=tenant_id, id=transfer_id).update(
                review_status="SUBMITTED"
            )
            row.review_status = "SUBMITTED"
        await self._enter_review(tenant_id, row, user_id)
        return self._payload(await self._get(tenant_id, transfer_id))

    async def withdraw_transfer(
        self, tenant_id: int, transfer_id: int, user_id: int
    ) -> dict[str, Any]:
        from apps.kuaicaiwu.services.finance_audit_workflow import _norm_review
        from core.services.approval.approval_instance_service import ApprovalInstanceService

        row = await self._get(tenant_id, transfer_id)
        raw = str(row.review_status or "").strip()
        if raw == "SUBMITTED":
            await FundTransfer.filter(tenant_id=tenant_id, id=transfer_id).update(
                review_status="草稿"
            )
            row.review_status = "草稿"
            return self._payload(row)
        if _norm_review(raw) in _PENDING_REVIEW:
            cancelled = await ApprovalInstanceService.cancel_approval(
                tenant_id=tenant_id,
                entity_type="fund_transfer",
                entity_id=transfer_id,
                operator_id=user_id,
            )
            if cancelled is False:
                raise BusinessLogicError("撤回失败：无法取消审批流程，请重试")
            await FundTransfer.filter(tenant_id=tenant_id, id=transfer_id).update(
                review_status="SUBMITTED"
            )
            row.review_status = "SUBMITTED"
            return self._payload(row)
        raise BusinessLogicError("仅已提交或待审核可撤回")

    async def approve_transfer(
        self,
        tenant_id: int,
        transfer_id: int,
        user_id: int,
        rejection_reason: str | None = None,
        *,
        is_auto_approve: bool = False,
    ) -> dict[str, Any]:
        from apps.kuaicaiwu.services.finance_audit_workflow import (
            _PENDING_REVIEW,
            _norm_review,
            assert_finance_pending_approval_flow,
        )
        from core.services.approval.uni_audit_service import UniAuditService

        row = await self._get(tenant_id, transfer_id)
        self._assert_draft_voucher(row)

        async def _write() -> dict[str, Any]:
            current = await self._get(tenant_id, transfer_id)
            if _norm_review(current.review_status) not in _PENDING_REVIEW:
                raise BusinessLogicError(
                    f"资金调拨单审核状态不是待审核，当前: {current.review_status!r}"
                )
            review_status = "驳回" if rejection_reason else "已审核"
            await FundTransfer.filter(tenant_id=tenant_id, id=transfer_id).update(
                review_status=review_status
            )
            current.review_status = review_status
            return self._payload(current)

        if is_auto_approve:
            return await _write()

        await assert_finance_pending_approval_flow(
            tenant_id=tenant_id,
            doc_id=transfer_id,
            node_key="fund_transfer",
            doc_label="资金调拨单",
            verb="驳回" if rejection_reason else "审核",
        )
        if rejection_reason:
            result = await UniAuditService.reject_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="fund_transfer",
                entity_id=transfer_id,
                approver_id=user_id,
                reason=rejection_reason,
                flow_reject=lambda _reason=None: _write(),
            )
        else:
            result = await UniAuditService.approve_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="fund_transfer",
                entity_id=transfer_id,
                approver_id=user_id,
                flow_approve=_write,
            )
        return result if result is not None else await _write()

    async def revoke_transfer(
        self, tenant_id: int, transfer_id: int, user_id: int
    ) -> dict[str, Any]:
        row = await self._get(tenant_id, transfer_id)
        if str(row.status or "") == "Confirmed":
            raise BusinessLogicError("已确认调拨，请先撤回确认")
        raw = str(row.review_status or "").strip()
        if raw not in _APPROVED_REVIEW:
            raise BusinessLogicError("资金调拨单未审核通过，无法反审核")
        await FundTransfer.filter(tenant_id=tenant_id, id=transfer_id).update(
            review_status="草稿"
        )
        row.review_status = "草稿"
        return self._payload(row)

    async def _enter_review(
        self, tenant_id: int, row: FundTransfer, user_id: int
    ) -> None:
        from core.services.approval.approval_instance_service import ApprovalInstanceService
        from core.services.approval.audit_flow_guard import approval_instance_finished_on_submit
        from infra.services.business_config_service import BusinessConfigService

        audit_required = await BusinessConfigService().check_audit_required(
            tenant_id, "fund_transfer"
        )
        if not audit_required:
            await FundTransfer.filter(tenant_id=tenant_id, id=row.id).update(
                review_status="已审核"
            )
            return

        content = f"资金调拨单 {row.transfer_code}"
        if row.amount is not None:
            content = f"{content}, 金额: {row.amount}"
        instance = await ApprovalInstanceService.start_approval_for_node(
            tenant_id=tenant_id,
            user_id=user_id,
            node_key="fund_transfer",
            entity_type="fund_transfer",
            entity_id=int(row.id),
            entity_uuid=str(row.uuid),
            title=f"资金调拨单审核: {row.transfer_code}",
            content=content,
        )
        if not instance:
            raise BusinessLogicError(
                "资金调拨单审核已开启但未找到可用的审批流程，"
                "请在配置中心检查 fund_transfer 审批流程是否已激活"
            )
        await FundTransfer.filter(tenant_id=tenant_id, id=row.id).update(
            review_status="待审核"
        )
        if approval_instance_finished_on_submit(instance):
            await FundTransfer.filter(tenant_id=tenant_id, id=row.id).update(
                review_status="已审核"
            )

    @staticmethod
    def _payload(row: FundTransfer) -> dict[str, Any]:
        return {
            "id": int(row.id),
            "transfer_code": row.transfer_code,
            "status": row.status,
            "review_status": row.review_status,
        }
