"""付款单加载明细：按来源单据记录本次付款分配金额。"""

from tortoise import fields

from core.models.base import BaseModel


class PaymentPullLine(BaseModel):
    class Meta:
        table = "apps_kuaicaiwu_payment_pull_lines"
        table_description = "管理会计 - 付款单加载明细"
        indexes = [
            ("tenant_id", "payment_id"),
            ("tenant_id", "source_type", "source_id"),
        ]

    id = fields.IntField(pk=True)
    tenant_id = fields.IntField(description="租户ID")
    payment_id = fields.IntField(description="付款单ID")
    line_no = fields.IntField(description="行号")
    source_type = fields.CharField(
        max_length=50, description="来源类型 payable|payment_application|purchase_order"
    )
    source_id = fields.IntField(description="来源单据ID")
    source_code = fields.CharField(max_length=50, null=True, description="来源单号")
    amount = fields.DecimalField(max_digits=16, decimal_places=4, description="本次付款金额")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
