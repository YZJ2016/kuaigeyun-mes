"""
单据行物料伙伴映射与型号快照字段（销售/采购/成品入库等共用）。

Author: Agent
Date: 2026-10-21
"""

from tortoise import fields


class DocumentLinePartnerMaterialSnapshotMixin:
    """写路径快照：伙伴料号/品名 + 主数据型号。"""

    partner_material_code = fields.CharField(
        max_length=100, null=True, description="伙伴物料编码（客户/供应商料号）"
    )
    partner_material_name = fields.CharField(
        max_length=200, null=True, description="伙伴物料名称（客户/供应商品名）"
    )
    material_model = fields.CharField(max_length=200, null=True, description="物料型号")
