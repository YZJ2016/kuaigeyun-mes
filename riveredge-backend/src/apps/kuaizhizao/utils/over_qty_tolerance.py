"""物料超收/超发容差解析（物料覆盖组织默认）。"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, Optional, Sequence

from apps.master_data.models.material import Material
from infra.services.business_config_service import BusinessConfigService


def max_allowed(base: Decimal, tolerance_pct: Decimal) -> Decimal:
    """基准数量 × (1 + 容差%/100)。"""
    base_dec = Decimal(str(base or 0))
    if base_dec <= 0:
        return Decimal("0")
    pct = max(Decimal("0"), Decimal(str(tolerance_pct or 0)))
    return base_dec * (Decimal("1") + pct / Decimal("100"))


def _optional_pct(value: object) -> Optional[Decimal]:
    if value is None:
        return None
    dec = Decimal(str(value))
    if dec < 0:
        return Decimal("0")
    if dec > 100:
        return Decimal("100")
    return dec


class OverQtyToleranceResolver:
    """按租户解析物料/组织容差，批量预取避免 N+1。"""

    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = int(tenant_id)
        self._org_receipt_pct: Optional[Decimal] = None
        self._org_issue_ratio: Optional[Decimal] = None
        self._material_receipt: Dict[int, Optional[Decimal]] = {}
        self._material_issue: Dict[int, Optional[Decimal]] = {}

    async def _ensure_org(self) -> None:
        if self._org_receipt_pct is not None:
            return
        svc = BusinessConfigService()
        self._org_receipt_pct = Decimal(
            str(await svc.get_purchase_tolerance_percentage(self.tenant_id))
        )
        self._org_issue_ratio = await svc.get_over_issue_allowance_ratio(self.tenant_id)

    async def preload_materials(self, material_ids: Sequence[int]) -> None:
        await self._ensure_org()
        missing = {
            int(mid)
            for mid in material_ids
            if int(mid) > 0 and int(mid) not in self._material_receipt
        }
        if not missing:
            return
        rows = await Material.filter(
            tenant_id=self.tenant_id,
            id__in=list(missing),
            deleted_at__isnull=True,
        ).all()
        found = {int(row.id): row for row in rows}
        for mid in missing:
            row = found.get(mid)
            self._material_receipt[mid] = _optional_pct(
                getattr(row, "over_receipt_tolerance_pct", None) if row else None
            )
            self._material_issue[mid] = _optional_pct(
                getattr(row, "over_issue_tolerance_pct", None) if row else None
            )

    async def resolve_over_receipt_pct(self, material_id: int) -> Decimal:
        await self.preload_materials([material_id])
        override = self._material_receipt.get(int(material_id))
        if override is not None:
            return override
        return self._org_receipt_pct or Decimal("0")

    async def resolve_over_issue_pct(self, material_id: int) -> Decimal:
        await self.preload_materials([material_id])
        override = self._material_issue.get(int(material_id))
        if override is not None:
            return override
        ratio = self._org_issue_ratio or Decimal("0")
        return ratio * Decimal("100")

    async def resolve_over_issue_ratio(self, material_id: int) -> Decimal:
        pct = await self.resolve_over_issue_pct(material_id)
        return pct / Decimal("100")


def max_remaining_after_tolerance(
    base_quantity: Decimal,
    committed_quantity: Decimal,
    tolerance_pct: Decimal,
) -> Decimal:
    """容差后上限 − 已占用，用于采购/入库剩余可收。"""
    cap = max_allowed(base_quantity, tolerance_pct)
    remaining = cap - Decimal(str(committed_quantity or 0))
    return remaining if remaining > 0 else Decimal("0")


async def max_pushable_with_issue_tolerance(
    tenant_id: int,
    *,
    material_id: int,
    base_pushable: Decimal,
    resolver: Optional[OverQtyToleranceResolver] = None,
) -> tuple[Decimal, Decimal]:
    """销售/领料：在基准可下推量上叠加超发容差。返回 (上限, 容差%)。"""
    svc = resolver or OverQtyToleranceResolver(tenant_id)
    pct = await svc.resolve_over_issue_pct(material_id)
    return max_allowed(base_pushable, pct), pct
