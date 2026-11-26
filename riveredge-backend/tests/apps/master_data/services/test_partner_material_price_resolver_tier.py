"""有数量时价本标准价不得短路阶梯价。"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from apps.master_data.schemas.partner_price_book_schemas import PartnerPriceResolveResponse
from apps.master_data.services.partner_material_price_resolver import PartnerMaterialPriceResolver


@pytest.mark.asyncio
async def test_book_standard_before_tier_still_hits_tier_when_quantity_present():
    """配置顺序为标准→阶梯时，有数量应一次 auto 命中阶梯，而不是先返回标准价。"""
    book_resp = PartnerPriceResolveResponse(
        found=True,
        unit_price=Decimal("1.1"),
        tax_rate=Decimal("13"),
        price_source="book_tier",
        material_id=10,
    )
    resolve_mock = AsyncMock(return_value=book_resp)

    with (
        patch(
            "apps.master_data.services.partner_material_price_resolver.get_partner_price_resolution_order",
            new=AsyncMock(return_value=["book_standard", "book_tier"]),
        ),
        patch(
            "apps.master_data.services.partner_material_price_resolver.PartnerPriceBookService.resolve",
            new=resolve_mock,
        ),
        patch(
            "apps.master_data.services.partner_material_price_resolver.Material.filter",
            new=lambda **_kwargs: type("Q", (), {"first": AsyncMock(return_value=None)})(),
        ),
        patch(
            "apps.master_data.services.partner_price_book_service.PartnerPriceBookService._get_partner_alias",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await PartnerMaterialPriceResolver.resolve(
            tenant_id=1,
            side="sales",
            partner_id=2,
            material_id=10,
            quantity=Decimal("200"),
        )

    assert result.found is True
    assert result.unit_price == Decimal("1.1")
    assert result.price_source == "book_tier"
    assert resolve_mock.await_count == 1
    req = resolve_mock.await_args.args[2]
    assert req.resolve_mode == "auto"
    assert req.quantity == Decimal("200")


@pytest.mark.asyncio
async def test_book_without_quantity_uses_standard_only():
    book_resp = PartnerPriceResolveResponse(
        found=True,
        unit_price=Decimal("2"),
        price_source="book_standard",
        material_id=10,
    )
    resolve_mock = AsyncMock(return_value=book_resp)

    with (
        patch(
            "apps.master_data.services.partner_material_price_resolver.get_partner_price_resolution_order",
            new=AsyncMock(return_value=["book_standard", "book_tier"]),
        ),
        patch(
            "apps.master_data.services.partner_material_price_resolver.PartnerPriceBookService.resolve",
            new=resolve_mock,
        ),
        patch(
            "apps.master_data.services.partner_material_price_resolver.Material.filter",
            new=lambda **_kwargs: type("Q", (), {"first": AsyncMock(return_value=None)})(),
        ),
        patch(
            "apps.master_data.services.partner_price_book_service.PartnerPriceBookService._get_partner_alias",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await PartnerMaterialPriceResolver.resolve(
            tenant_id=1,
            side="sales",
            partner_id=2,
            material_id=10,
            quantity=None,
        )

    assert result.unit_price == Decimal("2")
    req = resolve_mock.await_args.args[2]
    assert req.resolve_mode == "standard_only"
