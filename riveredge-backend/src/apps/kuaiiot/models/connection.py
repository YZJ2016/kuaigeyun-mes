"""星数采连接源（apps_kuaiiot_connections）。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiiotConnection(BaseModel):
    class Meta:
        table = "apps_kuaiiot_connections"
        table_description = "快数采 - 连接源"
        unique_together = (("tenant_id", "code"),)
        indexes = [
            ("tenant_id", "connection_type"),
            ("tenant_id", "is_enabled"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    code = fields.CharField(max_length=50, description="连接编码")
    name = fields.CharField(max_length=100, description="连接名称")
    connection_type = fields.CharField(max_length=30, description="连接类型")
    integration = fields.ForeignKeyField(
        "models.IntegrationConfig", related_name="kuaiiot_connections",
        null=True, on_delete=fields.RESTRICT, description="同租户公共连接",
    )
    subscriber_owner = fields.CharField(max_length=36, null=True, description="订阅进程租约")
    subscriber_lease_until = fields.DatetimeField(null=True, description="订阅租约截止时间")
    config = fields.JSONField(null=True, description="数采映射配置，不保存连接地址或凭据")
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    health_status = fields.CharField(max_length=20, default="unknown", description="健康状态")
    last_health_at = fields.DatetimeField(null=True, description="最近健康检查时间")
    remark = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")
