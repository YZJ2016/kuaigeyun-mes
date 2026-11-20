"""质量体系第 3 期：纠正预防，接通不符合报告、投诉、评审决议、8D 单号。"""

from __future__ import annotations

from typing import Any, Optional

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.common.base_service import AppBaseService
from apps.kuaizhizao.models.qms_corrective_action import QmsCorrectiveAction
from apps.kuaizhizao.models.qms_management_review import QmsManagementReview
from apps.kuaizhizao.models.qms_management_review_resolution import QmsManagementReviewResolution
from apps.kuaizhizao.models.qms_nonconformity_report import QmsNonconformityReport
from apps.kuaizhizao.models.quality_8d_report import Quality8DReport
from apps.kuaizhizao.models.quality_complaint import QualityComplaint
from apps.kuaizhizao.schemas.quality_qms import (
    QmsCorrectiveActionCreate,
    QmsCorrectiveActionFromSource,
    QmsCorrectiveActionListResponse,
    QmsCorrectiveActionResponse,
    QmsCorrectiveActionUpdate,
    QmsManagementReviewResolutionCreate,
    QmsManagementReviewResolutionListResponse,
    QmsManagementReviewResolutionResponse,
    QmsManagementReviewResolutionUpdate,
)
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

CA_SOURCE_TYPES = {
    "nonconformity_report",
    "quality_complaint",
    "management_review_resolution",
}
CA_STATUSES = {"registered", "in_progress", "pending_verify", "closed"}
OPEN_CA_STATUSES = {"registered", "in_progress", "pending_verify"}


