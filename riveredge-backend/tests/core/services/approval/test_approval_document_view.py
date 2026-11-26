"""审批关联单据视图：loader 覆盖不得拖垮单条详情；采购申请明细可组成 lines。"""

from decimal import Decimal
from datetime import date

import pytest

from core.services.approval.approval_document_view import (
    DOCUMENT_LOADERS,
    _assert_loader_coverage,
    compose_document_view,
)
from core.services.approval.uni_audit_handlers import HANDLERS


def test_document_loaders_cover_all_handlers() -> None:
    missing = sorted(set(HANDLERS) - set(DOCUMENT_LOADERS))
    assert missing == []
    _assert_loader_coverage()


def test_compose_purchase_request_lines() -> None:
    view = compose_document_view(
        entity_type="purchase_request",
        entity_name="采购申请",
        payload={
            "requisition_code": "PR001",
            "requisition_name": "补料",
            "status": "待审核",
            "applicant_name": "张三",
            "items": [
                {
                    "id": 11,
                    "material_name": "垫片",
                    "material_code": "M-01",
                    "material_spec": "Φ10",
                    "quantity": Decimal("12.5"),
                    "unit": "件",
                    "required_date": date(2026, 11, 1),
                }
            ],
        },
    )
    assert view.code == "PR001"
    assert len(view.lines) == 1
    assert "垫片" in view.lines[0].title
    field_map = {f.key: f.value for f in view.lines[0].fields}
    assert field_map.get("code") == "M-01"
    assert "12.5" in (field_map.get("quantity") or "")


def test_compose_ignores_empty_items_none() -> None:
    view = compose_document_view(
        entity_type="purchase_request",
        entity_name="采购申请",
        payload={"requisition_code": "PR002", "items": None},
    )
    assert view.lines == []


def test_compose_payment_application_lines() -> None:
    """付款申请行以 request_amount/source_code 为主，不能只显示「明细 N」。"""
    view = compose_document_view(
        entity_type="payment_application",
        entity_name="付款申请",
        payload={
            "application_code": "FKSQ202611110003",
            "supplier_name": "淘宝",
            "applicant_name": "程艳",
            "total_request_amount": Decimal("50.44"),
            "remaining_amount": Decimal("50.44"),
            "items": [
                {
                    "id": 1,
                    "source_type": "payable",
                    "source_code": "YF202611110001",
                    "payable_code": "YF202611110001",
                    "line_kind": "goods",
                    "request_amount": Decimal("50.44"),
                    "notes": "货款请款",
                }
            ],
        },
    )
    assert view.code == "FKSQ202611110003"
    assert len(view.lines) == 1
    line = view.lines[0]
    assert line.title == "YF202611110001"
    field_map = {f.key: f.value for f in line.fields}
    assert field_map.get("source_code") == "YF202611110001"
    assert field_map.get("payable_code") == "YF202611110001"
    assert field_map.get("line_kind") == "货款"
    assert field_map.get("amount") == "50.44"
    assert field_map.get("notes") == "货款请款"


def test_compose_other_expense_header_shows_payee_account() -> None:
    view = compose_document_view(
        entity_type="other_expense",
        entity_name="其他费用支出",
        payload={
            "expense_code": "QTFY202611110001",
            "business_date": date(2026, 11, 11),
            "counterparty_name": "某供应商",
            "payment_method": "银行转账",
            "counterparty_account_name": "某某公司",
            "counterparty_bank_name": "工商银行无锡支行",
            "counterparty_bank_account": "6222021234567890",
            "total_amount": Decimal("1000"),
            "items": [
                {
                    "category_name": "交通费",
                    "amount": Decimal("1000"),
                    "gl_account_code": "6601",
                }
            ],
        },
    )
    assert view.code == "QTFY202611110001"
    header_map = {f.key: f.value for f in view.header}
    assert header_map.get("counterparty_account_name") == "某某公司"
    assert header_map.get("counterparty_bank_name") == "工商银行无锡支行"
    assert header_map.get("counterparty_bank_account") == "6222021234567890"
    assert len(view.lines) == 1
    assert view.lines[0].title == "交通费"
    line_fields = {f.key: f.value for f in view.lines[0].fields}
    assert line_fields.get("gl_account_code") == "6601"
    assert line_fields.get("amount") == "1000"


