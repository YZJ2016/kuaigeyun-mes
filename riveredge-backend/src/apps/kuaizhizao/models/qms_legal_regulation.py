"""质量体系 - 法律法规。禁止环境因素/排放/危险源字段。"""

from tortoise import fields

from core.models.base import BaseModel


class QmsLegalRegulation(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_qms_legal_regulations"
        table_description = "快格轻制造 - 法律法规"
        indexes = [("tenant_id",), ("doc_no",), ("next_evaluation_on",), ("evaluation_conclusion")]

    id = fields.IntField(pk=True, description="主键ID")
    name = fields.CharField(max_length=200, description="名称")
    doc_no = fields.CharField(max_length=100, description="文号")
    issuing_authority = fields.CharField(max_length=200, null=True, description="发布机关")
    effective_on = fields.DateField(null=True, description="实施日")
    applicable_scope = fields.TextField(null=True, description="适用范围")
    evaluation_conclusion = fields.CharField(
        max_length=20,
        null=True,
        description="conform/need_rectify",
    )
    evaluated_on = fields.DateField(null=True, description="评价日")
    next_evaluation_on = fields.DateField(null=True, description="下次评价日")
    capa_code = fields.CharField(max_length=50, null=True, description="纠正预防单号")
    evaluation_completed = fields.BooleanField(default=False, description="本次评价是否完成")
    remarks = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="软删除")
