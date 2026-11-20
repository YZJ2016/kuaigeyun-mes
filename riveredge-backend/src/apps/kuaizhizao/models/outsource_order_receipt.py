"""工序委外分批收货批次。"""

from tortoise import fields
from core.models.base import BaseModel


class OutsourceOrderReceipt(BaseModel):
    """工序委外单次收货登记（累计量由头表维护）。"""

    class Meta:
        table = "apps_kuaizhizao_outsource_order_receipts"
        table_description = "快格轻制造 - 工序委外收货批次"
        indexes = [
            ("tenant_id", "outsource_order_id"),
            ("created_at",),
        ]

    id = fields.IntField(pk=True)
    outsource_order_id = fields.IntField(description="工序委外单ID")
    outsource_order_code = fields.CharField(max_length=50, description="工序委外单编码")
    received_quantity = fields.DecimalField(max_digits=14, decimal_places=4, description="本批接收数量")
    qualified_quantity = fields.DecimalField(max_digits=14, decimal_places=4, description="本批合格数量")
    unqualified_quantity = fields.DecimalField(max_digits=14, decimal_places=4, description="本批不合格数量")
    payable_recognition = fields.CharField(max_length=40, null=True, description="立账策略快照")
    ledger_posted = fields.BooleanField(default=False, description="本批是否已立应付")
    remarks = fields.TextField(null=True, description="备注")
    # created_by / updated_by* 继承 BaseModel；表需有对应列（见迁移 1047）
    deleted_at = fields.DatetimeField(null=True, description="软删除")
