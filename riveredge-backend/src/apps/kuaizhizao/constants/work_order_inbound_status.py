"""快格轻制造 — 工单一键入库允许状态白名单（唯一真源）。

工单模型状态为英文枚举（draft/released/in_progress/completed/cancelled/split），
入库入口同时兼容历史中文展示态「进行中」「已完成」。

spec 140 / KR-CL1：调用方不得再各写一套同义字符串。
"""

from __future__ import annotations

WORK_ORDER_INBOUND_ALLOWED_STATUSES: tuple[str, ...] = (
    "in_progress",
    "completed",
    "进行中",
    "已完成",
)
