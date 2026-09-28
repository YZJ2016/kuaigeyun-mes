"""星报表定义（映射已有表 apps_kuaireport_reports）。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaireportReport(BaseModel):
    """一张报表。数据源绑定写在 report_config，不另加外键列。"""

    class Meta:
        table = "apps_kuaireport_reports"
        table_description = "快格报表 - 报表定义"
        indexes = [
            ("tenant_id", "code"),
            ("tenant_id", "status"),
            ("tenant_id", "category"),
            ("tenant_id", "owner_id"),
            ("tenant_id", "classify"),
        ]
        unique_together = (("tenant_id", "code"),)

    id = fields.IntField(pk=True, description="主键ID")
    code = fields.CharField(max_length=50, description="报表编码")
    name = fields.CharField(max_length=100, description="报表名称")
    description = fields.TextField(null=True, description="描述")
    category = fields.CharField(max_length=20, default="custom", description="system|custom")
    classify = fields.CharField(max_length=50, default="未分类", description="业务分类")
    is_system = fields.BooleanField(default=False, description="是否系统报表")
    owner_id = fields.IntField(null=True, description="拥有者")
    report_config = fields.JSONField(null=True, description="报表配置（不含 SQL）")
    status = fields.CharField(max_length=20, default="DRAFT", description="DRAFT 或已发布")
    is_shared = fields.BooleanField(default=False, description="是否开启分享")
    share_token = fields.CharField(max_length=64, null=True, description="分享令牌")
    share_expires_at = fields.DatetimeField(null=True, description="分享过期时间")
    share_password_hash = fields.CharField(max_length=128, null=True, description="分享口令哈希")
    share_allow_ip_cidrs = fields.JSONField(null=True, description="分享 IP 白名单")
    current_version = fields.IntField(default=0, description="当前版本号")

    def __str__(self) -> str:
        return f"KuaireportReport: {self.id} ({self.code})"
