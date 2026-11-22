"""字段权限 effective masks：默认 full 与显式收敛合并。"""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.models.field_permission_policy import FieldMaskLevel, FieldPermissionPolicy
from core.services.authorization.permission_policy_service import PermissionPolicyService
INVENTORY_RESOURCE = "kuaizhizao:warehouse-management-inventory"


def test_apply_single_mask_decimal_returns_zero_not_star_string():
    assert PermissionPolicyService._apply_single_mask(
        Decimal("100000.50"), FieldMaskLevel.MASKED
    ) == Decimal("0")
    assert PermissionPolicyService._apply_single_mask(
        "100000.50", FieldMaskLevel.MASKED
    ) == Decimal("0")
    assert PermissionPolicyService._apply_single_mask(42, FieldMaskLevel.MASKED) == 0
    assert PermissionPolicyService._apply_single_mask(
        "客户名称甲", FieldMaskLevel.MASKED
    ) != Decimal("0")


def test_merge_field_mask_levels_picks_strictest():
    nested: dict[str, dict[str, str]] = {
        INVENTORY_RESOURCE: {"total_amount": FieldMaskLevel.FULL},
    }
    PermissionPolicyService._merge_field_mask_levels(
        nested,
        resource=INVENTORY_RESOURCE,
        field="total_amount",
        level=FieldMaskLevel.MASKED,
    )
    assert nested[INVENTORY_RESOURCE]["total_amount"] == FieldMaskLevel.MASKED

    PermissionPolicyService._merge_field_mask_levels(
        nested,
        resource=INVENTORY_RESOURCE,
        field="total_amount",
        level=FieldMaskLevel.FULL,
    )
    assert nested[INVENTORY_RESOURCE]["total_amount"] == FieldMaskLevel.MASKED

    PermissionPolicyService._merge_field_mask_levels(
        nested,
        resource=INVENTORY_RESOURCE,
        field="total_amount",
        level=FieldMaskLevel.HIDDEN,
    )
    assert nested[INVENTORY_RESOURCE]["total_amount"] == FieldMaskLevel.HIDDEN


def test_get_user_effective_field_masks_defaults_full_without_db_rows():
    async def _run():
        with patch.object(
            PermissionPolicyService,
            "_collect_user_role_uuids",
            new=AsyncMock(return_value=["role-a"]),
        ), patch.object(
            PermissionPolicyService,
            "_load_tenant_field_alias_map",
            new=AsyncMock(return_value={}),
        ), patch.object(
            PermissionPolicyService,
            "_collect_user_granted_field_policy_resources",
            new=AsyncMock(return_value={INVENTORY_RESOURCE}),
        ), patch.object(
            FieldPermissionPolicy,
            "filter",
            return_value=MagicMock(all=AsyncMock(return_value=[])),
        ):
            return await PermissionPolicyService.get_user_effective_field_masks(
                tenant_id=1,
                user_id=99,
            )

    masks = asyncio.run(_run())
    assert masks[INVENTORY_RESOURCE]["total_amount"] == FieldMaskLevel.FULL
    assert masks[INVENTORY_RESOURCE]["amount"] == FieldMaskLevel.FULL


def test_resource_keys_from_permission_codes():
    keys = PermissionPolicyService._resource_keys_from_permission_codes(
        [
            "kuaizhizao:sales-order:read",
            "kuaizhizao:sales-order:update",
            "system:menu",
            "",
        ]
    )
    assert keys == {"kuaizhizao:sales-order"}


def test_resource_keys_with_only_display_action():
    only = PermissionPolicyService._resource_keys_with_only_display_action(
        [
            "kuaizhizao:demand:display",
            "kuaizhizao:sales-order:read",
            "kuaizhizao:sales-order:display",
            "master-data:material:update",
        ]
    )
    assert only == {"kuaizhizao:demand"}


