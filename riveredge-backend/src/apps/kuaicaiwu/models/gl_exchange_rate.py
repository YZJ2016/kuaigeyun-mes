"""总账汇率设置（按币种与生效日维护，相对本位币）。"""

from tortoise import fields

from core.models.base import BaseModel


class GlExchangeRate(BaseModel):
    """1 单位外币 = rate 单位本位币。"""

    class Meta:
        table = "apps_kuaicaiwu_gl_exchange_rates"
        table_description = "管理会计 - 汇率设置"
        unique_together = (("tenant_id", "currency_code", "effective_date"),)
        indexes = [
            ("tenant_id", "currency_code", "effective_date"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="租户ID")
    currency_code = fields.CharField(max_length=10, description="外币代码")
    effective_date = fields.DateField(description="生效日期（含当日）")
    rate = fields.DecimalField(max_digits=18, decimal_places=6, description="汇率（相对本位币）")
    notes = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self) -> str:
        return f"GlExchangeRate: {self.currency_code} @ {self.effective_date} = {self.rate}"
