"""应收票据审核。业务 status 仍是 held/endorsed/…；背书/贴现/托收须审核通过。"""

from __future__ import annotations

from typing import Any

from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

from apps.kuaicaiwu.models.finance_note import FinanceNote

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
_RECEIVABLE_TERMINAL = frozenset({"endorsed", "discounted", "collected", "dishonored"})


def assert_notes_receivable_review_editable(note: FinanceNote) -> None:
    if str(note.direction or "") != "receivable":
        raise BusinessLogicError("仅应收票据走保存提交审核")
    if str(note.status or "") != "held":
        raise BusinessLogicError("仅持有中的应收票据可修改或删除")
    raw = str(getattr(note, "review_status", "") or "").strip()
    if raw not in _EDITABLE_REVIEW:
        raise BusinessLogicError("仅草稿或已驳回的应收票据可修改或删除")


def assert_notes_receivable_action_allowed(note: FinanceNote) -> None:
    if str(note.direction or "") != "receivable":
        return
    raw = str(getattr(note, "review_status", "") or "").strip()
    if raw not in _APPROVED_REVIEW:
        raise BusinessLogicError("应收票据须审核通过后才能背书、贴现或托收")


class NotesReceivableAuditService:
    async def _get(self, tenant_id: int, note_id: int) -> FinanceNote:
        note = await FinanceNote.get_or_none(
            tenant_id=tenant_id, id=note_id, deleted_at__isnull=True
        )
        if not note:
            raise NotFoundError(f"应收票据不存在: {note_id}")
        if str(note.direction or "") != "receivable":
            raise NotFoundError(f"应收票据不存在: {note_id}")
        return note

    def _assert_held(self, note: FinanceNote) -> None:
        if str(note.status or "") != "held":
            raise BusinessLogicError("仅持有中的应收票据可提交或审核")

    async def commit_note(self, tenant_id: int, note_id: int, user_id: int) -> dict[str, Any]:
        note = await self._get(tenant_id, note_id)
        self._assert_held(note)
        raw = str(note.review_status or "").strip()
        if raw == "SUBMITTED":
            return self._payload(note)
        if raw not in _EDITABLE_REVIEW:
            raise BusinessLogicError("仅草稿或已驳回的应收票据可提交")
        await FinanceNote.filter(tenant_id=tenant_id, id=note_id).update(
            review_status="SUBMITTED"
        )
        note.review_status = "SUBMITTED"
        return self._payload(note)

    async def submit_note_for_review(
        self, tenant_id: int, note_id: int, user_id: int
    ) -> dict[str, Any]:
        note = await self._get(tenant_id, note_id)
        self._assert_held(note)
        if str(note.review_status or "").strip() != "SUBMITTED":
            raise BusinessLogicError("请先提交应收票据，再提交审核")
        await self._enter_review(tenant_id, note, user_id)
        return self._payload(await self._get(tenant_id, note_id))

    async def submit_note(self, tenant_id: int, note_id: int, user_id: int) -> dict[str, Any]:
        """内部一次性：草稿直接进入审核。页面提交请走 commit_note。"""
        note = await self._get(tenant_id, note_id)
        raw = str(note.review_status or "").strip()
        if raw in _APPROVED_REVIEW or raw in _PENDING_REVIEW:
            return self._payload(note)
        self._assert_held(note)
        if raw != "SUBMITTED":
            if raw not in _EDITABLE_REVIEW:
                raise BusinessLogicError("当前审核状态不可提交")
            await FinanceNote.filter(tenant_id=tenant_id, id=note_id).update(
                review_status="SUBMITTED"
            )
            note.review_status = "SUBMITTED"
        await self._enter_review(tenant_id, note, user_id)
        return self._payload(await self._get(tenant_id, note_id))

    async def withdraw_note(self, tenant_id: int, note_id: int, user_id: int) -> dict[str, Any]:
        from apps.kuaicaiwu.services.finance_audit_workflow import _norm_review
        from core.services.approval.approval_instance_service import ApprovalInstanceService

        note = await self._get(tenant_id, note_id)
        self._assert_held(note)
        raw = str(note.review_status or "").strip()
        if raw == "SUBMITTED":
            await FinanceNote.filter(tenant_id=tenant_id, id=note_id).update(
                review_status="草稿"
            )
            note.review_status = "草稿"
            return self._payload(note)
        if _norm_review(raw) in _PENDING_REVIEW:
            cancelled = await ApprovalInstanceService.cancel_approval(
                tenant_id=tenant_id,
                entity_type="notes_receivable",
                entity_id=note_id,
                operator_id=user_id,
            )
            if cancelled is False:
                raise BusinessLogicError("撤回失败：无法取消审批流程，请重试")
            await FinanceNote.filter(tenant_id=tenant_id, id=note_id).update(
                review_status="SUBMITTED"
            )
            note.review_status = "SUBMITTED"
            return self._payload(note)
        raise BusinessLogicError("仅已提交或待审核可撤回")

    async def approve_note(
        self,
        tenant_id: int,
        note_id: int,
        user_id: int,
        rejection_reason: str | None = None,
    ) -> dict[str, Any]:
        from apps.kuaicaiwu.services.finance_audit_workflow import (
            _PENDING_REVIEW,
            _norm_review,
            assert_finance_pending_approval_flow,
        )
        from core.services.approval.uni_audit_service import UniAuditService

        note = await self._get(tenant_id, note_id)
        self._assert_held(note)

        async def _write() -> dict[str, Any]:
            current = await self._get(tenant_id, note_id)
            if _norm_review(current.review_status) not in _PENDING_REVIEW:
                raise BusinessLogicError(
                    f"应收票据审核状态不是待审核，当前: {current.review_status!r}"
                )
            review_status = "已驳回" if rejection_reason else "已审核"
            await FinanceNote.filter(tenant_id=tenant_id, id=note_id).update(
                review_status=review_status
            )
            current.review_status = review_status
            return self._payload(current)

        await assert_finance_pending_approval_flow(
            tenant_id=tenant_id,
            doc_id=note_id,
            node_key="notes_receivable",
            doc_label="应收票据",
            verb="驳回" if rejection_reason else "审核",
        )
        if rejection_reason:
            result = await UniAuditService.reject_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="notes_receivable",
                entity_id=note_id,
                approver_id=user_id,
                reason=rejection_reason,
                flow_reject=lambda _reason=None: _write(),
            )
        else:
            result = await UniAuditService.approve_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="notes_receivable",
                entity_id=note_id,
                approver_id=user_id,
                flow_approve=_write,
            )
        return result if result is not None else await _write()

    async def revoke_note(self, tenant_id: int, note_id: int, user_id: int) -> dict[str, Any]:
        note = await self._get(tenant_id, note_id)
        if str(note.status or "") in _RECEIVABLE_TERMINAL:
            raise BusinessLogicError("票据已背书、贴现或托收，不能反审核")
        if note.receipt_id:
            raise BusinessLogicError("已关联收款单的应收票据不能反审核，请先解除关联")
        raw = str(note.review_status or "").strip()
        if raw not in _APPROVED_REVIEW:
            raise BusinessLogicError("应收票据未审核通过，无法反审核")
        await FinanceNote.filter(tenant_id=tenant_id, id=note_id).update(
            review_status="草稿"
        )
        note.review_status = "草稿"
        return self._payload(note)

    async def _enter_review(self, tenant_id: int, note: FinanceNote, user_id: int) -> None:
        from core.services.approval.approval_instance_service import ApprovalInstanceService
        from core.services.approval.audit_flow_guard import approval_instance_finished_on_submit
        from infra.services.business_config_service import BusinessConfigService

        audit_required = await BusinessConfigService().check_audit_required(
            tenant_id, "notes_receivable"
        )
        if not audit_required:
            await FinanceNote.filter(tenant_id=tenant_id, id=note.id).update(
                review_status="已审核"
            )
            return

        content = f"应收票据 {note.note_code}"
        if note.customer_name:
            content = f"{content}, 客户: {note.customer_name}"
        if note.amount is not None:
            content = f"{content}, 金额: {note.amount}"
        instance = await ApprovalInstanceService.start_approval_for_node(
            tenant_id=tenant_id,
            user_id=user_id,
            node_key="notes_receivable",
            entity_type="notes_receivable",
            entity_id=int(note.id),
            entity_uuid=str(note.uuid),
            title=f"应收票据审核: {note.note_code}",
            content=content,
        )
        if not instance:
            raise BusinessLogicError(
                "应收票据审核已开启但未找到可用的审批流程，请在配置中心检查 notes_receivable 审批流程是否已激活"
            )
        await FinanceNote.filter(tenant_id=tenant_id, id=note.id).update(
            review_status="待审核"
        )
        if approval_instance_finished_on_submit(instance):
            await FinanceNote.filter(tenant_id=tenant_id, id=note.id).update(
                review_status="已审核"
            )

    @staticmethod
    def _payload(note: FinanceNote) -> dict[str, Any]:
        return {
            "id": int(note.id),
            "note_code": note.note_code,
            "status": note.status,
            "review_status": note.review_status,
        }
