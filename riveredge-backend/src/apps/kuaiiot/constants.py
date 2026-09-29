"""星数采 W1 常量。节流按星制造设备，不读 IoT 设备 last_mes_sync_at。"""

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
VALUE_TYPES = ("number", "boolean", "text")
EDGE_PROTOCOLS = ("modbus_tcp", "modbus_rtu", "opc_ua", "s7")
INGEST_BATCH_MAX_ITEMS = 100
MODBUS_DATA_TYPES = ("int16", "uint16", "int32", "uint32", "float32", "bool")
PUBLISH_MODES = ("http_ingest", "mqtt")
DEVICE_BATCH_MAX = 100
OFFLINE_ALERT_TAG_KEY = "is_online"
OFFLINE_ALERT_OPERATOR = "eq"
OFFLINE_ALERT_THRESHOLD_TEXT = "false"
TSDB_INTEGRATION_CODE = "kuaiiot_tsdb"
TSDB_INTEGRATION_TYPE = "influxdb"
# 产品指令未声明 timeout_seconds 时的默认过期秒数（1 天）
COMMAND_DEFAULT_TIMEOUT_SECONDS = 86400
