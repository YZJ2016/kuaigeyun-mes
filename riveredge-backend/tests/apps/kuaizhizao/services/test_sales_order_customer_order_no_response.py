from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from apps.kuaizhizao.services.sales_order_service import SalesOrderService


def _minimal_order(**overrides):
    base = dict(
        id=1,
        uuid="00000000-0000-0000-0000-000000000001",
        tenant_id=1,
        order_code="XS202611230003",
        order_date=date(2026, 11, 23),
        delivery_date=date(2026, 11, 30),
        customer_id=1,
        customer_name="测试客户",
        customer_contact=None,
        customer_phone=None,
        customer_order_no="XSHT261123-02",
        total_quantity=Decimal("3"),
        total_amount=Decimal("165"),
        status="AUDITED",
        review_status="APPROVED",
        shipping_address=None,
        shipping_method=None,
        payment_terms=None,
        notes=None,
        is_active=True,
        created_by=1,
        created_by_name="admin",
        updated_by=1,
        updated_by_name="admin",
        created_at=date(2026, 11, 23),
        updated_at=date(2026, 11, 23),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_order_to_response_includes_header_customer_order_no():
    svc = SalesOrderService()
    resp = svc._order_to_response(_minimal_order(), items=None, audit_enabled=False)
    assert resp.customer_order_no == "XSHT261123-02"


def test_order_to_response_item_includes_customer_order_no():
    svc = SalesOrderService()
    order = _minimal_order(customer_order_no=None)
    item = SimpleNamespace(
        id=10,
        uuid="00000000-0000-0000-0000-000000000010",
        tenant_id=1,
        sales_order_id=1,
        material_id=1,
        material_code="CP10005",
        material_name="成品5",
        material_spec="590-08",
        material_unit="件",
        order_quantity=Decimal("3"),
        delivery_date=date(2026, 11, 30),
        unit_price=Decimal("50"),
        tax_rate=Decimal("13"),
        total_amount=Decimal("165"),
        delivered_quantity=Decimal("0"),
        remaining_quantity=Decimal("3"),
        delivery_status=None,
        work_order_id=None,
        work_order_code=None,
        customer_order_no="XSHT261123-02",
        is_gift=False,
        gift_ref_unit_price=None,
        price_settlement_status=None,
        provisional_unit_price=None,
        price_settled_at=None,
        price_settled_by=None,
        notes=None,
        variant_attributes=None,
        configurable_selections=None,
        created_at=date(2026, 11, 23),
        updated_at=date(2026, 11, 23),
    )
    resp = svc._order_to_response(order, items=[item], audit_enabled=False)
    assert resp.items is not None
    assert len(resp.items) == 1
    assert resp.items[0].customer_order_no == "XSHT261123-02"