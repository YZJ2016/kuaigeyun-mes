"""固定资产类别服务。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from apps.common.audit_actor import apply_create_audit
from apps.kuaicaiwu.models.fixed_asset import FaCategory
from apps.kuaicaiwu.services.fa_core import model_to_dict, touch_updated
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.user import User

# 租户尚无类别时写入的产品默认项（真源；非读侧猜值）
DEFAULT_FA_CATEGORIES: tuple[dict[str, Any], ...] = (
    {"category_code": "BUILDING", "category_name": "房屋建筑物", "useful_life_months": 240},
    {"category_code": "MACHINE", "category_name": "机器设备", "useful_life_months": 120},
    {"category_code": "VEHICLE", "category_name": "运输工具", "useful_life_months": 48},
    {"category_code": "ELECTRONIC", "category_name": "电子设备", "useful_life_months": 36},
    {"category_code": "OFFICE", "category_name": "办公设备", "useful_life_months": 60},
    {"category_code": "OTHER", "category_name": "其他固定资产", "useful_life_months": 60},
)


class FaCategoryService:
    async def ensure_default_categories(self, tenant_id: int, user: User) -> int:
        """若租户尚无任何资产类别，写入产品默认类别；已有数据则不改动。"""
        exists = await FaCategory.filter(tenant_id=tenant_id, deleted_at__isnull=True).exists()
        if exists:
            return 0
        created = 0
        for item in DEFAULT_FA_CATEGORIES:
            await self.create_category(tenant_id, dict(item), user)
            created += 1
        return created

    async def list_categories(
        self,
        tenant_id: int,
        *,
        keyword: Optional[str] = None,
        is_active: Optional[bool] = None,
        ensure_defaults: bool = False,
        user: Optional[User] = None,
    ) -> list[dict[str, Any]]:
        if ensure_defaults and user is not None:
            await self.ensure_default_categories(tenant_id, user)
        q = FaCategory.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if is_active is not None:
            q = q.filter(is_active=is_active)
        if keyword and keyword.strip():
            from tortoise.expressions import Q

            term = keyword.strip()
            q = q.filter(Q(category_code__icontains=term) | Q(category_name__icontains=term))
        rows = await q.order_by("category_code", "id")
        return [model_to_dict(r) for r in rows]

    async def get_category(self, tenant_id: int, category_id: int) -> dict[str, Any]:
        row = await FaCategory.get_or_none(
            id=category_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("资产类别不存在")
        return model_to_dict(row)

    async def create_category(
        self, tenant_id: int, data: dict[str, Any], user: User
    ) -> dict[str, Any]:
        code = (data.get("category_code") or "").strip()
        name = (data.get("category_name") or "").strip()
        if not code or not name:
            raise ValidationError("类别编码与名称必填")
        exists = await FaCategory.filter(
            tenant_id=tenant_id, category_code=code, deleted_at__isnull=True
        ).exists()
        if exists:
            raise ValidationError(f"类别编码 {code} 已存在")
        payload = {
            "tenant_id": tenant_id,
            "category_code": code,
            "category_name": name,
            "depreciation_method": data.get("depreciation_method") or "straight_line",
            "useful_life_months": int(data.get("useful_life_months") or 60),
            "residual_rate": Decimal(str(data.get("residual_rate") or "0.05")),
            "asset_account_code": data.get("asset_account_code") or "1601",
            "accumulated_depreciation_account_code": data.get(
                "accumulated_depreciation_account_code"
            )
            or "1602",
            "expense_account_code": data.get("expense_account_code") or "6602",
            "is_active": data.get("is_active") if data.get("is_active") is not None else True,
            "notes": data.get("notes"),
        }
        apply_create_audit(payload, user)
        row = await FaCategory.create(**payload)
        return model_to_dict(row)

    async def update_category(
        self, tenant_id: int, category_id: int, data: dict[str, Any], user: User
    ) -> dict[str, Any]:
        row = await FaCategory.get_or_none(
            id=category_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("资产类别不存在")
        for key in (
            "category_name",
            "depreciation_method",
            "useful_life_months",
            "residual_rate",
            "asset_account_code",
            "accumulated_depreciation_account_code",
            "expense_account_code",
            "is_active",
            "notes",
        ):
            if key in data and data[key] is not None:
                if key == "residual_rate":
                    setattr(row, key, Decimal(str(data[key])))
                elif key == "useful_life_months":
                    setattr(row, key, int(data[key]))
                else:
                    setattr(row, key, data[key])
        await touch_updated(row, user)
        await row.save()
        return model_to_dict(row)

    async def delete_category(self, tenant_id: int, category_id: int, user: User) -> None:
        row = await FaCategory.get_or_none(
            id=category_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("资产类别不存在")
        from apps.kuaicaiwu.models.fixed_asset import FaAsset

        in_use = await FaAsset.filter(
            tenant_id=tenant_id, category_id=category_id, deleted_at__isnull=True
        ).exists()
        if in_use:
            raise BusinessLogicError("类别已被资产引用，不可删除")
        row.deleted_at = resolve_business_datetime()
        await touch_updated(row, user)
        await row.save()
