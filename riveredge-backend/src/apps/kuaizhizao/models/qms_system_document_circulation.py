"""质量体系 - 体系文件发放、回收、宣贯记录。

记录挂在已生效文件上，不是文件状态。作废后记录仍保留。
"""

from tortoise import fields

from core.models.base import BaseModel


class QmsSystemDocumentCirculation(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_qms_system_document_circulations"
        table_description = "快格轻制造 - 体系文件发放回收宣贯"
        indexes = [
            ("tenant_id", "document_id"),
            ("record_type",),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    document_id = fields.IntField(description="体系文件ID")
    record_type = fields.CharField(max_length=20, description="issue/recall/briefing")
    document_version = fields.CharField(max_length=30, description="登记时的文件版本")
    copies = fields.IntField(null=True, description="份数（发放、回收）")
    party_name = fields.CharField(max_length=200, description="部门或人员、回收人、宣贯对象")
    event_on = fields.DateField(description="发放日、回收日或宣贯日期")
    signer_name = fields.CharField(max_length=100, null=True, description="签收人")
    signed_on = fields.DateField(null=True, description="签收日")
    destroyed = fields.BooleanField(default=False, description="回收是否销毁")
    completed = fields.BooleanField(default=False, description="宣贯是否完成")
    training_ref = fields.CharField(max_length=100, null=True, description="已有培训记录单号")
    remarks = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="软删除")
