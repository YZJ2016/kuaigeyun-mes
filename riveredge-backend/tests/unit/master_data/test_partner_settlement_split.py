"""客商结算字段拆分：码表与旧值迁移逻辑。"""

from apps.master_data.config.partner_settlement_codes import (
    coerce_partner_payment_method_code,
    coerce_partner_settlement_terms_code,
    partner_settlement_terms_for_pricing,
    split_legacy_settlement_method_code,
)


class _PartnerStub:
    def __init__(self, settlement_terms_code):
        self.settlement_terms_code = settlement_terms_code


def test_split_legacy_payment_methods():
    assert split_legacy_settlement_method_code("cash") == ("cash", None)
    assert split_legacy_settlement_method_code("bank_transfer") == ("bank_transfer", None)


def test_split_legacy_terms():
    assert split_legacy_settlement_method_code("monthly") == (None, "net_terms")
    assert split_legacy_settlement_method_code("prepaid") == (None, "prepaid")
    assert split_legacy_settlement_method_code("月结") == (None, "net_terms")
    assert split_legacy_settlement_method_code("货到付款") == (None, "cod")
    assert split_legacy_settlement_method_code("款到发货") == (None, "pay_before_ship")
    assert split_legacy_settlement_method_code("票到付款") == (None, "pay_on_invoice")


def test_coerce_rejects_unknown():
    assert coerce_partner_payment_method_code("wire") is None
    assert coerce_partner_settlement_terms_code("net30") is None


def test_coerce_settlement_terms_cn_aliases():
    assert coerce_partner_settlement_terms_code("货到付款") == "cod"
    assert coerce_partner_settlement_terms_code("票到付款") == "pay_on_invoice"
    assert coerce_partner_settlement_terms_code("pay_on_invoice") == "pay_on_invoice"
    assert coerce_partner_settlement_terms_code("COD") == "cod"
    assert coerce_partner_settlement_terms_code("cod") == "cod"


def test_pricing_reads_terms_only():
    assert partner_settlement_terms_for_pricing(_PartnerStub("monthly")) == "net_terms"
    assert partner_settlement_terms_for_pricing(_PartnerStub("net_terms")) == "net_terms"
    assert partner_settlement_terms_for_pricing(_PartnerStub("cash")) is None


def test_expand_legacy_partner_settlement_mapped_row():
    from apps.kuaiconnect.services.inbound_sync.master_data_sync_common import (
        expand_legacy_partner_settlement_mapped_row,
    )

    expanded = expand_legacy_partner_settlement_mapped_row(
        {"code": "C1", "settlement_method_code": "月结"}
    )
    assert "settlement_method_code" not in expanded
    assert expanded["settlement_terms_code"] == "net_terms"
    assert "default_payment_method_code" not in expanded

    keep_new = expand_legacy_partner_settlement_mapped_row(
        {
            "settlement_method_code": "cash",
            "default_payment_method_code": "bank_transfer",
        }
    )
    assert keep_new["default_payment_method_code"] == "bank_transfer"
    assert "settlement_method_code" not in keep_new
