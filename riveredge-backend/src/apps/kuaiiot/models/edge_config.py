"""边缘配置（apps_kuaiiot_edge_configs）。列来自迁移 521 与 522。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiiotEdgeConfig(BaseModel):
    class Meta:
        table = "apps_kuaiiot_edge_configs"
        table_description = "快数采 - 边缘 Agent 配置"
        unique_together = (("tenant_id", "code"),)
        indexes = [
            ("tenant_id", "device_id"),
            ("tenant_id", "is_enabled"),
            ("tenant_id", "agent_status"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    code = fields.CharField(max_length=50, description="配置编码")
    name = fields.CharField(max_length=100, description="配置名称")
    device_id = fields.IntField(description="IoT 设备ID")
    protocol = fields.CharField(max_length=30, default="modbus_tcp", description="采集协议")
    config = fields.JSONField(description="协议配置")
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    remark = fields.TextField(null=True, description="备注")
    config_version = fields.IntField(default=1, description="配置版本")
    last_agent_heartbeat_at = fields.DatetimeField(null=True, description="最近 Agent 心跳时间")
    agent_version = fields.CharField(max_length=50, null=True, description="Agent 版本")
    agent_status = fields.CharField(max_length=20, default="unknown", description="Agent 状态")
    buffer_pending_count = fields.IntField(default=0, description="本地缓冲条数")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")
