"""节日福利发放批次。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaioaWelfareBatch(BaseModel):
    """按年、节日、车间开立的福利发放单。"""

    tenant_id = fields.IntField(description="租户ID")
    batch_code = fields.CharField(max_length=50, description="单号")
    year = fields.IntField(description="发放年份")
    festival_type = fields.CharField(
        max_length=30,
        description="节日类型 dragon_boat/mid_autumn/spring_festival",
    )
    workshop_name = fields.CharField(max_length=100, description="车间")
    status = fields.CharField(max_length=20, default="draft", description="draft/confirmed")
    confirmed_at = fields.DatetimeField(null=True)
    confirmed_by = fields.IntField(null=True)
    confirmed_by_name = fields.CharField(max_length=100, null=True)
    notes = fields.TextField(null=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "apps_kuaioa_welfare_batches"
        table_description = "轻办公 - 节日福利发放单"
        unique_together = (("tenant_id", "batch_code"),)
        indexes = [
            ("tenant_id", "year", "festival_type"),
            ("tenant_id", "workshop_name"),
            ("tenant_id", "status"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at"]


class KuaioaWelfareBatchLine(BaseModel):
    """福利发放行（金额快照写死，禁止读侧 enrich）。"""

    tenant_id = fields.IntField(description="租户ID")
    batch_id = fields.IntField(description="发放单ID")
    employee_id = fields.IntField(description="员工档案ID")
    employee_code = fields.CharField(max_length=50, null=True)
    employee_name = fields.CharField(max_length=100)
    workshop_name = fields.CharField(max_length=100, null=True)
    standard_amount = fields.DecimalField(
        max_digits=12, decimal_places=2, null=True, description="档案标准快照"
    )
    amount = fields.DecimalField(max_digits=12, decimal_places=2, default=0, description="实发金额")
    received = fields.BooleanField(default=False, description="是否已领取")
    notes = fields.TextField(null=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "apps_kuaioa_welfare_batch_lines"
        table_description = "轻办公 - 节日福利发放行"
        unique_together = (("tenant_id", "batch_id", "employee_id"),)
        indexes = [("tenant_id", "batch_id"), ("tenant_id", "employee_id")]

    class PydanticMeta:
        exclude = ["deleted_at"]