class QmsCorrectiveActionService(AppBaseService[QmsCorrectiveAction]):
    code_field = "action_code"
    rule_code = "QMS_CORRECTIVE_ACTION_CODE"
    code_prefix = "JZYF"

    def __init__(self) -> None:
        super().__init__(QmsCorrectiveAction)
        self.model = QmsCorrectiveAction

    async def _ensure_code(self, tenant_id: int, code: Optional[str]) -> str:
        raw = (code or "").strip()
        if raw:
            return raw
        return await self.generate_code(tenant_id, self.rule_code, prefix=self.code_prefix)

    def _response(self, row: QmsCorrectiveAction) -> QmsCorrectiveActionResponse:
        return QmsCorrectiveActionResponse.model_validate(row)

    async def _assert_eight_d(self, tenant_id: int, need: bool, eight_d_code: Optional[str]) -> Optional[str]:
        code = (eight_d_code or "").strip() or None
        if need:
            if not code:
                raise BusinessLogicError("需要 8D 时须填写已存在的 8D 单号")
            exists = await Quality8DReport.filter(
                tenant_id=tenant_id, report_code=code, deleted_at__isnull=True
            ).exists()
            if not exists:
                raise BusinessLogicError(f"8D 单号不存在：{code}")
            return code
        return None

    async def _resolve_source(
        self,
        tenant_id: int,
        source_type: str,
        source_id: Optional[int],
        *,
        problem_summary: Optional[str] = None,
    ) -> tuple[int, str, str]:
        """返回 (source_id, source_code, problem_summary)。"""
        if source_type == "nonconformity_report":
            if source_id is None:
                raise BusinessLogicError("请指定不符合报告")
            row = await QmsNonconformityReport.filter(
                tenant_id=tenant_id, id=source_id, deleted_at__isnull=True
            ).first()
            if row is None:
                raise NotFoundError("不符合报告不存在")
            summary = (problem_summary or "").strip() or (row.fact or "").strip()[:500]
            if not summary:
                raise BusinessLogicError("问题摘要不能为空")
            return row.id, row.report_code, summary

        if source_type == "quality_complaint":
            if source_id is None:
                raise BusinessLogicError("请指定质量投诉")
            row = await QualityComplaint.filter(
                tenant_id=tenant_id, id=source_id, deleted_at__isnull=True
            ).first()
            if row is None:
                raise NotFoundError("质量投诉不存在")
            summary = (
                (problem_summary or "").strip()
                or (row.title or "").strip()
                or (row.description or "").strip()[:500]
            )
            if not summary:
                raise BusinessLogicError("问题摘要不能为空")
            return row.id, row.code, summary

        if source_type == "management_review_resolution":
            if source_id is None:
                raise BusinessLogicError("请指定管理评审决议")
            row = await QmsManagementReviewResolution.filter(
                tenant_id=tenant_id, id=source_id, deleted_at__isnull=True
            ).first()
            if row is None:
                raise NotFoundError("管理评审决议不存在")
            review = await QmsManagementReview.filter(
                tenant_id=tenant_id, id=row.review_id, deleted_at__isnull=True
            ).first()
            if review is None:
                raise NotFoundError("管理评审不存在")
            summary = (problem_summary or "").strip() or (row.content or "").strip()[:500]
            if not summary:
                raise BusinessLogicError("问题摘要不能为空")
            source_code = f"{review.review_code}-R{row.id}"
            return row.id, source_code, summary

        raise BusinessLogicError("来源须为不符合报告、质量投诉或管理评审决议")

    async def _link_source_after_create(
        self,
        tenant_id: int,
        row: QmsCorrectiveAction,
        *,
        actor: Any,
    ) -> None:
        if row.source_type == "nonconformity_report" and row.source_id:
            nc = await QmsNonconformityReport.filter(
                tenant_id=tenant_id, id=row.source_id, deleted_at__isnull=True
            ).first()
            if nc is None:
                return
            nc.capa_code = row.action_code
            if nc.status == "open":
                nc.status = "rectifying"
            apply_update_audit(nc, actor)
            await nc.save()
        elif row.source_type == "management_review_resolution" and row.source_id:
            res = await QmsManagementReviewResolution.filter(
                tenant_id=tenant_id, id=row.source_id, deleted_at__isnull=True
            ).first()
            if res is None:
                return
            res.convert_to_capa = True
            res.capa_code = row.action_code
            apply_update_audit(res, actor)
            await res.save()

    def _guard_close(self, status: Optional[str], verification_conclusion: Optional[str]) -> None:
        if status != "closed":
            return
        if not (verification_conclusion or "").strip():
            raise BusinessLogicError("关闭纠正预防前须填写验证结论")

    async def create_action(
        self,
        tenant_id: int,
        payload: QmsCorrectiveActionCreate,
        *,
        actor: Any,
    ) -> QmsCorrectiveActionResponse:
        source_type = (payload.source_type or "").strip()
        if source_type not in CA_SOURCE_TYPES:
            raise BusinessLogicError("来源须为不符合报告、质量投诉或管理评审决议")
        status = (payload.status or "registered").strip()
        if status not in CA_STATUSES:
            raise BusinessLogicError("状态不合法")
        source_id, source_code, summary = await self._resolve_source(
            tenant_id,
            source_type,
            payload.source_id,
            problem_summary=payload.problem_summary,
        )
        open_exists = await QmsCorrectiveAction.filter(
            tenant_id=tenant_id,
            source_type=source_type,
            source_id=source_id,
            deleted_at__isnull=True,
            status__in=list(OPEN_CA_STATUSES),
        ).exists()
        if open_exists:
            raise BusinessLogicError("该来源已有未关闭的纠正预防")
        eight_d = await self._assert_eight_d(tenant_id, bool(payload.need_eight_d), payload.eight_d_code)
        self._guard_close(status, payload.verification_conclusion)
        data = payload.model_dump(exclude_unset=False)
        data["action_code"] = await self._ensure_code(tenant_id, data.get("action_code"))
        data["source_type"] = source_type
        data["source_id"] = source_id
        data["source_code"] = source_code
        data["problem_summary"] = summary
        data["status"] = status
        data["need_eight_d"] = bool(payload.need_eight_d)
        data["eight_d_code"] = eight_d
        for key in (
            "cause",
            "correction",
            "prevention",
            "responsible_person",
            "verifier_name",
            "verification_conclusion",
            "remarks",
        ):
            if isinstance(data.get(key), str):
                data[key] = data[key].strip() or None
        clash = await QmsCorrectiveAction.filter(
            tenant_id=tenant_id, action_code=data["action_code"], deleted_at__isnull=True
        ).exists()
        if clash:
            raise BusinessLogicError("纠正预防编号已存在")
        data["tenant_id"] = tenant_id
        apply_create_audit(data, actor)
        row = await QmsCorrectiveAction.create(**data)
        await self._link_source_after_create(tenant_id, row, actor=actor)
        return self._response(row)

    async def create_from_source(
        self,
        tenant_id: int,
        payload: QmsCorrectiveActionFromSource,
        *,
        actor: Any,
    ) -> QmsCorrectiveActionResponse:
        source_type = (payload.source_type or "").strip()
        if source_type == "management_review_resolution" and payload.review_id is not None:
            review = await QmsManagementReview.filter(
                tenant_id=tenant_id, id=payload.review_id, deleted_at__isnull=True
            ).first()
            if review is None:
                raise NotFoundError("管理评审不存在")
            content = (payload.problem_summary or "").strip()
            if not content:
                raise BusinessLogicError("请填写决议内容或问题摘要")
            res_data = {
                "tenant_id": tenant_id,
                "review_id": review.id,
                "content": content,
                "responsible_person": (payload.responsible_person or "").strip() or None,
                "due_on": payload.due_on,
                "convert_to_capa": True,
                "status": "open",
                "sort_order": await QmsManagementReviewResolution.filter(
                    tenant_id=tenant_id, review_id=review.id, deleted_at__isnull=True
                ).count(),
            }
            apply_create_audit(res_data, actor)
            resolution = await QmsManagementReviewResolution.create(**res_data)
            create_payload = QmsCorrectiveActionCreate(
                source_type="management_review_resolution",
                source_id=resolution.id,
                problem_summary=content,
                cause=payload.cause,
                correction=payload.correction,
                prevention=payload.prevention,
                responsible_person=payload.responsible_person,
                due_on=payload.due_on,
                need_eight_d=payload.need_eight_d or False,
                eight_d_code=payload.eight_d_code,
                status="registered",
                remarks=payload.remarks,
            )
            return await self.create_action(tenant_id, create_payload, actor=actor)

        create_payload = QmsCorrectiveActionCreate(
            source_type=source_type,
            source_id=payload.source_id,
            problem_summary=payload.problem_summary,
            cause=payload.cause,
            correction=payload.correction,
            prevention=payload.prevention,
            responsible_person=payload.responsible_person,
            due_on=payload.due_on,
            need_eight_d=payload.need_eight_d or False,
            eight_d_code=payload.eight_d_code,
            status="registered",
            remarks=payload.remarks,
        )
        return await self.create_action(tenant_id, create_payload, actor=actor)

    async def list_actions(
        self,
        tenant_id: int,
        *,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> QmsCorrectiveActionListResponse:
        query = QmsCorrectiveAction.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if keyword:
            query = query.filter(problem_summary__icontains=keyword)
        if status:
            query = query.filter(status=status)
        if source_type:
            query = query.filter(source_type=source_type)
        if source_id is not None:
            query = query.filter(source_id=source_id)
        total = await query.count()
        rows = await query.order_by("-updated_at", "-id").offset(skip).limit(limit)
        return QmsCorrectiveActionListResponse(
            items=[self._response(r) for r in rows],
            total=total,
        )

    async def get_action(self, tenant_id: int, action_id: int) -> QmsCorrectiveActionResponse:
        row = await QmsCorrectiveAction.filter(
            tenant_id=tenant_id, id=action_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("纠正预防不存在")
        return self._response(row)

    async def update_action(
        self,
        tenant_id: int,
        action_id: int,
        payload: QmsCorrectiveActionUpdate,
        *,
        actor: Any,
    ) -> QmsCorrectiveActionResponse:
        row = await QmsCorrectiveAction.filter(
            tenant_id=tenant_id, id=action_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("纠正预防不存在")
        data = payload.model_dump(exclude_unset=True)
        if "status" in data:
            status = (data.get("status") or "").strip()
            if status not in CA_STATUSES:
                raise BusinessLogicError("状态不合法")
            data["status"] = status
        if "problem_summary" in data:
            summary = (data.get("problem_summary") or "").strip()
            if not summary:
                raise BusinessLogicError("问题摘要不能为空")
            data["problem_summary"] = summary
        next_need = data.get("need_eight_d", row.need_eight_d)
        next_eight = data.get("eight_d_code", row.eight_d_code)
        if "need_eight_d" in data or "eight_d_code" in data:
            data["eight_d_code"] = await self._assert_eight_d(
                tenant_id, bool(next_need), next_eight
            )
            data["need_eight_d"] = bool(next_need)
        next_status = data.get("status", row.status)
        next_verify = data.get("verification_conclusion", row.verification_conclusion)
        self._guard_close(next_status, next_verify)
        for key, value in data.items():
            if isinstance(value, str) and key in {
                "cause",
                "correction",
                "prevention",
                "responsible_person",
                "verifier_name",
                "verification_conclusion",
                "remarks",
            }:
                value = value.strip() or None
            setattr(row, key, value)
        apply_update_audit(row, actor)
        await row.save()
        if row.status == "closed" and row.source_type == "management_review_resolution" and row.source_id:
            res = await QmsManagementReviewResolution.filter(
                tenant_id=tenant_id, id=row.source_id, deleted_at__isnull=True
            ).first()
            if res is not None:
                res.status = "done"
                apply_update_audit(res, actor)
                await res.save()
        return self._response(row)

    async def delete_action(self, tenant_id: int, action_id: int, *, actor: Any) -> None:
        row = await QmsCorrectiveAction.filter(
            tenant_id=tenant_id, id=action_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("纠正预防不存在")
        if row.status == "closed":
            raise BusinessLogicError("已关闭的纠正预防不能删除")
        if row.source_type == "nonconformity_report" and row.source_id:
            nc = await QmsNonconformityReport.filter(
                tenant_id=tenant_id, id=row.source_id, deleted_at__isnull=True
            ).first()
            if nc and (nc.capa_code or "").strip() == row.action_code:
                nc.capa_code = None
                apply_update_audit(nc, actor)
                await nc.save()
        if row.source_type == "management_review_resolution" and row.source_id:
            res = await QmsManagementReviewResolution.filter(
                tenant_id=tenant_id, id=row.source_id, deleted_at__isnull=True
            ).first()
            if res and (res.capa_code or "").strip() == row.action_code:
                res.capa_code = None
                res.convert_to_capa = False
                apply_update_audit(res, actor)
                await res.save()
        row.deleted_at = resolve_business_datetime()
        apply_update_audit(row, actor)
        await row.save()


class QmsManagementReviewResolutionService:
    def _response(self, row: QmsManagementReviewResolution) -> QmsManagementReviewResolutionResponse:
        return QmsManagementReviewResolutionResponse.model_validate(row)

    async def list_resolutions(
        self, tenant_id: int, review_id: int
    ) -> QmsManagementReviewResolutionListResponse:
        review = await QmsManagementReview.filter(
            tenant_id=tenant_id, id=review_id, deleted_at__isnull=True
        ).first()
        if review is None:
            raise NotFoundError("管理评审不存在")
        rows = await QmsManagementReviewResolution.filter(
            tenant_id=tenant_id, review_id=review_id, deleted_at__isnull=True
        ).order_by("sort_order", "id")
        return QmsManagementReviewResolutionListResponse(
            items=[self._response(r) for r in rows],
            total=len(rows),
        )

    async def create_resolution(
        self,
        tenant_id: int,
        review_id: int,
        payload: QmsManagementReviewResolutionCreate,
        *,
        actor: Any,
    ) -> QmsManagementReviewResolutionResponse:
        review = await QmsManagementReview.filter(
            tenant_id=tenant_id, id=review_id, deleted_at__isnull=True
        ).first()
        if review is None:
            raise NotFoundError("管理评审不存在")
        content = (payload.content or "").strip()
        if not content:
            raise BusinessLogicError("请填写决议内容")
        count = await QmsManagementReviewResolution.filter(
            tenant_id=tenant_id, review_id=review_id, deleted_at__isnull=True
        ).count()
        data = {
            "tenant_id": tenant_id,
            "review_id": review_id,
            "content": content,
            "responsible_person": (payload.responsible_person or "").strip() or None,
            "due_on": payload.due_on,
            "convert_to_capa": bool(payload.convert_to_capa),
            "status": "open",
            "sort_order": payload.sort_order if payload.sort_order is not None else count,
            "remarks": (payload.remarks or "").strip() or None,
        }
        apply_create_audit(data, actor)
        row = await QmsManagementReviewResolution.create(**data)
        return self._response(row)

    async def update_resolution(
        self,
        tenant_id: int,
        review_id: int,
        resolution_id: int,
        payload: QmsManagementReviewResolutionUpdate,
        *,
        actor: Any,
    ) -> QmsManagementReviewResolutionResponse:
        row = await QmsManagementReviewResolution.filter(
            tenant_id=tenant_id,
            review_id=review_id,
            id=resolution_id,
            deleted_at__isnull=True,
        ).first()
        if row is None:
            raise NotFoundError("管理评审决议不存在")
        data = payload.model_dump(exclude_unset=True)
        if "content" in data:
            content = (data.get("content") or "").strip()
            if not content:
                raise BusinessLogicError("请填写决议内容")
            data["content"] = content
        for key, value in data.items():
            if isinstance(value, str) and key in {"responsible_person", "remarks"}:
                value = value.strip() or None
            setattr(row, key, value)
        apply_update_audit(row, actor)
        await row.save()
        return self._response(row)

    async def delete_resolution(
        self, tenant_id: int, review_id: int, resolution_id: int, *, actor: Any
    ) -> None:
        row = await QmsManagementReviewResolution.filter(
            tenant_id=tenant_id,
            review_id=review_id,
            id=resolution_id,
            deleted_at__isnull=True,
        ).first()
        if row is None:
            raise NotFoundError("管理评审决议不存在")
        if (row.capa_code or "").strip():
            raise BusinessLogicError("已关联纠正预防，不能删除决议")
        row.deleted_at = resolve_business_datetime()
        apply_update_audit(row, actor)
        await row.save()


async def assert_nc_capa_closed_for_close(
    tenant_id: int, *, severity: str, capa_code: Optional[str]
) -> None:
    """第 3 期：严重/一般关闭前纠正预防须已关闭。"""
    if severity == "observation":
        return
    code = (capa_code or "").strip()
    if not code:
        raise BusinessLogicError("严重或一般不符合关闭前须关联并关闭纠正预防")
    capa = await QmsCorrectiveAction.filter(
        tenant_id=tenant_id, action_code=code, deleted_at__isnull=True
    ).first()
    if capa is None:
        raise BusinessLogicError(f"关联的纠正预防不存在：{code}")
    if capa.status != "closed":
        raise BusinessLogicError("关联的纠正预防尚未关闭，不能关闭不符合报告")


async def assert_no_open_capa_for_complaint(tenant_id: int, complaint_id: int) -> None:
    open_count = await QmsCorrectiveAction.filter(
        tenant_id=tenant_id,
        source_type="quality_complaint",
        source_id=complaint_id,
        deleted_at__isnull=True,
        status__in=list(OPEN_CA_STATUSES),
    ).count()
    if open_count > 0:
        raise BusinessLogicError(f"仍有 {open_count} 份未关闭的纠正预防，不能关闭投诉")


async def assert_review_resolutions_ready_to_close(tenant_id: int, review_id: int) -> None:
    rows = await QmsManagementReviewResolution.filter(
        tenant_id=tenant_id, review_id=review_id, deleted_at__isnull=True
    )
    for row in rows:
        if row.status == "done":
            continue
        if row.convert_to_capa:
            code = (row.capa_code or "").strip()
            if not code:
                raise BusinessLogicError("存在已勾选转为纠正预防但尚未生成单据的决议，不能关闭评审")
            capa = await QmsCorrectiveAction.filter(
                tenant_id=tenant_id, action_code=code, deleted_at__isnull=True
            ).first()
            if capa is None or capa.status != "closed":
                raise BusinessLogicError("存在未关闭的纠正预防，不能关闭评审")
            continue
        raise BusinessLogicError("存在未关闭的决议，不能关闭评审")


corrective_action_service = QmsCorrectiveActionService()
resolution_service = QmsManagementReviewResolutionService()
