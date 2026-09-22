"""年度培训计划批准下发至各部门（R-12 #11 / 01 体系接收）。"""

from __future__ import annotations

from typing import Any, List, Set

from loguru import logger

from apps.kuaioa.models.training import KuaioaDeptTrainingApplication, KuaioaTrainingPlan
from apps.kuaioa.services.kuaioa_training_notification import (
    ACTION_ANNUAL_PLAN_DISTRIBUTED,
    ACTION_DEPT_APPLICATION_WINDOW,
    DOC_TRAINING,
    dispatch_kuaioa_training_notification,
)
from core.models.department import Department
from infra.models.user import User
from infra.services.business_config_service import BusinessConfigService


SYSTEM_DEPT_RECIPIENT_NAME = "体系"


def _normalize_user_ids(raw: Any) -> List[int]:
    if raw is None:
        return []
    if isinstance(raw, int):
        return [raw] if raw > 0 else []
    if not isinstance(raw, list):
        return []
    out: List[int] = []
    seen: Set[int] = set()
    for item in raw:
        try:
            uid = int(item)
        except (TypeError, ValueError):
            continue
        if uid < 1 or uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out


async def _approved_dept_names_for_year(tenant_id: int, plan_year: int) -> Set[str]:
    rows = await KuaioaDeptTrainingApplication.filter(
        tenant_id=tenant_id,
        plan_year=plan_year,
        status="approved",
        deleted_at__isnull=True,
    ).values_list("department_name", flat=True)
    return {(str(name or "").strip()) for name in rows if str(name or "").strip()}


async def filter_dept_application_window_recipient_ids(
    tenant_id: int,
    plan_year: int,
    candidate_user_ids: List[int],
) -> List[int]:
    """R-12 #10：该部门申请已批准则不再接收 11 月窗口提醒。"""
    if not candidate_user_ids:
        return []
    approved_depts = await _approved_dept_names_for_year(tenant_id, plan_year)
    if not approved_depts:
        return candidate_user_ids

    users = await User.filter(
        tenant_id=tenant_id,
        id__in=candidate_user_ids,
        is_active=True,
        deleted_at__isnull=True,
    ).all()
    dept_ids = sorted({int(u.department_id) for u in users if u.department_id})
    dept_name_by_id: dict[int, str] = {}
    if dept_ids:
        dept_rows = await Department.filter(
            tenant_id=tenant_id, id__in=dept_ids, deleted_at__isnull=True
        ).values("id", "name")
        dept_name_by_id = {int(r["id"]): str(r["name"] or "").strip() for r in dept_rows}

    filtered: List[int] = []
    for user in users:
        dept_name = dept_name_by_id.get(int(user.department_id or 0), "")
        if dept_name and dept_name in approved_depts:
            continue
        filtered.append(int(user.id))
    return filtered


async def resolve_dept_application_window_recipient_ids(tenant_id: int) -> List[int]:
    """从业务配置读取部门申请窗口固定接收人。"""
    cfg = await BusinessConfigService().get_business_config(tenant_id)
    notifications = (cfg.get("parameters") or {}).get("notifications") or {}
    rules = notifications.get("rules") if isinstance(notifications, dict) else None
    if not isinstance(rules, list):
        return []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if str(rule.get("trigger_document") or "").strip() != DOC_TRAINING:
            continue
        if str(rule.get("trigger_action") or "").strip() != ACTION_DEPT_APPLICATION_WINDOW:
            continue
        if rule.get("enabled") is False:
            continue
        ids = _normalize_user_ids(rule.get("recipient_user_ids"))
        if not ids:
            ids = _normalize_user_ids(rule.get("form_notify_default_user_ids"))
        return ids
    return []


async def _user_ids_by_department_names(tenant_id: int, department_names: Set[str]) -> List[int]:
    if not department_names:
        return []
    dept_rows = await Department.filter(
        tenant_id=tenant_id, name__in=list(department_names), deleted_at__isnull=True
    ).all()
    dept_ids = [int(d.id) for d in dept_rows]
    if not dept_ids:
        return []
    users = await User.filter(
        tenant_id=tenant_id,
        department_id__in=dept_ids,
        is_active=True,
        deleted_at__isnull=True,
    ).all()
    return sorted({int(u.id) for u in users})


async def notify_annual_plan_distributed(tenant_id: int, plan: KuaioaTrainingPlan) -> int:
    """计划批准下发后通知申请部门与体系部门人员查阅。"""
    plan_year = int(plan.plan_year or 0)
    if plan_year <= 0:
        return 0

    dept_names: Set[str] = {SYSTEM_DEPT_RECIPIENT_NAME}
    apps = await KuaioaDeptTrainingApplication.filter(
        tenant_id=tenant_id,
        plan_year=plan_year,
        deleted_at__isnull=True,
        status__in=["approved", "submitted", "pending"],
    ).all()
    for app in apps:
        name = (app.department_name or "").strip()
        if name:
            dept_names.add(name)

    recipient_ids = await _user_ids_by_department_names(tenant_id, dept_names)
    if plan.applicant_id:
        recipient_ids = sorted(set(recipient_ids) | {int(plan.applicant_id)})

    if not recipient_ids:
        logger.warning(
            "年度培训计划下发无接收人 tenant={} plan={} year={} depts={}",
            tenant_id,
            plan.id,
            plan_year,
            sorted(dept_names),
        )
        return 0

    detail_path = "/apps/kuaioa/hr/training-plans"
    return await dispatch_kuaioa_training_notification(
        tenant_id,
        trigger_action=ACTION_ANNUAL_PLAN_DISTRIBUTED,
        variables={
            "plan_year": plan_year,
            "plan_code": plan.plan_code,
            "plan_name": plan.plan_name,
            "detail_path": detail_path,
        },
        context={"form_notify_user_ids": recipient_ids},
    )
