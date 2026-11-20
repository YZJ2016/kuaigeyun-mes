"""质量体系 - 质量目标（头表 + 行表）。"""

from tortoise import fields

from core.models.base import BaseModel


class QmsQualityObjective(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_qms_quality_objectives"
        table_description = "快格轻制造 - 质量目标"
        indexes = [("tenant_id",), ("objective_code",), ("status",), ("plan_year",)]
        unique_together = [("tenant_id", "objective_code")]

    id = fields.IntField(pk=True, description="主键ID")
    objective_code = fields.CharField(max_length=50, description="质量目标编号")
    plan_year = fields.IntField(description="年度")
    standard_id = fields.IntField(null=True, description="覆盖标准ID")
    status = fields.CharField(
        max_length=20,
        default="draft",
        description="draft/published/ended",
    )
    remarks = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="软删除")


class QmsQualityObjectiveLine(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_qms_quality_objective_lines"
        table_description = "快格轻制造 - 质量目标行"
        indexes = [("tenant_id",), ("objective_id",)]

    id = fields.IntField(pk=True, description="主键ID")
    objective_id = fields.IntField(description="质量目标头ID")
    sort_order = fields.IntField(default=0, description="排序")
    name = fields.CharField(max_length=200, description="目标名称")
    metric_scope = fields.CharField(max_length=200, null=True, description="统计口径")
    target_value = fields.CharField(max_length=100, description="目标值")
    responsible_dept = fields.CharField(max_length=200, null=True, description="责任部门")
    period = fields.CharField(max_length=20, description="month/quarter")
    actual_value = fields.CharField(max_length=100, null=True, description="实际值")
    achieved = fields.BooleanField(null=True, description="是否达到（由目标值与实际值计算）")
    remarks = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="软删除")
