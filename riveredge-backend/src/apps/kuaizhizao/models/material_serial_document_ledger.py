"""序列号出入库留痕。一件序列号在一次出入库动作上一行。"""

from tortoise import fields

from core.models.base import BaseModel


class MaterialSerialDocumentLedger(BaseModel):
    """序列号单据归属台账。

    身份仍是 ``MaterialSerial``。本表只回答经过哪些出入库单据、当前落在哪一张。
    ``reverses_id`` 为空表示正向流水；撤回只追加，指向被冲销的那一行。
    """

    class Meta:
        table = "apps_kuaizhizao_material_serial_document_ledgers"
        table_description = "快格轻制造 - 序列号出入库留痕"
        unique_together = [("tenant_id", "idempotency_key", "serial_no")]
        indexes = [
            ("tenant_id", "serial_no", "occurred_at"),
            ("tenant_id", "reverses_id"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    serial_no = fields.CharField(max_length=100, description="序列号，与 MaterialSerial.serial_no 相同")
    material_id = fields.IntField(description="物料ID")
    direction = fields.CharField(max_length=8, description="方向：in 入 / out 出")
    movement_type = fields.CharField(max_length=50, description="移动类型，与库存过账 movement_type 同一套词")
    source_type = fields.CharField(max_length=50, description="来源单据类型，与库存过账 source_type 同一套词")
    source_doc_id = fields.IntField(null=True, description="来源单据ID")
    source_doc_code = fields.CharField(max_length=64, null=True, description="来源单据编码")
    idempotency_key = fields.CharField(max_length=200, description="库存幂等键")
    occurred_at = fields.DatetimeField(description="发生时间")
    operator_id = fields.IntField(null=True, description="操作人ID")
    operator_name = fields.CharField(max_length=100, null=True, description="操作人姓名")
    reverses_id = fields.IntField(null=True, description="反向指针，指向被冲销的台账行；空表示正向")
