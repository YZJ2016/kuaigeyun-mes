"""最低工资配置服务。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from tortoise.transactions import in_transaction

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
        ).order_by("-is_current", "-effective_date", "-id")
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
        try:
            eff = parse_optional_date(data.effective_date)
            end = parse_optional_date(data.end_date)
        except ValueError as exc:
            raise BusinessLogicError(str(exc)) from exc
        if not eff:
            raise BusinessLogicError("执行开始时间无效")
        if end and end < eff:
            raise BusinessLogicError("执行结束时间不能早于执行开始时间")
        if Decimal(str(data.amount)) <= 0:
            raise BusinessLogicError("金额须大于 0")
        is_current = bool(data.is_current)
        payload: dict[str, Any] = {
            "tenant_id": tenant_id,
            "amount": data.amount,
            "effective_date": eff,
            "end_date": end,
            "is_current": is_current,
            "notes": data.notes,
        }
        await apply_create_audit_by_user_id(payload, user_id)
        async with in_transaction():
            if is_current:
                await KuaioaMinimumWageConfig.filter(
                    tenant_id=tenant_id,
                    is_current=True,
                    deleted_at__isnull=True,
                ).update(is_current=False)
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
            try:
                eff = parse_optional_date(payload["effective_date"])
            except ValueError as exc:
                raise BusinessLogicError(str(exc)) from exc
            if not eff:
                raise BusinessLogicError("执行开始时间无效")
            payload["effective_date"] = eff
        if "end_date" in payload:
            try:
                payload["end_date"] = parse_optional_date(payload["end_date"])
            except ValueError as exc:
                raise BusinessLogicError(str(exc)) from exc
        if "amount" in payload and (
            payload["amount"] is None or Decimal(str(payload["amount"])) <= 0
        ):
            raise BusinessLogicError("金额须大于 0")
        if "is_current" in payload and payload["is_current"] is not None:
            payload["is_current"] = bool(payload["is_current"])
        final_eff = payload.get("effective_date", row.effective_date)
        final_end = payload["end_date"] if "end_date" in payload else row.end_date
        if final_end and final_eff and final_end < final_eff:
            raise BusinessLogicError("执行结束时间不能早于执行开始时间")
        async with in_transaction():
            if payload.get("is_current") is True:
                await KuaioaMinimumWageConfig.filter(
                    tenant_id=tenant_id,
                    is_current=True,
                    deleted_at__isnull=True,
                ).exclude(id=row.id).update(is_current=False)
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
                    tenant_id=tenant_id,
                    is_current=True,
                    deleted_at__isnull=True,
                )
                .order_by("-effective_date", "-id")
                .first()
            )
            if row is None:
                row = (
                    await KuaioaMinimumWageConfig.filter(
                        tenant_id=tenant_id, deleted_at__isnull=True
                    )
                    .order_by("-effective_date", "-id")
                    .first()
                )
            return Decimal(str(row.amount)) if row else None
        svc = PayrollSettlementService()
        return await svc._resolve_minimum_wage(tenant_id, year_month)
