"""采购询价需方（买方公司）主数据"""

from tortoise import fields

from core.models.base import BaseModel


class PurchaseDemandParty(BaseModel):
    """询价需方：本公司或采购方主体，供询价单下拉选用。"""

    tenant_id = fields.IntField(description="租户ID")
    code = fields.CharField(max_length=50, description="需方编码")
    name = fields.CharField(max_length=200, description="需方名称")
    contact_name = fields.CharField(max_length=100, null=True, description="联系人")
    contact_phone = fields.CharField(max_length=50, null=True, description="联系电话")
    contact_email = fields.CharField(max_length=100, null=True, description="邮箱")
    address = fields.CharField(max_length=500, null=True, description="地址")
    tax_no = fields.CharField(max_length=50, null=True, description="税号")
    notes = fields.TextField(null=True, description="备注")
    is_active = fields.BooleanField(default=True, description="是否启用")
    sort_order = fields.IntField(default=0, description="排序")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    class Meta:
        table = "apps_kuaizhizao_purchase_demand_parties"
        table_description = "快制造 - 采购询价需方"
        indexes = [
            ("tenant_id", "code"),
            ("tenant_id", "is_active"),
        ]
