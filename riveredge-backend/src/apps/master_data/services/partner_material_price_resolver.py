"""客商 + 物料取价唯一算法（价本 / 最近价 / 物料默认）。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Literal, Optional

from apps.master_data.models.material import Material
from apps.master_data.schemas.partner_price_book_schemas import PartnerPriceResolveRequest
from apps.master_data.services.partner_price_book_service import PartnerPriceBookService
from apps.master_data.services.partner_price_resolution_config import get_partner_price_resolution_order
from apps.master_data.services.partner_material_price_defaults import (
    material_default_tax_rate,
    resolve_material_default_unit_price,
)
from apps.kuaizhizao.services.partner_material_price_trend_service import PartnerMaterialPriceTrendService

Side = Literal["purchase", "sales"]


@dataclass
class PartnerMaterialPriceResult:
    found: bool
    unit_price: Decimal
    tax_rate: Optional[Decimal] = None
    price_source: Optional[str] = None
    currency_code: Optional[str] = None
    partner_material_code: Optional[str] = None
    partner_material_name: Optional[str] = None


class PartnerMaterialPriceResolver:
    _trend = PartnerMaterialPriceTrendService()

    @classmethod
    async def resolve(
        cls,
        tenant_id: int,
        side: Side,
        partner_id: int,
        material_id: int,
        *,
        quantity: Optional[Decimal] = None,
        as_of: Optional[date] = None,
        variant_attributes: Optional[Dict[str, Any]] = None,
    ) -> PartnerMaterialPriceResult:
        partner_type = "customer" if side == "sales" else "supplier"
        order = await get_partner_price_resolution_order(tenant_id, side)
        as_of = as_of or date.today()
        qty = Decimal(str(quantity)) if quantity is not None else None
        # 价本标准价与阶梯价属于同一本：有数量时按 auto（命中阶梯优先，否则标准价），
        # 禁止 book_standard 先命中后永远跳过 book_tier。
        book_consumed = False
        alias_code: Optional[str] = None
        alias_name: Optional[str] = None

        async def ensure_alias() -> None:
            """最近价/物料默认价提前返回时也须带上编号映射，否则新建单据明细客户料号空白。"""
            nonlocal alias_code, alias_name
            if alias_code or alias_name:
                return
            alias = await PartnerPriceBookService._get_partner_alias(
                tenant_id, partner_type, partner_id, material_id
            )
            if alias:
                alias_code = alias.code
                alias_name = alias.name

        async def attach_alias(res: PartnerMaterialPriceResult) -> PartnerMaterialPriceResult:
            await ensure_alias()
            ac = res.partner_material_code or alias_code
            an = res.partner_material_name or alias_name
            if ac == res.partner_material_code and an == res.partner_material_name:
                return res
            return replace(
                res,
                partner_material_code=ac,
                partner_material_name=an,
            )

        for step in order:
            if step == "recent":
                recent, recent_tax = await cls._resolve_recent(
                    tenant_id, side, partner_id, material_id
                )
                if recent is not None and recent > 0:
                    return await attach_alias(
                        PartnerMaterialPriceResult(
                            found=True,
                            unit_price=recent,
                            tax_rate=recent_tax,
                            price_source="recent",
                        )
                    )
            elif step in ("book_standard", "book_tier"):
                if book_consumed:
                    continue
                if step == "book_tier" and (qty is None or qty <= 0):
                    # 无数量时阶梯位跳过，留给后续标准价位
                    continue
                book_consumed = True
                resolve_mode = (
                    "auto" if qty is not None and qty > 0 else "standard_only"
                )
                book = await PartnerPriceBookService.resolve(
                    tenant_id,
                    partner_type,
                    PartnerPriceResolveRequest(
                        partner_id=partner_id,
                        material_id=material_id,
                        variant_attributes=variant_attributes,
                        as_of=as_of,
                        quantity=qty,
                        resolve_mode=resolve_mode,
                    ),
                )
                if book.partner_material_code:
                    alias_code = book.partner_material_code
                if book.partner_material_name:
                    alias_name = book.partner_material_name
                if book.found and book.unit_price is not None and book.unit_price > 0:
                    return await attach_alias(
                        PartnerMaterialPriceResult(
                            found=True,
                            unit_price=book.unit_price,
                            tax_rate=book.tax_rate,
                            price_source=book.price_source or "book_standard",
                            currency_code=book.currency_code,
                            partner_material_code=book.partner_material_code,
                            partner_material_name=book.partner_material_name,
                        )
                    )

        material = await Material.filter(
            tenant_id=tenant_id, id=material_id, deleted_at__isnull=True
        ).first()
        if material:
            mat_price = resolve_material_default_unit_price(material.defaults, side, qty)
            if mat_price is not None and mat_price > 0:
                return await attach_alias(
                    PartnerMaterialPriceResult(
                        found=True,
                        unit_price=mat_price,
                        tax_rate=material_default_tax_rate(material.defaults or {}),
                        price_source="material_default",
                    )
                )

        return await attach_alias(
            PartnerMaterialPriceResult(found=False, unit_price=Decimal("0"))
        )

    @classmethod
    async def _resolve_recent(
        cls,
        tenant_id: int,
        side: Side,
        partner_id: int,
        material_id: int,
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """返回 (未税单价, 税率%)。采购订单行单价已是未税。"""
        if side == "sales":
            return await cls._trend.get_latest_sales_exclusive_unit_price(
                tenant_id, material_id, partner_id
            )
        price = await cls._trend.get_latest_purchase_unit_price(
            tenant_id, material_id, partner_id
        )
        return price, None