def test_compose_purchase_order_lines_and_header() -> None:
    view = compose_document_view(
        entity_type="purchase_order",
        entity_name="采购订单",
        payload={
            "order_code": "CG202611140001",
            "supplier_name": "某供应商",
            "buyer_name": "采购员甲",
            "order_date": date(2026, 11, 14),
            "payment_terms": "月结30天",
            "estimated_arrival_date": date(2026, 11, 20),
            "items": [
                {
                    "id": 1,
                    "material_code": "M-100",
                    "material_name": "钢板",
                    "material_spec": "10mm",
                    "quantity": Decimal("2"),
                    "unit": "KG",
                    "unit_price": Decimal("50"),
                    "total_price": Decimal("100"),
                    "delivery_date": date(2026, 11, 20),
                    "notes": "急件",
                }
            ],
        },
    )
    assert view.code == "CG202611140001"
    header_map = {f.key: f.value for f in view.header}
    assert header_map.get("supplier_name") == "某供应商"
    assert header_map.get("buyer_name") == "采购员甲"
    assert len(view.lines) == 1
    field_map = {f.key: f.value for f in view.lines[0].fields}
    assert field_map.get("code") == "M-100"
    assert field_map.get("spec") == "10mm"
    assert field_map.get("amount") == "100"
    assert field_map.get("notes") == "急件"


def test_compose_sales_order_lines_and_header() -> None:
    view = compose_document_view(
        entity_type="sales_order",
        entity_name="销售订单",
        payload={
            "order_code": "XS202611140001",
            "customer_name": "某客户",
            "salesman_name": "销售员乙",
            "order_date": date(2026, 11, 14),
            "delivery_date": date(2026, 11, 25),
            "items": [
                {
                    "id": 1,
                    "material_code": "P-01",
                    "material_name": "成品A",
                    "material_spec": "规格1",
                    "quantity": Decimal("10"),
                    "unit": "件",
                    "unit_price": Decimal("88"),
                    "total_price": Decimal("880"),
                }
            ],
        },
    )
    assert view.code == "XS202611140001"
    header_map = {f.key: f.value for f in view.header}
    assert header_map.get("customer_name") == "某客户"
    assert len(view.lines) == 1
    assert view.lines[0].title == "成品A"
    field_map = {f.key: f.value for f in view.lines[0].fields}
    assert field_map.get("amount") == "880"


def test_compose_payment_header_and_pull_lines() -> None:
    view = compose_document_view(
        entity_type="payment",
        entity_name="付款单",
        payload={
            "payment_code": "FK202611140001",
            "supplier_name": "某供应商",
            "payment_date": date(2026, 11, 14),
            "payment_method": "银行转账",
            "total_amount": Decimal("1000"),
            "bank_account": "6222本方账号",
            "counterparty_account_name": "供应商户名",
            "counterparty_bank_account": "6228888888",
            "items": [
                {
                    "id": 1,
                    "source_type": "payable",
                    "source_code": "YF202611140001",
                    "amount": Decimal("1000"),
                }
            ],
        },
    )
    header_map = {f.key: f.value for f in view.header}
    assert header_map.get("supplier_name") == "某供应商"
    assert header_map.get("counterparty_account_name") == "供应商户名"
    assert header_map.get("bank_account") == "6222本方账号"
    assert len(view.lines) == 1
    line_fields = {f.key: f.value for f in view.lines[0].fields}
    assert line_fields.get("source_code") == "YF202611140001"
    assert line_fields.get("amount") == "1000"


