"""字段权限资源 → 策略类（唯一真源）。

角色「字段权限」页每个资源最多两类策略：
- amount：金额（含单价、税额、合计等）
- party_name：客户/供应商名称

未注册资源不生成任何字段策略。
"""

from __future__ import annotations

from typing import FrozenSet

FIELD_KIND_AMOUNT = "amount"
FIELD_KIND_PARTY_NAME = "party_name"

FIELD_PERMISSION_KINDS: FrozenSet[str] = frozenset(
    {FIELD_KIND_AMOUNT, FIELD_KIND_PARTY_NAME}
)

# 策略类 → 运行时脱敏的单据列（canonical）
FIELD_KIND_COLUMNS: dict[str, FrozenSet[str]] = {
    FIELD_KIND_AMOUNT: frozenset(
        {
            "amount",
            "total_amount",
            "tax_amount",
            "untaxed_amount",
            "unit_price",
            "price",
            "amount_with_tax",
            "amount_without_tax",
        }
    ),
    FIELD_KIND_PARTY_NAME: frozenset(
        {
            "customer_name",
            "supplier_name",
            "default_supplier_id",
            "default_supplier_name",
        }
    ),
}

_COLUMN_TO_KIND: dict[str, str] = {
    col: kind for kind, cols in FIELD_KIND_COLUMNS.items() for col in cols
}

_KINDS_AMOUNT_PARTY: FrozenSet[str] = frozenset(
    {FIELD_KIND_AMOUNT, FIELD_KIND_PARTY_NAME}
)
_KINDS_AMOUNT_ONLY: FrozenSet[str] = frozenset({FIELD_KIND_AMOUNT})
_KINDS_PARTY_ONLY: FrozenSet[str] = frozenset({FIELD_KIND_PARTY_NAME})

# app:resource（小写）→ 该单据具备的策略类
FIELD_PERMISSION_RESOURCE_KINDS: dict[str, FrozenSet[str]] = {
    # kuaizhizao - 销售
    "kuaizhizao:quotation": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:sales-contract": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:sales-order": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:sales-order-change": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:demand": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:outbound": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:sales-return": _KINDS_AMOUNT_PARTY,
    # kuaizhizao - 采购 / 外协
    "kuaizhizao:purchase-requisition": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:purchase-order": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:purchase-order-change": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:inbound": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:purchase-return": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:purchase-inquiry": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:payment-application": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:purchase-demand-party": _KINDS_PARTY_ONLY,
    "kuaizhizao:sales-forecast": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:sales-review": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:shipment-notice": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:receipt-notice": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:plan-management-demand-management": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:plan-management-demand-computation": _KINDS_AMOUNT_ONLY,
    "kuaizhizao:plan-management-demand-change": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:outsource-order": _KINDS_AMOUNT_ONLY,
    "kuaizhizao:outsource-work-order": _KINDS_AMOUNT_ONLY,
    "kuaizhizao:outsource-issue": _KINDS_AMOUNT_ONLY,
    "kuaizhizao:outsource-receipt": _KINDS_AMOUNT_ONLY,
    "kuaizhizao:outsource-material-return": _KINDS_AMOUNT_ONLY,
    "kuaizhizao:outsource-product-return": _KINDS_AMOUNT_ONLY,
    "kuaizhizao:outsource-settlement": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:work-order": _KINDS_AMOUNT_ONLY,
    "kuaizhizao:rework-order": _KINDS_AMOUNT_ONLY,
    # kuaizhizao - 仓储 / 物流
    "kuaizhizao:delivery-notice": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:other-inbound": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:other-outbound": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:material-borrow": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:material-return": _KINDS_AMOUNT_ONLY,
    "kuaizhizao:warehouse-management-inventory": _KINDS_AMOUNT_ONLY,
    "kuaizhizao:warehouse-management-customer-material-registration": _KINDS_PARTY_ONLY,
    "kuaizhizao:warehouse-management-inventory-transfer": _KINDS_AMOUNT_ONLY,
    "kuaizhizao:warehouse-management-stocktaking": _KINDS_AMOUNT_ONLY,
    "kuaizhizao:warehouse-management-assembly-orders": _KINDS_AMOUNT_ONLY,
    "kuaizhizao:warehouse-management-disassembly-orders": _KINDS_AMOUNT_ONLY,
    "kuaizhizao:freight-bill": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:freight-order": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:spare-part-requisition": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:delivery-project": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:delivery-follow-up": _KINDS_AMOUNT_ONLY,
    # kuaizhizao - 售后 / 服务（含往来与金额）
    "kuaizhizao:after-sales-ticket": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:after-sales-install": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:after-sales-spare-part-requisition": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:repair-order": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:service-dispatch": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:service-settlement": _KINDS_AMOUNT_PARTY,
    "kuaizhizao:service-asset": _KINDS_AMOUNT_ONLY,
    # kuaicaiwu - 应收 / 应付
    "kuaicaiwu:receivable": _KINDS_AMOUNT_PARTY,
    "kuaicaiwu:sales-invoice": _KINDS_AMOUNT_PARTY,
    "kuaicaiwu:receipt": _KINDS_AMOUNT_PARTY,
    "kuaicaiwu:payable": _KINDS_AMOUNT_ONLY,
    "kuaicaiwu:purchase-invoice": _KINDS_AMOUNT_ONLY,
    "kuaicaiwu:payment": _KINDS_AMOUNT_ONLY,
    "kuaicaiwu:other-expense": _KINDS_AMOUNT_PARTY,
    "kuaicaiwu:other-expense-application": _KINDS_AMOUNT_PARTY,
    "kuaicaiwu:other-income": _KINDS_AMOUNT_PARTY,
    "kuaicaiwu:partner-statement": _KINDS_AMOUNT_PARTY,
    "kuaicaiwu:notes-receivable": _KINDS_AMOUNT_ONLY,
    "kuaicaiwu:notes-payable": _KINDS_AMOUNT_ONLY,
    "kuaicaiwu:receipt-refund": _KINDS_AMOUNT_PARTY,
    "kuaicaiwu:payment-refund": _KINDS_AMOUNT_PARTY,
    "kuaicaiwu:settlement": _KINDS_AMOUNT_PARTY,
    "kuaicaiwu:document-reconciliation": _KINDS_AMOUNT_PARTY,
    "kuaicaiwu:prepayment": _KINDS_AMOUNT_ONLY,
    "kuaicaiwu:price-settlement": _KINDS_AMOUNT_ONLY,
    # master-data - 物料
    "master-data:material": _KINDS_PARTY_ONLY,
}


