"""员工每日考勤登记记录（打卡明细）。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaioaDailyAttendanceRecord(BaseModel):
    """员工每日考勤登记：上下班打卡时间与出勤结果。"""

    tenant_id = fields.IntField(description="租户ID")
    employee_id = fields.IntField(null=True, description="员工档案ID")
    employee_code = fields.CharField(max_length=50, null=True, description="工号")
    employee_name = fields.CharField(max_length=100, description="姓名")
    department_name = fields.CharField(max_length=100, null=True, description="部门")
    work_date = fields.DateField(description="日期")
    clock_in_1 = fields.CharField(max_length=16, null=True, description="上班1打卡时间 HH:mm")
    clock_out_1 = fields.CharField(max_length=16, null=True, description="下班1打卡时间")
    clock_in_2 = fields.CharField(max_length=16, null=True, description="上班2打卡时间")
    clock_out_2 = fields.CharField(max_length=16, null=True, description="下班2打卡时间")
    clock_in_3 = fields.CharField(max_length=16, null=True, description="上班3打卡时间")
    clock_out_3 = fields.CharField(max_length=16, null=True, description="下班3打卡时间")
    result = fields.CharField(max_length=50, null=True, description="考勤结果")
    expected_hours = fields.DecimalField(
        max_digits=8, decimal_places=2, null=True, description="应出勤(小时)"
    )
    paid_hours = fields.DecimalField(
        max_digits=8, decimal_places=2, null=True, description="计薪时长(小时)"
    )
    actual_hours = fields.DecimalField(
        max_digits=8, decimal_places=2, null=True, description="实际出勤(小时)"
    )
    late_minutes = fields.IntField(null=True, description="迟到时长(分钟)")
    early_leave_minutes = fields.IntField(null=True, description="早退时长(分钟)")
    ot_hours = fields.DecimalField(
        max_digits=8, decimal_places=2, null=True, description="加班时长(小时)"
    )
    notes = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "apps_kuaioa_daily_attendance_records"
        table_description = "轻办公 - 每日考勤登记记录"
        indexes = [
            ("tenant_id", "work_date"),
            ("tenant_id", "employee_id", "work_date"),
            ("tenant_id", "employee_code", "work_date"),
            ("tenant_id", "department_name"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at"]
