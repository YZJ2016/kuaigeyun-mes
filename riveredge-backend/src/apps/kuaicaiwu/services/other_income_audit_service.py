"""其他费用收入审核。业务 status 仍是 Draft/Confirmed/Cancelled；确认过账不在这里改名。"""

from __future__ import annotations

from typing import Any

from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

from apps.kuaicaiwu.models.other_voucher import OtherIncome

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


def assert_other_income_review_editable(head: OtherIncome) -> None:
    if str(head.status or "").strip() not in {"Draft", "草稿"}:
        raise BusinessLogicError("仅草稿其他费用收入可修改或删除")
    raw = str(getattr(head, "review_status", "") or "").strip()
    if raw not in _EDITABLE_REVIEW:
        raise BusinessLogicError("仅草稿或已驳回的其他费用收入可修改或删除")


class OtherIncomeAuditService:
    async def _get(self, tenant_id: int, income_id: int) -> OtherIncome:
        head = await OtherIncome.get_or_none(
            tenant_id=tenant_id, id=income_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用收入单不存在: {income_id}")
        return head

    def _assert_draft_voucher(self, head: OtherIncome) -> None:
        if str(head.status or "").strip() not in {"Draft", "草稿"}:
            raise BusinessLogicError("仅草稿其他费用收入可提交或审核")

    async def commit_income(
        self, tenant_id: int, income_id: int, user_id: int
    ) -> dict[str, Any]:
        head = await self._get(tenant_id, income_id)
        self._assert_draft_voucher(head)
        raw = str(head.review_status or "").strip()
        if raw == "SUBMITTED":
            return self._payload(head)
        if raw not in _EDITABLE_REVIEW:
            raise BusinessLogicError("仅草稿或已驳回的其他费用收入可提交")
        await OtherIncome.filter(tenant_id=tenant_id, id=income_id).update(
            review_status="SUBMITTED"
        )
        head.review_status = "SUBMITTED"
        return self._payload(head)

    async def submit_income_for_review(
        self,
        tenant_id: int,
        income_id: int,
        user_id: int,
        *,
        selected_approver_user_ids: list[int] | None = None,
        selected_approver_by_node: dict[str, list[int]] | None = None,
    ) -> dict[str, Any]:
        head = await self._get(tenant_id, income_id)
        self._assert_draft_voucher(head)
        if str(head.review_status or "").strip() != "SUBMITTED":
            raise BusinessLogicError("请先提交其他费用收入，再提交审核")
        await self._enter_review(
            tenant_id,
            head,
            user_id,
            selected_approver_user_ids=selected_approver_user_ids,
            selected_approver_by_node=selected_approver_by_node,
        )
        return self._payload(await self._get(tenant_id, income_id))

    async def submit_income(
        self,
        tenant_id: int,
        income_id: int,
        user_id: int,
        *,
        selected_approver_user_ids: list[int] | None = None,
        selected_approver_by_node: dict[str, list[int]] | None = None,
    ) -> dict[str, Any]:
        """内部一次性：草稿直接进入审核。页面提交请走 commit_income。"""
        head = await self._get(tenant_id, income_id)
        raw = str(head.review_status or "").strip()
        if raw in _APPROVED_REVIEW or raw in _PENDING_REVIEW:
            return self._payload(head)
        self._assert_draft_voucher(head)
        if raw != "SUBMITTED":
            if raw not in _EDITABLE_REVIEW:
                raise BusinessLogicError("当前审核状态不可提交")
            await OtherIncome.filter(tenant_id=tenant_id, id=income_id).update(
                review_status="SUBMITTED"
            )
            head.review_status = "SUBMITTED"
        await self._enter_review(
            tenant_id,
            head,
            user_id,
            selected_approver_user_ids=selected_approver_user_ids,
            selected_approver_by_node=selected_approver_by_node,
        )
        return self._payload(await self._get(tenant_id, income_id))

    async def withdraw_income(
        self, tenant_id: int, income_id: int, user_id: int
    ) -> dict[str, Any]:
        from apps.kuaicaiwu.services.finance_audit_workflow import _norm_review
        from core.services.approval.approval_instance_service import ApprovalInstanceService

        head = await self._get(tenant_id, income_id)
        self._assert_draft_voucher(head)
        raw = str(head.review_status or "").strip()
        if raw == "SUBMITTED":
            await OtherIncome.filter(tenant_id=tenant_id, id=income_id).update(
                review_status="草稿"
            )
            head.review_status = "草稿"
            return self._payload(head)
        if _norm_review(raw) in _PENDING_REVIEW:
            cancelled = await ApprovalInstanceService.cancel_approval(
                tenant_id=tenant_id,
                entity_type="other_income",
                entity_id=income_id,
                operator_id=user_id,
            )
            if cancelled is False:
                raise BusinessLogicError("撤回失败：无法取消审批流程，请重试")
            await OtherIncome.filter(tenant_id=tenant_id, id=income_id).update(
                review_status="SUBMITTED"
            )
            head.review_status = "SUBMITTED"
            return self._payload(head)
        raise BusinessLogicError("仅已提交或待审核可撤回")

    async def approve_income(
        self,
        tenant_id: int,
        income_id: int,
        user_id: int,
        *,
        approved: bool = True,
        review_remarks: str | None = None,
        is_auto_approve: bool = False,
    ) -> dict[str, Any]:
        from apps.kuaicaiwu.services.finance_audit_workflow import (
            _PENDING_REVIEW as _FLOW_PENDING,
            _norm_review,
            assert_finance_pending_approval_flow,
        )
        from apps.kuaicaiwu.services.other_income_service import OtherIncomeService
        from core.services.approval.uni_audit_service import UniAuditService

        head = await self._get(tenant_id, income_id)
        self._assert_draft_voucher(head)

        async def _write() -> dict[str, Any]:
            current = await self._get(tenant_id, income_id)
            if _norm_review(current.review_status) not in _FLOW_PENDING:
                raise BusinessLogicError(
                    f"其他费用收入审核状态不是待审核，当前: {current.review_status!r}"
                )
            svc = OtherIncomeService()
            user = await svc.get_user_info(user_id)
            from core.utils.timezone_utils import resolve_business_datetime

            patch: dict[str, Any] = {
                "reviewer_id": user_id,
                "reviewer_name": user["name"],
                "review_time": resolve_business_datetime(),
                "review_remarks": review_remarks,
                "updated_by": user_id,
                "updated_by_name": user["name"],
            }
            if approved:
                patch["review_status"] = "已审核"
                patch["status"] = "Draft"
            else:
                patch["review_status"] = "已驳回"
                patch["status"] = "Draft"
            await OtherIncome.filter(tenant_id=tenant_id, id=income_id).update(**patch)
            if approved:
                current = await self._get(tenant_id, income_id)
                await svc._on_income_approved(tenant_id, current, user_id)
            return self._payload(await self._get(tenant_id, income_id))

        if is_auto_approve:
            return await _write()

        await assert_finance_pending_approval_flow(
            tenant_id=tenant_id,
            doc_id=income_id,
            node_key="other_income",
            doc_label="其他费用收入",
            verb="驳回" if not approved else "审核",
        )
        if not approved:
            result = await UniAuditService.reject_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="other_income",
                entity_id=income_id,
                approver_id=user_id,
                reason=review_remarks or "审批驳回",
                flow_reject=lambda _reason=None: _write(),
            )
        else:
            result = await UniAuditService.approve_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="other_income",
                entity_id=income_id,
                approver_id=user_id,
                flow_approve=_write,
            )
        if result is not None:
            return result
        return self._payload(await self._get(tenant_id, income_id))

    async def revoke_income(
        self, tenant_id: int, income_id: int, user_id: int
    ) -> dict[str, Any]:
        from apps.kuaicaiwu.services.misc_voucher_finance_bridge import MiscVoucherFinanceBridge
        from apps.kuaicaiwu.services.other_income_service import OtherIncomeService

        head = await self._get(tenant_id, income_id)
        if str(head.status or "").strip() == "Confirmed":
            raise BusinessLogicError("已确认过账的其他费用收入须先反确认，再反审核")
        raw = str(head.review_status or "").strip()
        if raw not in _APPROVED_REVIEW:
            raise BusinessLogicError("其他费用收入未审核通过，无法反审核")
        bridge = MiscVoucherFinanceBridge()
        await bridge.assert_income_receivable_revokable(tenant_id, income_id)
        await bridge.void_receivable_for_income_revoke(tenant_id, income_id, user_id)
        user = await OtherIncomeService().get_user_info(user_id)
        await OtherIncome.filter(tenant_id=tenant_id, id=income_id).update(
            review_status="草稿",
            status="Draft",
            reviewer_id=None,
            reviewer_name=None,
            review_time=None,
            review_remarks=None,
            updated_by=user_id,
            updated_by_name=user["name"],
        )
        head.review_status = "草稿"
        head.status = "Draft"
        return self._payload(head)

    async def _enter_review(
        self,
        tenant_id: int,
        head: OtherIncome,
        user_id: int,
        *,
        selected_approver_user_ids: list[int] | None = None,
        selected_approver_by_node: dict[str, list[int]] | None = None,
    ) -> None:
        from apps.kuaicaiwu.services.misc_voucher_finance_bridge import MiscVoucherFinanceBridge
        from apps.kuaicaiwu.services.other_income_service import OtherIncomeService
        from core.services.approval.audit_flow_guard import (
            approval_instance_finished_on_submit,
            start_document_approval_or_raise,
        )
        from infra.services.business_config_service import BusinessConfigService

        MiscVoucherFinanceBridge().assert_income_ready_for_receivable_on_approve(head)
        audit_required = await BusinessConfigService().check_audit_required(
            tenant_id, "other_income"
        )
        svc = OtherIncomeService()
        user = await svc.get_user_info(user_id)
        if not audit_required:
            await OtherIncome.filter(tenant_id=tenant_id, id=head.id).update(
                review_status="已审核",
                status="Draft",
                updated_by=user_id,
                updated_by_name=user["name"],
            )
            refreshed = await self._get(tenant_id, int(head.id))
            await svc._on_income_approved(tenant_id, refreshed, user_id)
            return

        instance = await start_document_approval_or_raise(
            tenant_id=tenant_id,
            user_id=user_id,
            node_key="other_income",
            entity_type="other_income",
            entity_id=int(head.id),
            entity_uuid=str(head.uuid),
            title=f"其他费用收入审批: {head.income_code}",
            content=f"金额: {head.total_amount}",
            doc_label="其他费用收入",
            selected_approver_user_ids=selected_approver_user_ids,
            selected_approver_by_node=selected_approver_by_node,
        )
        await OtherIncome.filter(tenant_id=tenant_id, id=head.id).update(
            review_status="待审核",
            status="Draft",
            updated_by=user_id,
            updated_by_name=user["name"],
        )
        if approval_instance_finished_on_submit(instance):
            await self.approve_income(tenant_id, int(head.id), user_id, approved=True)

    @staticmethod
    def _payload(head: OtherIncome) -> dict[str, Any]:
        return {
            "id": int(head.id),
            "income_code": head.income_code,
            "status": head.status,
            "review_status": head.review_status,
        }
