"""开放 API 预置应用（产品级固定名称与 grants，勿写租户定制名）。"""

from __future__ import annotations

WORKBUDDY_OPEN_API_PRESET_APP_NAME = "WorkBuddy（实验室）"

WORKBUDDY_OPEN_API_PRESET_PERMISSION_CODES: tuple[str, ...] = (
    "kuaizhizao:sales-order:read",
    "kuaizhizao:work-order:read",
    "kuaizhizao:warehouse-management-inventory:read",
)
