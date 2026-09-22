"""最低工资标准配置。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaioaMinimumWageConfig(BaseModel):
    """租户最低工资标准（按生效日取最新）。"""

    tenant_id = fields.IntField(description="租户ID")
    amount = fields.DecimalField(max_digits=12, decimal_places=2, description="最低工资金额")
    effective_date = fields.DateField(description="生效日期")
    notes = fields.TextField(null=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "apps_kuaioa_minimum_wage_configs"
        table_description = "轻办公 - 最低工资配置"
        indexes = [("tenant_id", "effective_date")]

    class PydanticMeta:
        exclude = ["deleted_at"]
