"""星报表大屏（映射已有表 apps_kuaireport_dashboards / 版本表）。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaireportDashboard(BaseModel):
    """租户内大屏。code 的有效唯一约束是 (tenant_id, code) 且未删除。"""

    class Meta:
        table = "apps_kuaireport_dashboards"
        table_description = "快格报表 - 大屏定义"
        indexes = [
            ("tenant_id", "code"),
            ("tenant_id", "status"),
        ]
        unique_together = (("tenant_id", "code"),)

    id = fields.IntField(pk=True, description="主键ID")
    code = fields.CharField(max_length=50, description="大屏编码")
    name = fields.CharField(max_length=100, description="大屏名称")
    description = fields.TextField(null=True, description="描述")
    layout_config = fields.JSONField(null=True, description="布局")
    widgets_config = fields.JSONField(null=True, description="组件")
    theme_config = fields.JSONField(null=True, description="主题")
    tv_config = fields.JSONField(null=True, description="轮播")
    status = fields.CharField(max_length=20, default="DRAFT", description="DRAFT 或已发布")
    is_shared = fields.BooleanField(default=False, description="是否开启分享")
    current_version = fields.IntField(default=0, description="当前版本号")

    def __str__(self) -> str:
        return f"KuaireportDashboard: {self.id} ({self.code})"


class KuaireportDashboardVersion(BaseModel):
    """大屏保存快照。写入走 149 的 insert_dashboard_version。"""

    class Meta:
        table = "apps_kuaireport_dashboard_versions"
        unique_together = (("tenant_id", "dashboard_id", "version_no"),)

    id = fields.IntField(pk=True, description="主键ID")
    dashboard_id = fields.IntField(description="大屏ID")
    version_no = fields.IntField(description="版本号")
    snapshot = fields.JSONField(description="四段配置快照")
    note = fields.CharField(max_length=200, null=True, description="说明")
    created_by_user_id = fields.IntField(null=True, description="保存人")

    def __str__(self) -> str:
        return f"KuaireportDashboardVersion: {self.dashboard_id}#{self.version_no}"
