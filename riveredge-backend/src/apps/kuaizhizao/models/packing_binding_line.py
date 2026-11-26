"""
装箱绑定明细行（箱内 SN/件）

一箱多行；解绑留痕，不物理删除。
"""

from tortoise import fields

from core.models.base import BaseModel


class PackingBindingLine(BaseModel):
    """箱内装箱明细。"""

    class Meta:
        table = "apps_kuaizhizao_packing_binding_lines"
        table_description = "快格轻制造 - 装箱绑定明细行"
        indexes = [
            ("tenant_id", "binding_id"),
            ("tenant_id", "product_serial_no"),
            ("tenant_id", "line_status"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    binding_id = fields.IntField(description="装箱绑定（箱头）ID")
    product_id = fields.IntField(description="产品ID")
    product_serial_no = fields.CharField(max_length=200, description="序列号/条码")
    quantity = fields.DecimalField(max_digits=14, decimal_places=4, default=1, description="数量")
    line_status = fields.CharField(
        max_length=20,
        default="active",
        description="active/unbound/consumed",
    )
    scanned_at = fields.DatetimeField(description="扫码时间")
    unbound_at = fields.DatetimeField(null=True, description="解绑时间")
    consumed_at = fields.DatetimeField(null=True, description="核销时间")
    deleted_at = fields.DatetimeField(null=True, description="软删除")

    def __str__(self) -> str:
        return f"{self.product_serial_no} -> binding {self.binding_id}"
