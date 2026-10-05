"""质量体系 - 管理评审与标准关联"""

from tortoise import fields

from core.models.base import BaseModel


class QmsReviewStandard(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_qms_review_standards"
        table_description = "快格轻制造 - 管理评审标准关联"
        indexes = [
            ("tenant_id",),
            ("review_id",),
            ("standard_id",),
        ]
        unique_together = [("tenant_id", "review_id", "standard_id")]

    id = fields.IntField(pk=True, description="主键ID")
    review_id = fields.IntField(description="管理评审ID")
    standard_id = fields.IntField(description="标准ID")
    deleted_at = fields.DatetimeField(null=True, description="软删除")
