"""质量体系 - 标准/体系目录"""

from tortoise import fields

from core.models.base import BaseModel


class QmsStandard(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_qms_standards"
        table_description = "快格轻制造 - 质量体系标准目录"
        indexes = [
            ("tenant_id",),
            ("code",),
            ("is_active",),
        ]
        unique_together = [("tenant_id", "code")]

    id = fields.IntField(pk=True, description="主键ID")
    code = fields.CharField(max_length=30, description="标准代号，如 ISO9001:2015")
    name = fields.CharField(max_length=200, description="显示名称")
    family = fields.CharField(
        max_length=30,
        default="custom",
        description="iso9001|iso14001|iso45001|iatf16949|custom",
    )
    is_preset = fields.BooleanField(default=False, description="是否系统预置")
    is_active = fields.BooleanField(default=True, description="是否启用")
    sort_order = fields.IntField(default=0, description="排序")
    deleted_at = fields.DatetimeField(null=True, description="软删除")
    created_by = fields.IntField(null=True, description="创建人ID")
    created_by_name = fields.CharField(max_length=100, null=True, description="创建人姓名")
    updated_by = fields.IntField(null=True, description="更新人ID")
    updated_by_name = fields.CharField(max_length=100, null=True, description="更新人姓名")
