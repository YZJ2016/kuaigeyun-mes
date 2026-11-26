"""销售出库明细行 — 应收 / 开票 / 收款占用（行级财务真源）。"""

from tortoise import fields

from core.models.base import BaseModel


class SalesDeliveryLineFinanceOccupancy(BaseModel):
    """单行占用记录；明细发票按 target_item_id 关联。"""

    tenant_id = fields.IntField(description="租户ID")
    sales_delivery_id = fields.IntField(description="销售出库单ID")
    sales_delivery_item_id = fields.IntField(description="销售出库明细ID")

    occupancy_kind = fields.CharField(
        max_length=16,
        description="receivable | invoice | received",
    )
    quantity = fields.DecimalField(max_digits=12, decimal_places=4, description="占用数量")
    amount = fields.DecimalField(max_digits=14, decimal_places=4, description="占用金额")

    target_doc_type = fields.CharField(max_length=32, description="目标单据类型")
    target_doc_id = fields.IntField(description="目标单据ID")
    target_item_id = fields.IntField(null=True, description="目标发票明细行ID")

    deleted_at = fields.DatetimeField(null=True, description="软删除")

    class Meta:
        table = "apps_kuaicaiwu_sales_delivery_line_finance_occupancies"
        table_description = "轻管理会计 - 销售出库行财务占用"
        indexes = [
            ("tenant_id", "sales_delivery_item_id", "occupancy_kind"),
            ("tenant_id", "sales_delivery_id"),
            ("tenant_id", "target_doc_type", "target_doc_id"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at"]