def test_collect_user_granted_field_policy_resources_excludes_display_only():
    async def _run():
        from core.services.authorization.effective_access_service import (
            EffectiveUserAccess,
        )

        access = EffectiveUserAccess(
            user_id=1,
            tenant_id=1,
            roles=(),
            permission_codes=frozenset(
                {
                    "kuaizhizao:demand:display",
                    "kuaizhizao:sales-order:read",
                }
            ),
            role_resource_keys={"r1": frozenset({"kuaizhizao:demand", "kuaizhizao:sales-order"})},
            is_admin_bypass=False,
        )
        with patch(
            "core.services.authorization.effective_access_service.EffectiveAccessService.get",
            new=AsyncMock(return_value=access),
        ), patch.object(
            PermissionPolicyService,
            "_collect_allowed_function_resources",
            new=AsyncMock(
                return_value={"kuaizhizao:demand", "kuaizhizao:sales-order"}
            ),
        ):
            return await PermissionPolicyService._collect_user_granted_field_policy_resources(
                tenant_id=1,
                user_id=1,
            )

    resources = asyncio.run(_run())
    assert resources == {"kuaizhizao:sales-order"}


def test_get_user_effective_field_masks_resource_filter_uses_lean_grant_check():
    async def _run():
        collect_all = AsyncMock(return_value={INVENTORY_RESOURCE})
        with patch.object(
            PermissionPolicyService,
            "_collect_user_role_uuids",
            new=AsyncMock(return_value=["role-a"]),
        ), patch.object(
            PermissionPolicyService,
            "_load_tenant_field_alias_map",
            new=AsyncMock(return_value={}),
        ), patch.object(
            PermissionPolicyService,
            "_user_has_granted_function_resource",
            new=AsyncMock(return_value=True),
        ) as has_resource, patch.object(
            PermissionPolicyService,
            "_collect_user_granted_field_policy_resources",
            new=collect_all,
        ), patch.object(
            FieldPermissionPolicy,
            "filter",
            return_value=MagicMock(
                filter=MagicMock(
                    return_value=MagicMock(all=AsyncMock(return_value=[]))
                ),
                all=AsyncMock(return_value=[]),
            ),
        ):
            masks = await PermissionPolicyService.get_user_effective_field_masks(
                tenant_id=1,
                user_id=99,
                resource="kuaizhizao:sales-order",
            )
            return masks, has_resource, collect_all

    masks, has_resource, collect_all = asyncio.run(_run())
    has_resource.assert_awaited_once()
    collect_all.assert_not_awaited()
    assert "kuaizhizao:sales-order" in masks


def test_get_user_effective_field_masks_resource_filter_empty_when_ungranted():
    async def _run():
        with patch.object(
            PermissionPolicyService,
            "_collect_user_role_uuids",
            new=AsyncMock(return_value=["role-a"]),
        ), patch.object(
            PermissionPolicyService,
            "_load_tenant_field_alias_map",
            new=AsyncMock(return_value={}),
        ), patch.object(
            PermissionPolicyService,
            "_user_has_granted_function_resource",
            new=AsyncMock(return_value=False),
        ), patch.object(
            FieldPermissionPolicy,
            "filter",
            return_value=MagicMock(
                filter=MagicMock(
                    return_value=MagicMock(all=AsyncMock(return_value=[]))
                ),
                all=AsyncMock(return_value=[]),
            ),
        ):
            return await PermissionPolicyService.get_user_effective_field_masks(
                tenant_id=1,
                user_id=99,
                resource="kuaizhizao:sales-order",
            )

    masks = asyncio.run(_run())
    assert masks == {}


def _amount_hidden(resource: str, *, party: str | None = None) -> dict[str, dict[str, str]]:
    fields = {
        "amount": FieldMaskLevel.HIDDEN,
        "total_amount": FieldMaskLevel.HIDDEN,
        "unit_price": FieldMaskLevel.HIDDEN,
        "tax_amount": FieldMaskLevel.HIDDEN,
        "price": FieldMaskLevel.HIDDEN,
    }
    if party:
        fields[party] = FieldMaskLevel.HIDDEN
        fields["party_name"] = FieldMaskLevel.HIDDEN
    return {resource: fields}


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


