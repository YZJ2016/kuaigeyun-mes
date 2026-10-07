"""告警规则与告警记录。列来自迁移 521，rule_type 来自迁移 524，默认 threshold。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiiotAlertRule(BaseModel):
    class Meta:
        table = "apps_kuaiiot_alert_rules"
        table_description = "快数采 - 告警规则"
        unique_together = (("tenant_id", "code"),)
        indexes = [
            ("tenant_id", "device_id"),
            ("tenant_id", "equipment_uuid"),
            ("tenant_id", "is_enabled"),
            ("tenant_id", "rule_type"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    code = fields.CharField(max_length=50, description="规则编码")
    name = fields.CharField(max_length=100, description="规则名称")
    device_id = fields.IntField(null=True, description="IoT 设备ID")
    equipment_uuid = fields.CharField(max_length=36, null=True, description="星制造设备UUID")
    tag_key = fields.CharField(max_length=100, description="点位键")
    operator = fields.CharField(max_length=10, description="比较符")
    threshold_number = fields.DecimalField(max_digits=18, decimal_places=6, null=True, description="数值阈值")
    threshold_text = fields.CharField(max_length=200, null=True, description="文本阈值")
    severity = fields.CharField(max_length=20, default="warning", description="严重级别")
    cooldown_seconds = fields.IntField(default=300, description="冷却秒数")
    notify_enabled = fields.BooleanField(default=False, description="是否通知")
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    rule_type = fields.CharField(max_length=20, default="threshold", description="规则类型")
    remark = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")


class KuaiiotAlert(BaseModel):
    class Meta:
        table = "apps_kuaiiot_alerts"
        table_description = "快数采 - 告警记录"
        indexes = [
            ("tenant_id", "status"),
            ("tenant_id", "device_id"),
            ("triggered_at",),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    rule_id = fields.IntField(null=True, description="规则ID")
    device_id = fields.IntField(description="IoT 设备ID")
    equipment_uuid = fields.CharField(max_length=36, null=True, description="星制造设备UUID")
    tag_key = fields.CharField(max_length=100, description="点位键")
    severity = fields.CharField(max_length=20, description="严重级别")
    message = fields.TextField(description="告警说明")
    actual_value = fields.TextField(null=True, description="触发时的实际值")
    status = fields.CharField(max_length=20, default="open", description="告警状态")
    triggered_at = fields.DatetimeField(description="触发时间")
    acknowledged_at = fields.DatetimeField(null=True, description="确认时间")
    acknowledged_by = fields.IntField(null=True, description="确认人ID")
    recovered_at = fields.DatetimeField(null=True, description="恢复时间")
    closed_at = fields.DatetimeField(null=True, description="处置时间")
    closed_by = fields.IntField(null=True, description="处置人ID")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")
