"""
行业包容器应用（唯一真源）。

- 侧栏仅展示一个「行业包」应用根
- 各行业模块名称作为行业包一级菜单，模块内原菜单作为二级及以下
- 与 industry_app_catalog 中 ALL_INDUSTRY_APP_CODES 区分：后者为可安装模块，不含 industry-pack
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

INDUSTRY_PACK_APP_CODE = "industry-pack"
INDUSTRY_PACK_SORT_ORDER = 290


def resolve_industry_pack_navigation_visible(*, is_installed: bool, active_module_count: int) -> bool:
    """侧栏是否展示行业包容器：已安装且至少有一个已启用的行业模块。"""
    return bool(is_installed) and active_module_count > 0


def is_industry_pack_shell_code(app_code: str | None) -> bool:
    return str(app_code or "") == INDUSTRY_PACK_APP_CODE


def is_industry_module_app_code(app_code: str | None) -> bool:
    from core.config.industry_app_catalog import is_industry_app_code

    code = str(app_code or "")
    if not code or is_industry_pack_shell_code(code):
        return False
    return is_industry_app_code(code)


def should_hide_from_application_center(app_code: str | None) -> bool:
    return is_industry_pack_shell_code(app_code)


def _app_menu_title_key(app_code: str) -> str:
    return f"app.{app_code}.name"


def _normalize_pack_menu_node(raw: Dict[str, Any]) -> Dict[str, Any]:
    """将 manifest 菜单节点规范为行业包同步结构（支持递归 children）。"""
    node: Dict[str, Any] = {}
    title = raw.get("title") or raw.get("name")
    if title:
        node["title"] = title
    icon = raw.get("icon")
    if icon:
        node["icon"] = icon
    path = str(raw.get("path") or "").strip()
    if path:
        node["path"] = path
    permission = raw.get("permission")
    if permission:
        node["permission"] = permission
    if raw.get("sort_order") is not None:
        node["sort_order"] = int(raw.get("sort_order"))
    children = raw.get("children") or []
    if isinstance(children, list) and children:
        normalized_children = [
            _normalize_pack_menu_node(child)
            for child in children
            if isinstance(child, dict)
        ]
        normalized_children.sort(
            key=lambda item: (int(item.get("sort_order") or 999), str(item.get("title") or ""))
        )
        node["children"] = normalized_children
    return node


def _find_menu_leaf_in_config(
    node: Any, target_path: str
) -> Optional[Dict[str, Any]]:
    """在宿主 manifest menu_config 树中按 path 查找叶子节点。"""
    if not isinstance(node, dict):
        return None
    path = str(node.get("path") or "").strip()
    if path == target_path:
        return node
    for child in node.get("children") or []:
        hit = _find_menu_leaf_in_config(child, target_path)
        if hit:
            return hit
    return None


def _load_manifest_by_code(app_code: str) -> Optional[Dict[str, Any]]:
    """读取应用 manifest（轻量，避免拉取 ApplicationService 重依赖链）。"""
    apps_dir = Path(__file__).resolve().parents[2] / "apps"
    if not apps_dir.is_dir():
        return None
    for plugin_dir in apps_dir.iterdir():
        if not plugin_dir.is_dir():
            continue
        manifest_file = plugin_dir / "manifest.json"
        if not manifest_file.exists():
            continue
        try:
            with open(manifest_file, encoding="utf-8") as handle:
                data = json.load(handle)
            if str(data.get("code") or "") == app_code:
                return data
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _resolve_host_menu_leaf(host_app: str, menu_path: str) -> Optional[Dict[str, Any]]:
    manifest = _load_manifest_by_code(host_app) or {}
    menu_config = manifest.get("menu_config")
    if not isinstance(menu_config, dict):
        return None
    return _find_menu_leaf_in_config(menu_config, menu_path)


def _permission_for_resource(resource: str) -> str:
    code = str(resource or "").strip()
    if not code:
        return ""
    if ":" in code and code.count(":") >= 2:
        return code
    return f"{code}:read"


def _collect_extension_pack_menu_children(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 industry_extensions（pack_menu=true 的 replace）生成行业包子菜单。"""
    from core.config.industry_extension_registry import parse_industry_extensions

    code = str(manifest.get("code") or "").strip()
    if not code:
        return []

    children: List[Dict[str, Any]] = []
    for idx, decl in enumerate(parse_industry_extensions(code, manifest)):
        if decl.kind != "replace" or not decl.pack_menu:
            continue

        if decl.strategy == "document":
            path = str(decl.replacement_path or "").strip()
            permission = (
                f"{decl.replacement_app}:entry:read"
                if decl.replacement_app
                else f"{code}:entry:read"
            )
            if decl.replacement_app:
                replacement_manifest = _load_manifest_by_code(decl.replacement_app) or {}
                perms = replacement_manifest.get("permissions") or []
                read_perms = [
                    str(p)
                    for p in perms
                    if isinstance(p, str) and str(p).endswith(":read")
                ]
                specific = [p for p in read_perms if not p.endswith(":entry:read")]
                if specific:
                    permission = specific[0]
                elif read_perms:
                    permission = read_perms[0]
        else:
            path = str(decl.menu_path or "").strip()
            host_leaf = (
                _resolve_host_menu_leaf(str(decl.host_app or ""), path)
                if decl.host_app and path
                else None
            )
            permission = (
                str(host_leaf.get("permission") or "").strip()
                if host_leaf
                else _permission_for_resource(str(decl.resource or ""))
            )

        if not path:
            continue

        title = decl.menu_title
        if not title and decl.strategy == "profile" and decl.host_app and decl.menu_path:
            host_leaf = _resolve_host_menu_leaf(decl.host_app, decl.menu_path)
            if host_leaf:
                title = host_leaf.get("title")
        if not title:
            title = f"app.{code}.menu.{decl.id.split('.')[-1]}"

        sort_order = (
            decl.menu_sort_order
            if decl.menu_sort_order is not None
            else (idx + 1) * 10
        )
        children.append(
            _normalize_pack_menu_node(
                {
                    "title": title,
                    "path": path,
                    "permission": permission,
                    "sort_order": sort_order,
                    "meta": {"industry_extension_id": decl.id},
                }
            )
        )
    return children


