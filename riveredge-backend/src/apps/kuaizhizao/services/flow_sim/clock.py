"""单一业务时钟：preview / execute 共用；真实模式不启用截止窗压缩。"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from core.services.document_time_rewrite_service import WorkScheduleParams
from core.utils.timezone_utils import resolve_business_datetime, site_timezone_name


class IntervalSpec:
    """轻量间隔（避免循环依赖 flow_data_generate_service）。"""

    __slots__ = ("min_seconds", "max_seconds")

    def __init__(self, min_seconds: int = 300, max_seconds: int = 1800) -> None:
        lo = max(1, int(min_seconds))
        hi = max(lo, int(max_seconds))
        self.min_seconds = lo
        self.max_seconds = hi

    def clamp(self) -> "IntervalSpec":
        return IntervalSpec(self.min_seconds, self.max_seconds)


class BusinessClock:
    """按间隔推进严格递增业务时刻（禁止整秒；可钳工作时段）。

    真实模式：deadline / remaining_events 恒为 None，只用标准工时与步骤间隔。
    填数模式：可设 deadline 按剩余工作秒均摊。
    """

    def __init__(
        self,
        *,
        anchor: datetime,
        default_interval: IntervalSpec,
        intervals: dict[str, IntervalSpec],
        work_schedule: Optional[WorkScheduleParams] = None,
        use_work_schedule: bool = False,
        deadline: Optional[datetime] = None,
        remaining_events: Optional[int] = None,
    ) -> None:
        self._default = default_interval.clamp()
        self._intervals = {k: v.clamp() for k, v in intervals.items()}
        self._schedule = work_schedule
        self._use_schedule = bool(use_work_schedule and work_schedule)
        self._tz = ZoneInfo(site_timezone_name())
        self._deadline = (
            resolve_business_datetime(deadline).replace(microsecond=0)
            if deadline is not None
            else None
        )
        self._remaining = (
            max(1, int(remaining_events)) if remaining_events is not None else None
        )
        self._cursor = self._normalize_to_work(
            resolve_business_datetime(anchor).replace(microsecond=0)
        )

    @classmethod
    def build(
        cls,
        *,
        anchor: datetime,
        default_interval: IntervalSpec,
        intervals: dict[str, IntervalSpec],
        work_schedule: Optional[WorkScheduleParams] = None,
        use_work_schedule: bool = False,
        deadline: Optional[datetime] = None,
        remaining_events: Optional[int] = None,
        allow_budget: bool = False,
    ) -> "BusinessClock":
        """工厂：真实模式强制去掉截止窗。"""
        if not allow_budget:
            deadline = None
            remaining_events = None
        return cls(
            anchor=anchor,
            default_interval=default_interval,
            intervals=intervals,
            work_schedule=work_schedule,
            use_work_schedule=use_work_schedule,
            deadline=deadline,
            remaining_events=remaining_events,
        )

    def interval_for(self, step_key: str) -> IntervalSpec:
        return self._intervals.get(step_key, self._default)

    def current(self) -> datetime:
        return self._cursor

    def set_cursor(self, when: datetime) -> None:
        self._cursor = self._normalize_to_work(
            resolve_business_datetime(when).replace(microsecond=0)
        )

    def bump_to(self, when: datetime) -> None:
        when_utc = self._normalize_to_work(
            resolve_business_datetime(when).replace(microsecond=0)
        )
        if when_utc > self._cursor:
            self._cursor = when_utc

    def fork(self) -> "BusinessClock":
        other = BusinessClock(
            anchor=self._cursor,
            default_interval=self._default,
            intervals=dict(self._intervals),
            work_schedule=self._schedule,
            use_work_schedule=self._use_schedule,
            deadline=self._deadline,
            remaining_events=self._remaining,
        )
        other._cursor = self._cursor
        return other

    @staticmethod
    def _avoid_round_clock(when: datetime) -> datetime:
        when = when.replace(microsecond=0)
        if when.second == 0 or when.second >= 57:
            when = when + timedelta(seconds=random.randint(7, 53))
        return when

    def _normalize_to_work(self, when_utc: datetime) -> datetime:
        when_utc = self._avoid_round_clock(when_utc)
        if not (self._use_schedule and self._schedule is not None):
            return when_utc
        site = when_utc.astimezone(self._tz)
        site = self._clamp_forward(site)
        return self._avoid_round_clock(
            site.astimezone(timezone.utc).replace(microsecond=0)
        )

    def work_seconds_between(self, start_utc: datetime, end_utc: datetime) -> float:
        start_utc = resolve_business_datetime(start_utc)
        end_utc = resolve_business_datetime(end_utc)
        if end_utc <= start_utc:
            return 0.0
        if not (self._use_schedule and self._schedule is not None):
            return max(0.0, (end_utc - start_utc).total_seconds())
        start_site = start_utc.astimezone(self._tz)
        end_site = end_utc.astimezone(self._tz)
        total = 0.0
        day = start_site.date()
        while day <= end_site.date():
            window = self._schedule.window_on(day, self._tz)
            if window is not None:
                a, b = window
                lo = max(a, start_site)
                hi = min(b, end_site)
                if hi > lo:
                    total += (hi - lo).total_seconds()
            day += timedelta(days=1)
        return max(0.0, total)

    def next(self, step_key: str) -> datetime:
        if self._deadline is not None and self._remaining is not None:
            remain_sec = self.work_seconds_between(self._cursor, self._deadline)
            left = max(1, int(self._remaining))
            base = max(1.0, (remain_sec * 0.92) / left) if remain_sec > 0 else 60.0
            gap = random.uniform(base * 0.78, base * 0.98)
            gap += random.uniform(3.0, 17.0)
            self._remaining = left - 1
            return self.advance_by_seconds(gap)

        cfg = self.interval_for(step_key)
        gap = random.uniform(float(cfg.min_seconds), float(cfg.max_seconds))
        nearest_min = round(gap / 60.0) * 60.0
        if abs(gap - nearest_min) < 8.0:
            gap += random.uniform(11.0, 47.0)
        else:
            gap += random.uniform(3.0, 29.0)
        return self.advance_by_seconds(gap)

    def advance_capped(
        self,
        desired_seconds: float,
        *,
        max_fraction_of_remain: float = 0.28,
    ) -> datetime:
        gap = max(1.0, float(desired_seconds))
        if self._deadline is not None:
            remain = self.work_seconds_between(self._cursor, self._deadline)
            if remain > 0:
                cap = max(12.0, remain * max(0.05, float(max_fraction_of_remain)))
                gap = min(gap, cap)
            else:
                gap = random.uniform(11.0, 47.0)
        return self.advance_by_seconds(gap)

    def advance_by_seconds(self, seconds: float) -> datetime:
        gap = max(1.0, float(seconds))
        nxt = self._cursor + timedelta(seconds=gap)
        nxt = self._normalize_to_work(nxt)
        if nxt <= self._cursor:
            nxt = self._normalize_to_work(
                self._cursor + timedelta(seconds=random.randint(60, 180))
            )
            if nxt <= self._cursor and self._use_schedule and self._schedule is not None:
                site = self._cursor.astimezone(self._tz)
                day = site.date() + timedelta(days=1)
                for _ in range(14):
                    window = self._schedule.window_on(day, self._tz)
                    if window is not None:
                        nxt = self._avoid_round_clock(
                            window[0].astimezone(timezone.utc).replace(microsecond=0)
                        )
                        break
                    day += timedelta(days=1)
        if self._deadline is not None and nxt >= self._deadline:
            remain_work = self.work_seconds_between(self._cursor, self._deadline)
            step = max(8.0, min(remain_work * 0.5, 120.0)) if remain_work > 0 else 8.0
            nxt = self._normalize_to_work(self._cursor + timedelta(seconds=step))
            if nxt >= self._deadline:
                nxt = self._normalize_to_work(
                    self._deadline - timedelta(seconds=random.randint(11, 47))
                )
                if nxt <= self._cursor:
                    nxt = self._cursor
        self._cursor = nxt
        return nxt

    def _clamp_forward(self, when_site: datetime) -> datetime:
        assert self._schedule is not None
        cur = when_site.replace(microsecond=0)
        day = cur.date()
        for _ in range(400):
            window = self._schedule.window_on(day, self._tz)
            if window is None:
                day += timedelta(days=1)
                continue
            start, end = window
            last = end - timedelta(seconds=1)
            if last < start:
                last = start
            if cur.date() < day:
                return self._avoid_round_clock(start)
            if cur < start:
                return self._avoid_round_clock(start)
            if cur > last:
                day += timedelta(days=1)
                cur = datetime(day.year, day.month, day.day, tzinfo=self._tz)
                continue
            return self._avoid_round_clock(cur)
        return when_site
