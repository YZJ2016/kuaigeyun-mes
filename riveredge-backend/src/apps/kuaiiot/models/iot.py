"""星数采 IoT 模型。"""

from __future__ import annotations

import secrets

from tortoise import fields

from core.models.base import BaseModel


def _generate_device_token() -> str:
    return secrets.token_urlsafe(32)


class IotConnection(BaseModel):
    """IoT 连接源。"""

    tenant_id = fields.IntField(description="租户ID")
    code = fields.CharField(max_length=50, description="连接编码")
    name = fields.CharField(max_length=100, description="连接名称")
    connection_type = fields.CharField(max_length=30, description="mqtt|thingsboard|jetlinks|http_webhook")
    integration = fields.ForeignKeyField(
        "models.IntegrationConfig", related_name="kuaiiot_connections",
        null=True, on_delete=fields.RESTRICT, description="同租户公共连接",
    )
    subscriber_owner = fields.CharField(max_length=36, null=True, description="订阅进程租约")
    subscriber_lease_until = fields.DatetimeField(null=True, description="订阅租约截止时间")
    config = fields.JSONField(null=True, description="数采映射配置，不保存连接地址或凭据")
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    health_status = fields.CharField(max_length=20, default="unknown", description="healthy|unhealthy|unknown")
    last_health_at = fields.DatetimeField(null=True, description="上次健康检查时间")
    remark = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")

    class Meta:
        table = "apps_kuaiiot_connections"
        table_description = "星数采 - 连接源"
        unique_together = (("tenant_id", "code"),)
        indexes = [
            ("tenant_id", "connection_type"),
            ("tenant_id", "is_enabled"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at", "deleted_by", "deleted_by_name"]


class IotConnectionMessage(BaseModel):
    """MQTT 连接源最近原始报文（API / Worker 跨进程可见）。"""

    tenant_id = fields.IntField(description="租户ID")
    connection_id = fields.IntField(description="连接源 ID")
    topic = fields.CharField(max_length=255, description="MQTT Topic")
    qos = fields.IntField(default=0, description="QoS")
    retained = fields.BooleanField(default=False, description="是否保留消息")
    payload = fields.JSONField(null=True, description="消息体 JSON")
    payload_format = fields.CharField(max_length=30, default="unknown", description="报文格式")
    ingest_summary = fields.JSONField(null=True, description="入站摘要")
    error_message = fields.TextField(null=True, description="解析/入站错误")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")

    class Meta:
        table = "apps_kuaiiot_connection_messages"
        table_description = "星数采 - 连接源最近消息"
        indexes = [
            ("tenant_id", "connection_id", "created_at"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at", "deleted_by", "deleted_by_name"]


class IotDiscoveredMqttDevice(BaseModel):
    """MQTT 现场设备名录（从完整报文抽出，供新建设备下拉）。"""

    tenant_id = fields.IntField(description="租户ID")
    connection_id = fields.IntField(description="连接源 ID")
    external_device_id = fields.CharField(max_length=100, description="MQTT device_id")
    device_name = fields.CharField(max_length=100, null=True, description="现场设备名称")
    device_key = fields.CharField(max_length=100, null=True, description="现场设备 key")
    line_name = fields.CharField(max_length=100, null=True, description="产线名称")
    line_code = fields.CharField(max_length=50, null=True, description="产线编码")
    workshop_name = fields.CharField(max_length=100, null=True, description="车间名称")
    workshop_code = fields.CharField(max_length=50, null=True, description="车间编码")
    status = fields.CharField(max_length=30, null=True, description="报文中的状态")
    topic = fields.CharField(max_length=255, null=True, description="最近 Topic")
    last_seen_at = fields.DatetimeField(null=True, description="最近出现时间")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")

    class Meta:
        table = "apps_kuaiiot_discovered_mqtt_devices"
        table_description = "星数采 - MQTT 现场设备名录"
        unique_together = (("tenant_id", "connection_id", "external_device_id"),)
        indexes = [
            ("tenant_id", "connection_id"),
            ("tenant_id", "external_device_id"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at", "deleted_by", "deleted_by_name"]


class IotDeviceGroup(BaseModel):
    """IoT 设备分组。"""

    tenant_id = fields.IntField(description="租户ID")
    code = fields.CharField(max_length=50, description="分组编码")
    name = fields.CharField(max_length=100, description="分组名称")
    parent_id = fields.IntField(null=True, description="父分组 ID")
    sort_order = fields.IntField(default=0, description="排序")
    remark = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")

    class Meta:
        table = "apps_kuaiiot_device_groups"
        table_description = "星数采 - 设备分组"
        unique_together = (("tenant_id", "code"),)
        indexes = [
            ("tenant_id", "parent_id"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at", "deleted_by", "deleted_by_name"]


class IotDeviceCommand(BaseModel):
    """IoT 设备指令下发记录。"""

    tenant_id = fields.IntField(description="租户ID")
    device_id = fields.IntField(description="IoT 设备 ID")
    function_key = fields.CharField(max_length=100, description="功能 key")
    params = fields.JSONField(default=dict, description="指令参数 JSON")
    dispatch_channel = fields.CharField(max_length=30, description="edge|thingsboard|jetlinks")
    status = fields.CharField(max_length=20, default="pending", description="pending|sent|success|failed|timeout")
    result = fields.JSONField(null=True, description="执行结果 JSON")
    error_message = fields.TextField(null=True, description="错误信息")
    requested_by = fields.IntField(null=True, description="发起人 ID")
    sent_at = fields.DatetimeField(null=True, description="下发时间")
    completed_at = fields.DatetimeField(null=True, description="完成时间")
    expires_at = fields.DatetimeField(null=True, description="超时时间")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")

    class Meta:
        table = "apps_kuaiiot_device_commands"
        table_description = "星数采 - 设备指令"
        indexes = [
            ("tenant_id", "device_id"),
            ("tenant_id", "status", "expires_at"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at", "deleted_by", "deleted_by_name"]


class IotMessageLog(BaseModel):
    """IoT 设备消息追踪日志。"""

    tenant_id = fields.IntField(description="租户ID")
    device_id = fields.IntField(description="IoT 设备 ID")
    direction = fields.CharField(max_length=10, description="up|down")
    msg_type = fields.CharField(max_length=30, description="ingest|event|command|command_result")
    payload = fields.JSONField(null=True, description="消息载荷 JSON")
    result = fields.CharField(max_length=20, description="accepted|rejected|synced|error")
    error_message = fields.TextField(null=True, description="错误信息")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")

    class Meta:
        table = "apps_kuaiiot_message_logs"
        table_description = "星数采 - 消息追踪"
        indexes = [
            ("tenant_id", "device_id", "created_at"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at", "deleted_by", "deleted_by_name"]


class IotProduct(BaseModel):
    """IoT 产品物模型（租户自定义点位模板）。"""

    tenant_id = fields.IntField(description="租户ID")
    code = fields.CharField(max_length=50, description="产品编码")
    name = fields.CharField(max_length=100, description="产品名称")
    description = fields.TextField(null=True, description="描述")
    tags = fields.JSONField(default=list, description="点位定义 JSON 数组")
    events = fields.JSONField(default=list, description="事件定义 JSON 数组")
    functions = fields.JSONField(default=list, description="功能定义 JSON 数组")
    remark = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")

    class Meta:
        table = "apps_kuaiiot_products"
        table_description = "星数采 - 产品物模型"
        unique_together = (("tenant_id", "code"),)
        indexes = [
            ("tenant_id", "name"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at", "deleted_by", "deleted_by_name"]


class IotDevice(BaseModel):
    """IoT 设备。"""

    tenant_id = fields.IntField(description="租户ID")
    connection_id = fields.IntField(null=True, description="连接源 ID")
    product_id = fields.IntField(null=True, description="产品物模型 ID")
    group_id = fields.IntField(null=True, description="设备分组 ID")
    external_device_id = fields.CharField(max_length=100, description="外部设备 ID")
    code = fields.CharField(max_length=50, description="设备编码")
    name = fields.CharField(max_length=100, description="设备名称")
    device_token = fields.CharField(max_length=64, default=_generate_device_token, description="上报鉴权 token")
    equipment_uuid = fields.CharField(max_length=36, null=True, description="绑定的 MES 设备 UUID")
    is_online = fields.BooleanField(default=False, description="是否在线")
    latest_sampled_at = fields.DatetimeField(null=True, description="最新样本时间水位，包含事件")
    last_seen_at = fields.DatetimeField(null=True, description="最后上报时间")
    last_mes_sync_at = fields.DatetimeField(null=True, description="上次写 MES 状态时间")
    remark = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")

    class Meta:
        table = "apps_kuaiiot_devices"
        table_description = "星数采 - IoT 设备"
        unique_together = (("tenant_id", "code"),)
        indexes = [
            ("tenant_id", "connection_id"),
            ("tenant_id", "product_id"),
            ("tenant_id", "group_id"),
            ("tenant_id", "equipment_uuid"),
            ("device_token",),
            ("tenant_id", "is_online"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at", "deleted_by", "deleted_by_name"]


class IotTagDefinition(BaseModel):
    """点位定义与 MES 映射。"""

    tenant_id = fields.IntField(description="租户ID")
    device_id = fields.IntField(description="IoT 设备 ID")
    tag_key = fields.CharField(max_length=100, description="点位 key")
    name = fields.CharField(max_length=100, description="点位名称")
    value_type = fields.CharField(max_length=20, default="number", description="string|number|boolean")
    unit = fields.CharField(max_length=30, null=True, description="单位")
    map_target = fields.CharField(max_length=100, description="MES 写回目标")
    fill_target = fields.CharField(max_length=100, null=True, description="表单回填目标")
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")

    class Meta:
        table = "apps_kuaiiot_tag_definitions"
        table_description = "星数采 - 点位定义"
        unique_together = (("tenant_id", "device_id", "tag_key"),)
        indexes = [
            ("tenant_id", "device_id"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at", "deleted_by", "deleted_by_name"]


class IotTagSnapshot(BaseModel):
    """点位最新值快照。"""

    tenant_id = fields.IntField(description="租户ID")
    device_id = fields.IntField(description="IoT 设备 ID")
    tag_key = fields.CharField(max_length=100, description="点位 key")
    value_text = fields.TextField(null=True, description="字符串值")
    value_number = fields.DecimalField(max_digits=18, decimal_places=6, null=True, description="数值")
    value_bool = fields.BooleanField(null=True, description="布尔值")
    quality = fields.CharField(max_length=20, default="good", description="数据质量")
    sampled_at = fields.DatetimeField(description="采样时间")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")

    class Meta:
        table = "apps_kuaiiot_tag_snapshots"
        table_description = "星数采 - 点位快照"
        unique_together = (("tenant_id", "device_id", "tag_key"),)
        indexes = [
            ("tenant_id", "device_id"),
            ("sampled_at",),
        ]

    class PydanticMeta:
        exclude = ["deleted_at", "deleted_by", "deleted_by_name"]


class IotIngestDedup(BaseModel):
    """入站幂等记录。"""

    tenant_id = fields.IntField(description="租户ID")
    device_id = fields.IntField(description="IoT 设备 ID")
    idempotency_key = fields.CharField(max_length=128, description="幂等键")
    response_json = fields.TextField(description="首次响应 JSON")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")

    class Meta:
        table = "apps_kuaiiot_ingest_dedup"
        table_description = "星数采 - 入站幂等"
        unique_together = (("tenant_id", "device_id", "idempotency_key"),)
        indexes = [
            ("tenant_id", "device_id"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at", "deleted_by", "deleted_by_name"]


class IotTagHistory(BaseModel):
    """点位短窗历史（采样）。"""

    tenant_id = fields.IntField(description="租户ID")
    device_id = fields.IntField(description="IoT 设备 ID")
    tag_key = fields.CharField(max_length=100, description="点位 key")
    value_text = fields.TextField(null=True, description="字符串值")
    value_number = fields.DecimalField(max_digits=18, decimal_places=6, null=True, description="数值")
    value_bool = fields.BooleanField(null=True, description="布尔值")
    quality = fields.CharField(max_length=20, default="good", description="数据质量")
    sampled_at = fields.DatetimeField(description="采样时间")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")

    class Meta:
        table = "apps_kuaiiot_tag_history"
        table_description = "星数采 - 点位历史"
        indexes = [
            ("tenant_id", "device_id", "tag_key"),
            ("sampled_at",),
        ]

    class PydanticMeta:
        exclude = ["deleted_at", "deleted_by", "deleted_by_name"]


class IotAlertRule(BaseModel):
    """IoT 点位阈值告警规则。"""

    tenant_id = fields.IntField(description="租户ID")
    code = fields.CharField(max_length=50, description="规则编码")
    name = fields.CharField(max_length=100, description="规则名称")
    rule_type = fields.CharField(max_length=20, default="threshold", description="threshold|offline")
    device_id = fields.IntField(null=True, description="IoT 设备 ID")
    equipment_uuid = fields.CharField(max_length=36, null=True, description="MES 设备 UUID")
    tag_key = fields.CharField(max_length=100, description="点位 key")
    operator = fields.CharField(max_length=10, description="gt|lt|gte|lte|eq|ne")
    threshold_number = fields.DecimalField(max_digits=18, decimal_places=6, null=True, description="数值阈值")
    threshold_text = fields.CharField(max_length=200, null=True, description="文本阈值")
    severity = fields.CharField(max_length=20, default="warning", description="info|warning|critical")
    cooldown_seconds = fields.IntField(default=300, description="重复告警冷却秒数")
    notify_enabled = fields.BooleanField(default=False, description="是否触发站内通知")
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    remark = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")

    class Meta:
        table = "apps_kuaiiot_alert_rules"
        table_description = "星数采 - 告警规则"
        unique_together = (("tenant_id", "code"),)
        indexes = [
            ("tenant_id", "device_id"),
            ("tenant_id", "equipment_uuid"),
            ("tenant_id", "is_enabled"),
            ("tenant_id", "rule_type"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at", "deleted_by", "deleted_by_name"]


class IotAlert(BaseModel):
    """IoT 告警记录。"""

    tenant_id = fields.IntField(description="租户ID")
    rule_id = fields.IntField(null=True, description="规则 ID")
    device_id = fields.IntField(description="IoT 设备 ID")
    equipment_uuid = fields.CharField(max_length=36, null=True, description="MES 设备 UUID")
    tag_key = fields.CharField(max_length=100, description="点位 key")
    severity = fields.CharField(max_length=20, description="info|warning|critical")
    message = fields.TextField(description="告警消息")
    actual_value = fields.TextField(null=True, description="触发时的实际值")
    status = fields.CharField(max_length=20, default="open", description="open|acknowledged")
    triggered_at = fields.DatetimeField(description="触发时间")
    acknowledged_at = fields.DatetimeField(null=True, description="确认时间")
    acknowledged_by = fields.IntField(null=True, description="确认人 ID")
    recovered_at = fields.DatetimeField(null=True, description="恢复时间")
    closed_at = fields.DatetimeField(null=True, description="关闭时间")
    closed_by = fields.IntField(null=True, description="关闭人ID")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")

    class Meta:
        table = "apps_kuaiiot_alerts"
        table_description = "星数采 - 告警记录"
        indexes = [
            ("tenant_id", "status"),
            ("tenant_id", "device_id"),
            ("triggered_at",),
        ]

    class PydanticMeta:
        exclude = ["deleted_at", "deleted_by", "deleted_by_name"]


class IotEdgeConfig(BaseModel):
    """边缘 Agent 采集配置（Modbus 等 → HTTP ingest）。"""

    tenant_id = fields.IntField(description="租户ID")
    code = fields.CharField(max_length=50, description="配置编码")
    name = fields.CharField(max_length=100, description="配置名称")
    device_id = fields.IntField(description="目标 IoT 设备 ID")
    protocol = fields.CharField(max_length=30, default="modbus_tcp", description="modbus_tcp|modbus_rtu")
    config = fields.JSONField(description="寄存器映射与发布配置 JSON")
    config_version = fields.IntField(default=1, description="配置版本")
    last_agent_heartbeat_at = fields.DatetimeField(null=True, description="Agent 最近心跳时间")
    agent_config_version = fields.IntField(null=True, description="Agent 心跳报告的已应用版本")
    agent_version = fields.CharField(max_length=50, null=True, description="Agent 版本")
    agent_status = fields.CharField(max_length=20, default="unknown", description="online|offline|unknown")
    buffer_pending_count = fields.IntField(default=0, description="Agent 本地缓冲待传条数")
    trial_request_uuid = fields.CharField(max_length=36, null=True, description="试用下发请求ID")
    trial_result = fields.JSONField(null=True, description="试用下发结果")
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    remark = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")

    class Meta:
        table = "apps_kuaiiot_edge_configs"
        table_description = "星数采 - 边缘 Agent 配置"
        unique_together = (("tenant_id", "code"),)
        indexes = [
            ("tenant_id", "device_id"),
            ("tenant_id", "is_enabled"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at", "deleted_by", "deleted_by_name"]


