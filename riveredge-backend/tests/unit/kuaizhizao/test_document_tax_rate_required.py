from apps.kuaicaiwu.schemas.finance import (
    MergePurchaseInvoiceCreate,
    MergeSalesInvoiceCreate,
    PurchaseInvoiceCreate,
    SalesInvoiceCreate,
)
from apps.kuaicaiwu.schemas.invoice import InvoiceCreate
from apps.kuaizhizao.schemas.purchase import PurchaseOrderItemCreate
from apps.kuaizhizao.schemas.purchase_inquiry import PurchaseInquiryCreate
from apps.kuaizhizao.schemas.quotation import QuotationItemCreate
from apps.kuaizhizao.schemas.sales_contract import SalesContractItemCreate
from apps.kuaizhizao.schemas.sales import SalesOrderItemCreate as LegacySalesOrderItemCreate
from apps.kuaizhizao.schemas.sales_order import SalesOrderItemCreate
from apps.kuaizhizao.schemas.warehouse import PurchaseReceiptItemCreate, SalesDeliveryItemCreate


def test_document_create_tax_rate_fields_are_required():
    schemas = (
        QuotationItemCreate,
        SalesContractItemCreate,
        SalesOrderItemCreate,
        LegacySalesOrderItemCreate,
        PurchaseOrderItemCreate,
        PurchaseReceiptItemCreate,
        SalesDeliveryItemCreate,
        PurchaseInquiryCreate,
        PurchaseInvoiceCreate,
        SalesInvoiceCreate,
        MergePurchaseInvoiceCreate,
        MergeSalesInvoiceCreate,
        InvoiceCreate,
    )

    for schema in schemas:
        assert schema.model_fields["tax_rate"].is_required(), schema.__name__
