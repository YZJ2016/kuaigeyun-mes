"""考勤分析报表：基于每日考勤登记聚合按天/按月序列与排行。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from apps.kuaioa.models.daily_attendance import KuaioaDailyAttendanceRecord
from apps.kuaioa.services.kuaioa_list_core import build_keyword_q, parse_optional_date
from infra.exceptions.exceptions import BusinessLogicError

_RESULT_CODES = ("normal", "late", "early", "absent", "leave", "rest")

# 兼容历史中文结果与英文 code
_RESULT_ALIASES = {
    "normal": "normal",
    "late": "late",
    "early": "early",
    "absent": "absent",
    "leave": "leave",
    "rest": "rest",
    "正常": "normal",
    "迟到": "late",
    "早退": "early",
    "旷工": "absent",
    "请假": "leave",
    "休息": "rest",
}


def _d(v: Any) -> Decimal:
    if v is None or v == "":
        return Decimal("0")
    return Decimal(str(v))


def _i(v: Any) -> int:
    if v is None or v == "":
        return 0
    return int(v)


def _norm_result(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return "other"
    return _RESULT_ALIASES.get(text) or _RESULT_ALIASES.get(text.lower()) or "other"


def _period_key(work_date: date, granularity: str) -> str:
    if granularity == "month":
        return work_date.strftime("%Y-%m")
    return work_date.isoformat()


class AttendanceAnalysisService:
    async def analyze(
        self,
        tenant_id: int,
        *,
        granularity: str = "day",
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        department_name: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> dict[str, Any]:
        gran = (granularity or "day").strip().lower()
        if gran not in ("day", "month"):
            raise BusinessLogicError("granularity 仅支持 day 或 month")

        d_from = parse_optional_date(date_from) if date_from else None
        d_to = parse_optional_date(date_to) if date_to else None
        if date_from and not d_from:
            raise BusinessLogicError("开始日期无效")
        if date_to and not d_to:
            raise BusinessLogicError("结束日期无效")
        if not d_from and not d_to:
            today = date.today()
            if gran == "month":
                d_from = date(today.year, 1, 1)
                d_to = today
            else:
                d_from = today - timedelta(days=30)
                d_to = today
        elif d_from and not d_to:
            d_to = d_from
        elif d_to and not d_from:
            d_from = d_to
        assert d_from and d_to
        if d_from > d_to:
            raise BusinessLogicError("开始日期不能晚于结束日期")
        # 防误查过大区间
        if (d_to - d_from).days > 800:
            raise BusinessLogicError("查询区间不能超过 800 天")

        q = KuaioaDailyAttendanceRecord.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            work_date__gte=d_from,
            work_date__lte=d_to,
        )
        if department_name and department_name.strip():
            q = q.filter(department_name=department_name.strip())
        if keyword and keyword.strip():
            q = q.filter(build_keyword_q(keyword.strip(), "employee_name", "employee_code", "department_name"))

        rows = await q.order_by("work_date", "employee_name")

        summary_counts = {code: 0 for code in _RESULT_CODES}
        summary_counts["other"] = 0
        late_minutes = 0
        early_leave_minutes = 0
        ot_hours = Decimal("0")
        actual_hours = Decimal("0")
        expected_hours = Decimal("0")
        paid_hours = Decimal("0")
        employee_keys: set[str] = set()

        series_map: dict[str, dict[str, Any]] = {}
        dept_map: dict[str, dict[str, Any]] = {}
        emp_map: dict[str, dict[str, Any]] = {}

        def _bucket(store: dict[str, dict[str, Any]], key: str, *, label: str) -> dict[str, Any]:
            if key not in store:
                store[key] = {
                    "key": key,
                    "label": label,
                    "record_count": 0,
                    "late_minutes": 0,
                    "early_leave_minutes": 0,
                    "ot_hours": Decimal("0"),
                    "actual_hours": Decimal("0"),
                    "expected_hours": Decimal("0"),
                    **{f"{c}_count": 0 for c in _RESULT_CODES},
                    "other_count": 0,
                }
            return store[key]

        for row in rows:
            result = _norm_result(row.result)
            wd: date = row.work_date
            period = _period_key(wd, gran)
            late_m = _i(row.late_minutes)
            early_m = _i(row.early_leave_minutes)
            ot = _d(row.ot_hours)
            actual = _d(row.actual_hours)
            expected = _d(row.expected_hours)
            paid = _d(row.paid_hours)

            summary_counts[result] = summary_counts.get(result, 0) + 1
            late_minutes += late_m
            early_leave_minutes += early_m
            ot_hours += ot
            actual_hours += actual
            expected_hours += expected
            paid_hours += paid

            emp_id = row.employee_id or row.employee_code or row.employee_name
            employee_keys.add(str(emp_id))

            series = _bucket(series_map, period, label=period)
            series["record_count"] += 1
            series["late_minutes"] += late_m
            series["early_leave_minutes"] += early_m
            series["ot_hours"] += ot
            series["actual_hours"] += actual
            series["expected_hours"] += expected
            series[f"{result}_count"] = int(series.get(f"{result}_count", 0)) + 1

            dept_name = (row.department_name or "").strip() or "—"
            dept = _bucket(dept_map, dept_name, label=dept_name)
            dept["record_count"] += 1
            dept["late_minutes"] += late_m
            dept["early_leave_minutes"] += early_m
            dept["ot_hours"] += ot
            dept["actual_hours"] += actual
            dept["expected_hours"] += expected
            dept[f"{result}_count"] = int(dept.get(f"{result}_count", 0)) + 1

            emp_key = str(row.employee_id or row.employee_code or f"name:{row.employee_name}")
            emp_label = f"{(row.employee_code or '').strip()} {(row.employee_name or '').strip()}".strip()
            emp = _bucket(emp_map, emp_key, label=emp_label or emp_key)
            emp["employee_name"] = row.employee_name
            emp["employee_code"] = row.employee_code
            emp["department_name"] = row.department_name
            emp["record_count"] += 1
            emp["late_minutes"] += late_m
            emp["early_leave_minutes"] += early_m
            emp["ot_hours"] += ot
            emp["actual_hours"] += actual
            emp["expected_hours"] += expected
            emp[f"{result}_count"] = int(emp.get(f"{result}_count", 0)) + 1

        record_count = len(rows)
        # 出勤率：非休息样本中，正常+迟到+早退 占比
        work_samples = (
            summary_counts["normal"]
            + summary_counts["late"]
            + summary_counts["early"]
            + summary_counts["absent"]
            + summary_counts["leave"]
            + summary_counts["other"]
        )
        present = summary_counts["normal"] + summary_counts["late"] + summary_counts["early"]
        attendance_rate = float(present / work_samples * 100) if work_samples else 0.0

        def _serialize_bucket(item: dict[str, Any]) -> dict[str, Any]:
            out = {**item}
            for k in ("ot_hours", "actual_hours", "expected_hours", "paid_hours"):
                if k in out:
                    out[k] = float(out[k])
            return out

        series = [_serialize_bucket(series_map[k]) for k in sorted(series_map.keys())]
        by_department = sorted(
            (_serialize_bucket(v) for v in dept_map.values()),
            key=lambda x: (-int(x["record_count"]), str(x["label"])),
        )
        by_employee = sorted(
            (_serialize_bucket(v) for v in emp_map.values()),
            key=lambda x: (-int(x["late_minutes"]), -float(x["ot_hours"]), str(x["label"])),
        )[:50]

        result_distribution = [
            {"result": code, "count": summary_counts[code]}
            for code in (*_RESULT_CODES, "other")
            if summary_counts.get(code, 0) > 0
        ]

        return {
            "granularity": gran,
            "date_from": d_from.isoformat(),
            "date_to": d_to.isoformat(),
            "summary": {
                "record_count": record_count,
                "employee_count": len(employee_keys),
                "normal_count": summary_counts["normal"],
                "late_count": summary_counts["late"],
                "early_count": summary_counts["early"],
                "absent_count": summary_counts["absent"],
                "leave_count": summary_counts["leave"],
                "rest_count": summary_counts["rest"],
                "other_count": summary_counts["other"],
                "late_minutes": late_minutes,
                "early_leave_minutes": early_leave_minutes,
                "ot_hours": float(ot_hours),
                "actual_hours": float(actual_hours),
                "expected_hours": float(expected_hours),
                "paid_hours": float(paid_hours),
                "attendance_rate": round(attendance_rate, 2),
            },
            "series": series,
            "result_distribution": result_distribution,
            "by_department": by_department,
            "by_employee": by_employee,
        }
