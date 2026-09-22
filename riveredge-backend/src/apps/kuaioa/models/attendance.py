"""月度考勤模型。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaioaAttendanceSheet(BaseModel):
    """车间月度考勤单（提交后锁定日格）。"""

    tenant_id = fields.IntField(description="租户ID")
    sheet_code = fields.CharField(max_length=50, description="考勤单号")
    year_month = fields.CharField(max_length=7, description="年月 YYYY-MM")
    workshop_name = fields.CharField(max_length=100, description="车间")
    production_line_name = fields.CharField(max_length=100, null=True, description="产线（可选）")
    has_night = fields.BooleanField(default=False, description="是否夜班模板")
    standard_hours = fields.DecimalField(
        max_digits=6, decimal_places=2, default=8, description="标准日工时"
    )
    status = fields.CharField(max_length=20, default="draft", description="draft/submitted")
    submitted_at = fields.DatetimeField(null=True, description="提交时间")
    submitted_by = fields.IntField(null=True, description="提交人")
    submitted_by_name = fields.CharField(max_length=100, null=True, description="提交人姓名")
    notes = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "apps_kuaioa_attendance_sheets"
        table_description = "轻办公 - 月度考勤单"
        unique_together = (("tenant_id", "sheet_code"),)
        indexes = [
            ("tenant_id", "year_month"),
            ("tenant_id", "workshop_name"),
            ("tenant_id", "status"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at"]


class KuaioaAttendanceDay(BaseModel):
    """考勤日格。"""

    tenant_id = fields.IntField(description="租户ID")
    sheet_id = fields.IntField(description="考勤单ID")
    employee_id = fields.IntField(description="员工档案ID")
    employee_code = fields.CharField(max_length=50, null=True, description="员工编号快照")
    employee_name = fields.CharField(max_length=100, description="姓名快照")
    work_date = fields.DateField(description="出勤日")
    regular_hours = fields.DecimalField(
        max_digits=6, decimal_places=2, default=8, description="正常工时"
    )
    ot_hours = fields.DecimalField(
        max_digits=6, decimal_places=2, default=0, description="加班工时"
    )
    mark = fields.CharField(
        max_length=20, default="normal", description="normal/leave/rest"
    )
    is_night = fields.BooleanField(default=False, description="夜班标记")
    leave_deduct_amount = fields.DecimalField(
        max_digits=12, decimal_places=2, null=True, description="请假扣款"
    )
    leave_request_id = fields.IntField(null=True, description="关联请假单")
    notes = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "apps_kuaioa_attendance_days"
        table_description = "轻办公 - 考勤日格"
        unique_together = (("tenant_id", "sheet_id", "employee_id", "work_date"),)
        indexes = [
            ("tenant_id", "sheet_id"),
            ("tenant_id", "employee_id", "work_date"),
            ("tenant_id", "work_date"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at"]
