"""整仓库位解析：`_require_line_location` 契约与采购入库写路径接入（无需 ORM 运行时）。"""

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


@pytest.fixture(scope="module")
def warehouse_tree() -> ast.Module:
    return ast.parse(_WAREHOUSE_SERVICE.read_text(encoding="utf-8"))


def _function_defs(tree: ast.AST) -> dict[str, ast.AsyncFunctionDef | ast.FunctionDef]:
    out: dict[str, ast.AsyncFunctionDef | ast.FunctionDef] = {}
    for node in tree.body:
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            out[node.name] = node
    return out


def _calls_name(func: ast.AsyncFunctionDef | ast.FunctionDef, callee: str) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == callee:
                return True
            if isinstance(node.func, ast.Attribute) and node.func.attr == callee:
                return True
    return False


def test_require_line_location_and_outbound_wrapper_exist(warehouse_tree: ast.Module) -> None:
    funcs = _function_defs(warehouse_tree)
    assert "_require_line_location" in funcs
    assert "_require_outbound_line_location" in funcs
    outbound = funcs["_require_outbound_line_location"]
    assert _calls_name(outbound, "_require_line_location")


def test_require_line_location_defaults_when_empty(warehouse_tree: ast.Module) -> None:
    """未选手选库位须 ensure 整仓/首库位，禁止再因仓下已有库位硬拦。"""
    funcs = _function_defs(warehouse_tree)
    require_fn = funcs["_require_line_location"]
    assert _calls_name(require_fn, "ensure_whole_warehouse_location")
    src = ast.get_source_segment(
        _WAREHOUSE_SERVICE.read_text(encoding="utf-8"), require_fn
    ) or ""
    assert "选择" not in src or "无法确定库位" in src
    assert "find_first_storage_location_for_warehouse" not in src


def test_purchase_receipt_create_resolves_line_location(warehouse_tree: ast.Module) -> None:
    classes = {
        node.name: node
        for node in warehouse_tree.body
        if isinstance(node, ast.ClassDef)
    }
    svc = classes["PurchaseReceiptService"]
    create_fn = next(
        node
        for node in svc.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "create_purchase_receipt"
    )
    assert _calls_name(create_fn, "_resolve_line_location_into_mapping")


def test_confirm_receipt_posting_resolves_missing_location(warehouse_tree: ast.Module) -> None:
    classes = {
        node.name: node
        for node in warehouse_tree.body
        if isinstance(node, ast.ClassDef)
    }
    svc = classes["PurchaseReceiptService"]
    confirm_fn = next(
        node
        for node in svc.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_confirm_receipt_posting"
    )
    assert _calls_name(confirm_fn, "_resolve_line_location_into_mapping")
