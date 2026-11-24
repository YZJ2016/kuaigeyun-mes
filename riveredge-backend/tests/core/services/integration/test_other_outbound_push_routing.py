"""其他出库外推：表头出库类型与 variant 路由。"""

import pytest
from unittest.mock import AsyncMock, patch

from apps.kuaizhizao.constants.other_outbound_type import (
    OTHER_OUTBOUND_TYPE_ASSET,
    OTHER_OUTBOUND_TYPE_MATERIAL,
)
from apps.master_data.constants.material_inventory_category import INVENTORY_CATEGORY_ASSET
from core.services.integration.kingdee_warehouse_push_routing import (
    OTHER_OUTBOUND_ASSET_KEY,
    OTHER_OUTBOUND_AUXILIARY_KEY,
    OTHER_OUTBOUND_BASE_KEY,
    resolve_other_outbound_push_config,
    resolve_other_outbound_variant_key_from_outbound_type,
)
from infra.exceptions.exceptions import BusinessLogicError


def test_variant_from_outbound_type_asset():
    assert (
        resolve_other_outbound_variant_key_from_outbound_type(OTHER_OUTBOUND_TYPE_ASSET)
        == OTHER_OUTBOUND_ASSET_KEY
    )
    assert resolve_other_outbound_variant_key_from_outbound_type(OTHER_OUTBOUND_TYPE_MATERIAL) is None
    assert resolve_other_outbound_variant_key_from_outbound_type(None) is None


@pytest.mark.asyncio
async def test_resolve_push_config_asset_header():
    warehouse = {
        OTHER_OUTBOUND_BASE_KEY: {"enabled": True, "linetype_number": "010"},
        OTHER_OUTBOUND_ASSET_KEY: {"enabled": True, "linetype_number": "030"},
    }
    with patch(
        "core.services.integration.kingdee_warehouse_push_routing.load_material_inventory_categories",
        new_callable=AsyncMock,
        return_value={1: INVENTORY_CATEGORY_ASSET},
    ):
        cfg = await resolve_other_outbound_push_config(
            1,
            warehouse,
            material_ids=[1],
            outbound_type=OTHER_OUTBOUND_TYPE_ASSET,
        )
    assert cfg.get("linetype_number") == "030"


@pytest.mark.asyncio
async def test_resolve_push_config_legacy_category_infer():
    warehouse = {
        OTHER_OUTBOUND_BASE_KEY: {"enabled": True},
        OTHER_OUTBOUND_ASSET_KEY: {"enabled": True, "billtype_number": "ASSET_BT"},
    }
    with patch(
        "core.services.integration.kingdee_warehouse_push_routing.load_material_inventory_categories",
        new_callable=AsyncMock,
        return_value={9: INVENTORY_CATEGORY_ASSET},
    ):
        cfg = await resolve_other_outbound_push_config(
            1,
            warehouse,
            material_ids=[9],
            outbound_type=None,
        )
    assert cfg.get("billtype_number") == "ASSET_BT"


@pytest.mark.asyncio
async def test_resolve_push_config_material_header_mixed_raises():
    from apps.master_data.constants.material_inventory_category import (
        INVENTORY_CATEGORY_AUXILIARY,
    )

    with patch(
        "core.services.integration.kingdee_warehouse_push_routing.load_material_inventory_categories",
        new_callable=AsyncMock,
        return_value={1: INVENTORY_CATEGORY_ASSET, 2: INVENTORY_CATEGORY_AUXILIARY},
    ):
        with pytest.raises(BusinessLogicError):
            await resolve_other_outbound_push_config(
                1,
                {},
                material_ids=[1, 2],
                outbound_type=OTHER_OUTBOUND_TYPE_MATERIAL,
            )


@pytest.mark.asyncio
async def test_resolve_push_config_material_auxiliary_variant():
    from apps.master_data.constants.material_inventory_category import (
        INVENTORY_CATEGORY_AUXILIARY,
    )

    warehouse = {
        OTHER_OUTBOUND_BASE_KEY: {"enabled": True, "linetype_number": "010"},
        OTHER_OUTBOUND_AUXILIARY_KEY: {"enabled": True, "linetype_number": "020"},
    }
    with patch(
        "core.services.integration.kingdee_warehouse_push_routing.load_material_inventory_categories",
        new_callable=AsyncMock,
        return_value={1: INVENTORY_CATEGORY_AUXILIARY},
    ):
        cfg = await resolve_other_outbound_push_config(
            1,
            warehouse,
            material_ids=[1],
            outbound_type=OTHER_OUTBOUND_TYPE_MATERIAL,
        )
    assert cfg.get("linetype_number") == "020"