"""星数采常量与枚举。"""

from __future__ import annotations

CONNECTION_TYPES = frozenset({"mqtt", "thingsboard", "jetlinks", "http_webhook"})

TAG_VALUE_TYPES = frozenset({"string", "number", "boolean"})

MAP_TARGETS = frozenset(
    {
        "status",
        "temperature",
        "pressure",
        "vibration",
        "is_online",
    }
)

FILL_TARGET_PREFIXES = (
    "sop_parameters.",
    "other_parameters.",
    "process_params.",
)

EVENT_LEVELS = frozenset({"info", "warning", "critical"})

ALERT_RULE_TYPES = frozenset({"threshold", "offline"})
ALERT_OPERATORS = frozenset({"gt", "lt", "gte", "lte", "eq", "ne"})
ALERT_SEVERITIES = frozenset({"info", "warning", "critical"})
OFFLINE_ALERT_TAG_KEY = "is_online"
EVENT_ALERT_TAG_PREFIX = "event:"

EDGE_PROTOCOLS = frozenset({"modbus_tcp", "modbus_rtu", "opc_ua", "s7"})
MODBUS_DATA_TYPES = frozenset({"int16", "uint16", "int32", "uint32", "float32", "bool"})

INGEST_THROTTLE_SECONDS = 5
INGEST_MAX_TAGS_PER_PAYLOAD = 200
INGEST_BATCH_MAX_ITEMS = 100
INGEST_DEDUP_RETENTION_DAYS = 7

OFFLINE_THRESHOLD_SECONDS = 300
EDGE_AGENT_OFFLINE_SECONDS = 120

DEVICE_BATCH_MAX = 100

ALERT_RETENTION_DAYS = 90
MESSAGE_LOG_RETENTION_DAYS = 30
MESSAGE_LOG_PAYLOAD_MAX = 4000
MESSAGE_DIRECTIONS = frozenset({"inbound", "outbound", "in", "out"})
MESSAGE_TYPES = frozenset(
    {"ingest", "command", "command_result", "heartbeat", "sync", "event", "monitor_writeback", "other"}
)
MESSAGE_RESULTS = frozenset(
    {
        "success",
        "failed",
        "timeout",
        "skipped",
        "pending",
        "sent",
        "uncertain",
        "accepted",
        "alerted",
        "recorded",
        "written",
        "synced",
        "error",
    }
)

# 产品指令未声明 timeout_seconds 时的默认过期秒数（1 天）
COMMAND_DEFAULT_TIMEOUT_SECONDS = 86400
COMMAND_STATUSES = frozenset({"pending", "sent", "success", "failed", "timeout", "uncertain"})
DISPATCH_CHANNELS = frozenset({"http", "mqtt", "edge", "edge_heartbeat", "thingsboard", "jetlinks"})

TSDB_INTEGRATION_CODE = "kuaiiot_tsdb"
TSDB_INTEGRATION_TYPE = "influxdb"

MES_DATA_SOURCE = "sensor"

# ---- 星数采本地执行版常量 ----
THROTTLE_SECONDS = 5
SENSOR_DATA_SOURCE = "sensor"

MONITOR_COLUMNS = (
    "status",
    "is_online",
    "temperature",
    "pressure",
    "vibration",
    "other_parameters",
)
OTHER_PARAMETERS_PREFIX = "other_parameters."
VALUE_TYPES = ("number", "boolean", "text", "string")
PUBLISH_MODES = ("http_ingest", "mqtt")
OFFLINE_ALERT_OPERATOR = "eq"
OFFLINE_ALERT_THRESHOLD_TEXT = "false"
