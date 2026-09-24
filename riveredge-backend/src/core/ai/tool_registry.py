"""AI 工具注册表：OpenAI function schema + RBAC 包装执行。"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from loguru import logger

ToolHandler = Callable[..., Awaitable[str]]


@dataclass
class RegisteredTool:
    name: str
    definition: Dict[str, Any]
    permission: Optional[str] = None
    handler: Optional[ToolHandler] = None


class ToolRegistry:
    _tools: Dict[str, RegisteredTool] = {}
    _defaults_loaded: bool = False

    @classmethod
    def register(
        cls,
        name: str,
        definition: Dict[str, Any],
        *,
        permission: Optional[str] = None,
        handler: Optional[ToolHandler] = None,
    ) -> None:
        cls._tools[name] = RegisteredTool(
            name=name,
            definition=definition,
            permission=permission,
            handler=handler,
        )

    @classmethod
    def get_definitions(cls, names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        cls.ensure_defaults()
        if names is None:
            return [t.definition for t in cls._tools.values()]
        return [cls._tools[n].definition for n in names if n in cls._tools]

    @classmethod
    def get_handler(cls, name: str) -> Optional[ToolHandler]:
        cls.ensure_defaults()
        tool = cls._tools.get(name)
        return tool.handler if tool else None

    @classmethod
    def ensure_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        try:
            from apps.kuaiai.services.chat_tools import CHAT_TOOL_DEFINITIONS
        except ImportError:
            # KU-AI 未组装是进程内稳定状态，置位避免每调用重复 import
            cls._defaults_loaded = True
            logger.debug("KU-AI 未组装，跳过默认 ToolRegistry 注册")
            return
        for item in CHAT_TOOL_DEFINITIONS:
            fn = item.get("function") or {}
            name = str(fn.get("name") or "")
            if not name or name in cls._tools:
                continue
            permission = item.get("permission")
            if not permission:
                # 配合 tool_bridge fail-closed：兜底项无权限码不注册，
                # 不用 entry:read 放大到写工具，也不用哨兵码占位
                logger.debug("AI tool 兜底定义无权限码，跳过注册: {}", name)
                continue
            cls.register(name, item, permission=permission)
        # 标记只在 import + 注册循环成功后置位；非 ImportError 异常
        # 不置位，允许下次调用重试
        cls._defaults_loaded = True

    @classmethod
    def register_from_manifest(cls, app_code: str, manifest: Dict[str, Any]) -> None:
        """应用 manifest ai_tools 声明注册（安装 / 同步时调用）。"""
        tools = manifest.get("ai_tools")
        if not isinstance(tools, list):
            return
        for item in tools:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            handler_path = str(item.get("handler") or "").strip()
            if not name or not handler_path:
                continue
            try:
                module_path, attr = handler_path.rsplit(":", 1)
                module = importlib.import_module(module_path)
                handler = getattr(module, attr)
            except Exception as exc:
                logger.warning(
                    "AI tool manifest 注册失败 app={} tool={} error={}",
                    app_code,
                    name,
                    exc,
                )
                continue
            definition = item.get("definition")
            if not isinstance(definition, dict):
                definition = {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": item.get("description") or name,
                        "parameters": item.get("parameters") or {"type": "object", "properties": {}},
                    },
                }
            cls.register(
                name,
                definition,
                permission=item.get("permission"),
                handler=handler,
            )
            logger.info("AI tool 已注册 app={} name={}", app_code, name)
