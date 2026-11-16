"""
采购入库明细行 — 应付 / 收票 / 付款占用（行级财务真源，供报表与核销余量）。
"""

from tortoise import fields

from core.models.base import BaseModel


class PurchaseReceiptLineFinanceOccupancy(BaseModel):
    """单行占用记录；同一目标单据可对应多行分摊。"""

    tenant_id = fields.IntField(description="租户ID")
    purchase_receipt_id = fields.IntField(description="采购入库单ID")
    purchase_receipt_item_id = fields.IntField(description="采购入库明细ID")

    occupancy_kind = fields.CharField(
        max_length=16,
        description="占用类型 payable 已立应付 invoice 已收票 paid 已付款",
    )
    quantity = fields.DecimalField(max_digits=12, decimal_places=4, description="占用数量")
    amount = fields.DecimalField(max_digits=14, decimal_places=4, description="占用金额")

    target_doc_type = fields.CharField(max_length=32, description="目标单据类型")
    target_doc_id = fields.IntField(description="目标单据ID")
    deleted_at = fields.DatetimeField(null=True, description="软删除时间")

    class Meta:
        table = "apps_kuaicaiwu_purchase_receipt_line_finance_occupancies"
        table_description = "轻管理会计 - 采购入库行财务占用"
        indexes = [
            ("tenant_id", "purchase_receipt_item_id", "occupancy_kind"),
            ("tenant_id", "purchase_receipt_id"),
            ("tenant_id", "target_doc_type", "target_doc_id"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at"]