@pytest.mark.asyncio
async def test_purchase_order_read_hides_supplier_and_amounts():
    from apps.kuaizhizao.api.purchases.purchases import mask_purchase_order_read_payload

    secret_supplier = "秘密供应商"
    header_amount = "8800.50"
    line_price = "12.50"
    line_total = "25.00"
    rows = [
        {
            "supplier_name": secret_supplier,
            "order_code": "PO-1",
            "total_amount": header_amount,
            "net_amount": "8000.00",
            "items": [
                {
                    "material_name": "螺丝",
                    "unit_price": line_price,
                    "display_unit_price": "13.00",
                    "total_price": line_total,
                    "ordered_quantity": "2",
                }
            ],
        }
    ]
    summary = {
        "active_count": 4,
        "total_amount": 8800.5,
        "annual_total_amount": 8800.5,
        "monthly_arrival_rate": 80.0,
        "trends": {"arrival_rate": [80.0], "annual_total": [1000.0, 7800.5]},
    }
    masks = _amount_hidden("kuaizhizao:purchase-order", party="supplier_name")
    with _patch_masks(masks)[0], _patch_masks(masks)[1]:
        masked_rows = await mask_purchase_order_read_payload(1, 7, rows)
        masked_summary = await mask_purchase_order_read_payload(1, 7, summary)

    row = masked_rows[0]
    assert row["order_code"] == "PO-1"
    assert row["supplier_name"] is None
    assert row["total_amount"] is None
    assert row["net_amount"] is None
    line = row["items"][0]
    assert line["material_name"] == "螺丝"
    assert line["ordered_quantity"] == "2"
    assert line["unit_price"] is None
    assert line["display_unit_price"] is None
    assert line["total_price"] is None
    blob = str(masked_rows)
    assert secret_supplier not in blob
    assert header_amount not in blob
    assert line_price not in blob
    assert line_total not in blob

    assert masked_summary["active_count"] == 4
    assert masked_summary["monthly_arrival_rate"] == 80.0
    assert masked_summary["trends"]["arrival_rate"] == [80.0]
    assert masked_summary["total_amount"] is None
    assert masked_summary["annual_total_amount"] is None
    assert masked_summary["trends"]["annual_total"] == [None, None]
    assert "8800.5" not in str(masked_summary)
    assert "7800.5" not in str(masked_summary)


@pytest.mark.asyncio
async def test_purchase_order_read_keeps_amounts_without_hide_policy():
    from apps.kuaizhizao.api.purchases.purchases import mask_purchase_order_read_payload

    payload = {
        "supplier_name": "公开供应商",
        "total_amount": "100.00",
        "items": [{"unit_price": "10.00", "total_price": "100.00"}],
    }
    full = {
        "kuaizhizao:purchase-order": {
            "amount": FieldMaskLevel.FULL,
            "total_amount": FieldMaskLevel.FULL,
            "unit_price": FieldMaskLevel.FULL,
            "supplier_name": FieldMaskLevel.FULL,
            "party_name": FieldMaskLevel.FULL,
        }
    }
    with _patch_masks(full)[0], _patch_masks(full)[1]:
        kept = await mask_purchase_order_read_payload(1, 7, payload)
    assert kept["supplier_name"] == "公开供应商"
    assert kept["total_amount"] == "100.00"
    assert kept["items"][0]["total_price"] == "100.00"

    with _patch_masks({})[0], _patch_masks({})[1]:
        untouched = await mask_purchase_order_read_payload(1, 7, payload)
    assert untouched["total_amount"] == "100.00"
    assert untouched["items"][0]["unit_price"] == "10.00"


