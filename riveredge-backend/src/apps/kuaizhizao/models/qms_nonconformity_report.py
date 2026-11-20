"""质量体系 - 不符合报告。第 3 期起严重/一般须关联并关闭纠正预防才能关闭。"""

from tortoise import fields

from core.models.base import BaseModel


class QmsNonconformityReport(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_qms_nonconformity_reports"
        table_description = "快格轻制造 - 不符合报告"
        indexes = [
            ("tenant_id",),
            ("report_code",),
            ("status",),
            ("source_type", "source_id"),
            ("clause_id",),
        ]
        unique_together = [("tenant_id", "report_code")]

    id = fields.IntField(pk=True, description="主键ID")
    report_code = fields.CharField(max_length=50, description="报告编号")
    source_type = fields.CharField(
        max_length=30,
        description="internal_audit/external_audit",
    )
    source_id = fields.IntField(null=True, description="来源单据ID")
    source_code = fields.CharField(max_length=50, null=True, description="来源单号")
    checklist_item_id = fields.IntField(null=True, description="内审检查表行ID")
    clause_id = fields.IntField(null=True, description="条款ID")
    fact = fields.TextField(description="不符合事实")
    severity = fields.CharField(
        max_length=20,
        description="severe/general/observation",
    )
    responsible_dept = fields.CharField(max_length=200, null=True, description="责任部门")
    due_on = fields.DateField(null=True, description="要求完成日")
    cause = fields.TextField(null=True, description="原因")
    correction = fields.TextField(null=True, description="纠正")
    corrective_action = fields.TextField(null=True, description="纠正措施")
    verifier_name = fields.CharField(max_length=100, null=True, description="验证人")
    verified_on = fields.DateField(null=True, description="验证日")
    verification_conclusion = fields.TextField(null=True, description="验证结论")
    capa_code = fields.CharField(max_length=50, null=True, description="关联纠正预防单号")
    status = fields.CharField(
        max_length=20,
        default="open",
        description="open/rectifying/pending_verify/closed",
    )
    remarks = fields.TextField(null=True, description="备注")
    attachments = fields.JSONField(null=True, description="附件")
    deleted_at = fields.DatetimeField(null=True, description="软删除")
