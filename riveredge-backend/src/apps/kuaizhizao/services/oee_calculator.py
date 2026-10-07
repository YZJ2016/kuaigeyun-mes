"""两端共用 OEE 口径；技术参数 oee 保存理想节拍和明确计划窗口。"""
from datetime import datetime, timedelta, timezone
import math


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def validate_oee_config(config: dict) -> dict:
    if not isinstance(config, dict):
        raise ValueError("oee 必须是对象")
    cycle = config.get("ideal_cycle_seconds")
    if cycle is not None and (isinstance(cycle, bool) or not isinstance(cycle, (int, float)) or not math.isfinite(cycle) or cycle <= 0):
        raise ValueError("理想节拍必须是正数秒")
    windows = config.get("planned_windows", [])
    if not isinstance(windows, list) or len(windows) > 1000:
        raise ValueError("计划窗口无效")
    intervals = []
    for window in windows:
        try:
            start, end = datetime.fromisoformat(window["start"]), datetime.fromisoformat(window["end"])
            if start.tzinfo is None or end.tzinfo is None or start >= end:
                raise ValueError()
            intervals.append((_aware(start), _aware(end)))
        except (ValueError, KeyError, TypeError):
            raise ValueError("计划窗口须为带时区的开始/结束时间且结束晚于开始") from None
    intervals.sort()
    if any(intervals[i][0] < intervals[i - 1][1] for i in range(1, len(intervals))):
        raise ValueError("计划窗口不能重叠")
    return config


def calculate_oee(rows, start, end, config, quantity, qualified):
    start, end = _aware(start), _aware(end)
    reasons = []
    try:
        validate_oee_config(config)
    except ValueError:
        config = {}
        reasons.append("OEE 配置无效")
    intervals = [(max(start, _aware(datetime.fromisoformat(w["start"]))), min(end, _aware(datetime.fromisoformat(w["end"])))) for w in config.get("planned_windows", [])]
    intervals = [(a, b) for a, b in intervals if a < b]
    planned = sum((b - a).total_seconds() for a, b in intervals)
    if planned <= 0:
        reasons.append("未维护本窗口的计划生产时间")
    cycle = config.get("ideal_cycle_seconds")
    if cycle is None:
        reasons.append("未维护理想节拍")
    ordered = sorted(rows, key=lambda r: (_aware(r.monitored_at), r.id))
    running = covered = 0.0
    for i, row in enumerate(ordered):
        at = _aware(row.monitored_at)
        # 沿用已有 5 分钟设备离线门槛；不能将最后状态无限延伸。
        until = min(end, at + timedelta(minutes=5), _aware(ordered[i + 1].monitored_at) if i + 1 < len(ordered) else end)
        if row.status not in {"正常", "运行中", "待机", "故障", "维修中", "停用", "校验中", "报废"}:
            continue
        for left, right in intervals:
            seconds = max(0, (min(right, until) - max(left, at)).total_seconds())
            covered += seconds
            if row.status == "运行中":
                running += seconds
    coverage = min(1, covered / planned) if planned else None
    complete = coverage is not None and coverage >= 1 - 1e-9
    if planned and not complete:
        reasons.append("计划窗口数采覆盖不足")
    availability = running / planned if planned and complete else None
    performance = min(1, quantity * cycle / running) if cycle and running > 0 and quantity > 0 and complete else None
    quality = min(1, max(0, qualified / quantity)) if quantity > 0 and qualified is not None else None
    if performance is None:
        reasons.append("性能因子不可用：检查运行时间、产量及理想节拍")
    if quality is None:
        reasons.append("缺少有效产量或合格数量")
    oee = availability * performance * quality if all(v is not None for v in [availability, performance, quality]) else None
    return {"availability_rate": availability, "performance_rate": performance, "quality_rate": quality, "oee": oee, "coverage_rate": coverage, "planned_seconds": planned or None, "running_seconds": running, "reasons": reasons}


def reports_in_plan(records, config, start, end):
    """有明确生产窗口时仅统计窗口内报工；无计划时保留产量，OEE 仍不可用。"""
    try:
        validate_oee_config(config)
    except ValueError:
        return records
    windows = config.get("planned_windows", [])
    if not windows:
        return records
    intervals = [(max(_aware(start), _aware(datetime.fromisoformat(w["start"]))), min(_aware(end), _aware(datetime.fromisoformat(w["end"])))) for w in windows]
    return [r for r in records if any(a <= _aware(r.reported_at) < b for a, b in intervals)]
