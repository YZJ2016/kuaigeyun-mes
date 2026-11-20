"""质量体系第 2 期：年度计划、检查表行、不符合报告。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.common.base_service import AppBaseService
from apps.kuaizhizao.models.qms_internal_audit import QmsInternalAudit
from apps.kuaizhizao.models.qms_internal_audit_annual_plan import QmsInternalAuditAnnualPlan
from apps.kuaizhizao.models.qms_internal_audit_checklist_item import QmsInternalAuditChecklistItem
from apps.kuaizhizao.models.qms_iso_clause import QmsIsoClause
from apps.kuaizhizao.models.qms_nonconformity_report import QmsNonconformityReport
from apps.kuaizhizao.schemas.quality_qms import (
    QmsInternalAuditAnnualPlanCreate,
    QmsInternalAuditAnnualPlanListResponse,
    QmsInternalAuditAnnualPlanResponse,
    QmsInternalAuditAnnualPlanUpdate,
    QmsInternalAuditChecklistItemCreate,
    QmsInternalAuditChecklistItemListResponse,
    QmsInternalAuditChecklistItemResponse,
    QmsInternalAuditChecklistItemUpdate,
    QmsNonconformityReportCreate,
    QmsNonconformityReportListResponse,
    QmsNonconformityReportResponse,
    QmsNonconformityReportUpdate,
)
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

CHECKLIST_CONCLUSIONS = {"pending", "conform", "nonconform", "observation"}
NC_SEVERITIES = {"severe", "general", "observation"}
NC_STATUSES = {"open", "rectifying", "pending_verify", "closed"}
NC_SOURCE_TYPES = {"internal_audit", "external_audit"}
OPEN_NC_STATUSES = {"open", "rectifying", "pending_verify"}


def _normalize_months(raw: Optional[List[int]]) -> Optional[List[int]]:
    if raw is None:
        return None
    months: List[int] = []
    for item in raw:
        month = int(item)
        if month < 1 or month > 12:
            raise BusinessLogicError("计划月份须在 1 到 12 之间")
        if month not in months:
            months.append(month)
    return sorted(months)


async def _clause_label(tenant_id: int, clause_id: Optional[int]) -> Optional[str]:
    if clause_id is None:
        return None
    row = await QmsIsoClause.filter(
        tenant_id=tenant_id, id=clause_id, deleted_at__isnull=True
    ).first()
    if row is None:
        return None
    code = (row.clause_code or "").strip()
    title = (row.title or "").strip()
    if code and title:
        return f"{code} {title}"
    return code or title or None


async def count_open_nc_for_audit(tenant_id: int, audit_id: int) -> int:
    return await QmsNonconformityReport.filter(
        tenant_id=tenant_id,
        source_type="internal_audit",
        source_id=audit_id,
        deleted_at__isnull=True,
        status__in=list(OPEN_NC_STATUSES),
    ).count()


class QmsInternalAuditAnnualPlanService(AppBaseService[QmsInternalAuditAnnualPlan]):
    def __init__(self) -> None:
        super().__init__(QmsInternalAuditAnnualPlan)
        self.model = QmsInternalAuditAnnualPlan

    async def create_plan(
        self,
        tenant_id: int,
        payload: QmsInternalAuditAnnualPlanCreate,
        *,
        actor: Any,
    ) -> QmsInternalAuditAnnualPlanResponse:
        year = int(payload.plan_year)
        if year < 2000 or year > 2100:
            raise BusinessLogicError("年度不合法")
        exists = await QmsInternalAuditAnnualPlan.filter(
            tenant_id=tenant_id, plan_year=year, deleted_at__isnull=True
        ).exists()
        if exists:
            raise BusinessLogicError(f"{year} 年年度计划已存在")
        data: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "plan_year": year,
            "covered_processes": (payload.covered_processes or "").strip() or None,
            "planned_months": _normalize_months(payload.planned_months),
            "lead_auditor": (payload.lead_auditor or "").strip() or None,
            "remarks": (payload.remarks or "").strip() or None,
        }
        apply_create_audit(data, actor)
        row = await QmsInternalAuditAnnualPlan.create(**data)
        return QmsInternalAuditAnnualPlanResponse.model_validate(row)

    async def list_plans(
        self,
        tenant_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> QmsInternalAuditAnnualPlanListResponse:
        query = QmsInternalAuditAnnualPlan.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        total = await query.count()
        rows = await query.order_by("-plan_year", "-id").offset(skip).limit(limit)
        return QmsInternalAuditAnnualPlanListResponse(
            items=[QmsInternalAuditAnnualPlanResponse.model_validate(r) for r in rows],
            total=total,
        )

    async def update_plan(
        self,
        tenant_id: int,
        plan_id: int,
        payload: QmsInternalAuditAnnualPlanUpdate,
        *,
        actor: Any,
    ) -> QmsInternalAuditAnnualPlanResponse:
        row = await QmsInternalAuditAnnualPlan.filter(
            tenant_id=tenant_id, id=plan_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("年度计划不存在")
        data = payload.model_dump(exclude_unset=True)
        if "planned_months" in data:
            data["planned_months"] = _normalize_months(data.get("planned_months"))
        for key in ("covered_processes", "lead_auditor", "remarks"):
            if key in data and isinstance(data[key], str):
                data[key] = data[key].strip() or None
        for key, value in data.items():
            setattr(row, key, value)
        apply_update_audit(row, actor)
        await row.save()
        return QmsInternalAuditAnnualPlanResponse.model_validate(row)

    async def delete_plan(self, tenant_id: int, plan_id: int, *, actor: Any) -> None:
        row = await QmsInternalAuditAnnualPlan.filter(
            tenant_id=tenant_id, id=plan_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("年度计划不存在")
        linked = await QmsInternalAudit.filter(
            tenant_id=tenant_id, annual_plan_id=plan_id, deleted_at__isnull=True
        ).exists()
        if linked:
            raise BusinessLogicError("年度计划下已有内审，不能删除")
        row.deleted_at = resolve_business_datetime()
        apply_update_audit(row, actor)
        await row.save()


class QmsNonconformityReportService(AppBaseService[QmsNonconformityReport]):
    code_field = "report_code"
    rule_code = "QMS_NONCONFORMITY_REPORT_CODE"
    code_prefix = "BFH"

    def __init__(self) -> None:
        super().__init__(QmsNonconformityReport)
        self.model = QmsNonconformityReport

    async def _ensure_code(self, tenant_id: int, code: Optional[str]) -> str:
        raw = (code or "").strip()
        if raw:
            return raw
        return await self.generate_code(tenant_id, self.rule_code, prefix=self.code_prefix)

    async def _response(self, tenant_id: int, row: QmsNonconformityReport) -> QmsNonconformityReportResponse:
        payload = QmsNonconformityReportResponse.model_validate(row).model_dump()
        payload["clause_label"] = await _clause_label(tenant_id, row.clause_id)
        return QmsNonconformityReportResponse.model_validate(payload)

    async def _guard_close(
        self,
        tenant_id: int,
        *,
        status: Optional[str],
        verification_conclusion: Optional[str],
        severity: Optional[str],
        capa_code: Optional[str],
    ) -> None:
        if status != "closed":
            return
        if not (verification_conclusion or "").strip():
            raise BusinessLogicError("关闭不符合报告前须填写验证结论")
        from apps.kuaizhizao.services.qms_corrective_action_service import (
            assert_nc_capa_closed_for_close,
        )

        await assert_nc_capa_closed_for_close(
            tenant_id, severity=(severity or "").strip(), capa_code=capa_code
        )

    async def create_report(
        self,
        tenant_id: int,
        payload: QmsNonconformityReportCreate,
        *,
        actor: Any,
        lock_source: bool = False,
    ) -> QmsNonconformityReportResponse:
        source_type = (payload.source_type or "").strip()
        if source_type not in NC_SOURCE_TYPES:
            raise BusinessLogicError("来源须为内部审核或外审")
        severity = (payload.severity or "").strip()
        if severity not in NC_SEVERITIES:
            raise BusinessLogicError("类型须为严重、一般或观察项")
        status = (payload.status or "open").strip()
        if status not in NC_STATUSES:
            raise BusinessLogicError("状态不合法")
        fact = (payload.fact or "").strip()
        if not fact:
            raise BusinessLogicError("请填写不符合事实")
        await self._guard_close(
            tenant_id,
            status=status,
            verification_conclusion=payload.verification_conclusion,
            severity=severity,
            capa_code=payload.capa_code,
        )
        data = payload.model_dump(exclude_unset=False)
        data["report_code"] = await self._ensure_code(tenant_id, data.get("report_code"))
        data["source_type"] = source_type
        data["severity"] = severity
        data["status"] = status
        data["fact"] = fact
        for key in (
            "source_code",
            "responsible_dept",
            "cause",
            "correction",
            "corrective_action",
            "verifier_name",
            "verification_conclusion",
            "capa_code",
            "remarks",
        ):
            if isinstance(data.get(key), str):
                data[key] = data[key].strip() or None
        if lock_source:
            pass
        clash = await QmsNonconformityReport.filter(
            tenant_id=tenant_id, report_code=data["report_code"], deleted_at__isnull=True
        ).exists()
        if clash:
            raise BusinessLogicError("不符合报告编号已存在")
        data["tenant_id"] = tenant_id
        apply_create_audit(data, actor)
        row = await QmsNonconformityReport.create(**data)
        return await self._response(tenant_id, row)

    async def list_reports(
        self,
        tenant_id: int,
        *,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> QmsNonconformityReportListResponse:
        query = QmsNonconformityReport.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if keyword:
            query = query.filter(fact__icontains=keyword)
        if status:
            query = query.filter(status=status)
        if source_type:
            query = query.filter(source_type=source_type)
        if source_id is not None:
            query = query.filter(source_id=source_id)
        total = await query.count()
        rows = await query.order_by("-updated_at", "-id").offset(skip).limit(limit)
        items = [await self._response(tenant_id, r) for r in rows]
        return QmsNonconformityReportListResponse(items=items, total=total)

    async def get_report(self, tenant_id: int, report_id: int) -> QmsNonconformityReportResponse:
        row = await QmsNonconformityReport.filter(
            tenant_id=tenant_id, id=report_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("不符合报告不存在")
        return await self._response(tenant_id, row)

    async def update_report(
        self,
        tenant_id: int,
        report_id: int,
        payload: QmsNonconformityReportUpdate,
        *,
        actor: Any,
    ) -> QmsNonconformityReportResponse:
        row = await QmsNonconformityReport.filter(
            tenant_id=tenant_id, id=report_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("不符合报告不存在")
        data = payload.model_dump(exclude_unset=True)
        if "severity" in data:
            severity = (data.get("severity") or "").strip()
            if severity not in NC_SEVERITIES:
                raise BusinessLogicError("类型须为严重、一般或观察项")
            data["severity"] = severity
        if "status" in data:
            status = (data.get("status") or "").strip()
            if status not in NC_STATUSES:
                raise BusinessLogicError("状态不合法")
            data["status"] = status
        if "fact" in data:
            fact = (data.get("fact") or "").strip()
            if not fact:
                raise BusinessLogicError("请填写不符合事实")
            data["fact"] = fact
        next_status = data.get("status", row.status)
        next_verify = data.get("verification_conclusion", row.verification_conclusion)
        next_severity = data.get("severity", row.severity)
        next_capa = data.get("capa_code", row.capa_code) if "capa_code" in data else row.capa_code
        await self._guard_close(
            tenant_id,
            status=next_status,
            verification_conclusion=next_verify,
            severity=next_severity,
            capa_code=next_capa,
        )
        for key, value in data.items():
            if isinstance(value, str) and key in {
                "responsible_dept",
                "cause",
                "correction",
                "corrective_action",
                "verifier_name",
                "verification_conclusion",
                "remarks",
            }:
                value = value.strip() or None
            setattr(row, key, value)
        apply_update_audit(row, actor)
        await row.save()
        return await self._response(tenant_id, row)

    async def delete_report(self, tenant_id: int, report_id: int, *, actor: Any) -> None:
        row = await QmsNonconformityReport.filter(
            tenant_id=tenant_id, id=report_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("不符合报告不存在")
        if (row.capa_code or "").strip():
            raise BusinessLogicError("已关联纠正预防，不能删除")
        if row.checklist_item_id:
            item = await QmsInternalAuditChecklistItem.filter(
                tenant_id=tenant_id,
                id=row.checklist_item_id,
                deleted_at__isnull=True,
            ).first()
            if item and item.nc_report_id == row.id:
                item.nc_report_id = None
                apply_update_audit(item, actor)
                await item.save()
        row.deleted_at = resolve_business_datetime()
        apply_update_audit(row, actor)
        await row.save()


class QmsInternalAuditChecklistService:
    async def _item_response(
        self,
        tenant_id: int,
        row: QmsInternalAuditChecklistItem,
        nc_map: Optional[Dict[int, QmsNonconformityReport]] = None,
    ) -> QmsInternalAuditChecklistItemResponse:
        nc = None
        if row.nc_report_id:
            if nc_map is not None:
                nc = nc_map.get(row.nc_report_id)
            else:
                nc = await QmsNonconformityReport.filter(
                    tenant_id=tenant_id, id=row.nc_report_id, deleted_at__isnull=True
                ).first()
        payload = QmsInternalAuditChecklistItemResponse.model_validate(row).model_dump()
        payload["clause_label"] = await _clause_label(tenant_id, row.clause_id)
        payload["nc_report_code"] = nc.report_code if nc else None
        payload["nc_report_status"] = nc.status if nc else None
        return QmsInternalAuditChecklistItemResponse.model_validate(payload)

    async def list_items(
        self, tenant_id: int, audit_id: int
    ) -> QmsInternalAuditChecklistItemListResponse:
        audit = await QmsInternalAudit.filter(
            tenant_id=tenant_id, id=audit_id, deleted_at__isnull=True
        ).first()
        if audit is None:
            raise NotFoundError("内审不存在")
        rows = await QmsInternalAuditChecklistItem.filter(
            tenant_id=tenant_id, audit_id=audit_id, deleted_at__isnull=True
        ).order_by("sort_order", "id")
        nc_ids = [r.nc_report_id for r in rows if r.nc_report_id]
        nc_map: Dict[int, QmsNonconformityReport] = {}
        if nc_ids:
            ncs = await QmsNonconformityReport.filter(
                tenant_id=tenant_id, id__in=nc_ids, deleted_at__isnull=True
            )
            nc_map = {n.id: n for n in ncs}
        items = [await self._item_response(tenant_id, r, nc_map) for r in rows]
        return QmsInternalAuditChecklistItemListResponse(items=items, total=len(items))

    async def _ensure_clause(self, tenant_id: int, clause_id: int) -> None:
        exists = await QmsIsoClause.filter(
            tenant_id=tenant_id, id=clause_id, deleted_at__isnull=True
        ).exists()
        if not exists:
            raise BusinessLogicError("条款不存在")

    async def _maybe_create_nc(
        self,
        tenant_id: int,
        audit: QmsInternalAudit,
        item: QmsInternalAuditChecklistItem,
        *,
        severity: Optional[str],
        actor: Any,
        fact_hint: Optional[str],
    ) -> None:
        if item.conclusion != "nonconform":
            return
        if item.nc_report_id:
            return
        sev = (severity or "general").strip()
        if sev not in {"severe", "general"}:
            raise BusinessLogicError("检查表判不符合时，报告类型须为严重或一般")
        nc_service = QmsNonconformityReportService()
        report = await nc_service.create_report(
            tenant_id,
            QmsNonconformityReportCreate(
                source_type="internal_audit",
                source_id=audit.id,
                source_code=audit.audit_code,
                checklist_item_id=item.id,
                clause_id=item.clause_id,
                fact=(fact_hint or item.checkpoint or "内审不符合").strip(),
                severity=sev,
                status="open",
            ),
            actor=actor,
            lock_source=True,
        )
        item.nc_report_id = report.id
        apply_update_audit(item, actor)
        await item.save()

    async def create_item(
        self,
        tenant_id: int,
        audit_id: int,
        payload: QmsInternalAuditChecklistItemCreate,
        *,
        actor: Any,
    ) -> QmsInternalAuditChecklistItemResponse:
        audit = await QmsInternalAudit.filter(
            tenant_id=tenant_id, id=audit_id, deleted_at__isnull=True
        ).first()
        if audit is None:
            raise NotFoundError("内审不存在")
        if audit.status == "closed":
            raise BusinessLogicError("已关闭的内审不能改检查表")
        conclusion = (payload.conclusion or "pending").strip()
        if conclusion not in CHECKLIST_CONCLUSIONS:
            raise BusinessLogicError("检查表结论不合法")
        await self._ensure_clause(tenant_id, payload.clause_id)
        data: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "audit_id": audit_id,
            "clause_id": payload.clause_id,
            "sort_order": int(payload.sort_order or 0),
            "checkpoint": (payload.checkpoint or "").strip() or None,
            "conclusion": conclusion,
            "evidence": (payload.evidence or "").strip() or None,
            "remarks": (payload.remarks or "").strip() or None,
        }
        apply_create_audit(data, actor)
        item = await QmsInternalAuditChecklistItem.create(**data)
        await self._maybe_create_nc(
            tenant_id,
            audit,
            item,
            severity=payload.nc_severity,
            actor=actor,
            fact_hint=payload.checkpoint,
        )
        return await self._item_response(tenant_id, item)

    async def update_item(
        self,
        tenant_id: int,
        audit_id: int,
        item_id: int,
        payload: QmsInternalAuditChecklistItemUpdate,
        *,
        actor: Any,
    ) -> QmsInternalAuditChecklistItemResponse:
        audit = await QmsInternalAudit.filter(
            tenant_id=tenant_id, id=audit_id, deleted_at__isnull=True
        ).first()
        if audit is None:
            raise NotFoundError("内审不存在")
        if audit.status == "closed":
            raise BusinessLogicError("已关闭的内审不能改检查表")
        item = await QmsInternalAuditChecklistItem.filter(
            tenant_id=tenant_id,
            audit_id=audit_id,
            id=item_id,
            deleted_at__isnull=True,
        ).first()
        if item is None:
            raise NotFoundError("检查表行不存在")
        data = payload.model_dump(exclude_unset=True)
        nc_severity = data.pop("nc_severity", None)
        if "clause_id" in data and data["clause_id"] is not None:
            await self._ensure_clause(tenant_id, int(data["clause_id"]))
        if "conclusion" in data:
            conclusion = (data.get("conclusion") or "").strip()
            if conclusion not in CHECKLIST_CONCLUSIONS:
                raise BusinessLogicError("检查表结论不合法")
            data["conclusion"] = conclusion
        for key in ("checkpoint", "evidence", "remarks"):
            if key in data and isinstance(data[key], str):
                data[key] = data[key].strip() or None
        for key, value in data.items():
            setattr(item, key, value)
        apply_update_audit(item, actor)
        await item.save()
        await self._maybe_create_nc(
            tenant_id,
            audit,
            item,
            severity=nc_severity,
            actor=actor,
            fact_hint=item.checkpoint,
        )
        return await self._item_response(tenant_id, item)

    async def delete_item(
        self,
        tenant_id: int,
        audit_id: int,
        item_id: int,
        *,
        actor: Any,
    ) -> None:
        item = await QmsInternalAuditChecklistItem.filter(
            tenant_id=tenant_id,
            audit_id=audit_id,
            id=item_id,
            deleted_at__isnull=True,
        ).first()
        if item is None:
            raise NotFoundError("检查表行不存在")
        if item.nc_report_id:
            raise BusinessLogicError("已生成不符合报告，不能删除该行")
        item.deleted_at = resolve_business_datetime()
        apply_update_audit(item, actor)
        await item.save()


annual_plan_service = QmsInternalAuditAnnualPlanService()
checklist_service = QmsInternalAuditChecklistService()
nonconformity_service = QmsNonconformityReportService()
