"""
其他收支类别模型（收入/支出分表）。
"""

from tortoise import fields
from core.models.base import BaseModel


class MiscIncomeCategory(BaseModel):
    """其他费用收入类别"""

    class Meta:
        table = "apps_kuaicaiwu_misc_income_categories"
        table_description = "管理会计 - 其他收入类别"
        indexes = [("tenant_id", "code")]

    id = fields.IntField(pk=True, description="主键ID")
    code = fields.CharField(max_length=50, description="类别编码")
    name = fields.CharField(max_length=200, description="类别名称")
    is_active = fields.BooleanField(default=True, description="是否启用")
    default_gl_account_code = fields.CharField(max_length=20, null=True, description="默认会计科目编码")
    sort_order = fields.IntField(default=0, description="排序")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self):
        return f"MiscIncomeCategory: {self.code} {self.name}"


class MiscExpenseCategory(BaseModel):
    """其他费用支出类别"""

    class Meta:
        table = "apps_kuaicaiwu_misc_expense_categories"
        table_description = "管理会计 - 其他支出类别"
        indexes = [("tenant_id", "code")]

    id = fields.IntField(pk=True, description="主键ID")
    code = fields.CharField(max_length=50, description="类别编码")
    name = fields.CharField(max_length=200, description="类别名称")
    is_active = fields.BooleanField(default=True, description="是否启用")
    default_gl_account_code = fields.CharField(max_length=20, null=True, description="默认会计科目编码")
    sort_order = fields.IntField(default=0, description="排序")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self):
        return f"MiscExpenseCategory: {self.code} {self.name}"
