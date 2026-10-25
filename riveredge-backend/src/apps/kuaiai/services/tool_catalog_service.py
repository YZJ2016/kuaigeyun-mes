"""KU-AI Tool 目录服务（spec 189）：manifest ``ai_tools`` 为唯一真源。

下发口径：按 manifest 声明顺序稳定排序，仅返回同时满足「已注册
（``ToolRegistry`` 内含 handler）」且在 ``ENABLED_TOOL_NAMES`` 闭集内
的 Tool；未注册/闭集外的条目不返回。目录为进程级注册信息，不含租户
数据；字段裁剪为 name/label/description/kind/permission/permissions_any
（spec 207 X2=b），不回 handler
路径与参数 schema。

失败关闭约定（评审 B-M1）：manifest 不可读/``ai_tools`` 非法/``kind``
不在 ``{read, write}`` 闭集一律抛 ``ConfigurationError``，不做运行期
降级——静默收敛会让写 Tool 脱离 HITL 确认闸（工具照常装配进图却无
中断配置）。``hitl_service.tool_label`` 逐名调用本模块，manifest 经
mtime 进程级缓存避免逐次读盘。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from apps.kuaiai.constants import ENABLED_TOOL_NAMES
from apps.kuaiai.schemas.tool_catalog import ToolCatalogItem
from core.ai.tool_registry import ToolRegistry
from infra.exceptions.exceptions import ConfigurationError

_TOOL_KINDS = frozenset({"read", "write"})

_MANIFEST_PATH = Path(__file__).resolve().parents[1] / "manifest.json"
# (mtime, parsed manifest)；mtime 变化即失效重读
_manifest_cache: Optional[Tuple[float, Dict[str, Any]]] = None


def _load_manifest() -> Dict[str, Any]:
    """读取同目录 manifest.json（与 chat_tools._register_manifest_tools 同一路径）。

    进程级缓存按文件 mtime 失效：manifest 为部署期静态文件，正常运行
    不会变化；编辑/换包后下一次调用自动重读。
    """
    global _manifest_cache
    mtime = _MANIFEST_PATH.stat().st_mtime
    cached = _manifest_cache
    if cached is not None and cached[0] == mtime:
        return cached[1]
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    _manifest_cache = (mtime, manifest)
    return manifest


def manifest_tool_meta() -> Dict[str, Dict[str, str]]:
    """manifest ``ai_tools`` name → ``{label, kind}`` 真源（spec 193 确认闸）。

    失败关闭：manifest 不可读/``ai_tools`` 非列表/任一条目 ``kind``
    不在 ``{read, write}`` 闭集 → 抛 ``ConfigurationError``。调用方
    （``manifest_write_tool_names`` → 装配；``hitl_service.tool_label``
    → 待确认展示）必须显式失败，禁止静默回退为 read/空表。
    """
    try:
        manifest = _load_manifest()
    except Exception as exc:
        raise ConfigurationError(
            "kuaiai manifest 读取失败，AI 工具目录不可用"
        ) from exc
    tools = manifest.get("ai_tools")
    if not isinstance(tools, list):
        raise ConfigurationError("kuaiai manifest ai_tools 缺失或非法")
    out: Dict[str, Dict[str, str]] = {}
    for item in tools:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        kind = str(item.get("kind") or "").strip()
        if kind not in _TOOL_KINDS:
            raise ConfigurationError(
                f"kuaiai manifest ai_tools[{name}] kind 非法: {kind!r}"
            )
        label = str(item.get("label") or "").strip()
        out[name] = {"kind": kind, "label": label or name}
    return out


def manifest_write_tool_names() -> frozenset:
    """manifest ``ai_tools`` 中 ``kind == "write"`` 的名字闭集。

    失败关闭补充：``ENABLED_TOOL_NAMES`` 中未能从 manifest 解析出
    ``kind`` 的名字一律按 write 处理——宁多挂确认闸，不让写 Tool
    脱离 HITL 裸奔（B-M1）。
    """
    meta = manifest_tool_meta()
    write = {name for name, m in meta.items() if m.get("kind") == "write"}
    unresolved = set(ENABLED_TOOL_NAMES) - set(meta)
    return frozenset(write | unresolved)


def list_tool_catalog() -> List[ToolCatalogItem]:
    """Tool 目录：manifest 声明序 ∩ 已注册（含 handler）∩ ENABLED_TOOL_NAMES。"""
    try:
        manifest = _load_manifest()
    except Exception as exc:
        logger.warning(
            "kuaiai manifest 读取失败，Tool 目录返回空 error_type={}",
            type(exc).__name__,
        )
        return []
    tools = manifest.get("ai_tools")
    if not isinstance(tools, list):
        return []
    # kind/label 与 manifest_tool_meta 同一真源；非法 kind 失败关闭（抛错）
    meta = manifest_tool_meta()
    ToolRegistry.ensure_defaults()
    items: List[ToolCatalogItem] = []
    for item in tools:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name not in ENABLED_TOOL_NAMES:
            continue
        registered = ToolRegistry._tools.get(name)
        if registered is None or registered.handler is None:
            continue
        m = meta[name]
        items.append(
            ToolCatalogItem(
                name=name,
                label=m["label"],
                description=item.get("description") or None,
                kind=m["kind"],
                permission=item.get("permission") or registered.permission,
                permissions_any=(
                    item.get("permissions_any") or registered.permissions_any
                ),
            )
        )
    return items
