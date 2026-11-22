"""销售订单打印：invoice_title 与 customer_name 同一客商名策略。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.models.field_permission_policy import FieldMaskLevel
from core.services.authorization.permission_policy_service import PermissionPolicyService


def _patch_masks(masks: dict):
    return patch.object(
        PermissionPolicyService,
        "get_user_effective_field_masks",
        new=AsyncMock(return_value=masks),
    ), patch.object(
        PermissionPolicyService,
        "_load_tenant_field_alias_map",
        new=AsyncMock(return_value={}),
    )


async def _print_sales(payload: dict, masks: dict):
    from apps.kuaizhizao.services.print_service import DocumentPrintService

    async def _so_format(self, document, i18n):
        return payload

    with _patch_masks(masks)[0], _patch_masks(masks)[1], patch.object(
        DocumentPrintService, "_format_sales_order_data", _so_format
    ), patch(
        "apps.kuaizhizao.services.print_service.SalesOrder.get_or_none",
        new=AsyncMock(return_value=SimpleNamespace()),
    ), patch(
        "apps.kuaizhizao.services.print_service._sales_order_print_allowed",
        return_value=True,
    ), patch(
        "infra.services.business_config_service.BusinessConfigService"
    ) as cfg:
        cfg.return_value.get_sales_require_audit_before_print = AsyncMock(return_value=False)
        return await DocumentPrintService()._get_document_data(
            1, "sales_order", 9, i18n=SimpleNamespace(), viewer_user_id=7
        )


@pytest.mark.asyncio
async def test_hidden_customer_name_also_hides_invoice_title():
    masks = {
        "kuaizhizao:sales-order": {
            "customer_name": FieldMaskLevel.HIDDEN,
            "party_name": FieldMaskLevel.HIDDEN,
        }
    }
    hidden = await _print_sales(
        {
            "customer_name": "秘密客户",
            "invoice_title": "秘密客户",
            "order_code": "SO-9",
        },
        masks,
    )
    assert hidden["order_code"] == "SO-9"
    assert hidden["customer_name"] is None
    assert hidden["invoice_title"] is None
    assert "秘密客户" not in str(hidden)

    real_title = await _print_sales(
        {
            "customer_name": "秘密客户",
            "invoice_title": "真实抬头有限公司",
            "order_code": "SO-9",
        },
        masks,
    )
    assert real_title["invoice_title"] is None
    assert "秘密客户" not in str(real_title)
    assert "真实抬头有限公司" not in str(real_title)


@pytest.mark.asyncio
async def test_real_invoice_title_stays_when_customer_name_is_not_hidden():
    masks = {
        "kuaizhizao:sales-order": {
            "customer_name": FieldMaskLevel.FULL,
            "party_name": FieldMaskLevel.FULL,
            "total_amount": FieldMaskLevel.HIDDEN,
        }
    }
    printed = await _print_sales(
        {
            "customer_name": "客户甲",
            "invoice_title": "真实抬头有限公司",
            "total_amount": "500.00",
            "order_code": "SO-1",
        },
        masks,
    )
    assert printed["customer_name"] == "客户甲"
    assert printed["invoice_title"] == "真实抬头有限公司"
    assert printed["total_amount"] is None


@pytest.mark.asyncio
async def test_invoice_title_unchanged_without_hide_policy():
    printed = await _print_sales(
        {
            "customer_name": "客户甲",
            "invoice_title": "真实抬头有限公司",
            "order_code": "SO-1",
        },
        {},
    )
    assert printed["customer_name"] == "客户甲"
    assert printed["invoice_title"] == "真实抬头有限公司"


@pytest.mark.asyncio
async def test_print_without_viewer_keeps_customer_name_and_invoice_title():
    from apps.kuaizhizao.services.print_service import _mask_print_payload_for_viewer

    payload = {
        "customer_name": "秘密客户",
        "invoice_title": "秘密客户",
        "supplier_name": "秘密供应商",
    }
    out = await _mask_print_payload_for_viewer(
        1, None, "kuaizhizao:sales-order", payload
    )
    assert out["customer_name"] == "秘密客户"
    assert out["invoice_title"] == "秘密客户"
    assert out["supplier_name"] == "秘密供应商"
