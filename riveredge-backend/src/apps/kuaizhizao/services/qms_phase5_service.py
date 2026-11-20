"""质量体系第 5 期：质量目标、法律法规、外审与证书。"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, List, Optional

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.common.base_service import AppBaseService
from apps.kuaizhizao.models.qms_certificate import QmsCertificate
from apps.kuaizhizao.models.qms_corrective_action import QmsCorrectiveAction
from apps.kuaizhizao.models.qms_external_audit import QmsExternalAudit
from apps.kuaizhizao.models.qms_legal_regulation import QmsLegalRegulation
from apps.kuaizhizao.models.qms_nonconformity_report import QmsNonconformityReport
from apps.kuaizhizao.models.qms_quality_objective import QmsQualityObjective, QmsQualityObjectiveLine
from apps.kuaizhizao.models.qms_standard import QmsStandard
from apps.kuaizhizao.schemas.quality_qms import (
    QmsCertificateCreate,
    QmsCertificateListResponse,
    QmsCertificateResponse,
    QmsCertificateUpdate,
    QmsExternalAuditCreate,
    QmsExternalAuditListResponse,
    QmsExternalAuditResponse,
    QmsExternalAuditUpdate,
    QmsLegalRegulationCreate,
    QmsLegalRegulationListResponse,
    QmsLegalRegulationResponse,
    QmsLegalRegulationUpdate,
    QmsManagementReviewInputDocItem,
    QmsQualityObjectiveCreate,
    QmsQualityObjectiveLinePayload,
    QmsQualityObjectiveLineResponse,
    QmsQualityObjectiveListResponse,
    QmsQualityObjectiveResponse,
    QmsQualityObjectiveUpdate,
)
from core.utils.timezone_utils import resolve_business_datetime, to_site_date
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

OBJECTIVE_STATUSES = {"draft", "published", "ended"}
OBJECTIVE_PERIODS = {"month", "quarter"}
LEGAL_CONCLUSIONS = {"conform", "need_rectify"}
EXTERNAL_AUDIT_TYPES = {"initial", "surveillance", "recertification"}
OPEN_NC_STATUSES = {"open", "rectifying", "pending_verify"}


def compute_achieved(target_value: str, actual_value: Optional[str]) -> Optional[bool]:
    actual = (actual_value or "").strip()
    target = (target_value or "").strip()
    if not actual:
        return None
    try:
        return Decimal(actual) >= Decimal(target)
    except (InvalidOperation, TypeError):
        return actual == target


def compute_certificate_status(expire_on: date, today: date) -> str:
    if expire_on < today:
        return "expired"
    if expire_on <= today + timedelta(days=90):
        return "expiring"
    return "valid"


class QmsQualityObjectiveService(AppBaseService[QmsQualityObjective]):
    code_field = "objective_code"
    rule_code = "QMS_QUALITY_OBJECTIVE_CODE"
    code_prefix = "ZLMB"

    def __init__(self) -> None:
        super().__init__(QmsQualityObjective)
        self.model = QmsQualityObjective

    async def _ensure_code(self, tenant_id: int, code: Optional[str]) -> str:
        raw = (code or "").strip()
        if raw:
            return raw
        return await self.generate_code(tenant_id, self.rule_code, prefix=self.code_prefix)

    async def _response(self, tenant_id: int, row: QmsQualityObjective) -> QmsQualityObjectiveResponse:
        lines = await QmsQualityObjectiveLine.filter(
            tenant_id=tenant_id, objective_id=row.id, deleted_at__isnull=True
        ).order_by("sort_order", "id")
        standard_label = None
        if row.standard_id:
            std = await QmsStandard.filter(
                tenant_id=tenant_id, id=row.standard_id, deleted_at__isnull=True
            ).first()
            if std:
                standard_label = f"{std.code} {std.name}".strip()
        payload = QmsQualityObjectiveResponse.model_validate(row).model_dump()
        payload["standard_label"] = standard_label
        payload["lines"] = [
            QmsQualityObjectiveLineResponse.model_validate(line) for line in lines
        ]
        return QmsQualityObjectiveResponse.model_validate(payload)

    async def _replace_lines(
        self,
        tenant_id: int,
        objective_id: int,
        lines: List[QmsQualityObjectiveLinePayload],
        *,
        actor: Any,
    ) -> None:
        existing = await QmsQualityObjectiveLine.filter(
            tenant_id=tenant_id, objective_id=objective_id, deleted_at__isnull=True
        )
        for row in existing:
            row.deleted_at = resolve_business_datetime()
            apply_update_audit(row, actor)
            await row.save()
        for idx, line in enumerate(lines):
            period = (line.period or "month").strip()
            if period not in OBJECTIVE_PERIODS:
                raise BusinessLogicError("周期须为月或季")
            name = (line.name or "").strip()
            target = (line.target_value or "").strip()
            if not name or not target:
                raise BusinessLogicError("目标名称与目标值不能为空")
            actual = (line.actual_value or "").strip() or None
            data = {
                "tenant_id": tenant_id,
                "objective_id": objective_id,
                "sort_order": line.sort_order if line.sort_order is not None else idx,
                "name": name,
                "metric_scope": (line.metric_scope or "").strip() or None,
                "target_value": target,
                "responsible_dept": (line.responsible_dept or "").strip() or None,
                "period": period,
                "actual_value": actual,
                "achieved": compute_achieved(target, actual),
                "remarks": (line.remarks or "").strip() or None,
            }
            apply_create_audit(data, actor)
            await QmsQualityObjectiveLine.create(**data)

    async def create_objective(
        self, tenant_id: int, payload: QmsQualityObjectiveCreate, *, actor: Any
    ) -> QmsQualityObjectiveResponse:
        status = (payload.status or "draft").strip()
        if status not in OBJECTIVE_STATUSES:
            raise BusinessLogicError("状态不合法")
        code = await self._ensure_code(tenant_id, payload.objective_code)
        if await QmsQualityObjective.filter(
            tenant_id=tenant_id, objective_code=code, deleted_at__isnull=True
        ).exists():
            raise BusinessLogicError("质量目标编号已存在")
        data = {
            "tenant_id": tenant_id,
            "objective_code": code,
            "plan_year": int(payload.plan_year),
            "standard_id": payload.standard_id,
            "status": status,
            "remarks": (payload.remarks or "").strip() or None,
        }
        apply_create_audit(data, actor)
        row = await QmsQualityObjective.create(**data)
        await self._replace_lines(tenant_id, row.id, payload.lines or [], actor=actor)
        return await self._response(tenant_id, row)

    async def list_objectives(
        self,
        tenant_id: int,
        *,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        plan_year: Optional[int] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> QmsQualityObjectiveListResponse:
        query = QmsQualityObjective.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if keyword:
            query = query.filter(objective_code__icontains=keyword)
        if status:
            query = query.filter(status=status)
        if plan_year is not None:
            query = query.filter(plan_year=plan_year)
        total = await query.count()
        rows = await query.order_by("-plan_year", "-id").offset(skip).limit(limit)
        items = [await self._response(tenant_id, r) for r in rows]
        return QmsQualityObjectiveListResponse(items=items, total=total)

    async def get_objective(self, tenant_id: int, objective_id: int) -> QmsQualityObjectiveResponse:
        row = await QmsQualityObjective.filter(
            tenant_id=tenant_id, id=objective_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("质量目标不存在")
        return await self._response(tenant_id, row)

    async def update_objective(
        self,
        tenant_id: int,
        objective_id: int,
        payload: QmsQualityObjectiveUpdate,
        *,
        actor: Any,
    ) -> QmsQualityObjectiveResponse:
        row = await QmsQualityObjective.filter(
            tenant_id=tenant_id, id=objective_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("质量目标不存在")
        data = payload.model_dump(exclude_unset=True)
        lines = data.pop("lines", None)
        if "status" in data:
            status = (data.get("status") or "").strip()
            if status not in OBJECTIVE_STATUSES:
                raise BusinessLogicError("状态不合法")
            data["status"] = status
        if "remarks" in data and isinstance(data["remarks"], str):
            data["remarks"] = data["remarks"].strip() or None
        for key, value in data.items():
            setattr(row, key, value)
        apply_update_audit(row, actor)
        await row.save()
        if lines is not None:
            await self._replace_lines(
                tenant_id,
                row.id,
                [QmsQualityObjectiveLinePayload.model_validate(x) for x in lines],
                actor=actor,
            )
        return await self._response(tenant_id, row)

    async def delete_objective(self, tenant_id: int, objective_id: int, *, actor: Any) -> None:
        row = await QmsQualityObjective.filter(
            tenant_id=tenant_id, id=objective_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("质量目标不存在")
        now = resolve_business_datetime()
        lines = await QmsQualityObjectiveLine.filter(
            tenant_id=tenant_id, objective_id=objective_id, deleted_at__isnull=True
        )
        for line in lines:
            line.deleted_at = now
            apply_update_audit(line, actor)
            await line.save()
        row.deleted_at = now
        apply_update_audit(row, actor)
        await row.save()


async def list_published_unmet_objective_docs(
    tenant_id: int,
) -> List[QmsManagementReviewInputDocItem]:
    objectives = await QmsQualityObjective.filter(
        tenant_id=tenant_id, deleted_at__isnull=True, status="published"
    )
    out: List[QmsManagementReviewInputDocItem] = []
    for obj in objectives:
        lines = await QmsQualityObjectiveLine.filter(
            tenant_id=tenant_id,
            objective_id=obj.id,
            deleted_at__isnull=True,
            achieved=False,
        )
        for line in lines:
            out.append(
                QmsManagementReviewInputDocItem(
                    ref_type="qms_quality_objective_line",
                    ref_id=line.id,
                    ref_code=obj.objective_code,
                    ref_name=line.name,
                    status="not_achieved",
                    note=f"目标 {line.target_value} / 实际 {line.actual_value or '-'}",
                )
            )
    return out


class QmsLegalRegulationService(AppBaseService[QmsLegalRegulation]):
    def __init__(self) -> None:
        super().__init__(QmsLegalRegulation)
        self.model = QmsLegalRegulation

    def _guard_eval(
        self,
        *,
        evaluation_conclusion: Optional[str],
        evaluation_completed: bool,
        capa_code: Optional[str],
    ) -> None:
        conclusion = (evaluation_conclusion or "").strip() or None
        if conclusion and conclusion not in LEGAL_CONCLUSIONS:
            raise BusinessLogicError("评价结论须为符合或需整改")
        if evaluation_completed and conclusion == "need_rectify" and not (capa_code or "").strip():
            raise BusinessLogicError("评价结论为需整改时，完成评价前须关联纠正预防")

    async def _response(self, row: QmsLegalRegulation) -> QmsLegalRegulationResponse:
        today = to_site_date(resolve_business_datetime())
        payload = QmsLegalRegulationResponse.model_validate(row).model_dump()
        due = bool(row.next_evaluation_on and row.next_evaluation_on <= today)
        payload["due_for_evaluation"] = due
        return QmsLegalRegulationResponse.model_validate(payload)

    async def create_regulation(
        self, tenant_id: int, payload: QmsLegalRegulationCreate, *, actor: Any
    ) -> QmsLegalRegulationResponse:
        self._guard_eval(
            evaluation_conclusion=payload.evaluation_conclusion,
            evaluation_completed=bool(payload.evaluation_completed),
            capa_code=payload.capa_code,
        )
        if (payload.capa_code or "").strip():
            exists = await QmsCorrectiveAction.filter(
                tenant_id=tenant_id,
                action_code=payload.capa_code.strip(),
                deleted_at__isnull=True,
            ).exists()
            if not exists:
                raise BusinessLogicError(f"纠正预防单号不存在：{payload.capa_code.strip()}")
        data = payload.model_dump()
        data["tenant_id"] = tenant_id
        data["name"] = payload.name.strip()
        data["doc_no"] = payload.doc_no.strip()
        for key in ("issuing_authority", "applicable_scope", "capa_code", "remarks"):
            if isinstance(data.get(key), str):
                data[key] = data[key].strip() or None
        if data.get("evaluation_conclusion"):
            data["evaluation_conclusion"] = data["evaluation_conclusion"].strip()
        apply_create_audit(data, actor)
        row = await QmsLegalRegulation.create(**data)
        return await self._response(row)

    async def list_regulations(
        self,
        tenant_id: int,
        *,
        keyword: Optional[str] = None,
        due_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> QmsLegalRegulationListResponse:
        query = QmsLegalRegulation.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if keyword:
            query = query.filter(name__icontains=keyword)
        if due_only:
            today = to_site_date(resolve_business_datetime())
            query = query.filter(next_evaluation_on__lte=today)
        total = await query.count()
        rows = await query.order_by("next_evaluation_on", "-id").offset(skip).limit(limit)
        items = [await self._response(r) for r in rows]
        return QmsLegalRegulationListResponse(items=items, total=total)

    async def get_regulation(self, tenant_id: int, regulation_id: int) -> QmsLegalRegulationResponse:
        row = await QmsLegalRegulation.filter(
            tenant_id=tenant_id, id=regulation_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("法律法规不存在")
        return await self._response(row)

    async def update_regulation(
        self,
        tenant_id: int,
        regulation_id: int,
        payload: QmsLegalRegulationUpdate,
        *,
        actor: Any,
    ) -> QmsLegalRegulationResponse:
        row = await QmsLegalRegulation.filter(
            tenant_id=tenant_id, id=regulation_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("法律法规不存在")
        data = payload.model_dump(exclude_unset=True)
        next_conclusion = data.get("evaluation_conclusion", row.evaluation_conclusion)
        next_completed = data.get("evaluation_completed", row.evaluation_completed)
        next_capa = data.get("capa_code", row.capa_code)
        self._guard_eval(
            evaluation_conclusion=next_conclusion,
            evaluation_completed=bool(next_completed),
            capa_code=next_capa,
        )
        if (next_capa or "").strip() and "capa_code" in data:
            exists = await QmsCorrectiveAction.filter(
                tenant_id=tenant_id,
                action_code=str(next_capa).strip(),
                deleted_at__isnull=True,
            ).exists()
            if not exists:
                raise BusinessLogicError(f"纠正预防单号不存在：{str(next_capa).strip()}")
        for key, value in data.items():
            if isinstance(value, str) and key in {
                "name",
                "doc_no",
                "issuing_authority",
                "applicable_scope",
                "capa_code",
                "remarks",
                "evaluation_conclusion",
            }:
                value = value.strip() or None
            setattr(row, key, value)
        apply_update_audit(row, actor)
        await row.save()
        return await self._response(row)

    async def delete_regulation(self, tenant_id: int, regulation_id: int, *, actor: Any) -> None:
        row = await QmsLegalRegulation.filter(
            tenant_id=tenant_id, id=regulation_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("法律法规不存在")
        row.deleted_at = resolve_business_datetime()
        apply_update_audit(row, actor)
        await row.save()


class QmsExternalAuditService(AppBaseService[QmsExternalAudit]):
    code_field = "audit_code"
    rule_code = "QMS_EXTERNAL_AUDIT_CODE"
    code_prefix = "WS"

    def __init__(self) -> None:
        super().__init__(QmsExternalAudit)
        self.model = QmsExternalAudit

    async def _ensure_code(self, tenant_id: int, code: Optional[str]) -> str:
        raw = (code or "").strip()
        if raw:
            return raw
        return await self.generate_code(tenant_id, self.rule_code, prefix=self.code_prefix)

    async def _response(self, tenant_id: int, row: QmsExternalAudit) -> QmsExternalAuditResponse:
        open_nc = await QmsNonconformityReport.filter(
            tenant_id=tenant_id,
            source_type="external_audit",
            source_id=row.id,
            deleted_at__isnull=True,
            status__in=list(OPEN_NC_STATUSES),
        ).count()
        payload = QmsExternalAuditResponse.model_validate(row).model_dump()
        payload["open_nc_count"] = open_nc
        return QmsExternalAuditResponse.model_validate(payload)

    async def create_audit(
        self, tenant_id: int, payload: QmsExternalAuditCreate, *, actor: Any
    ) -> QmsExternalAuditResponse:
        audit_type = (payload.audit_type or "").strip()
        if audit_type not in EXTERNAL_AUDIT_TYPES:
            raise BusinessLogicError("外审类型须为初次、监督或再认证")
        code = await self._ensure_code(tenant_id, payload.audit_code)
        if await QmsExternalAudit.filter(
            tenant_id=tenant_id, audit_code=code, deleted_at__isnull=True
        ).exists():
            raise BusinessLogicError("外审编号已存在")
        data = {
            "tenant_id": tenant_id,
            "audit_code": code,
            "body_name": payload.body_name.strip(),
            "audit_type": audit_type,
            "planned_on": payload.planned_on,
            "actual_on": payload.actual_on,
            "audit_scope": (payload.audit_scope or "").strip() or None,
            "remarks": (payload.remarks or "").strip() or None,
        }
        apply_create_audit(data, actor)
        row = await QmsExternalAudit.create(**data)
        return await self._response(tenant_id, row)

    async def list_audits(
        self,
        tenant_id: int,
        *,
        keyword: Optional[str] = None,
        audit_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> QmsExternalAuditListResponse:
        query = QmsExternalAudit.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if keyword:
            query = query.filter(body_name__icontains=keyword)
        if audit_type:
            query = query.filter(audit_type=audit_type)
        total = await query.count()
        rows = await query.order_by("-planned_on", "-id").offset(skip).limit(limit)
        items = [await self._response(tenant_id, r) for r in rows]
        return QmsExternalAuditListResponse(items=items, total=total)

    async def get_audit(self, tenant_id: int, audit_id: int) -> QmsExternalAuditResponse:
        row = await QmsExternalAudit.filter(
            tenant_id=tenant_id, id=audit_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("外审不存在")
        return await self._response(tenant_id, row)

    async def update_audit(
        self,
        tenant_id: int,
        audit_id: int,
        payload: QmsExternalAuditUpdate,
        *,
        actor: Any,
    ) -> QmsExternalAuditResponse:
        row = await QmsExternalAudit.filter(
            tenant_id=tenant_id, id=audit_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("外审不存在")
        data = payload.model_dump(exclude_unset=True)
        if "audit_type" in data:
            audit_type = (data.get("audit_type") or "").strip()
            if audit_type not in EXTERNAL_AUDIT_TYPES:
                raise BusinessLogicError("外审类型须为初次、监督或再认证")
            data["audit_type"] = audit_type
        for key, value in data.items():
            if isinstance(value, str) and key in {"body_name", "audit_scope", "remarks"}:
                value = value.strip() or None
            setattr(row, key, value)
        apply_update_audit(row, actor)
        await row.save()
        return await self._response(tenant_id, row)

    async def delete_audit(self, tenant_id: int, audit_id: int, *, actor: Any) -> None:
        row = await QmsExternalAudit.filter(
            tenant_id=tenant_id, id=audit_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("外审不存在")
        open_nc = await QmsNonconformityReport.filter(
            tenant_id=tenant_id,
            source_type="external_audit",
            source_id=audit_id,
            deleted_at__isnull=True,
            status__in=list(OPEN_NC_STATUSES),
        ).count()
        if open_nc:
            raise BusinessLogicError(f"仍有 {open_nc} 份未关闭不符合报告，不能删除外审")
        row.deleted_at = resolve_business_datetime()
        apply_update_audit(row, actor)
        await row.save()


class QmsCertificateService(AppBaseService[QmsCertificate]):
    def __init__(self) -> None:
        super().__init__(QmsCertificate)
        self.model = QmsCertificate

    async def _response(self, row: QmsCertificate) -> QmsCertificateResponse:
        today = to_site_date(resolve_business_datetime())
        return QmsCertificateResponse.model_validate(
            {
                "id": row.id,
                "uuid": row.uuid,
                "tenant_id": row.tenant_id,
                "name": row.name,
                "standard_name": row.standard_name,
                "certificate_no": row.certificate_no,
                "issuer": row.issuer,
                "effective_on": row.effective_on,
                "expire_on": row.expire_on,
                "remarks": row.remarks,
                "status": compute_certificate_status(row.expire_on, today),
                "created_by_name": row.created_by_name,
                "updated_by_name": row.updated_by_name,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )

    async def create_certificate(
        self, tenant_id: int, payload: QmsCertificateCreate, *, actor: Any
    ) -> QmsCertificateResponse:
        no = payload.certificate_no.strip()
        if await QmsCertificate.filter(
            tenant_id=tenant_id, certificate_no=no, deleted_at__isnull=True
        ).exists():
            raise BusinessLogicError("证书号已存在")
        data = {
            "tenant_id": tenant_id,
            "name": payload.name.strip(),
            "standard_name": (payload.standard_name or "").strip() or None,
            "certificate_no": no,
            "issuer": (payload.issuer or "").strip() or None,
            "effective_on": payload.effective_on,
            "expire_on": payload.expire_on,
            "remarks": (payload.remarks or "").strip() or None,
        }
        apply_create_audit(data, actor)
        row = await QmsCertificate.create(**data)
        return await self._response(row)

    async def list_certificates(
        self,
        tenant_id: int,
        *,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> QmsCertificateListResponse:
        query = QmsCertificate.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if keyword:
            query = query.filter(name__icontains=keyword)
        rows = await query.order_by("expire_on", "-id")
        today = to_site_date(resolve_business_datetime())
        items = []
        for row in rows:
            item = await self._response(row)
            if status and item.status != status:
                continue
            items.append(item)
        total = len(items)
        page = items[skip : skip + limit]
        return QmsCertificateListResponse(items=page, total=total)

    async def get_certificate(self, tenant_id: int, certificate_id: int) -> QmsCertificateResponse:
        row = await QmsCertificate.filter(
            tenant_id=tenant_id, id=certificate_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("证书不存在")
        return await self._response(row)

    async def update_certificate(
        self,
        tenant_id: int,
        certificate_id: int,
        payload: QmsCertificateUpdate,
        *,
        actor: Any,
    ) -> QmsCertificateResponse:
        row = await QmsCertificate.filter(
            tenant_id=tenant_id, id=certificate_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("证书不存在")
        data = payload.model_dump(exclude_unset=True)
        if "certificate_no" in data:
            no = (data.get("certificate_no") or "").strip()
            clash = await QmsCertificate.filter(
                tenant_id=tenant_id, certificate_no=no, deleted_at__isnull=True
            ).exclude(id=certificate_id).exists()
            if clash:
                raise BusinessLogicError("证书号已存在")
            data["certificate_no"] = no
        for key, value in data.items():
            if isinstance(value, str) and key in {"name", "standard_name", "issuer", "remarks"}:
                value = value.strip() or None
            setattr(row, key, value)
        apply_update_audit(row, actor)
        await row.save()
        return await self._response(row)

    async def delete_certificate(self, tenant_id: int, certificate_id: int, *, actor: Any) -> None:
        row = await QmsCertificate.filter(
            tenant_id=tenant_id, id=certificate_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("证书不存在")
        row.deleted_at = resolve_business_datetime()
        apply_update_audit(row, actor)
        await row.save()


quality_objective_service = QmsQualityObjectiveService()
legal_regulation_service = QmsLegalRegulationService()
external_audit_service = QmsExternalAuditService()
certificate_service = QmsCertificateService()
