"""
快格轻制造 APP - API 路由模块

延迟加载主 router，避免 finance 子包与 pull_query_params 形成循环 import。
"""

from __future__ import annotations

from typing import Any

__all__ = ["router"]


def __getattr__(name: str) -> Any:
    if name == "router":
        from .router import router

        return router
    raise AttributeError(name)
