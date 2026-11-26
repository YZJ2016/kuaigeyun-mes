"""装箱箱规（Packing Profile）服务。"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Dict, List, Optional

from apps.common.base_service import AppBaseService
from apps.kuaizhizao.models.packing_profile import PackingProfile
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import NotFoundError, ValidationError


class PackingProfileService(AppBaseService[PackingProfile]):
    def __init__(self) -> None:
        super().__init__(PackingProfile)

    async def get_effective_profile(
        self,
        tenant_id: int,
        *,
        material_id: Optional[int] = None,
    ) -> PackingProfile:
        if material_id is not None:
            specific = await PackingProfile.get_or_none(
                tenant_id=tenant_id,
                material_id=int(material_id),
                is_active=True,
                deleted_at__isnull=True,
            )
            if specific:
                return specific
        default = await PackingProfile.get_or_none(
            tenant_id=tenant_id,
            material_id__isnull=True,
            profile_code="default",
            is_active=True,
            deleted_at__isnull=True,
        )
        if default:
            return default
        return await self.ensure_tenant_default_profile(tenant_id)

    async def ensure_tenant_default_profile(self, tenant_id: int) -> PackingProfile:
        existing = await PackingProfile.get_or_none(
            tenant_id=tenant_id,
            material_id__isnull=True,
            profile_code="default",
            deleted_at__isnull=True,
        )
        if existing:
            if not existing.is_active:
                existing.is_active = True
                await existing.save()
            return existing
        import uuid

        return await PackingProfile.create(
            tenant_id=tenant_id,
            uuid=str(uuid.uuid4()),
            profile_code="default",
            material_id=None,
            pack_mode="box_first",
            mix_policy="same_material",
            max_quantity=None,
            seal_policy="manual",
            refill_open_box=False,
            require_sealed_for_consume=True,
            allow_manual_box_code=True,
            is_active=True,
        )

    async def list_profiles(self, tenant_id: int) -> List[PackingProfile]:
        return await PackingProfile.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).order_by("material_id", "profile_code")

    async def update_profile(
        self,
        tenant_id: int,
        profile_id: int,
        data: Dict[str, Any],
    ) -> PackingProfile:
        profile = await PackingProfile.get_or_none(
            id=profile_id,
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        )
        if not profile:
            raise NotFoundError(f"装箱箱规不存在: {profile_id}")
        allowed = {
            "pack_mode",
            "mix_policy",
            "max_quantity",
            "seal_policy",
            "refill_open_box",
            "require_sealed_for_consume",
            "allow_manual_box_code",
            "is_active",
        }
        for key, value in data.items():
            if key not in allowed:
                continue
            setattr(profile, key, value)
        await profile.save()
        return profile

    def suggest_cartonization(
        self,
        profile: PackingProfile,
        *,
        line_count: int,
        total_quantity: Decimal,
    ) -> Dict[str, Any]:
        """
        进阶 Cartonization 占位：按 Profile 容量估算箱数，不做体积/重量优化。
        """
        cap = profile.max_quantity
        if cap is None or cap <= Decimal("0"):
            return {
                "suggested_box_count": max(1, line_count),
                "suggested_capacity_per_box": None,
                "algorithm": "profile_capacity_unset",
            }
        cap_d = Decimal(str(cap))
        qty = Decimal(str(total_quantity or 0))
        if qty <= Decimal("0"):
            boxes = 1
        else:
            boxes = max(1, math.ceil(qty / cap_d))
        return {
            "suggested_box_count": boxes,
            "suggested_capacity_per_box": float(cap_d),
            "algorithm": "profile_max_quantity_ceil",
        }
