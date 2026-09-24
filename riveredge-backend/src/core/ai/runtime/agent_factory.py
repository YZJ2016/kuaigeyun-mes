"""Agent 装配入口（设计 §6.2，KR-D14）。

每请求 ``create_agent``（图构造毫秒级）；``recursion_limit`` 由调用方经
``config={"recursion_limit": ...}`` 在 ainvoke/astream 时传入，默认上限 8
（替代旧 ``MAX_TOOL_ROUNDS``）。checkpointer 本期默认 ``None``（KR-G3）。
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from langchain.agents import create_agent

DEFAULT_RECURSION_LIMIT = 8


def build_agent(
    model: Any,
    tools: Optional[Sequence[Any]],
    system_prompt: Optional[Any] = None,
    middleware: Sequence[Any] = (),
    checkpointer: Optional[Any] = None,
):
    return create_agent(
        model=model,
        tools=list(tools or []),
        system_prompt=system_prompt,
        middleware=tuple(middleware or ()),
        checkpointer=checkpointer,
    )
