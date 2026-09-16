"""岗位补贴服务。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from apps.kuaioa.models.post_subsidy import KuaioaPostSubsidy
from apps.kuaioa.schemas.post_subsidy import PostSubsidyCreate, PostSubsidyUpdate
from apps.kuaioa.services.kuaioa_list_core import (
    apply_create_audit_by_user_id,
    build_keyword_q,
    generate_daily_code,
    model_to_dict,
    touch_updated,
)
from apps.kuaioa.services.payroll_service import _get_employee, _parse_ym
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

ZERO = Decimal("0")


class PostSubsidyService:
    async def list_rows(
        self,
        tenant_id: int,
        *,
        keyword: Optional[str] = None,
        year_month: Optional[str] = None,
        workshop_name: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        q = KuaioaPostSubsidy.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if year_month:
            q = q.filter(year_month=year_month.strip())
        if workshop_name:
            q = q.filter(workshop_name=workshop_name.strip())
        if keyword:
            q = q.filter(
                build_keyword_q(keyword, "subsidy_code", "employee_name", "item_name")
            )
        rows = await q.order_by("-year_month", "-id")
        return [model_to_dict(r) for r in rows]

    async def get_row(self, tenant_id: int, row_id: int) -> dict[str, Any]:
        row = await KuaioaPostSubsidy.get_or_none(
            id=row_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("岗位补贴不存在")
        return model_to_dict(row)

    async def create_row(
        self, tenant_id: int, data: PostSubsidyCreate, user_id: int
    ) -> dict[str, Any]:
        ym = _parse_ym(data.year_month)
        if Decimal(str(data.amount)) <= ZERO:
            raise BusinessLogicError("金额须大于 0")
        emp = await _get_employee(tenant_id, data.employee_id)
        code = await generate_daily_code(
            KuaioaPostSubsidy, tenant_id, "PSB", code_field="subsidy_code"
        )
        payload: dict[str, Any] = {
            "tenant_id": tenant_id,
            "subsidy_code": code,
            "year_month": ym,
            "employee_id": int(emp.id),
            "employee_code": emp.employee_code,
            "employee_name": emp.full_name,
            "workshop_name": emp.workshop_name,
            "item_name": data.item_name.strip(),
            "amount": data.amount,
            "notes": data.notes,
        }
        await apply_create_audit_by_user_id(payload, user_id)
        row = await KuaioaPostSubsidy.create(**payload)
        return model_to_dict(row)

    async def update_row(
        self, tenant_id: int, row_id: int, data: PostSubsidyUpdate, user_id: int
    ) -> dict[str, Any]:
        row = await KuaioaPostSubsidy.get_or_none(
            id=row_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("岗位补贴不存在")
        payload = data.model_dump(exclude_unset=True)
        if "amount" in payload and Decimal(str(payload["amount"])) <= ZERO:
            raise BusinessLogicError("金额须大于 0")
        for k, v in payload.items():
            setattr(row, k, v)
        await touch_updated(row, user_id)
        await row.save()
        return model_to_dict(row)

    async def delete_row(self, tenant_id: int, row_id: int, user_id: int) -> None:
        row = await KuaioaPostSubsidy.get_or_none(
            id=row_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("岗位补贴不存在")
        row.deleted_at = resolve_business_datetime()
        await touch_updated(row, user_id)
        await row.save()
