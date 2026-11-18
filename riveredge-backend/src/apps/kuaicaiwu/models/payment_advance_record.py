"""员工垫付审计台账（付款确认即 cleared）。"""

from tortoise import fields

from core.models.base import BaseModel


class PaymentAdvanceRecord(BaseModel):
    class Meta:
        table = "apps_kuaicaiwu_payment_advance_records"
        table_description = "管理会计 - 付款单员工垫付台账"

    id = fields.IntField(pk=True)
    tenant_id = fields.IntField(description="租户ID")
    payment_id = fields.IntField(description="付款单ID")
    payment_code = fields.CharField(max_length=50, description="付款单号")
    supplier_id = fields.IntField(description="供应商ID")
    supplier_name = fields.CharField(max_length=200, description="供应商名称")
    payee_id = fields.IntField(description="领款人ID")
    payee_name = fields.CharField(max_length=100, description="领款人姓名")
    amount = fields.DecimalField(max_digits=16, decimal_places=4, description="垫付补款金额")
    status = fields.CharField(max_length=20, default="cleared", description="cleared")
    confirmed_at = fields.DatetimeField(null=True, description="确认时间")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
