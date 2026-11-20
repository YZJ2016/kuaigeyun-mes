"""质量体系 - 管理评审决议行（第 3 期供纠正预防挂接；第 4 期再扩带入与关闭规则）。"""

from tortoise import fields

from core.models.base import BaseModel


class QmsManagementReviewResolution(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_qms_management_review_resolutions"
        table_description = "快格轻制造 - 管理评审决议"
        indexes = [
            ("tenant_id",),
            ("review_id",),
            ("status",),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    review_id = fields.IntField(description="管理评审ID")
    content = fields.TextField(description="决议内容")
    responsible_person = fields.CharField(max_length=100, null=True, description="责任人")
    due_on = fields.DateField(null=True, description="要求完成日")
    convert_to_capa = fields.BooleanField(default=False, description="是否转为纠正预防")
    capa_code = fields.CharField(max_length=50, null=True, description="纠正预防单号")
    status = fields.CharField(
        max_length=20,
        default="open",
        description="open/done",
    )
    sort_order = fields.IntField(default=0, description="排序")
    remarks = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="软删除")
