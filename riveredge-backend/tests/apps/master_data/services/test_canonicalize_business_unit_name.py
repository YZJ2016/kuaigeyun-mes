"""业务单位写入前：编码解析为目录名称。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from apps.master_data.services.sync_association_service import (
    canonicalize_business_unit_name,
    material_snapshot_unit_name,
)


def test_canonicalize_empty_uses_default():
    assert asyncio.run(canonicalize_business_unit_name(1, None)) == "个"
    assert asyncio.run(canonicalize_business_unit_name(1, "  ", default="件")) == "件"


def test_canonicalize_resolves_code_to_name():
    with patch(
        "apps.master_data.services.sync_association_service.resolve_material_base_unit",
        new=AsyncMock(return_value="千克"),
    ):
        assert asyncio.run(canonicalize_business_unit_name(1, "004")) == "千克"


def test_canonicalize_keeps_unknown_raw():
    from infra.exceptions.exceptions import ValidationError

    with patch(
        "apps.master_data.services.sync_association_service.resolve_material_base_unit",
        new=AsyncMock(side_effect=ValidationError("missing")),
    ):
        assert asyncio.run(canonicalize_business_unit_name(1, "自定义袋")) == "自定义袋"


def test_material_snapshot_unit_name_uses_base_unit():
    mat = MagicMock(base_unit="007")
    with patch(
        "apps.master_data.services.sync_association_service.canonicalize_business_unit_name",
        new=AsyncMock(return_value="米"),
    ) as canon:
        assert asyncio.run(material_snapshot_unit_name(1, mat)) == "米"
        canon.assert_awaited_once()
        assert canon.await_args.args[1] == "007"
