"""质量体系 - 内审检查表行。结论为不符合时生成不符合报告。"""

from tortoise import fields

from core.models.base import BaseModel


class QmsInternalAuditChecklistItem(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_qms_internal_audit_checklist_items"
        table_description = "快格轻制造 - 内审检查表行"
        indexes = [
            ("tenant_id", "audit_id"),
            ("clause_id",),
            ("nc_report_id",),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    audit_id = fields.IntField(description="内审ID")
    sort_order = fields.IntField(default=0, description="行序")
    clause_id = fields.IntField(description="条款ID")
    checkpoint = fields.TextField(null=True, description="审核要点")
    conclusion = fields.CharField(
        max_length=20,
        default="pending",
        description="pending/conform/nonconform/observation",
    )
    evidence = fields.TextField(null=True, description="证据")
    nc_report_id = fields.IntField(null=True, description="生成的不符合报告ID")
    remarks = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="软删除")
