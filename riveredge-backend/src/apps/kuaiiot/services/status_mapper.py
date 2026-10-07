"""入站 status 只接受星制造设备主数据字段说明里的八个值。"""

from typing import Any

EQUIPMENT_STATUS_VALUES = frozenset(
    {"正常", "运行中", "待机", "故障", "维修中", "停用", "校验中", "报废"}
)
BLOCKED_EQUIPMENT_STATUSES = frozenset({"停用", "报废", "校验中"})
OPEN_FAULT_STATUSES = frozenset({"待处理", "处理中"})
OPEN_REPAIR_STATUSES = frozenset({"进行中"})
MONITOR_STATUS_WHEN_ABSENT = "正常"


def normalize_equipment_status(value: Any) -> str:
    """未知值明确保留未知，不能冒充设备待机。"""
    if isinstance(value, str) and value in EQUIPMENT_STATUS_VALUES:
        return value
    return "未知"