def _merge_pack_menu_children(
    manual: List[Dict[str, Any]], extension: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """合并手工 industry_pack_menu 与扩展自动生成项；同 path 以手工为准。"""
    by_path: Dict[str, Dict[str, Any]] = {}
    ordered: List[Dict[str, Any]] = []
    for item in extension + manual:
        path = str(item.get("path") or "").strip()
        if path:
            if path in by_path:
                continue
            by_path[path] = item
            ordered.append(item)
        else:
            ordered.append(item)
    ordered.sort(
        key=lambda x: (int(x.get("sort_order") or 999), str(x.get("title") or ""))
    )
    return ordered


def _collect_manual_pack_menu_children(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """收集 manifest 手工声明的 industry_pack_menu / menu_config 子项。"""
    code = str(manifest.get("code") or "").strip()
    raw = manifest.get("industry_pack_menu")
    if isinstance(raw, dict):
        children_raw = raw.get("children")
        if isinstance(children_raw, list) and children_raw:
            return [
                _normalize_pack_menu_node(child)
                for child in children_raw
                if isinstance(child, dict)
            ]
        if str(raw.get("path") or "").strip():
            return [_normalize_pack_menu_node(raw)]

    menu_config = manifest.get("menu_config")
    if isinstance(menu_config, dict):
        config_children = menu_config.get("children")
        if isinstance(config_children, list) and config_children:
            return [
                _normalize_pack_menu_node(child)
                for child in config_children
                if isinstance(child, dict)
            ]
        if str(menu_config.get("path") or "").strip():
            return [_normalize_pack_menu_node(menu_config)]

    route_path = str(manifest.get("route_path") or "").strip()
    if route_path:
        return [
            {
                "title": _app_menu_title_key(code),
                "path": route_path,
                "permission": f"{code}:entry:read",
            }
        ]
    return []


def _collect_module_menu_children(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """收集行业模块在行业包应用节点下的子菜单（扩展单据 + 手工声明）。"""
    manual = _collect_manual_pack_menu_children(manifest)
    extension = _collect_extension_pack_menu_children(manifest)
    merged = _merge_pack_menu_children(manual, extension)
    if merged:
        return merged
    return manual


def manifest_to_industry_pack_menu_item(manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    从 manifest 解析行业模块在行业包下的菜单节点。

    结构：行业包 → 应用名（一级）→ 原应用菜单（二级及以下）

    有子菜单时，应用名节点不设 path（纯分组）。否则会与子项「概览」等同 path
   （如 /apps/kuaielectronics）在按 path 同步时互相覆盖，产生 parent_id 自引用，侧栏看不到子菜单。
    """
    code = str(manifest.get("code") or "").strip()
    if not code:
        return None

    children = _collect_module_menu_children(manifest)
    if not children:
        return None

    route_path = str(manifest.get("route_path") or "").strip()
    # 有 children 时禁止与叶子共用 path，避免 MenuService 按 path upsert 打坏树
    group_path = None if children else (route_path or None)
    return {
        "title": _app_menu_title_key(code),
        "icon": manifest.get("icon") or "cpu",
        "path": group_path,
        "permission": f"{code}:entry:read",
        "sort_order": int(manifest.get("sort_order") or 999),
        "children": children,
    }
