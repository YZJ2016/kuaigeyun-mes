"""岗位补贴登记。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaioaPostSubsidy(BaseModel):
    """岗位补贴多行登记，结算重建时汇总进 post_allowance。"""

    tenant_id = fields.IntField(description="租户ID")
    subsidy_code = fields.CharField(max_length=50, description="单号")
    year_month = fields.CharField(max_length=7, description="年月 YYYY-MM")
    employee_id = fields.IntField(description="员工档案ID")
    employee_code = fields.CharField(max_length=50, null=True)
    employee_name = fields.CharField(max_length=100)
    workshop_name = fields.CharField(max_length=100, null=True)
    item_name = fields.CharField(max_length=100, description="补贴项目")
    amount = fields.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = fields.TextField(null=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "apps_kuaioa_post_subsidies"
        table_description = "轻办公 - 岗位补贴"
        unique_together = (("tenant_id", "subsidy_code"),)
        indexes = [("tenant_id", "year_month"), ("tenant_id", "employee_id")]

    class PydanticMeta:
        exclude = ["deleted_at"]
