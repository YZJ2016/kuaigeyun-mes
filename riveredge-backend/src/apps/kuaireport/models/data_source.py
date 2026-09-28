"""星报表数据源（映射已有表 apps_kuaireport_data_sources）。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaireportDataSource(BaseModel):
    """租户内数据源登记。type 只使用 static / dataset / http。"""

    class Meta:
        table = "apps_kuaireport_data_sources"
        table_description = "快格报表 - 数据源"
        indexes = [
            ("tenant_id", "type"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    name = fields.CharField(max_length=100, description="数据源名称")
    type = fields.CharField(max_length=20, default="static", description="static|dataset|http")
    config = fields.JSONField(null=True, description="类型配置（不含 SQL / query_config）")
    description = fields.TextField(null=True, description="描述")
    is_default = fields.BooleanField(default=False, description="是否默认")
    is_system = fields.BooleanField(default=False, description="是否系统预置")

    def __str__(self) -> str:
        return f"KuaireportDataSource: {self.id} ({self.name})"
