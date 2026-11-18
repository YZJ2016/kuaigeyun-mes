"""
资金调拨单模型（内部互转 / 内外部调拨）
"""

from tortoise import fields

from core.models.base import BaseModel


class FundTransfer(BaseModel):
    """公司内部账户互转或与外部账户的单向调入/调出。"""

    class Meta:
        table = "apps_kuaicaiwu_fund_transfers"
        table_description = "管理会计 - 资金调拨"
        indexes = [
            ("tenant_id", "transfer_date"),
            ("tenant_id", "status"),
            ("tenant_id", "transfer_type"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="租户ID")
    transfer_code = fields.CharField(max_length=50, db_index=True, description="调拨单号")

    transfer_date = fields.DateField(description="调拨日期")
    transfer_type = fields.CharField(
        max_length=20,
        description="调拨类型 internal/external_out/external_in",
    )

    from_bank_account_id = fields.IntField(null=True, description="调出账户ID")
    to_bank_account_id = fields.IntField(null=True, description="调入账户ID")

    external_account_name = fields.CharField(max_length=200, null=True, description="外部户名")
    external_bank_name = fields.CharField(max_length=200, null=True, description="外部开户行")
    external_account_number = fields.CharField(max_length=64, null=True, description="外部账号")

    amount = fields.DecimalField(max_digits=16, decimal_places=4, description="调拨金额")
    currency = fields.CharField(max_length=10, default="CNY", description="币种")

    status = fields.CharField(max_length=20, default="Draft", description="Draft/Confirmed/Cancelled")

    notes = fields.TextField(null=True, description="备注")
    attachments = fields.JSONField(null=True, description="附件列表")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self) -> str:
        return f"FundTransfer: {self.transfer_code} ({self.amount})"
