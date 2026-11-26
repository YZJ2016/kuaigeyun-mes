from apps.kuaicaiwu.constants.finance_source_types import PAYABLE_SOURCE_PURCHASE_RECEIPT
from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
    resolve_purchase_receipt_id_from_payable,
)


def test_resolve_receipt_from_payable_source():
    assert resolve_purchase_receipt_id_from_payable(PAYABLE_SOURCE_PURCHASE_RECEIPT, 99) == 99
    assert resolve_purchase_receipt_id_from_payable("purchase_receipt", 5) == 5
    assert resolve_purchase_receipt_id_from_payable("采购订单", 5) is None
    assert resolve_purchase_receipt_id_from_payable(PAYABLE_SOURCE_PURCHASE_RECEIPT, None) is None
