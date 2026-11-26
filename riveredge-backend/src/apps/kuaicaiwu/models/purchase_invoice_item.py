"""采购发票明细行（明细模式 1:1 绑定源单行）。"""

from tortoise import fields

from core.models.base import BaseModel


class PurchaseInvoiceItem(BaseModel):
    tenant_id = fields.IntField(description="租户ID")
    purchase_invoice = fields.ForeignKeyField(
        "models.PurchaseInvoice",
        related_name="items",
        on_delete=fields.CASCADE,
    )

    item_name = fields.CharField(max_length=200, description="货物或应税劳务名称")
    spec_model = fields.CharField(max_length=100, null=True, description="规格型号")
    unit = fields.CharField(max_length=20, null=True, description="单位")
    quantity = fields.DecimalField(max_digits=12, decimal_places=4, null=True, description="数量")
    unit_price = fields.DecimalField(max_digits=12, decimal_places=4, null=True, description="单价(不含税)")
    amount = fields.DecimalField(max_digits=16, decimal_places=4, description="金额(不含税)")
    tax_rate = fields.DecimalField(max_digits=6, decimal_places=4, description="税率")
    tax_amount = fields.DecimalField(max_digits=16, decimal_places=4, description="税额")

    source_doc_type = fields.CharField(max_length=50, null=True, description="源单类型")
    source_doc_id = fields.IntField(null=True, description="源单ID")
    source_line_id = fields.IntField(null=True, description="源单物料行ID")
    partner_statement_line_id = fields.IntField(null=True, description="对账单行ID")

    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    class Meta:
        table = "apps_kuaicaiwu_purchase_invoice_items"
        table_description = "轻管理会计 - 采购发票明细"
        indexes = [
            ("tenant_id", "purchase_invoice_id"),
            ("tenant_id", "source_doc_type", "source_doc_id", "source_line_id"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at"]