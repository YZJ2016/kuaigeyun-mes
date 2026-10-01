"""质量体系 - 内审与条款关联"""

from tortoise import fields

from core.models.base import BaseModel


class QmsAuditClause(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_qms_audit_clauses"
        table_description = "快格轻制造 - 内审条款关联"
        indexes = [
            ("tenant_id",),
            ("audit_id",),
            ("clause_id",),
        ]
        unique_together = [("tenant_id", "audit_id", "clause_id")]

    id = fields.IntField(pk=True, description="主键ID")
    audit_id = fields.IntField(description="内审ID")
    clause_id = fields.IntField(description="条款ID")
    is_primary = fields.BooleanField(default=False, description="是否主条款")
    deleted_at = fields.DatetimeField(null=True, description="软删除")
