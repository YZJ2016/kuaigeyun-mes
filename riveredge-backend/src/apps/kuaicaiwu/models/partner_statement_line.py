"""往来对账单明细行（物料行级真源）。"""

from tortoise import fields

from core.models.base import BaseModel


class PartnerStatementLine(BaseModel):
    """对账单一行：业务类为物料行，财务类为单据行（source_line_id=0）。"""

    tenant_id = fields.IntField(description="租户ID")
    statement = fields.ForeignKeyField(
        "models.PartnerStatement",
        related_name="statement_lines",
        on_delete=fields.CASCADE,
        description="对账单",
    )

    line_kind = fields.CharField(max_length=16, default="material", description="material|finance")
    source_doc_type = fields.CharField(max_length=50, description="规范化源单类型")
    source_doc_id = fields.IntField(description="源单ID")
    source_line_id = fields.IntField(default=0, description="源单物料行ID，财务单为0")

    doc_code = fields.CharField(max_length=50, null=True, description="单据编码")
    doc_date = fields.DateField(null=True, description="业务日期")
    material_id = fields.IntField(null=True, description="物料ID")
    material_code = fields.CharField(max_length=50, null=True, description="物料编码")
    material_name = fields.CharField(max_length=200, null=True, description="物料名称")
    material_spec = fields.CharField(max_length=200, null=True, description="规格")
    unit = fields.CharField(max_length=20, null=True, description="单位")
    quantity = fields.DecimalField(max_digits=12, decimal_places=4, null=True, description="数量")

    amount_basis = fields.CharField(max_length=20, default="tax_inclusive", description="含税/未税口径")
    doc_amount = fields.DecimalField(max_digits=16, decimal_places=4, default=0, description="单据金额")
    prior_stated_amount = fields.DecimalField(max_digits=16, decimal_places=4, default=0, description="已对账")
    statement_amount = fields.DecimalField(max_digits=16, decimal_places=4, default=0, description="本次对账")
    remaining_amount = fields.DecimalField(max_digits=16, decimal_places=4, default=0, description="未对金额")
    invoice_occupied_amount = fields.DecimalField(max_digits=16, decimal_places=4, default=0, description="已开票占用")
    invoiceable_amount = fields.DecimalField(max_digits=16, decimal_places=4, default=0, description="可开票")

    debit = fields.DecimalField(max_digits=16, decimal_places=4, default=0, description="借方")
    credit = fields.DecimalField(max_digits=16, decimal_places=4, default=0, description="贷方")
    doc_type_label = fields.CharField(max_length=50, null=True, description="展示用单据类型")

    is_read_only = fields.BooleanField(default=False, description="已审核快照只读")
    sort_index = fields.IntField(default=0, description="排序")
    line_snapshot = fields.JSONField(null=True, description="扩展快照（树层级/质检等）")

    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    class Meta:
        table = "apps_kuaicaiwu_partner_statement_lines"
        table_description = "轻管理会计 - 往来对账单明细行"
        indexes = [
            ("tenant_id", "statement_id"),
            ("tenant_id", "source_doc_type", "source_doc_id", "source_line_id"),
        ]
        unique_together = (("statement_id", "source_doc_type", "source_doc_id", "source_line_id"),)

    class PydanticMeta:
        exclude = ["deleted_at"]