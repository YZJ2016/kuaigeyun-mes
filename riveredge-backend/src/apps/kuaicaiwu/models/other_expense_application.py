"""其他费用支出申请单"""

from tortoise import fields

from core.models.base import BaseModel


class OtherExpenseApplication(BaseModel):
    """其他费用支出申请头"""

    class Meta:
        table = "apps_kuaicaiwu_other_expense_applications"
        table_description = "快财务 - 其他费用支出申请"
        indexes = [
            ("tenant_id", "application_code"),
            ("tenant_id", "status"),
            ("business_date",),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    application_code = fields.CharField(max_length=50, db_index=True, description="申请单号")

    business_date = fields.DateField(description="业务日期")
    counterparty_kind = fields.CharField(
        max_length=20, default="none", description="none/customer/supplier/employee/other"
    )
    counterparty_id = fields.IntField(null=True, description="往来ID")
    counterparty_name = fields.CharField(max_length=200, null=True, description="往来名称快照")
    counterparty_account_name = fields.CharField(max_length=200, null=True, description="对方收款户名")
    counterparty_bank_name = fields.CharField(max_length=200, null=True, description="对方收款开户行")
    counterparty_bank_account = fields.CharField(max_length=64, null=True, description="对方收款账号")

    total_amount = fields.DecimalField(max_digits=16, decimal_places=4, default=0, description="申请合计")
    pushed_amount = fields.DecimalField(
        max_digits=16, decimal_places=4, default=0, description="已下推/占用累计"
    )
    remaining_amount = fields.DecimalField(
        max_digits=16, decimal_places=4, default=0, description="待下推余额"
    )

    payment_method = fields.CharField(max_length=50, description="收付方式")
    bank_account_id = fields.IntField(null=True, description="银行账户ID")
    bank_account = fields.CharField(max_length=100, null=True, description="账户快照")

    status = fields.CharField(
        max_length=20,
        default="Draft",
        description="业务状态：Draft/Approved/Rejected/Cancelled（审核见 review_status）",
    )
    review_status = fields.CharField(
        max_length=20,
        default="草稿",
        description="审核状态：草稿/SUBMITTED/待审核/已审核/已驳回",
    )
    reviewer_id = fields.IntField(null=True, description="审核人ID")
    reviewer_name = fields.CharField(max_length=100, null=True, description="审核人")
    review_time = fields.DatetimeField(null=True, description="审核时间")
    review_remarks = fields.TextField(null=True, description="审核备注")

    department_id = fields.IntField(null=True, description="部门ID")
    department_name = fields.CharField(max_length=200, null=True, description="部门名称")
    project_id = fields.IntField(null=True, description="项目ID")
    project_name = fields.CharField(max_length=200, null=True, description="项目名称")

    notes = fields.TextField(null=True, description="备注")
    attachments = fields.JSONField(null=True, description="附件")
    related_purchase_receipts = fields.JSONField(
        null=True,
        description="关联采购入库单 [{id, code}]",
    )
    payable_recognition = fields.CharField(
        max_length=32,
        default="on_receipt",
        description="立账策略（应付确认时点）",
    )
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self):
        return f"OtherExpenseApplication: {self.application_code} ({self.total_amount})"


class OtherExpenseApplicationLine(BaseModel):
    """其他费用支出申请明细行"""

    class Meta:
        table = "apps_kuaicaiwu_other_expense_application_lines"
        table_description = "快财务 - 其他费用支出申请明细"
        indexes = [("tenant_id", "application_id")]

    id = fields.IntField(pk=True, description="主键ID")
    application_id = fields.IntField(description="申请头ID")
    line_no = fields.IntField(default=1, description="行号")
    category_code = fields.CharField(max_length=50, description="类别编码")
    category_name = fields.CharField(max_length=200, description="类别名称")
    amount = fields.DecimalField(max_digits=16, decimal_places=4, description="申请金额")
    pushed_amount = fields.DecimalField(
        max_digits=16, decimal_places=4, default=0, description="已下推金额"
    )
    description = fields.TextField(null=True, description="行摘要")
    gl_account_code = fields.CharField(max_length=20, null=True, description="科目")
    payee_id = fields.IntField(null=True, description="领款人用户ID")
    payee_name = fields.CharField(max_length=100, null=True, description="领款人姓名快照")

    def __str__(self):
        return f"OtherExpenseApplicationLine: {self.application_id}#{self.line_no}"
