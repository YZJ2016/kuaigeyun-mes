"""质量体系 - 证书。状态由到期日计算，禁止手改矛盾状态。"""

from tortoise import fields

from core.models.base import BaseModel


class QmsCertificate(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_qms_certificates"
        table_description = "快格轻制造 - 体系证书"
        indexes = [("tenant_id",), ("certificate_no",), ("expire_on")]
        unique_together = [("tenant_id", "certificate_no")]

    id = fields.IntField(pk=True, description="主键ID")
    name = fields.CharField(max_length=200, description="证书名称")
    standard_name = fields.CharField(max_length=200, null=True, description="标准")
    certificate_no = fields.CharField(max_length=100, description="证书号")
    issuer = fields.CharField(max_length=200, null=True, description="发证机构")
    effective_on = fields.DateField(null=True, description="生效日")
    expire_on = fields.DateField(description="到期日")
    remarks = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="软删除")
