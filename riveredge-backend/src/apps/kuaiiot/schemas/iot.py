"""快数采 Pydantic Schema。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.kuaiiot.constants import INGEST_MAX_TAGS_PER_PAYLOAD


class ConnectionBase(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    connection_type: str = Field(..., max_length=30)
    config: Optional[Dict[str, Any]] = None
    is_enabled: bool = True
    remark: Optional[str] = None


class ConnectionCreate(ConnectionBase):
    pass


class ConnectionUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    connection_type: Optional[str] = Field(None, max_length=30)
    config: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    remark: Optional[str] = None


class ConnectionResponse(ConnectionBase):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    id: int
    tenant_id: int
    health_status: str
    last_health_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ConnectionListResponse(BaseModel):
    items: List[ConnectionResponse]
    total: int
    page: int
    page_size: int


class ConnectionRecentMessage(BaseModel):
    uuid: str
    topic: str
    qos: int = 0
    retained: bool = False
    received_at: str
    payload: Optional[Any] = None
    payload_format: str = "unknown"
    ingest_summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ConnectionRecentMessageListResponse(BaseModel):
    items: List[ConnectionRecentMessage]
    total: int


class DiscoveredMqttDevice(BaseModel):
    external_device_id: str
    device_name: str
    device_key: Optional[str] = None
    line_name: Optional[str] = None
    line_code: Optional[str] = None
    workshop_name: Optional[str] = None
    workshop_code: Optional[str] = None
    status: Optional[str] = None
    last_seen_at: Optional[str] = None
    topic: Optional[str] = None
    already_bound: bool = False
    label: str
    connection_id: Optional[int] = None


class DiscoveredMqttDeviceListResponse(BaseModel):
    items: List[DiscoveredMqttDevice]
    total: int


class DeviceBase(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    external_device_id: str = Field(..., max_length=100)
    connection_id: Optional[int] = None
    product_id: Optional[int] = None
    group_id: Optional[int] = None
    equipment_uuid: Optional[str] = Field(None, max_length=36)
    remark: Optional[str] = None


class DeviceCreate(DeviceBase):
    tag_template_code: Optional[str] = Field(None, max_length=50)


class DeviceUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    external_device_id: Optional[str] = Field(None, max_length=100)
    connection_id: Optional[int] = None
    product_id: Optional[int] = None
    group_id: Optional[int] = None
    equipment_uuid: Optional[str] = Field(None, max_length=36)
    remark: Optional[str] = None


class DeviceResponse(DeviceBase):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    id: int
    tenant_id: int
    device_token: str
    is_online: bool
    last_seen_at: Optional[datetime] = None
    last_mes_sync_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class DeviceListResponse(BaseModel):
    items: List[DeviceResponse]
    total: int
    page: int
    page_size: int


class DeviceBatchCreate(BaseModel):
    product_id: int
    name_prefix: str = Field(..., max_length=80)
    count: int = Field(..., ge=1, le=100)
    code_prefix: Optional[str] = Field(None, max_length=50)
    connection_id: Optional[int] = None
    group_id: Optional[int] = None
    equipment_uuid: Optional[str] = Field(None, max_length=36)
    remark: Optional[str] = None


class DeviceBatchItemResponse(BaseModel):
    uuid: str
    code: str
    name: str
    device_token: str


class DeviceBatchResponse(BaseModel):
    items: List[DeviceBatchItemResponse]
    total: int


class TagDefinitionBase(BaseModel):
    device_id: int
    tag_key: str = Field(..., max_length=100)
    name: str = Field(..., max_length=100)
    value_type: str = Field(default="number", max_length=20)
    unit: Optional[str] = Field(None, max_length=30)
    map_target: str = Field(..., max_length=100)
    fill_target: Optional[str] = Field(None, max_length=100)
    is_enabled: bool = True


class TagDefinitionCreate(TagDefinitionBase):
    pass


class TagDefinitionUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    value_type: Optional[str] = Field(None, max_length=20)
    unit: Optional[str] = Field(None, max_length=30)
    map_target: Optional[str] = Field(None, max_length=100)
    fill_target: Optional[str] = Field(None, max_length=100)
    is_enabled: Optional[bool] = None


class TagDefinitionResponse(TagDefinitionBase):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    id: int
    tenant_id: int
    created_at: datetime
    updated_at: datetime


class TagDefinitionListResponse(BaseModel):
    items: List[TagDefinitionResponse]
    total: int
    page: int
    page_size: int


class TagSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tag_key: str
    value_text: Optional[str] = None
    value_number: Optional[Decimal] = None
    value_bool: Optional[bool] = None
    quality: str
    sampled_at: datetime


class TagHistoryResponse(BaseModel):
    tag_key: str
    value_text: Optional[str] = None
    value_number: Optional[Decimal] = None
    value_bool: Optional[bool] = None
    quality: str = "good"
    sampled_at: datetime


class TagHistoryListResponse(BaseModel):
    items: List[TagHistoryResponse]
    tsdb_configured: bool


class IngestPayload(BaseModel):
    tags: Dict[str, Any] = Field(default_factory=dict)
    events: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: Optional[datetime] = None
    idempotency_key: Optional[str] = Field(None, max_length=128)

    @field_validator("tags")
    @classmethod
    def validate_tags_limit(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        if len(value) > INGEST_MAX_TAGS_PER_PAYLOAD:
            raise ValueError(f"单次入站 tags 最多 {INGEST_MAX_TAGS_PER_PAYLOAD} 个")
        return value


class IngestResponse(BaseModel):
    accepted: int
    events_accepted: int = 0
    synced_to_mes: bool
    message: str = "ok"


class IngestBatchItem(BaseModel):
    tags: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None
    idempotency_key: Optional[str] = Field(None, max_length=128)

    @field_validator("tags")
    @classmethod
    def validate_tags_limit(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        if len(value) > INGEST_MAX_TAGS_PER_PAYLOAD:
            raise ValueError(f"单次入站 tags 最多 {INGEST_MAX_TAGS_PER_PAYLOAD} 个")
        return value


class IngestBatchPayload(BaseModel):
    items: List[IngestBatchItem] = Field(..., min_length=1)


class IngestBatchResponse(BaseModel):
    total: int
    accepted: int
    duplicates: int
    failed: int
    synced_to_mes: bool


class DashboardSummaryResponse(BaseModel):
    total_devices: int
    online_devices: int
    total_connections: int
    enabled_connections: int
    total_tags: int
    points_today: int
    recent_devices: List[DeviceResponse]


class ConnectorSyncRequest(BaseModel):
    connection_uuid: str


class ConnectorSyncResponse(BaseModel):
    synced_devices: int
    message: str


class ConnectorPullTelemetryResponse(BaseModel):
    ingested_devices: int
    skipped_devices: int
    message: str


class ConnectorPushTelemetryRequest(BaseModel):
    connection_uuid: str
    device_uuid: str
    tags: Dict[str, Any]


class ConnectorPushTelemetryResponse(BaseModel):
    pushed: bool
    message: str


class TagTemplateResponse(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    tag_count: int


class ApplyTagTemplateResponse(BaseModel):
    created: int
    skipped: int
    template_code: str


class ProductTagDefinition(BaseModel):
    tag_key: str = Field(..., max_length=100)
    name: str = Field(..., max_length=100)
    value_type: str = Field(default="number", max_length=20)
    unit: Optional[str] = Field(None, max_length=30)
    map_target: str = Field(..., max_length=100)
    fill_target: Optional[str] = Field(None, max_length=100)


class ProductEventDefinition(BaseModel):
    event_key: str = Field(..., max_length=100)
    name: str = Field(..., max_length=100)
    level: str = Field(default="info", max_length=20)


class ProductFunctionParamDefinition(BaseModel):
    key: str = Field(..., max_length=100)
    name: str = Field(..., max_length=100)
    value_type: str = Field(default="number", max_length=20)
    required: bool = True


class ProductFunctionDefinition(BaseModel):
    function_key: str = Field(..., max_length=100)
    name: str = Field(..., max_length=100)
    params: List[ProductFunctionParamDefinition] = Field(default_factory=list)
    timeout_seconds: int = Field(default=30, ge=1, le=3600)
    edge_action: Optional[Dict[str, Any]] = None


class ProductBase(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    tags: List[ProductTagDefinition] = Field(default_factory=list)
    events: List[ProductEventDefinition] = Field(default_factory=list)
    functions: List[ProductFunctionDefinition] = Field(default_factory=list)
    remark: Optional[str] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    tags: Optional[List[ProductTagDefinition]] = None
    events: Optional[List[ProductEventDefinition]] = None
    functions: Optional[List[ProductFunctionDefinition]] = None
    remark: Optional[str] = None


class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    id: int
    tenant_id: int
    created_at: datetime
    updated_at: datetime


class ProductListResponse(BaseModel):
    items: List[ProductResponse]
    total: int
    page: int
    page_size: int


class LoadBuiltinProductPresetsResponse(BaseModel):
    created: int
    skipped: int
    total: int


class AlertRuleBase(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    rule_type: str = Field(default="threshold", max_length=20)
    device_id: Optional[int] = None
    equipment_uuid: Optional[str] = Field(None, max_length=36)
    tag_key: Optional[str] = Field(None, max_length=100)
    operator: Optional[str] = Field(None, max_length=10)
    threshold_number: Optional[Decimal] = None
    threshold_text: Optional[str] = Field(None, max_length=200)
    severity: str = Field(default="warning", max_length=20)
    cooldown_seconds: int = Field(default=300, ge=0)
    notify_enabled: bool = False
    is_enabled: bool = True
    remark: Optional[str] = None


class AlertRuleCreate(AlertRuleBase):
    pass


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    rule_type: Optional[str] = Field(None, max_length=20)
    device_id: Optional[int] = None
    equipment_uuid: Optional[str] = Field(None, max_length=36)
    tag_key: Optional[str] = Field(None, max_length=100)
    operator: Optional[str] = Field(None, max_length=10)
    threshold_number: Optional[Decimal] = None
    threshold_text: Optional[str] = Field(None, max_length=200)
    severity: Optional[str] = Field(None, max_length=20)
    cooldown_seconds: Optional[int] = Field(None, ge=0)
    notify_enabled: Optional[bool] = None
    is_enabled: Optional[bool] = None
    remark: Optional[str] = None


class AlertRuleResponse(AlertRuleBase):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    id: int
    tenant_id: int
    created_at: datetime
    updated_at: datetime


class AlertRuleListResponse(BaseModel):
    items: List[AlertRuleResponse]
    total: int
    page: int
    page_size: int


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    id: int
    tenant_id: int
    rule_id: Optional[int] = None
    device_id: int
    equipment_uuid: Optional[str] = None
    tag_key: str
    severity: str
    message: str
    actual_value: Optional[str] = None
    status: str
    triggered_at: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class AlertListResponse(BaseModel):
    items: List[AlertResponse]
    total: int
    page: int
    page_size: int


class EdgeConfigBase(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    device_id: int
    protocol: str = Field(default="modbus_tcp", max_length=30)
    config: Dict[str, Any]
    is_enabled: bool = True
    remark: Optional[str] = None


class EdgeConfigCreate(EdgeConfigBase):
    pass


class EdgeConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    device_id: Optional[int] = None
    protocol: Optional[str] = Field(None, max_length=30)
    config: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    remark: Optional[str] = None


class EdgeConfigResponse(EdgeConfigBase):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    id: int
    tenant_id: int
    config_version: int = 1
    last_agent_heartbeat_at: Optional[datetime] = None
    agent_version: Optional[str] = None
    agent_status: str = "unknown"
    buffer_pending_count: int = 0
    created_at: datetime
    updated_at: datetime


class EdgeConfigListResponse(BaseModel):
    items: List[EdgeConfigResponse]
    total: int
    page: int
    page_size: int


class EdgeAgentSpecResponse(BaseModel):
    version: int
    protocol: str
    device_token: str
    config: Dict[str, Any]
    config_version: int = 1


class EdgeRuntimeConfigResponse(EdgeAgentSpecResponse):
    ingest_path: str
    batch_ingest_path: str
    heartbeat_path: str
    command_result_path: str


class EdgeAgentHeartbeatPayload(BaseModel):
    edge_config_code: str = Field(..., max_length=50)
    config_version: Optional[int] = None
    agent_version: Optional[str] = Field(None, max_length=50)
    buffer_pending_count: int = Field(default=0, ge=0)
    status: str = Field(default="online", max_length=20)
    message: Optional[str] = None


class EdgeAgentHeartbeatResponse(BaseModel):
    config_version: int
    config_changed: bool
    pending_commands: List[Dict[str, Any]] = Field(default_factory=list)
    message: str = "ok"


class EdgeAgentCommandResultPayload(BaseModel):
    command_uuid: str = Field(..., max_length=36)
    success: bool
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class DeviceGroupBase(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    parent_id: Optional[int] = None
    sort_order: int = 0
    remark: Optional[str] = None


class DeviceGroupCreate(DeviceGroupBase):
    pass


class DeviceGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None
    remark: Optional[str] = None


class DeviceGroupResponse(DeviceGroupBase):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    id: int
    tenant_id: int
    created_at: datetime
    updated_at: datetime


class DeviceGroupTreeNode(BaseModel):
    uuid: str
    id: int
    code: str
    name: str
    parent_id: Optional[int] = None
    sort_order: int = 0
    remark: Optional[str] = None
    children: List[DeviceGroupTreeNode] = Field(default_factory=list)


class DeviceGroupListResponse(BaseModel):
    items: List[DeviceGroupResponse]
    total: int


class DeviceGroupTreeResponse(BaseModel):
    items: List[DeviceGroupTreeNode]


class DeviceCommandCreate(BaseModel):
    function_key: str = Field(..., max_length=100)
    params: Dict[str, Any] = Field(default_factory=dict)
    dispatch_channel: Optional[str] = Field(None, max_length=30)


class DeviceCommandResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    id: int
    tenant_id: int
    device_id: int
    function_key: str
    params: Dict[str, Any]
    dispatch_channel: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    requested_by: Optional[int] = None
    sent_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class DeviceCommandListResponse(BaseModel):
    items: List[DeviceCommandResponse]
    total: int
    page: int
    page_size: int


class MessageLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    id: int
    tenant_id: int
    device_id: int
    direction: str
    msg_type: str
    payload: Optional[Dict[str, Any]] = None
    result: str
    error_message: Optional[str] = None
    created_at: datetime


class MessageLogListResponse(BaseModel):
    items: List[MessageLogResponse]
    total: int
    page: int
    page_size: int


class OpsSummaryResponse(BaseModel):
    connections: Dict[str, int]
    devices: Dict[str, int]
    edge_agents: Dict[str, int]
    alerts: Dict[str, int]
    ingest: Dict[str, int]
    tsdb_configured: bool


class OeeLiveEquipmentResponse(BaseModel):
    equipment_uuid: str
    equipment_code: str
    equipment_name: str
    window_start: datetime
    window_end: datetime
    sensor: Dict[str, Any]
    mes_quality_rate: Optional[float] = None
    oee_live: Optional[float] = None
    oee_note: str
    latest_status: Optional[str] = None
    is_online: bool = False
    iot_device_uuid: Optional[str] = None
    monitor_points: int = 0


class OeeLiveListResponse(BaseModel):
    items: List[OeeLiveEquipmentResponse]
    total: int


class PipelineNodeResponse(BaseModel):
    id: str
    node_type: str
    label: str
    status: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class PipelineEdgeResponse(BaseModel):
    source: str
    target: str
    edge_type: str


class PipelineGraphResponse(BaseModel):
    nodes: List[PipelineNodeResponse]
    edges: List[PipelineEdgeResponse]
    summary: Dict[str, Any]


class EquipmentOpsFeedResponse(BaseModel):
    generated_at: datetime
    equipment_list: List[Dict[str, Any]]
    ops_metrics: List[Dict[str, Any]]
    status_dist: List[Dict[str, Any]]
    workshop_stats: List[Dict[str, Any]]
    spot_check_recent: List[Dict[str, Any]]


class FillContextResponse(BaseModel):
    values: Dict[str, Any]
    device_uuid: Optional[str] = None
    equipment_uuid: Optional[str] = None