@pytest.mark.asyncio
async def test_sales_invoice_detail_hides_line_amounts():
    from datetime import date, datetime, timezone

    from apps.kuaicaiwu.api.finance.sales_invoices import _serialize_detail

    item = SimpleNamespace(
        id=1,
        item_name="螺栓",
        spec_model=None,
        unit="个",
        quantity=Decimal("2"),
        unit_price=Decimal("12.50"),
        amount=Decimal("25.00"),
        tax_rate=Decimal("13"),
        tax_amount=Decimal("3.25"),
    )
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    obj = SimpleNamespace(
        id=9,
        tenant_id=1,
        invoice_code="SI1",
        partner_id=3,
        partner_name="客户甲",
        partner_tax_no=None,
        partner_bank_info=None,
        partner_address_phone=None,
        source_document_code="SO1",
        invoice_number="N1",
        invoice_date=date(2026, 1, 2),
        invoice_type="增值税专用发票",
        tax_rate=Decimal("0.13"),
        amount_excluding_tax=Decimal("25.00"),
        tax_amount=Decimal("3.25"),
        total_amount=Decimal("28.25"),
        receivable_id=None,
        receivable_code=None,
        attachment_uuid=None,
        attachments=None,
        description=None,
        tax_period=None,
        invoice_color=None,
        original_invoice_id=None,
        red_flush_invoice_id=None,
        void_reason=None,
        voided_at=None,
        status="未审核",
        created_at=now,
        updated_at=now,
        created_by=1,
        created_by_name="甲",
        updated_by=1,
        updated_by_name="甲",
        items=[item],
        fetch_related=AsyncMock(),
    )
    masks = _amount_hidden("kuaicaiwu:sales-invoice")
    masks["kuaicaiwu:sales-invoice"]["customer_name"] = FieldMaskLevel.FULL
    with _patch_masks(masks)[0], _patch_masks(masks)[1]:
        detail = await _serialize_detail(1, 7, obj)
    dumped = detail.model_dump()
    assert dumped["customer_name"] == "客户甲"
    assert dumped["invoice_code"] == "SI1"
    assert dumped["invoice_amount"] is None
    assert dumped["total_amount"] is None
    line = dumped["items"][0]
    assert line["item_name"] == "螺栓"
    assert line["quantity"] == Decimal("2")
    assert line["unit_price"] is None
    assert line["amount"] is None
    assert line["tax_amount"] is None
    text = str(dumped)
    assert "12.50" not in text
    assert "25.00" not in text
    assert "3.25" not in text
    assert "28.25" not in text


@pytest.mark.asyncio
async def test_sales_order_and_purchase_print_hide_party_and_amounts():
    from apps.kuaizhizao.services.print_service import DocumentPrintService

    po_masks = _amount_hidden("kuaizhizao:purchase-order", party="supplier_name")
    so_masks = _amount_hidden("kuaizhizao:sales-order", party="customer_name")

    async def _po_format(self, document, i18n):
        return {
            "supplier_name": "秘密供应商",
            "total_amount": "9999.99",
            "code": "PO-9",
            "items": [
                {"material_code": "M1", "unit_price": "10.50", "total_amount": "21.00"}
            ],
        }

    async def _so_format(self, document, i18n):
        return {
            "customer_name": "秘密客户",
            "total_amount": "500.00",
            "order_code": "SO-9",
            "items": [
                {"material_code": "M2", "unit_price": "5.00", "total_amount": "50.00"}
            ],
        }

    with _patch_masks(po_masks)[0], _patch_masks(po_masks)[1], patch.object(
        DocumentPrintService, "_format_purchase_order_data", _po_format
    ), patch(
        "apps.kuaizhizao.services.print_service.PurchaseOrder.get_or_none",
        new=AsyncMock(return_value=SimpleNamespace()),
    ):
        po = await DocumentPrintService()._get_document_data(
            1, "purchase_order", 9, i18n=SimpleNamespace(), viewer_user_id=7
        )
    assert po["code"] == "PO-9"
    assert po["supplier_name"] is None
    assert po["total_amount"] is None
    assert po["items"][0]["material_code"] == "M1"
    assert po["items"][0]["unit_price"] is None
    assert po["items"][0]["total_amount"] is None
    assert "秘密供应商" not in str(po)
    assert "9999.99" not in str(po)
    assert "10.50" not in str(po)

    with _patch_masks(so_masks)[0], _patch_masks(so_masks)[1], patch.object(
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
        so = await DocumentPrintService()._get_document_data(
            1, "sales_order", 9, i18n=SimpleNamespace(), viewer_user_id=7
        )
    assert so["order_code"] == "SO-9"
    assert so["customer_name"] is None
    assert so["total_amount"] is None
    assert so["items"][0]["unit_price"] is None
    assert so["items"][0]["total_amount"] is None
    assert "秘密客户" not in str(so)
    assert "500.00" not in str(so)
    assert "50.00" not in str(so)
