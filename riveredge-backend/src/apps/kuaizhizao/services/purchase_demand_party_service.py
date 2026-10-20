"""采购询价需方服务"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from tortoise.expressions import Q

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.kuaizhizao.models.purchase_demand_party import PurchaseDemandParty
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User


class PurchaseDemandPartyService:
    async def _allocate_code(self, tenant_id: int) -> str:
        rows = await PurchaseDemandParty.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        ).values_list("code", flat=True)
        max_seq = 0
        for raw in rows:
            code = str(raw or "")
            if not code.startswith("XF"):
                continue
            suffix = code[2:]
            if suffix.isdigit():
                max_seq = max(max_seq, int(suffix))
        return f"XF{max_seq + 1:04d}"

    def _to_dict(self, row: PurchaseDemandParty) -> Dict[str, Any]:
        return {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "code": row.code,
            "name": row.name,
            "contact_name": row.contact_name,
            "contact_phone": row.contact_phone,
            "contact_email": row.contact_email,
            "address": row.address,
            "tax_no": row.tax_no,
            "notes": row.notes,
            "is_active": row.is_active,
            "sort_order": row.sort_order,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    async def list_parties(
        self,
        tenant_id: int,
        *,
        keyword: Optional[str] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 200,
    ) -> Dict[str, Any]:
        q = PurchaseDemandParty.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if is_active is not None:
            q = q.filter(is_active=is_active)
        kw = (keyword or "").strip()
        if kw:
            q = q.filter(
                Q(code__icontains=kw)
                | Q(name__icontains=kw)
                | Q(contact_name__icontains=kw)
                | Q(contact_phone__icontains=kw)
                | Q(contact_email__icontains=kw)
            )
        total = await q.count()
        rows = await q.order_by("sort_order", "code").offset(skip).limit(limit)
        return {
            "data": [self._to_dict(r) for r in rows],
            "total": total,
            "success": True,
        }

    async def get_party(self, tenant_id: int, party_id: int) -> Dict[str, Any]:
        row = await PurchaseDemandParty.get_or_none(
            tenant_id=tenant_id, id=party_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("需方不存在")
        return self._to_dict(row)

    async def create_party(
        self, tenant_id: int, payload: Dict[str, Any], user: User
    ) -> Dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValidationError("需方名称必填")
        code = str(payload.get("code") or "").strip()
        if not code:
            code = await self._allocate_code(tenant_id)
        exists = await PurchaseDemandParty.filter(
            tenant_id=tenant_id, code=code, deleted_at__isnull=True
        ).exists()
        if exists:
            raise ValidationError(f"需方编码 {code} 已存在")
        row = PurchaseDemandParty(
            tenant_id=tenant_id,
            code=code,
            name=name,
            contact_name=(str(payload.get("contact_name") or "").strip() or None),
            contact_phone=(str(payload.get("contact_phone") or "").strip() or None),
            contact_email=(str(payload.get("contact_email") or "").strip() or None),
            address=(str(payload.get("address") or "").strip() or None),
            tax_no=(str(payload.get("tax_no") or "").strip() or None),
            notes=(str(payload.get("notes") or "").strip() or None),
            is_active=bool(payload.get("is_active", True)),
            sort_order=int(payload.get("sort_order") or 0),
        )
        apply_create_audit(row, user)
        await row.save()
        return self._to_dict(row)

    async def update_party(
        self,
        tenant_id: int,
        party_id: int,
        payload: Dict[str, Any],
        user: User,
    ) -> Dict[str, Any]:
        row = await PurchaseDemandParty.get_or_none(
            tenant_id=tenant_id, id=party_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("需方不存在")
        if "name" in payload and payload["name"] is not None:
            name = str(payload["name"]).strip()
            if not name:
                raise ValidationError("需方名称必填")
            row.name = name
        for field in (
            "contact_name",
            "contact_phone",
            "contact_email",
            "address",
            "tax_no",
            "notes",
        ):
            if field in payload:
                raw = payload.get(field)
                setattr(row, field, (str(raw).strip() if raw is not None else "") or None)
        if "is_active" in payload and payload["is_active"] is not None:
            row.is_active = bool(payload["is_active"])
        if "sort_order" in payload and payload["sort_order"] is not None:
            row.sort_order = int(payload["sort_order"])
        apply_update_audit(row, user)
        await row.save()
        return self._to_dict(row)

    async def delete_party(self, tenant_id: int, party_id: int, user: User) -> None:
        row = await PurchaseDemandParty.get_or_none(
            tenant_id=tenant_id, id=party_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("需方不存在")
        row.deleted_at = resolve_business_datetime()
        apply_update_audit(row, user)
        await row.save()