def normalize_field_permission_resource(raw: str) -> str:
    return (raw or "").strip().lower()


def normalize_field_permission_kind(raw: str) -> str:
    return (raw or "").strip().lower()


def kinds_for_resource(resource: str) -> FrozenSet[str]:
    """返回资源可配置的策略类；未注册资源返回空集。"""
    key = normalize_field_permission_resource(resource)
    return FIELD_PERMISSION_RESOURCE_KINDS.get(key, frozenset())


def field_names_for_resource(resource: str) -> FrozenSet[str]:
    """兼容旧调用：字段权限页/校验用的策略类集合。"""
    return kinds_for_resource(resource)


def columns_for_kind(kind: str) -> FrozenSet[str]:
    key = normalize_field_permission_kind(kind)
    return FIELD_KIND_COLUMNS.get(key, frozenset())


def columns_for_resource(resource: str) -> FrozenSet[str]:
    """资源下全部可脱敏列（由策略类展开）。"""
    out: set[str] = set()
    for kind in kinds_for_resource(resource):
        out |= set(columns_for_kind(kind))
    return frozenset(out)


def resolve_policy_kind(field_or_kind: str) -> str | None:
    """细字段名或策略类 → 策略类；无法识别返回 None。"""
    key = normalize_field_permission_kind(field_or_kind)
    if not key:
        return None
    if key in FIELD_PERMISSION_KINDS:
        return key
    return _COLUMN_TO_KIND.get(key)


def is_valid_field_policy(resource: str, field_name: str) -> bool:
    """field_name 可为策略类，或历史细字段（映射到策略类后校验）。"""
    kinds = kinds_for_resource(resource)
    if not kinds:
        return False
    kind = resolve_policy_kind(field_name)
    return kind is not None and kind in kinds


def resources_with_field_policies() -> frozenset[str]:
    return frozenset(FIELD_PERMISSION_RESOURCE_KINDS.keys())
