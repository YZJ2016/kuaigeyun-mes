"""质量体系 - 体系文件与条款关联"""

from tortoise import fields

from core.models.base import BaseModel


class QmsDocumentClause(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_qms_document_clauses"
        table_description = "快格轻制造 - 体系文件条款关联"
        indexes = [
            ("tenant_id",),
            ("document_id",),
            ("clause_id",),
        ]
        unique_together = [("tenant_id", "document_id", "clause_id")]

    id = fields.IntField(pk=True, description="主键ID")
    document_id = fields.IntField(description="体系文件ID")
    clause_id = fields.IntField(description="条款ID")
    is_primary = fields.BooleanField(default=False, description="是否主条款")
    deleted_at = fields.DatetimeField(null=True, description="软删除")
