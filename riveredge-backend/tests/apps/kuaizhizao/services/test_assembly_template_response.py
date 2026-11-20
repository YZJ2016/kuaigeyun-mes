"""组装模板响应不得把 Tortoise ReverseRelation 交给 Pydantic。"""

import asyncio
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from apps.kuaizhizao.services.assembly_template_service import AssemblyTemplateService


def test_build_response_replaces_reverse_relation_with_loaded_items():
    now = datetime(2026, 11, 17, 12, 0, 0)
    template = SimpleNamespace(
        id=12,
        tenant_id=7,
        uuid="template-uuid",
        template_code="ZZMB0012",
        template_name="测试模板",
        product_material_id=101,
        product_material_code="P-101",
        product_material_name="成品",
        base_quantity=Decimal("1"),
        source_type="manual",
        is_active=True,
        total_items=0,
        remarks=None,
        created_at=now,
        updated_at=now,
        created_by=9,
        created_by_name="测试用户",
        items=object(),
    )
    service = AssemblyTemplateService()
    service._load_items = AsyncMock(return_value=[])

    response = asyncio.run(service._build_response(template))

    assert response.id == 12
    assert response.items == []
    service._load_items.assert_awaited_once_with(7, 12)
