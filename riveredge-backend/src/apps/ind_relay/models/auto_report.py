from tortoise import fields

from core.models.base import BaseModel

MODE_REALTIME = "REALTIME_INCREMENT"
MODE_PLAN_OFFLINE = "PLAN_REACHED_OR_OFFLINE"
ZSCL_TAG_KEY = "zscl"


class RelayAutoReportConfig(BaseModel):
    """租户级自动报工策略。"""

    class Meta:
        table = "apps_ind_relay_auto_report_configs"
        table_description = "继电器行业 - 自动报工配置"
        app = "models"
        indexes = [("tenant_id",), ("uuid",)]

    id = fields.IntField(pk=True)
    is_enabled = fields.BooleanField(default=False, description="启用自动报工")
    match_by_device = fields.BooleanField(
        default=False,
        description="True=按设备匹配工序；False=只报末道工序",
    )
    interval_minutes = fields.IntField(default=5, description="结算间隔（分钟）")
    report_mode = fields.CharField(
        max_length=40,
        default=MODE_REALTIME,
        description="REALTIME_INCREMENT | PLAN_REACHED_OR_OFFLINE",
    )
    offline_threshold_seconds = fields.IntField(
        default=180,
        description="离线兜底秒数（仅计划量/断链模式）",
    )
    reporter_user_id = fields.IntField(null=True, description="报工创建人用户 ID")
    reporter_user_name = fields.CharField(max_length=100, null=True, description="报工创建人姓名")
    remarks = fields.TextField(null=True)
    deleted_at = fields.DatetimeField(null=True)


class RelayAutoReportBinding(BaseModel):
    """启用自动报工的快数采设备（须已绑 MES 设备）。"""

    class Meta:
        table = "apps_ind_relay_auto_report_bindings"
        table_description = "继电器行业 - 自动报工设备绑定"
        app = "models"
        indexes = [
            ("tenant_id",),
            ("iot_device_id",),
            ("equipment_id",),
            ("uuid",),
        ]

    id = fields.IntField(pk=True)
    iot_device_id = fields.IntField(description="快数采 IotDevice.id")
    iot_device_uuid = fields.CharField(max_length=36, null=True)
    iot_device_code = fields.CharField(max_length=50, null=True)
    iot_device_name = fields.CharField(max_length=100, null=True)
    external_device_id = fields.CharField(max_length=100, null=True, description="MQTT 外部设备 ID")
    equipment_uuid = fields.CharField(max_length=36, description="MES 设备 UUID")
    equipment_id = fields.IntField(null=True, description="MES 设备 ID")
    equipment_code = fields.CharField(max_length=50, null=True)
    equipment_name = fields.CharField(max_length=100, null=True)
    is_enabled = fields.BooleanField(default=True)
    last_zscl = fields.DecimalField(max_digits=18, decimal_places=6, null=True)
    pending_quantity = fields.DecimalField(max_digits=18, decimal_places=6, default=0)
    baseline_aligned = fields.BooleanField(default=False, description="是否已对齐 zscl 基线")
    bound_work_order_id = fields.IntField(null=True)
    bound_work_order_code = fields.CharField(max_length=50, null=True)
    bound_operation_id = fields.IntField(null=True, description="工艺工序 ID")
    bound_operation_name = fields.CharField(max_length=200, null=True)
    last_settle_at = fields.DatetimeField(null=True)
    last_seen_at = fields.DatetimeField(null=True)
    offline_flushed = fields.BooleanField(default=False, description="本次离线是否已兜底报工")
    remarks = fields.TextField(null=True)
    deleted_at = fields.DatetimeField(null=True)


class RelayAutoReportLog(BaseModel):
    """自动报工运行日志。"""

    class Meta:
        table = "apps_ind_relay_auto_report_logs"
        table_description = "继电器行业 - 自动报工日志"
        app = "models"
        indexes = [
            ("tenant_id", "created_at"),
            ("binding_id",),
            ("uuid",),
        ]

    id = fields.IntField(pk=True)
    binding_id = fields.IntField(null=True)
    iot_device_id = fields.IntField(null=True)
    level = fields.CharField(max_length=20, default="info")
    event = fields.CharField(max_length=50, description="baseline/skip/report/error/offline")
    message = fields.TextField(null=True)
    zscl = fields.DecimalField(max_digits=18, decimal_places=6, null=True)
    increment_qty = fields.DecimalField(max_digits=18, decimal_places=6, null=True)
    work_order_id = fields.IntField(null=True)
    work_order_code = fields.CharField(max_length=50, null=True)
    operation_id = fields.IntField(null=True)
    reporting_record_id = fields.IntField(null=True)
    extra = fields.JSONField(null=True)
    deleted_at = fields.DatetimeField(null=True)
