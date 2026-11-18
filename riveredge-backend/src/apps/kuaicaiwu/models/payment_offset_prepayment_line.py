"""预付抵扣付款单：用户指定的预付款付款单及本次扣减金额。"""

from tortoise import fields

from core.models.base import BaseModel


class PaymentOffsetPrepaymentLine(BaseModel):
    class Meta:
        table = "apps_kuaicaiwu_payment_offset_prepayment_lines"
        table_description = "管理会计 - 预付抵扣预付款明细"
        indexes = [
            ("tenant_id", "payment_id"),
            ("tenant_id", "prepayment_payment_id"),
        ]

    id = fields.IntField(pk=True)
    tenant_id = fields.IntField(description="租户ID")
    payment_id = fields.IntField(description="预付抵扣付款单ID")
    line_no = fields.IntField(description="行号")
    prepayment_payment_id = fields.IntField(description="预付款付款单ID")
    source_code = fields.CharField(max_length=50, null=True, description="预付款单号快照")
    amount = fields.DecimalField(max_digits=16, decimal_places=4, description="本次抵扣金额")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
