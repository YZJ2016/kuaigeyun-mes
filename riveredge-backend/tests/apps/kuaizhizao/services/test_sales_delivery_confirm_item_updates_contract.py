"""销售出库确认：明细写入方法须与调用同属 SalesDeliveryService（防 AttributeError 回归）。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_WAREHOUSE_SERVICE = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "apps"
    / "kuaizhizao"
    / "services"
    / "warehouse_service.py"
)

_OUTBOUND_APPLY_METHODS = (
    ("ProductionPickingService", "_apply_production_picking_confirm_item_updates"),
    ("SalesDeliveryService", "_apply_sales_delivery_confirm_item_updates"),
    ("OtherOutboundService", "_apply_other_outbound_confirm_item_updates"),
    ("MaterialBorrowService", "_apply_material_borrow_confirm_item_updates"),
)


def _class_defs(tree: ast.AST) -> dict[str, ast.ClassDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }


def _method_names(cls: ast.ClassDef) -> set[str]:
    return {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _attr_refs(cls: ast.ClassDef, attr: str) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(cls)
        if isinstance(node, ast.Attribute) and node.attr == attr
    ]


@pytest.fixture(scope="module")
def warehouse_tree() -> ast.Module:
    src = _WAREHOUSE_SERVICE.read_text(encoding="utf-8")
    return ast.parse(src)


@pytest.mark.parametrize("class_name,apply_name", _OUTBOUND_APPLY_METHODS)
def test_outbound_confirm_apply_method_bound_on_same_class(
    warehouse_tree: ast.Module,
    class_name: str,
    apply_name: str,
) -> None:
    classes = _class_defs(warehouse_tree)
    assert class_name in classes, f"缺少类 {class_name}"
    cls = classes[class_name]
    names = _method_names(cls)
    assert apply_name in names, (
        f"{class_name} 缺少 {apply_name}；确认过账会 AttributeError"
    )
    refs = _attr_refs(cls, apply_name)
    assert refs, f"{class_name} 未调用 {apply_name}"


def test_sales_delivery_confirm_locked_calls_apply(warehouse_tree: ast.Module) -> None:
    cls = _class_defs(warehouse_tree)["SalesDeliveryService"]
    locked = next(
        (
            node
            for node in cls.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_confirm_delivery_locked"
        ),
        None,
    )
    assert locked is not None
    apply_refs = [
        node.lineno
        for node in ast.walk(locked)
        if isinstance(node, ast.Attribute)
        and node.attr == "_apply_sales_delivery_confirm_item_updates"
    ]
    assert apply_refs, "_confirm_delivery_locked 须调用 _apply_sales_delivery_confirm_item_updates"