def test_compose_receipt_header() -> None:
    view = compose_document_view(
        entity_type="receipt",
        entity_name="收款单",
        payload={
            "receipt_code": "SK202611140001",
            "customer_name": "某客户",
            "receipt_date": date(2026, 11, 14),
            "payment_method": "银行转账",
            "total_amount": Decimal("2000"),
            "bank_account": "本方收款账号",
        },
    )
    header_map = {f.key: f.value for f in view.header}
    assert header_map.get("customer_name") == "某客户"
    assert header_map.get("bank_account") == "本方收款账号"
    assert header_map.get("total_amount") == "2000"


def test_compose_other_income_lines_use_lines_key() -> None:
    view = compose_document_view(
        entity_type="other_income",
        entity_name="其他费用收入",
        payload={
            "income_code": "QTSR202611140001",
            "business_date": date(2026, 11, 14),
            "counterparty_name": "某客户",
            "payment_method": "银行转账",
            "bank_account": "本方账户",
            "total_amount": Decimal("500"),
            "lines": [
                {
                    "category_name": "服务费",
                    "description": "咨询收入",
                    "amount": Decimal("500"),
                    "gl_account_code": "6001",
                }
            ],
        },
    )
    assert view.code == "QTSR202611140001"
    header_map = {f.key: f.value for f in view.header}
    assert header_map.get("counterparty_name") == "某客户"
    assert header_map.get("bank_account") == "本方账户"
    assert len(view.lines) == 1
    assert view.lines[0].title == "服务费"
    fields = {f.key: f.value for f in view.lines[0].fields}
    assert fields.get("description") == "咨询收入"
    assert fields.get("amount") == "500"


def test_compose_payment_application_merges_purchase_detail_lines() -> None:
    view = compose_document_view(
        entity_type="payment_application",
        entity_name="付款申请",
        payload={
            "application_code": "FKSQ002",
            "supplier_name": "供应商A",
            "items": [],
            "purchase_detail_lines": [
                {
                    "purchase_order_code": "CG001",
                    "material_code": "M1",
                    "material_name": "物料1",
                    "material_spec": "S1",
                    "quantity": Decimal("3"),
                    "unit": "件",
                    "unit_price": Decimal("10"),
                    "total_price": Decimal("30"),
                }
            ],
        },
    )
    assert len(view.lines) == 1
    assert view.lines[0].title == "物料1"
    field_map = {f.key: f.value for f in view.lines[0].fields}
    assert field_map.get("purchase_order_code") == "CG001"
    assert field_map.get("code") == "M1"
    assert field_map.get("amount") == "30"


def test_compose_other_expense_uses_lines_collection() -> None:
    view = compose_document_view(
        entity_type="other_expense",
        entity_name="其他费用支出",
        payload={
            "expense_code": "QTFY002",
            "lines": [
                {
                    "category_name": "差旅",
                    "description": "出差报销",
                    "amount": Decimal("200"),
                }
            ],
        },
    )
    assert len(view.lines) == 1
    fields = {f.key: f.value for f in view.lines[0].fields}
    assert fields.get("description") == "出差报销"
    field_order = [f.key for f in view.lines[0].fields]
    assert field_order.index("description") < field_order.index("amount")


def test_compose_payment_application_header_shows_supplier_bank() -> None:
    view = compose_document_view(
        entity_type="payment_application",
        entity_name="付款申请",
        payload={
            "application_code": "FKSQ001",
            "supplier_name": "淘宝",
            "application_kind": "goods",
            "payment_method": "银行转账",
            "supplier_account_name": "淘宝（中国）软件有限公司",
            "supplier_bank_name": "支付宝",
            "supplier_bank_account": "2088",
            "total_request_amount": Decimal("50.44"),
            "items": [],
        },
    )
    header_map = {f.key: f.value for f in view.header}
    assert header_map.get("application_kind") == "货款"
    assert header_map.get("supplier_account_name") == "淘宝（中国）软件有限公司"
    assert header_map.get("supplier_bank_account") == "2088"
