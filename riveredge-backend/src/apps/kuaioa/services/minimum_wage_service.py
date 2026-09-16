"""最低工资配置服务。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from apps.kuaioa.models.minimum_wage import KuaioaMinimumWageConfig
from apps.kuaioa.schemas.minimum_wage import MinimumWageCreate, MinimumWageUpdate
from apps.kuaioa.services.kuaioa_list_core import (
    apply_create_audit_by_user_id,
    model_to_dict,
    parse_optional_date,
    touch_updated,
)
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError


class MinimumWageService:
    async def list_configs(self, tenant_id: int) -> list[dict[str, Any]]:
        rows = await KuaioaMinimumWageConfig.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        ).order_by("-effective_date", "-id")
        return [model_to_dict(r) for r in rows]

    async def get_config(self, tenant_id: int, config_id: int) -> dict[str, Any]:
        row = await KuaioaMinimumWageConfig.get_or_none(
            id=config_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("最低工资配置不存在")
        return model_to_dict(row)

    async def create_config(
        self, tenant_id: int, data: MinimumWageCreate, user_id: int
    ) -> dict[str, Any]:
        eff = parse_optional_date(data.effective_date)
        if not eff:
            raise BusinessLogicError("生效日期无效")
        if Decimal(str(data.amount)) <= 0:
            raise BusinessLogicError("金额须大于 0")
        payload: dict[str, Any] = {
            "tenant_id": tenant_id,
            "amount": data.amount,
            "effective_date": eff,
            "notes": data.notes,
        }
        await apply_create_audit_by_user_id(payload, user_id)
        row = await KuaioaMinimumWageConfig.create(**payload)
        return model_to_dict(row)

    async def update_config(
        self, tenant_id: int, config_id: int, data: MinimumWageUpdate, user_id: int
    ) -> dict[str, Any]:
        row = await KuaioaMinimumWageConfig.get_or_none(
            id=config_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("最低工资配置不存在")
        payload = data.model_dump(exclude_unset=True)
        if "effective_date" in payload:
            eff = parse_optional_date(payload["effective_date"])
            if not eff:
                raise BusinessLogicError("生效日期无效")
            payload["effective_date"] = eff
        if "amount" in payload and Decimal(str(payload["amount"])) <= 0:
            raise BusinessLogicError("金额须大于 0")
        for k, v in payload.items():
            setattr(row, k, v)
        await touch_updated(row, user_id)
        await row.save()
        return model_to_dict(row)

    async def delete_config(self, tenant_id: int, config_id: int, user_id: int) -> None:
        row = await KuaioaMinimumWageConfig.get_or_none(
            id=config_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("最低工资配置不存在")
        row.deleted_at = resolve_business_datetime()
        await touch_updated(row, user_id)
        await row.save()

    async def current_amount(
        self, tenant_id: int, *, year_month: Optional[str] = None
    ) -> Optional[Decimal]:
        from apps.kuaioa.services.payroll_service import PayrollSettlementService

        if not year_month:
            row = (
                await KuaioaMinimumWageConfig.filter(
                    tenant_id=tenant_id, deleted_at__isnull=True
                )
                .order_by("-effective_date")
                .first()
            )
            return Decimal(str(row.amount)) if row else None
        svc = PayrollSettlementService()
        return await svc._resolve_minimum_wage(tenant_id, year_month)
