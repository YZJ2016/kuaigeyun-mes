"""消息追踪（apps_kuaiiot_message_logs）。列来自迁移 525。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiiotMessageLog(BaseModel):
    class Meta:
        table = "apps_kuaiiot_message_logs"
        table_description = "快数采 - 消息追踪"
        indexes = [("tenant_id", "device_id", "created_at")]

    id = fields.IntField(pk=True, description="主键ID")
    device_id = fields.IntField(description="IoT 设备ID")
    direction = fields.CharField(max_length=10, description="方向")
    msg_type = fields.CharField(max_length=30, description="消息类型")
    payload = fields.JSONField(null=True, description="消息体")
    result = fields.CharField(max_length=20, description="处理结果")
    error_message = fields.TextField(null=True, description="失败说明")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")
