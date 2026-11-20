"""field_permission_resource_registry 单元测试。"""

from core.config.field_permission_resource_registry import (
    FIELD_KIND_AMOUNT,
    FIELD_KIND_PARTY_NAME,
    columns_for_kind,
    field_names_for_resource,
    is_valid_field_policy,
    resolve_policy_kind,
)


def test_unregistered_resource_has_no_fields():
    assert field_names_for_resource("system:user-message") == frozenset()
    assert not is_valid_field_policy("system:user-preference", "amount")


def test_sales_order_has_amount_and_party():
    kinds = field_names_for_resource("kuaizhizao:sales-order")
    assert kinds == frozenset({FIELD_KIND_AMOUNT, FIELD_KIND_PARTY_NAME})
    assert is_valid_field_policy("kuaizhizao:sales-order", "unit_price")
    assert is_valid_field_policy("kuaizhizao:sales-order", "customer_name")


def test_purchase_order_has_amount_and_party():
    kinds = field_names_for_resource("kuaizhizao:purchase-order")
    assert FIELD_KIND_AMOUNT in kinds
    assert FIELD_KIND_PARTY_NAME in kinds
    assert is_valid_field_policy("kuaizhizao:purchase-order", "supplier_name")


def test_outsource_order_amount_only():
    kinds = field_names_for_resource("kuaizhizao:outsource-order")
    assert kinds == frozenset({FIELD_KIND_AMOUNT})
    assert not is_valid_field_policy("kuaizhizao:outsource-order", "customer_name")


def test_outsource_work_order_registered():
    kinds = field_names_for_resource("kuaizhizao:outsource-work-order")
    assert kinds == frozenset({FIELD_KIND_AMOUNT})


def test_outbound_inbound_return_resources():
    assert FIELD_KIND_AMOUNT in field_names_for_resource("kuaizhizao:outbound")
    assert FIELD_KIND_PARTY_NAME in field_names_for_resource("kuaizhizao:sales-return")
    assert FIELD_KIND_AMOUNT in field_names_for_resource("kuaizhizao:inbound")
    assert FIELD_KIND_PARTY_NAME in field_names_for_resource("kuaizhizao:purchase-return")


def test_master_data_material_party_only():
    kinds = field_names_for_resource("master-data:material")
    assert kinds == frozenset({FIELD_KIND_PARTY_NAME})
    assert is_valid_field_policy("master-data:material", "default_supplier_id")
    assert not is_valid_field_policy("master-data:material", "amount")


def test_delivery_notice_registered_amount_and_party():
    kinds = field_names_for_resource("kuaizhizao:delivery-notice")
    assert FIELD_KIND_AMOUNT in kinds
    assert FIELD_KIND_PARTY_NAME in kinds
    assert is_valid_field_policy("kuaizhizao:delivery-notice", "customer_name")


def test_other_expense_and_freight_bill_registered():
    assert FIELD_KIND_AMOUNT in field_names_for_resource("kuaicaiwu:other-expense")
    assert FIELD_KIND_PARTY_NAME in field_names_for_resource("kuaicaiwu:other-expense")
    assert is_valid_field_policy("kuaizhizao:freight-bill", "amount")
    assert is_valid_field_policy("kuaizhizao:warehouse-management-stocktaking", "total_amount")


def test_production_inbound_resource_key_is_inbound():
    kinds = field_names_for_resource("kuaizhizao:inbound")
    assert FIELD_KIND_AMOUNT in kinds
    assert FIELD_KIND_PARTY_NAME in kinds


def test_amount_kind_includes_unit_price():
    cols = columns_for_kind(FIELD_KIND_AMOUNT)
    assert "unit_price" in cols
    assert "total_amount" in cols
    assert resolve_policy_kind("unit_price") == FIELD_KIND_AMOUNT
    assert resolve_policy_kind("party_name") == FIELD_KIND_PARTY_NAME
