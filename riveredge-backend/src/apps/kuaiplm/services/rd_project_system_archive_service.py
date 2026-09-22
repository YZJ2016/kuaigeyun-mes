"""研发项目体系归档八类服务（R-01 #70）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from tortoise.exceptions import IntegrityError

from apps.kuaiplm.constants.rd_project_system_archive import (
    SYSTEM_ARCHIVE_TOTAL_COUNT,
    SYSTEM_ARCHIVE_TYPE_BY_CODE,
    SYSTEM_ARCHIVE_TYPE_DEFINITIONS,
    SYSTEM_ARCHIVE_UPLOAD_TEMPLATES,
    RdSystemArchiveAcceptanceStatus,
    RdSystemArchiveFillStatus,
)
from apps.kuaiplm.models.rd_project_system_archive import RdProjectSystemArchiveItem
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from core.utils.timezone_utils import resolve_business_datetime


def _type_def(code: str) -> Dict[str, Any]:
    row = SYSTEM_ARCHIVE_TYPE_BY_CODE.get(code)
    if not row:
        raise ValidationError(f"未知归档类型: {code}")
    return row


def _compute_fill_status(row: RdProjectSystemArchiveItem) -> str:
    if row.missing_marked_at is not None:
        return RdSystemArchiveFillStatus.MISSING_MARKED.value
    if row.file_uuid:
        return RdSystemArchiveFillStatus.UPLOADED.value
    if row.linked_target_id or row.linked_target_uuid:
        return RdSystemArchiveFillStatus.LINKED.value
    return RdSystemArchiveFillStatus.EMPTY.value


def _is_filled(fill_status: str) -> bool:
    return fill_status in {
        RdSystemArchiveFillStatus.UPLOADED.value,
        RdSystemArchiveFillStatus.LINKED.value,
    }


def summarize_archive_items(items: List[RdProjectSystemArchiveItem]) -> Dict[str, Any]:
    filled = sum(1 for i in items if _is_filled(_compute_fill_status(i)))
    missing_marked = sum(
        1
        for i in items
        if _compute_fill_status(i) == RdSystemArchiveFillStatus.MISSING_MARKED.value
    )
    accepted = sum(
        1
        for i in items
        if str(i.acceptance_status or "") == RdSystemArchiveAcceptanceStatus.ACCEPTED.value
    )
    pending_acceptance = sum(
        1
        for i in items
        if str(i.acceptance_status or "") == RdSystemArchiveAcceptanceStatus.PENDING.value
    )
    empty = sum(
        1
        for i in items
        if _compute_fill_status(i) == RdSystemArchiveFillStatus.EMPTY.value
    )
    total = SYSTEM_ARCHIVE_TOTAL_COUNT
    return {
        "total": total,
        "filled": filled,
        "empty": empty,
        "missing_marked": missing_marked,
        "accepted": accepted,
        "pending_acceptance": pending_acceptance,
        "complete": filled + missing_marked >= total,
        "all_accepted": accepted >= total,
    }


def item_to_dict(row: RdProjectSystemArchiveItem) -> Dict[str, Any]:
    type_def = SYSTEM_ARCHIVE_TYPE_BY_CODE.get(row.archive_type_code, {})
    fill_status = _compute_fill_status(row)
    template_key = type_def.get("template_key")
    return {
        "id": row.id,
        "uuid": str(row.uuid),
        "tenant_id": row.tenant_id,
        "project_id": row.project_id,
        "archive_type_code": row.archive_type_code,
        "archive_type_name": row.archive_type_name,
        "sort_order": row.sort_order,
        "fill_status": fill_status,
        "modes": list(type_def.get("modes") or []),
        "link_target_types": list(type_def.get("link_target_types") or []),
        "template_key": template_key,
        "upload_template": SYSTEM_ARCHIVE_UPLOAD_TEMPLATES.get(template_key)
        if template_key
        else None,
        "file_uuid": row.file_uuid,
        "file_name": row.file_name,
        "file_url": row.file_url,
        "linked_target_type": row.linked_target_type,
        "linked_target_id": row.linked_target_id,
        "linked_target_uuid": row.linked_target_uuid,
        "linked_target_code": row.linked_target_code,
        "linked_target_name": row.linked_target_name,
        "acceptance_status": row.acceptance_status,
        "acceptance_notes": row.acceptance_notes,
        "accepted_at": row.accepted_at,
        "accepted_by": row.accepted_by,
        "accepted_by_name": row.accepted_by_name,
        "missing_notes": row.missing_notes,
        "missing_marked_at": row.missing_marked_at,
        "missing_marked_by": row.missing_marked_by,
        "missing_marked_by_name": row.missing_marked_by_name,
        "notes": row.notes,
        "updated_by_name": row.updated_by_name,
        "updated_at": row.updated_at,
    }


class RdProjectSystemArchiveService:
    async def seed_for_project(
        self, tenant_id: int, project_id: int, *, actor_id: Optional[int] = None
    ) -> None:
        for type_def in SYSTEM_ARCHIVE_TYPE_DEFINITIONS:
            code = str(type_def["code"])
            exists = await RdProjectSystemArchiveItem.filter(
                tenant_id=tenant_id,
                project_id=project_id,
                archive_type_code=code,
            ).exists()
            if exists:
                continue
            payload: Dict[str, Any] = {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "archive_type_code": code,
                "archive_type_name": str(type_def["name"]),
                "sort_order": int(type_def.get("sort_order") or 0),
            }
            if actor_id is not None:
                from infra.models.user import User

                user = await User.get_or_none(id=actor_id)
                payload["updated_by"] = actor_id
                payload["updated_by_name"] = (
                    getattr(user, "full_name", None) or getattr(user, "username", None)
                    if user
                    else None
                )
            try:
                await RdProjectSystemArchiveItem.create(**payload)
            except IntegrityError:
                continue

    async def list_for_project(self, tenant_id: int, project_id: int) -> Dict[str, Any]:
        rows = await RdProjectSystemArchiveItem.filter(
            tenant_id=tenant_id, project_id=project_id
        ).order_by("sort_order", "id")
        items = [item_to_dict(r) for r in rows]
        if len(items) < SYSTEM_ARCHIVE_TOTAL_COUNT:
            await self.seed_for_project(tenant_id, project_id)
            rows = await RdProjectSystemArchiveItem.filter(
                tenant_id=tenant_id, project_id=project_id
            ).order_by("sort_order", "id")
            items = [item_to_dict(r) for r in rows]
        summary = summarize_archive_items(list(rows))
        return {"items": items, "summary": summary, "templates": SYSTEM_ARCHIVE_UPLOAD_TEMPLATES}

    async def _get_item_or_404(
        self, tenant_id: int, project_id: int, item_id: int
    ) -> RdProjectSystemArchiveItem:
        row = await RdProjectSystemArchiveItem.get_or_none(
            id=item_id, tenant_id=tenant_id, project_id=project_id
        )
        if not row:
            raise NotFoundError("归档条目不存在")
        return row

    async def upload_file(
        self,
        tenant_id: int,
        project_id: int,
        item_id: int,
        *,
        file_uuid: str,
        file_name: Optional[str],
        file_url: Optional[str],
        actor_id: int,
        actor_name: Optional[str],
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        row = await self._get_item_or_404(tenant_id, project_id, item_id)
        type_def = _type_def(row.archive_type_code)
        if "upload" not in (type_def.get("modes") or []):
            raise ValidationError(f"{row.archive_type_name} 不支持上传")
        row.file_uuid = file_uuid.strip()
        row.file_name = file_name
        row.file_url = file_url
        row.linked_target_type = None
        row.linked_target_id = None
        row.linked_target_uuid = None
        row.linked_target_code = None
        row.linked_target_name = None
        row.missing_notes = None
        row.missing_marked_at = None
        row.missing_marked_by = None
        row.missing_marked_by_name = None
        row.fill_status = RdSystemArchiveFillStatus.UPLOADED.value
        if row.acceptance_status == RdSystemArchiveAcceptanceStatus.NONE.value:
            row.acceptance_status = RdSystemArchiveAcceptanceStatus.PENDING.value
        if notes is not None:
            row.notes = notes
        row.updated_by = actor_id
        row.updated_by_name = actor_name
        await row.save()
        return item_to_dict(row)

    async def link_target(
        self,
        tenant_id: int,
        project_id: int,
        item_id: int,
        *,
        linked_target_type: str,
        linked_target_id: Optional[int],
        linked_target_uuid: Optional[str],
        linked_target_code: Optional[str],
        linked_target_name: Optional[str],
        actor_id: int,
        actor_name: Optional[str],
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        row = await self._get_item_or_404(tenant_id, project_id, item_id)
        type_def = _type_def(row.archive_type_code)
        allowed = [str(x) for x in (type_def.get("link_target_types") or [])]
        target_type = linked_target_type.strip()
        if "link" not in (type_def.get("modes") or []):
            raise ValidationError(f"{row.archive_type_name} 不支持关联")
        if target_type not in allowed:
            raise ValidationError(
                f"{row.archive_type_name} 不允许关联类型 {target_type}，允许: {', '.join(allowed)}"
            )
        if not linked_target_id and not linked_target_uuid:
            raise ValidationError("关联目标 ID 或 UUID 至少填一项")
        row.linked_target_type = target_type
        row.linked_target_id = linked_target_id
        row.linked_target_uuid = linked_target_uuid
        row.linked_target_code = linked_target_code
        row.linked_target_name = linked_target_name
        row.file_uuid = None
        row.file_name = None
        row.file_url = None
        row.missing_notes = None
        row.missing_marked_at = None
        row.missing_marked_by = None
        row.missing_marked_by_name = None
        row.fill_status = RdSystemArchiveFillStatus.LINKED.value
        if row.acceptance_status == RdSystemArchiveAcceptanceStatus.NONE.value:
            row.acceptance_status = RdSystemArchiveAcceptanceStatus.PENDING.value
        if notes is not None:
            row.notes = notes
        row.updated_by = actor_id
        row.updated_by_name = actor_name
        await row.save()
        return item_to_dict(row)

    async def mark_missing(
        self,
        tenant_id: int,
        project_id: int,
        item_id: int,
        *,
        missing_notes: str,
        actor_id: int,
        actor_name: Optional[str],
    ) -> Dict[str, Any]:
        row = await self._get_item_or_404(tenant_id, project_id, item_id)
        if not (missing_notes or "").strip():
            raise ValidationError("缺项说明不能为空")
        row.file_uuid = None
        row.file_name = None
        row.file_url = None
        row.linked_target_type = None
        row.linked_target_id = None
        row.linked_target_uuid = None
        row.linked_target_code = None
        row.linked_target_name = None
        row.missing_notes = missing_notes.strip()
        row.missing_marked_at = resolve_business_datetime()
        row.missing_marked_by = actor_id
        row.missing_marked_by_name = actor_name
        row.fill_status = RdSystemArchiveFillStatus.MISSING_MARKED.value
        row.acceptance_status = RdSystemArchiveAcceptanceStatus.NONE.value
        row.updated_by = actor_id
        row.updated_by_name = actor_name
        await row.save()
        return item_to_dict(row)

    async def clear_content(
        self,
        tenant_id: int,
        project_id: int,
        item_id: int,
        *,
        actor_id: int,
        actor_name: Optional[str],
    ) -> Dict[str, Any]:
        row = await self._get_item_or_404(tenant_id, project_id, item_id)
        row.file_uuid = None
        row.file_name = None
        row.file_url = None
        row.linked_target_type = None
        row.linked_target_id = None
        row.linked_target_uuid = None
        row.linked_target_code = None
        row.linked_target_name = None
        row.missing_notes = None
        row.missing_marked_at = None
        row.missing_marked_by = None
        row.missing_marked_by_name = None
        row.fill_status = RdSystemArchiveFillStatus.EMPTY.value
        row.acceptance_status = RdSystemArchiveAcceptanceStatus.NONE.value
        row.acceptance_notes = None
        row.accepted_at = None
        row.accepted_by = None
        row.accepted_by_name = None
        row.updated_by = actor_id
        row.updated_by_name = actor_name
        await row.save()
        return item_to_dict(row)

    async def accept_item(
        self,
        tenant_id: int,
        project_id: int,
        item_id: int,
        *,
        acceptance_notes: Optional[str],
        actor_id: int,
        actor_name: Optional[str],
    ) -> Dict[str, Any]:
        row = await self._get_item_or_404(tenant_id, project_id, item_id)
        fill_status = _compute_fill_status(row)
        if not _is_filled(fill_status):
            raise BusinessLogicError("仅已上传或已关联的归档条目可验收确认")
        row.acceptance_status = RdSystemArchiveAcceptanceStatus.ACCEPTED.value
        row.acceptance_notes = acceptance_notes
        row.accepted_at = resolve_business_datetime()
        row.accepted_by = actor_id
        row.accepted_by_name = actor_name
        row.updated_by = actor_id
        row.updated_by_name = actor_name
        await row.save()
        return item_to_dict(row)

    async def reject_item(
        self,
        tenant_id: int,
        project_id: int,
        item_id: int,
        *,
        acceptance_notes: str,
        actor_id: int,
        actor_name: Optional[str],
    ) -> Dict[str, Any]:
        row = await self._get_item_or_404(tenant_id, project_id, item_id)
        if not (acceptance_notes or "").strip():
            raise ValidationError("驳回须填写验收备注")
        row.acceptance_status = RdSystemArchiveAcceptanceStatus.REJECTED.value
        row.acceptance_notes = acceptance_notes.strip()
        row.accepted_at = None
        row.accepted_by = None
        row.accepted_by_name = None
        row.updated_by = actor_id
        row.updated_by_name = actor_name
        await row.save()
        return item_to_dict(row)

    async def load_summaries_for_projects(
        self, tenant_id: int, project_ids: List[int]
    ) -> Dict[int, Dict[str, Any]]:
        if not project_ids:
            return {}
        rows = await RdProjectSystemArchiveItem.filter(
            tenant_id=tenant_id, project_id__in=project_ids
        ).order_by("project_id", "sort_order", "id")
        grouped: Dict[int, List[RdProjectSystemArchiveItem]] = {}
        for row in rows:
            grouped.setdefault(int(row.project_id), []).append(row)
        out: Dict[int, Dict[str, Any]] = {}
        for pid in project_ids:
            items = grouped.get(int(pid), [])
            if len(items) < SYSTEM_ARCHIVE_TOTAL_COUNT:
                await self.seed_for_project(tenant_id, int(pid))
                items = await RdProjectSystemArchiveItem.filter(
                    tenant_id=tenant_id, project_id=int(pid)
                ).order_by("sort_order", "id")
            out[int(pid)] = summarize_archive_items(list(items))
        return out
