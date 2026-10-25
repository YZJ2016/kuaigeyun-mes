"""KU-AI spec 189 单测：GET /tools 目录接口（manifest 唯一真源）。

全部 mock，不需要真实数据库。覆盖：
- manifest ai_tools 名称集合 == ENABLED_TOOL_NAMES；
- 每项必有非空 label、kind ∈ {read,write}、permission 或 permissions_any
  非空（spec 207 X2=b 二选一）、handler 可 import；
- list_tool_catalog 按 manifest 声明序稳定输出、字段齐全；
- 未注册（无 handler）/闭集外条目不返回；
- /tools 路由已注册且挂 kuaiai:agent:read 权限依赖。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import apps.kuaiai.services.chat_tools as chat_tools
import apps.kuaiai.services.tool_catalog_service as catalog_svc
from apps.kuaiai.constants import ENABLED_TOOL_NAMES
from apps.kuaiai.schemas.tool_catalog import ToolCatalogItem
from core.ai.tool_registry import ToolRegistry


def _manifest() -> dict:
    path = Path(chat_tools.__file__).resolve().parents[1] / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


class TestManifestToolFields:
    def test_manifest_names_match_closed_set(self):
        tools = _manifest()["ai_tools"]
        assert {t["name"] for t in tools} == set(ENABLED_TOOL_NAMES)

    def test_every_tool_has_label_kind_permission_handler(self):
        for item in _manifest()["ai_tools"]:
            name = item["name"]
            assert str(item.get("label") or "").strip(), f"{name} 缺 label"
            assert item.get("kind") in {"read", "write"}, f"{name} kind 非法"
            perm_single = str(item.get("permission") or "").strip()
            perm_any = [
                c for c in (item.get("permissions_any") or []) if str(c).strip()
            ]
            assert perm_single or perm_any, (
                f"{name} 缺 permission/permissions_any"
            )
            assert not (perm_single and perm_any), (
                f"{name} permission 与 permissions_any 须二选一"
            )
            module_path, attr = str(item["handler"]).rsplit(":", 1)
            handler = getattr(importlib.import_module(module_path), attr, None)
            assert callable(handler), f"{name} handler 不可 import"


class TestListToolCatalog:
    def test_returns_all_enabled_registered_in_manifest_order(self):
        items = catalog_svc.list_tool_catalog()
        manifest_order = [
            t["name"]
            for t in _manifest()["ai_tools"]
            if t["name"] in ENABLED_TOOL_NAMES
        ]
        assert [i.name for i in items] == manifest_order
        assert len(items) == len(ENABLED_TOOL_NAMES)
        for item in items:
            assert isinstance(item, ToolCatalogItem)
            assert item.label
            assert item.kind in {"read", "write"}
            assert item.permission or item.permissions_any

    def test_unregistered_or_handlerless_tools_filtered(self):
        """注册表缺条目/无 handler 的 Tool 不下发（其余照常）。"""
        ToolRegistry.ensure_defaults()
        real = dict(ToolRegistry._tools)
        missing = {
            k: v for k, v in real.items() if k != "query_work_orders"
        }
        with patch.object(ToolRegistry, "ensure_defaults"), patch.object(
            ToolRegistry, "_tools", missing
        ):
            names = [i.name for i in catalog_svc.list_tool_catalog()]
        assert "query_work_orders" not in names
        assert "search_knowledge" in names

        no_handler = {
            k: (
                v if k != "query_inventory"
                else type(v)(
                    name=v.name,
                    definition=v.definition,
                    permission=v.permission,
                    handler=None,
                )
            )
            for k, v in real.items()
        }
        with patch.object(ToolRegistry, "ensure_defaults"), patch.object(
            ToolRegistry, "_tools", no_handler
        ):
            names = [i.name for i in catalog_svc.list_tool_catalog()]
        assert "query_inventory" not in names

    def test_manifest_read_failure_returns_empty(self):
        with patch.object(
            catalog_svc, "_load_manifest", side_effect=OSError("io")
        ):
            assert catalog_svc.list_tool_catalog() == []


class TestToolsRoute:
    def test_route_registered_with_permission_dependency(self):
        from apps.kuaiai.api.router import router

        matches = [
            r
            for r in router.routes
            if getattr(r, "path", "") == "/tools"
            and "GET" in getattr(r, "methods", set())
        ]
        assert len(matches) == 1
        route = matches[0]
        assert route.dependencies, "/tools 未挂权限依赖"
        assert route.response_model == list[ToolCatalogItem]
