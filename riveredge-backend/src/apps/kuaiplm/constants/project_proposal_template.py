"""项目建议书模板字段常量。

产品类型 / 客户资料 / 开发要求分类：选项真源为系统数据字典（可增补），
下列字典码与 DEV_REQ 业务分支常量须与 SYSTEM_DICTIONARIES 预置项一致。
"""

from __future__ import annotations

from typing import FrozenSet, Tuple

PROJECT_PROPOSAL_PRODUCT_LINE_DICT = "PROJECT_PROPOSAL_PRODUCT_LINE"
PROJECT_PROPOSAL_CUSTOMER_MATERIAL_DICT = "PROJECT_PROPOSAL_CUSTOMER_MATERIAL"
PROJECT_PROPOSAL_DEV_REQ_TYPE_DICT = "PROJECT_PROPOSAL_DEV_REQ_TYPE"

PROPOSING_DEPTS = frozenset({"domestic_sales", "export_sales"})
# 开发要求 D/E/F：旧系列须完整填写供应商评审表（业务分支，非字典枚举）
DEV_REQ_TYPES_NEED_SUPPLIER: FrozenSet[str] = frozenset({"D", "E", "F"})

SUPPLIER_ASSESSMENT_MATERIALS: Tuple[Tuple[str, str], ...] = (
    ("plastic_shell", "塑壳"),
    ("conductive_adhesive", "导电胶"),
    ("metal_dome", "Metal-dome"),
    ("facing", "贴面"),
    ("pcb", "PCB"),
    ("chip", "芯片"),
    ("packaging", "包装箱/袋"),
)

SUPPLIER_ASSESSMENT_MATERIAL_KEYS = frozenset(k for k, _ in SUPPLIER_ASSESSMENT_MATERIALS)
