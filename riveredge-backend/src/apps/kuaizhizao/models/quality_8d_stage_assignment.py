"""8D 阶段负责人指派"""

from tortoise import fields

from core.models.base import BaseModel


class Quality8DStageAssignment(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_quality_8d_stage_assignments"
        table_description = "快格轻制造 - 8D 阶段负责人"
        indexes = [
            ("tenant_id",),
            ("report_id",),
            ("stage_key",),
            ("assignee_user_id",),
            ("status",),
        ]
        unique_together = [("tenant_id", "report_id", "stage_key")]

    id = fields.IntField(pk=True, description="主键ID")
    report_id = fields.IntField(description="8D 报告ID")
    stage_key = fields.CharField(max_length=30, description="阶段键 d0_prepare … d8_team_congratulation")
    assignee_user_id = fields.IntField(null=True, description="负责人用户ID")
    assignee_name = fields.CharField(max_length=100, null=True, description="负责人姓名快照")
    due_date = fields.DatetimeField(null=True, description="阶段截止")
    status = fields.CharField(
        max_length=20,
        default="pending",
        description="pending/in_progress/submitted/approved",
    )
    submitted_at = fields.DatetimeField(null=True, description="负责人提交时间")
    approved_at = fields.DatetimeField(null=True, description="牵头人确认时间")
    approved_by = fields.IntField(null=True, description="确认人用户ID")
    approved_by_name = fields.CharField(max_length=100, null=True, description="确认人姓名")
