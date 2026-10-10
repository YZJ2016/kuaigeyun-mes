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
"sanyi_plc_line": {
        "name": "三易产线 PLC",
        "description": "三易 MQTT 产线快照（devices[].variables），含产量/稼动率/时间类点位",
        "tags": [
            {"tag_key": "online", "name": "在线", "value_type": "boolean", "map_target": "is_online"},
            {"tag_key": "status", "name": "采集状态", "value_type": "string", "map_target": "other_parameters.device_status"},
            {"tag_key": "exception", "name": "异常信息", "value_type": "string", "map_target": "other_parameters.exception"},
            {"tag_key": "sczq", "name": "生产周期", "value_type": "number", "map_target": "other_parameters.sczq"},
            {"tag_key": "hgcl", "name": "合格产量", "value_type": "number", "map_target": "other_parameters.hgcl"},
            {"tag_key": "hgl", "name": "合格率", "value_type": "number", "map_target": "other_parameters.hgl", "unit": "%"},
            {"tag_key": "blsl", "name": "不良数量", "value_type": "number", "map_target": "other_parameters.blsl"},
            {"tag_key": "zscl", "name": "总生产量", "value_type": "number", "map_target": "other_parameters.zscl"},
            {"tag_key": "dbcl", "name": "当班产量", "value_type": "number", "map_target": "other_parameters.dbcl"},
            {"tag_key": "xscl", "name": "小时产量", "value_type": "number", "map_target": "other_parameters.xscl"},
            {"tag_key": "bzcn", "name": "标准产能", "value_type": "number", "map_target": "other_parameters.bzcn"},
            {"tag_key": "cnjdl", "name": "产能稼动率", "value_type": "number", "map_target": "other_parameters.cnjdl", "unit": "%"},
            {"tag_key": "jdl", "name": "稼动率", "value_type": "number", "map_target": "other_parameters.jdl", "unit": "%"},
            {"tag_key": "qdsj_zsj_s", "name": "启动总时间_秒", "value_type": "number", "map_target": "other_parameters.qdsj_zsj_s", "unit": "s"},
            {"tag_key": "qdsj_zsj_m", "name": "启动总时间_分", "value_type": "number", "map_target": "other_parameters.qdsj_zsj_m", "unit": "min"},
            {"tag_key": "qdsj_zsj_h", "name": "启动总时间_时", "value_type": "number", "map_target": "other_parameters.qdsj_zsj_h", "unit": "h"},
            {"tag_key": "qdsj_yxsj_s", "name": "运行时间_秒", "value_type": "number", "map_target": "other_parameters.qdsj_yxsj_s", "unit": "s"},
            {"tag_key": "qdsj_yxsj_m", "name": "运行时间_分", "value_type": "number", "map_target": "other_parameters.qdsj_yxsj_m", "unit": "min"},
            {"tag_key": "qdsj_yxsj_h", "name": "运行时间_时", "value_type": "number", "map_target": "other_parameters.qdsj_yxsj_h", "unit": "h"},
            {"tag_key": "ztjsj_s", "name": "总停机时间_秒", "value_type": "number", "map_target": "other_parameters.ztjsj_s", "unit": "s"},
            {"tag_key": "ztjsj_m", "name": "总停机时间_分", "value_type": "number", "map_target": "other_parameters.ztjsj_m", "unit": "min"},
            {"tag_key": "ztjsj_h", "name": "总停机时间_时", "value_type": "number", "map_target": "other_parameters.ztjsj_h", "unit": "h"},
            {"tag_key": "qdsj_qlsj_s", "name": "缺料时间_秒", "value_type": "number", "map_target": "other_parameters.qdsj_qlsj_s", "unit": "s"},
            {"tag_key": "qdsj_qlsj_m", "name": "缺料时间_分", "value_type": "number", "map_target": "other_parameters.qdsj_qlsj_m", "unit": "min"},
            {"tag_key": "qdsj_qlsj_h", "name": "缺料时间_时", "value_type": "number", "map_target": "other_parameters.qdsj_qlsj_h", "unit": "h"},
            {"tag_key": "tjsj_bjsj_s", "name": "报警时间_秒", "value_type": "number", "map_target": "other_parameters.tjsj_bjsj_s", "unit": "s"},
            {"tag_key": "tjsj_bjsj_m", "name": "报警时间_分", "value_type": "number", "map_target": "other_parameters.tjsj_bjsj_m", "unit": "min"},
            {"tag_key": "tjsj_bjsj_h", "name": "报警时间_时", "value_type": "number", "map_target": "other_parameters.tjsj_bjsj_h", "unit": "h"},
            {"tag_key": "tjsj_qtsj_s", "name": "其他停机_秒", "value_type": "number", "map_target": "other_parameters.tjsj_qtsj_s", "unit": "s"},
            {"tag_key": "tjsj_qtsj_m", "name": "其他停机_分", "value_type": "number", "map_target": "other_parameters.tjsj_qtsj_m", "unit": "min"},
            {"tag_key": "tjsj_qtsj_h", "name": "其他停机_时", "value_type": "number", "map_target": "other_parameters.tjsj_qtsj_h", "unit": "h"},
            {"tag_key": "qdsj_mlsj_s", "name": "满料时间_秒", "value_type": "number", "map_target": "other_parameters.qdsj_mlsj_s", "unit": "s"},
            {"tag_key": "qdsj_mlsj_m", "name": "满料时间_分", "value_type": "number", "map_target": "other_parameters.qdsj_mlsj_m", "unit": "min"},
            {"tag_key": "qdsj_mlsj_h", "name": "满料时间_时", "value_type": "number", "map_target": "other_parameters.qdsj_mlsj_h", "unit": "h"},
        ],
        "events": [
            {"event_key": "fault", "name": "设备故障", "level": "critical"},
            {"event_key": "material_shortage", "name": "缺料", "level": "warning"},
        ],
    },
}
