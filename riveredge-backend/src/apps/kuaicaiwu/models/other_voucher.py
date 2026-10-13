"""
其他费用收入/支出单据模型。

独立于收款单/付款单：不产生应收应付，不走核销，确认过账仅写入银行流水。
"""

from tortoise import fields
from core.models.base import BaseModel


class OtherIncome(BaseModel):
    """其他费用收入单"""

    class Meta:
        table = "apps_kuaicaiwu_other_incomes"
        table_description = "管理会计 - 其他费用收入单"
        indexes = [
            ("tenant_id", "income_code"),
            ("tenant_id", "status"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    income_code = fields.CharField(max_length=50, description="收入单号")
    business_date = fields.DateField(description="业务日期")
    counterparty_kind = fields.CharField(
        max_length=20, default="none",
        description="往来对象类型 none/customer/supplier/employee/other",
    )
    counterparty_id = fields.IntField(null=True, description="往来对象ID")
    counterparty_name = fields.CharField(max_length=200, null=True, description="往来对象名称")
    total_amount = fields.DecimalField(max_digits=16, decimal_places=4, default=0, description="收入总额")
    payment_method = fields.CharField(max_length=50, description="收款方式 (银行转账/现金等)")
    bank_account_id = fields.IntField(null=True, description="入账账户ID")
    bank_account = fields.CharField(max_length=100, null=True, description="入账账户")
    status = fields.CharField(
        max_length=20, default="Draft",
        description="状态 Draft/PendingReview/Approved/Rejected/Confirmed/Cancelled",
    )
    reviewer_id = fields.IntField(null=True, description="审核人ID")
    reviewer_name = fields.CharField(max_length=100, null=True, description="审核人姓名")
    review_time = fields.DatetimeField(null=True, description="审核时间")
    review_remarks = fields.TextField(null=True, description="审核备注")
    department_id = fields.IntField(null=True, description="部门ID")
    department_name = fields.CharField(max_length=200, null=True, description="部门名称")
    project_id = fields.IntField(null=True, description="项目ID")
    project_name = fields.CharField(max_length=200, null=True, description="项目名称")
    notes = fields.TextField(null=True, description="备注")
    attachments = fields.JSONField(null=True, description="附件列表")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self):
        return f"OtherIncome: {self.income_code} ({self.total_amount})"


class OtherIncomeLine(BaseModel):
    """其他费用收入单明细行"""

    class Meta:
        table = "apps_kuaicaiwu_other_income_lines"
        table_description = "管理会计 - 其他费用收入单明细"
        indexes = [("tenant_id", "other_income_id")]

    id = fields.IntField(pk=True, description="主键ID")
    other_income_id = fields.IntField(description="其他费用收入单ID")
    line_no = fields.IntField(default=1, description="行号")
    category_code = fields.CharField(max_length=50, description="收入类别编码")
    category_name = fields.CharField(max_length=200, description="收入类别名称")
    amount = fields.DecimalField(max_digits=16, decimal_places=4, description="金额")
    description = fields.TextField(null=True, description="说明")
    gl_account_code = fields.CharField(max_length=20, null=True, description="会计科目编码")

    def __str__(self):
        return f"OtherIncomeLine: {self.other_income_id}#{self.line_no}"


class OtherExpense(BaseModel):
    """其他费用支出单"""

    class Meta:
        table = "apps_kuaicaiwu_other_expenses"
        table_description = "管理会计 - 其他费用支出单"
        indexes = [
            ("tenant_id", "expense_code"),
            ("tenant_id", "status"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    expense_code = fields.CharField(max_length=50, description="支出单号")
    business_date = fields.DateField(description="业务日期")
    counterparty_kind = fields.CharField(
        max_length=20, default="none",
        description="往来对象类型 none/customer/supplier/employee/other",
    )
    counterparty_id = fields.IntField(null=True, description="往来对象ID")
    counterparty_name = fields.CharField(max_length=200, null=True, description="往来对象名称")
    total_amount = fields.DecimalField(max_digits=16, decimal_places=4, default=0, description="支出总额")
    payment_method = fields.CharField(max_length=50, description="付款方式 (银行转账/现金等)")
    bank_account_id = fields.IntField(null=True, description="出账账户ID")
    bank_account = fields.CharField(max_length=100, null=True, description="出账账户")
    status = fields.CharField(
        max_length=20, default="Draft",
        description="状态 Draft/PendingReview/Approved/Rejected/Confirmed/Cancelled",
    )
    reviewer_id = fields.IntField(null=True, description="审核人ID")
    reviewer_name = fields.CharField(max_length=100, null=True, description="审核人姓名")
    review_time = fields.DatetimeField(null=True, description="审核时间")
    review_remarks = fields.TextField(null=True, description="审核备注")
    department_id = fields.IntField(null=True, description="部门ID")
    department_name = fields.CharField(max_length=200, null=True, description="部门名称")
    project_id = fields.IntField(null=True, description="项目ID")
    project_name = fields.CharField(max_length=200, null=True, description="项目名称")
    notes = fields.TextField(null=True, description="备注")
    attachments = fields.JSONField(null=True, description="附件列表")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self):
        return f"OtherExpense: {self.expense_code} ({self.total_amount})"


class OtherExpenseLine(BaseModel):
    """其他费用支出单明细行"""

    class Meta:
        table = "apps_kuaicaiwu_other_expense_lines"
        table_description = "管理会计 - 其他费用支出单明细"
        indexes = [("tenant_id", "other_expense_id")]

    id = fields.IntField(pk=True, description="主键ID")
    other_expense_id = fields.IntField(description="其他费用支出单ID")
    line_no = fields.IntField(default=1, description="行号")
    category_code = fields.CharField(max_length=50, description="支出类别编码")
    category_name = fields.CharField(max_length=200, description="支出类别名称")
    amount = fields.DecimalField(max_digits=16, decimal_places=4, description="金额")
    description = fields.TextField(null=True, description="说明")
    gl_account_code = fields.CharField(max_length=20, null=True, description="会计科目编码")

    def __str__(self):
        return f"OtherExpenseLine: {self.other_expense_id}#{self.line_no}"
