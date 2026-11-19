"""采购入库单与数据接口的出站绑定（租户一条）。"""

from tortoise import fields

from core.models.base import BaseModel


class PurchaseReceiptSyncBinding(BaseModel):
    """每个租户一条：出站目标 + 触发无感外推的动作（确认入库等）。"""

    id = fields.IntField(pk=True, description="主键")

    class Meta:
        table = "apps_kuaizhizao_purchase_receipt_sync_binding"
        table_description = "快格轻制造 - 采购入库单同步/出站绑定"
        indexes = [("tenant_id",)]

    source_type = fields.CharField(max_length=20, null=True, description="来源类型：api | dataset")
    api_uuid = fields.CharField(max_length=36, null=True, description="关联的数据接口 UUID")
    dataset_uuid = fields.CharField(max_length=36, null=True, description="关联的数据集 UUID")
    field_mapping = fields.JSONField(null=True, description="字段映射：来源列名 -> 目标字段名")
    sources = fields.JSONField(null=True, description="多来源：kind + 接口/数据集 + field_mapping")
    push_targets = fields.JSONField(null=True, description="多目标外推")
    trigger_actions = fields.JSONField(null=True, description="触发无感外推的动作（如 confirm）")
    match_key_field = fields.CharField(
        max_length=64,
        default="receipt_code",
        description="匹配键目标字段名（默认 receipt_code）",
    )
    sync_mode = fields.CharField(
        max_length=32,
        default="manual_full",
        description="manual_full | scheduled_full | scheduled_incremental",
    )
    sync_direction = fields.CharField(
        max_length=20,
        default="push",
        description="pull | push | bidirectional",
    )
    schedule_interval_minutes = fields.IntField(default=15, description="定时同步间隔（分钟）")
    last_success_at = fields.DatetimeField(null=True, description="最近一次成功同步时间")
    last_attempt_at = fields.DatetimeField(null=True, description="最近一次尝试同步时间")
    last_error = fields.TextField(null=True, description="最近一次同步错误")
