"""设备指令（apps_kuaiiot_device_commands）。列来自迁移 525。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiiotDeviceCommand(BaseModel):
    class Meta:
        table = "apps_kuaiiot_device_commands"
        table_description = "快数采 - 设备指令"
        indexes = [
            ("tenant_id", "device_id"),
            ("tenant_id", "status", "expires_at"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    device_id = fields.IntField(description="IoT 设备ID")
    function_key = fields.CharField(max_length=100, description="指令键")
    params = fields.JSONField(default=dict, description="指令参数")
    dispatch_channel = fields.CharField(max_length=30, description="下发通道")
    status = fields.CharField(max_length=20, default="pending", description="指令状态")
    result = fields.JSONField(null=True, description="执行结果")
    error_message = fields.TextField(null=True, description="失败说明")
    requested_by = fields.IntField(null=True, description="下发人ID")
    sent_at = fields.DatetimeField(null=True, description="下发时间")
    completed_at = fields.DatetimeField(null=True, description="完成时间")
    expires_at = fields.DatetimeField(null=True, description="超时时间")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")
