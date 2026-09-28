"""三套内置点位模板。点位只使用已有监控映射，不新增第四套。"""

from typing import Any


def _tag(
    tag_key: str,
    name: str,
    value_type: str,
    map_target: str,
    unit: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "tag_key": tag_key,
        "name": name,
        "value_type": value_type,
        "map_target": map_target,
    }
    if unit:
        row["unit"] = unit
    return row


TAG_TEMPLATES: dict[str, dict[str, Any]] = {
    "generic_line": {
        "name": "通用产线",
        "tags": [
            _tag("status", "状态", "text", "status"),
            _tag("online", "在线", "boolean", "is_online"),
            _tag("temperature", "温度", "number", "temperature", "℃"),
            _tag("pressure", "压力", "number", "pressure"),
            _tag("vibration", "振动", "number", "vibration"),
        ],
    },
    "injection_molding": {
        "name": "注塑机",
        "tags": [
            _tag("status", "状态", "text", "status"),
            _tag("online", "在线", "boolean", "is_online"),
            _tag("barrel_temperature", "料筒温度", "number", "temperature", "℃"),
            _tag("injection_pressure", "注射压力", "number", "pressure"),
            _tag("mold_temperature", "模具温度", "number", "other_parameters.mold_temperature", "℃"),
        ],
    },
    "cnc": {
        "name": "CNC",
        "tags": [
            _tag("status", "状态", "text", "status"),
            _tag("online", "在线", "boolean", "is_online"),
            _tag("spindle_temperature", "主轴温度", "number", "temperature", "℃"),
            _tag("spindle_load", "主轴负载", "number", "vibration"),
            _tag("axis_load", "轴负载", "number", "other_parameters.axis_load"),
        ],
    },
}
