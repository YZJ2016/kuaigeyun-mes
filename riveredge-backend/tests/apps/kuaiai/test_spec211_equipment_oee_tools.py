"""KU-AI spec 211 单测：query_equipment_oee / analyze_equipment_losses。

全部 mock / 假数据，不需要真实数据库。覆盖：
- 参数校验（equipment_id 必填/整数、workshop_id、日期闭集）回固定文案；
- query_equipment_oee 与 list_equipment_oee 同参调用（start→日初 / end→日末），
  workshop_id 经 list_equipment 解析设备 id 交集，limit 截断 ≤20；
- analyze_equipment_losses 三分量透传 service 值（不由 LLM 估算）；
- 损失聚合确定性可复算：sensor 明细按状态延伸（min(end, at+5min, 下一行 at)）
  与计划窗口求交 → TopN=5 → 其余合并「其他」；
- 样本天数取自 get_equipment_oee_trend 行数，超 92 天截断注明；
- 空结果/设备不存在/底层异常固定文案。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.services.tools import equipment_performance as ep
from core.ai.runtime.context import AiRuntimeContext

TENANT = 7
USER_ID = 5

OEE_SVC = "apps.kuaizhizao.services.equipment_oee_service.EquipmentOEEService"
EQ_SVC = "apps.kuaizhizao.services.equipment_service.EquipmentService"
MON_SVC = (
    "apps.kuaizhizao.services.equipment_status_monitor_service"
    ".EquipmentStatusMonitorService"
)
EQ_FILTER = "apps.kuaizhizao.models.equipment.Equipment.filter"


def _ctx():
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
    )


def _oee_data(**kw):
    base = dict(
        equipment={
            "id": 11,
            "uuid": "eq-uuid-1",
            "code": "EQ-001",
            "name": "注塑机三号",
        },
        period={"start": "2026-01-01", "end": "2026-01-31"},
        metrics={
            "planned_runtime": 160.0,
            "actual_runtime": 120.0,
            "actual_quantity": 500.0,
            "qualified_quantity": 480.0,
            "unqualified_quantity": 20.0,
        },
        oee={
            "availability_rate": 75.0,
            "performance_rate": 80.0,
            "quality_rate": 96.0,
            "oee_value": 57.6,
        },
        coverage_rate=1.0,
        unavailable_reasons=[],
        record_count=12,
    )
    base.update(kw)
    return base


def _oee_svc(**kw):
    base = dict(
        calculate_equipment_oee=AsyncMock(return_value=_oee_data()),
        list_equipment_oee=AsyncMock(return_value=[_oee_data()]),
        get_equipment_oee_trend=AsyncMock(
            return_value={
                "equipment_id": 11,
                "period_type": "day",
                "trend_data": [
                    {"period": f"2026-01-0{i}", "oee": {}, "metrics": {}}
                    for i in range(1, 4)
                ],
            }
        ),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _equipment(**kw):
    base = dict(
        id=11,
        uuid="eq-uuid-1",
        code="EQ-001",
        name="注塑机三号",
        technical_parameters={},
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _equipment_qs(equipment):
    q = MagicMock()
    q.filter = MagicMock(return_value=q)
    q.first = AsyncMock(return_value=equipment)
    q.all = AsyncMock(return_value=[equipment] if equipment else [])
    return q


def _mon_svc(rows=(), total=None):
    return SimpleNamespace(
        list_equipment_status=AsyncMock(
            return_value=(
                list(rows),
                len(rows) if total is None else total,
            )
        )
    )


def _mon_row(status, at, row_id, data_source="sensor"):
    return SimpleNamespace(
        id=row_id, status=status, monitored_at=at, data_source=data_source
    )


_MISSING = object()


def _patch_loss(mon_svc=None, equipment=_MISSING, oee_svc=None):
    """组合 patch：Equipment.filter + OEE service + 监控 service。"""
    if equipment is _MISSING:
        equipment = _equipment()
    return (
        patch(EQ_FILTER, return_value=_equipment_qs(equipment)),
        patch(OEE_SVC, return_value=oee_svc or _oee_svc()),
        patch(MON_SVC, return_value=mon_svc or _mon_svc()),
    )


class TestQueryEquipmentOeeParams:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await ep.query_equipment_oee(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_dates(self):
        out = await ep.query_equipment_oee(
            date_start="2026/01/01", ctx=_ctx()
        )
        assert "date_start" in out
        out = await ep.query_equipment_oee(date_end="abc", ctx=_ctx())
        assert "date_end" in out

    @pytest.mark.asyncio
    async def test_invalid_ids(self):
        out = await ep.query_equipment_oee(equipment_id="abc", ctx=_ctx())
        assert "equipment_id" in out and "整数" in out
        out = await ep.query_equipment_oee(workshop_id="x", ctx=_ctx())
        assert "workshop_id" in out and "整数" in out


class TestQueryEquipmentOee:
    @pytest.mark.asyncio
    async def test_calls_service_with_day_bounds_and_outputs(self):
        svc = _oee_svc()
        with patch(OEE_SVC, return_value=svc):
            out = await ep.query_equipment_oee(
                date_start="2026-01-01",
                date_end="2026-01-31",
                ctx=_ctx(),
            )
        kw = svc.list_equipment_oee.await_args.kwargs
        assert kw["tenant_id"] == TENANT
        assert kw["equipment_ids"] is None
        assert kw["date_start"] == datetime(2026, 1, 1, 0, 0, 0)
        assert kw["date_end"] == datetime(2026, 1, 31, 23, 59, 59, 999999)
        assert kw["limit"] == 10
        assert "EQ-001" in out and "注塑机三号" in out
        # 三分量原样透传 service 值
        assert "OEE 57.6%" in out
        assert "75.0%" in out and "80.0%" in out and "96.0%" in out
        assert "计划 160.0h" in out and "实际运行 120.0h" in out
        assert "报工 12 条" in out

    @pytest.mark.asyncio
    async def test_equipment_id_filter(self):
        svc = _oee_svc()
        with patch(OEE_SVC, return_value=svc):
            await ep.query_equipment_oee(equipment_id=5, ctx=_ctx())
        assert svc.list_equipment_oee.await_args.kwargs["equipment_ids"] == [5]

    @pytest.mark.asyncio
    async def test_workshop_resolves_equipment_ids(self):
        eq_svc = SimpleNamespace(
            list_equipment=AsyncMock(
                return_value=(
                    [SimpleNamespace(id=11), SimpleNamespace(id=12)],
                    2,
                )
            )
        )
        svc = _oee_svc()
        with patch(OEE_SVC, return_value=svc), patch(
            EQ_SVC, eq_svc
        ):
            await ep.query_equipment_oee(workshop_id=3, ctx=_ctx())
        kw = eq_svc.list_equipment.await_args.kwargs
        assert kw["workshop_id"] == 3 and kw["is_active"] is True
        assert svc.list_equipment_oee.await_args.kwargs[
            "equipment_ids"
        ] == [11, 12]

    @pytest.mark.asyncio
    async def test_workshop_and_equipment_id_intersect(self):
        eq_svc = SimpleNamespace(
            list_equipment=AsyncMock(
                return_value=([SimpleNamespace(id=11)], 1)
            )
        )
        svc = _oee_svc()
        with patch(OEE_SVC, return_value=svc), patch(EQ_SVC, eq_svc):
            # 设备 5 不在车间设备集合内 → 空结果固定文案
            out = await ep.query_equipment_oee(
                equipment_id=5, workshop_id=3, ctx=_ctx()
            )
        assert "未查询到" in out
        with patch(OEE_SVC, return_value=svc), patch(EQ_SVC, eq_svc):
            out = await ep.query_equipment_oee(
                equipment_id=11, workshop_id=3, ctx=_ctx()
            )
        assert svc.list_equipment_oee.await_args.kwargs[
            "equipment_ids"
        ] == [11]

    @pytest.mark.asyncio
    async def test_workshop_no_equipment(self):
        eq_svc = SimpleNamespace(
            list_equipment=AsyncMock(return_value=([], 0))
        )
        svc = _oee_svc()
        with patch(OEE_SVC, return_value=svc), patch(EQ_SVC, eq_svc):
            out = await ep.query_equipment_oee(workshop_id=9, ctx=_ctx())
        assert "未查询到" in out
        svc.list_equipment_oee.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_limit_clamped_to_20(self):
        svc = _oee_svc()
        with patch(OEE_SVC, return_value=svc):
            await ep.query_equipment_oee(limit=99, ctx=_ctx())
        assert svc.list_equipment_oee.await_args.kwargs["limit"] == 20

    @pytest.mark.asyncio
    async def test_ids_path_adapter_truncates(self):
        svc = _oee_svc(
            list_equipment_oee=AsyncMock(
                return_value=[_oee_data() for _ in range(3)]
            )
        )
        with patch(OEE_SVC, return_value=svc):
            out = await ep.query_equipment_oee(
                equipment_id=11, limit=2, ctx=_ctx()
            )
        assert out.count("设备 EQ-001") == 2

    @pytest.mark.asyncio
    async def test_empty_and_none_metrics(self):
        svc = _oee_svc(list_equipment_oee=AsyncMock(return_value=[]))
        with patch(OEE_SVC, return_value=svc):
            out = await ep.query_equipment_oee(ctx=_ctx())
        assert "未查询到" in out

        svc = _oee_svc(
            list_equipment_oee=AsyncMock(
                return_value=[
                    _oee_data(
                        oee={
                            "availability_rate": None,
                            "performance_rate": None,
                            "quality_rate": None,
                            "oee_value": None,
                        },
                        unavailable_reasons=["未维护本窗口的计划生产时间"],
                    )
                ]
            )
        )
        with patch(OEE_SVC, return_value=svc):
            out = await ep.query_equipment_oee(ctx=_ctx())
        assert "不可用" in out and "未维护本窗口的计划生产时间" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = _oee_svc(
            list_equipment_oee=AsyncMock(side_effect=RuntimeError("db down"))
        )
        with patch(OEE_SVC, return_value=svc):
            out = await ep.query_equipment_oee(ctx=_ctx())
        assert out == "查询设备 OEE 失败，请稍后重试"
        assert "db down" not in out


class TestAnalyzeEquipmentLossesParams:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await ep.analyze_equipment_losses(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_equipment_id_required(self):
        out = await ep.analyze_equipment_losses(ctx=_ctx())
        assert "equipment_id" in out and "必填" in out
        out = await ep.analyze_equipment_losses(
            equipment_id="abc", ctx=_ctx()
        )
        assert "equipment_id" in out and "整数" in out

    @pytest.mark.asyncio
    async def test_invalid_dates(self):
        out = await ep.analyze_equipment_losses(
            equipment_id=11, date_start="bad", ctx=_ctx()
        )
        assert "date_start" in out

    @pytest.mark.asyncio
    async def test_equipment_not_found(self):
        p_filter, p_oee, p_mon = _patch_loss(
            equipment=None, mon_svc=_mon_svc()
        )
        with p_filter, p_oee, p_mon:
            out = await ep.analyze_equipment_losses(
                equipment_id=99,
                date_start="2026-01-05",
                date_end="2026-01-05",
                ctx=_ctx(),
            )
        assert "未查询到指定设备" in out


class TestAnalyzeEquipmentLosses:
    @pytest.mark.asyncio
    async def test_components_and_loss_topn(self):
        # 期间 01-05 全天（日初~日末，naive→UTC）；每行延伸上限 5min
        # （calculate_oee 同口径）：故障/待机各 300s=0.1h，运行中不计
        rows = [
            _mon_row("故障", datetime(2026, 1, 5, 10, 0), 1),
            _mon_row("待机", datetime(2026, 1, 5, 11, 0), 2),
            _mon_row("运行中", datetime(2026, 1, 5, 12, 0), 3),
        ]
        p_filter, p_oee, p_mon = _patch_loss(mon_svc=_mon_svc(rows))
        with p_filter, p_oee, p_mon:
            out = await ep.analyze_equipment_losses(
                equipment_id=11,
                date_start="2026-01-05",
                date_end="2026-01-05",
                ctx=_ctx(),
            )
        # 三分量透传
        assert "OEE 57.6%" in out
        assert "75.0%" in out and "80.0%" in out and "96.0%" in out
        # 样本天数 = trend_data 行数
        assert "样本 3 天" in out
        assert "报工 12 条" in out
        # 聚合可复算：300s+300s=600s=0.2h，各占 50%
        assert "合计 0.2 小时" in out and "Top5" in out
        assert out.count("0.1 小时") == 2
        assert "50.0%" in out
        # 运行中不列为损失
        assert "运行中：" not in out

    @pytest.mark.asyncio
    async def test_only_date_start(self):
        # 只传 date_start：缺省 end 与 _day_bounds 同口径 naive（UTC 解释），
        # 不得因 naive/aware 混算 TypeError 回落到失败文案
        svc = _oee_svc()
        p_filter, p_oee, p_mon = _patch_loss(oee_svc=svc)
        with p_filter, p_oee, p_mon:
            out = await ep.analyze_equipment_losses(
                equipment_id=11,
                date_start="2026-01-05",
                ctx=_ctx(),
            )
        assert "查询设备损失分析失败" not in out
        assert "OEE 损失分析" in out and "OEE 57.6%" in out
        kw = svc.calculate_equipment_oee.await_args.kwargs
        assert kw["date_start"] == datetime(2026, 1, 5, 0, 0, 0)
        assert kw["date_start"].tzinfo is None
        assert kw["date_end"].tzinfo is None
        assert kw["date_end"] > kw["date_start"]

    @pytest.mark.asyncio
    async def test_only_date_end(self):
        # 只传 date_end：缺省 start=end-30 天，与 end 同为 naive
        svc = _oee_svc()
        p_filter, p_oee, p_mon = _patch_loss(oee_svc=svc)
        with p_filter, p_oee, p_mon:
            out = await ep.analyze_equipment_losses(
                equipment_id=11,
                date_end="2026-01-31",
                ctx=_ctx(),
            )
        assert "查询设备损失分析失败" not in out
        assert "OEE 损失分析" in out
        kw = svc.calculate_equipment_oee.await_args.kwargs
        assert kw["date_end"] == datetime(2026, 1, 31, 23, 59, 59, 999999)
        assert kw["date_start"] == datetime(2026, 1, 1, 23, 59, 59, 999999)

    @pytest.mark.asyncio
    async def test_date_start_after_date_end_no_crash(self):
        # start>end：两端同 naive，趋势无样本、聚合为空，
        # 输出正常分析文本而非异常回落
        p_filter, p_oee, p_mon = _patch_loss()
        with p_filter, p_oee, p_mon:
            out = await ep.analyze_equipment_losses(
                equipment_id=11,
                date_start="2026-02-01",
                date_end="2026-01-01",
                ctx=_ctx(),
            )
        assert "查询设备损失分析失败" not in out
        assert "期间内无损失记录" in out

    @pytest.mark.asyncio
    async def test_topn_merges_rest_as_other(self):
        # 7 个非运行状态各 300s（行距恰 5min）→ Top5 + 其他合并 2 类 0.2h
        statuses = ["待机", "故障", "维修中", "停用", "校验中", "报废", "正常"]
        rows = [
            _mon_row(s, datetime(2026, 1, 5, 8, i * 5), i + 1)
            for i, s in enumerate(statuses)
        ]
        rows.append(_mon_row("运行中", datetime(2026, 1, 5, 8, 35), 8))
        p_filter, p_oee, p_mon = _patch_loss(mon_svc=_mon_svc(rows))
        with p_filter, p_oee, p_mon:
            out = await ep.analyze_equipment_losses(
                equipment_id=11,
                date_start="2026-01-05",
                date_end="2026-01-05",
                ctx=_ctx(),
            )
        assert "其他（合并 2 类）：0.2 小时" in out
        # Top5 行数 = 5 条编号行
        assert "\n5. " in out and "\n6. " not in out

    @pytest.mark.asyncio
    async def test_planned_window_intersection(self):
        # 计划窗口 09:30-10:30：故障/待机各行延伸 5min 均在窗口内各计
        # 300s；停用 12:00 在窗口外不计
        equipment = _equipment(
            technical_parameters={
                "oee": {
                    "planned_windows": [
                        {
                            "start": "2026-01-05T09:30:00+00:00",
                            "end": "2026-01-05T10:30:00+00:00",
                        }
                    ]
                }
            }
        )
        rows = [
            _mon_row("故障", datetime(2026, 1, 5, 10, 0), 1),
            _mon_row("待机", datetime(2026, 1, 5, 10, 10), 2),
            _mon_row("停用", datetime(2026, 1, 5, 12, 0), 3),
        ]
        p_filter, p_oee, p_mon = _patch_loss(
            mon_svc=_mon_svc(rows), equipment=equipment
        )
        with p_filter, p_oee, p_mon:
            out = await ep.analyze_equipment_losses(
                equipment_id=11,
                date_start="2026-01-05",
                date_end="2026-01-05",
                ctx=_ctx(),
            )
        assert "计划窗口内非运行时长" in out
        assert "合计 0.2 小时" in out
        assert "故障：0.1 小时" in out and "待机：0.1 小时" in out
        assert "停用" not in out.split("Top5")[-1]

    @pytest.mark.asyncio
    async def test_no_window_notes_full_period(self):
        rows = [_mon_row("故障", datetime(2026, 1, 5, 10, 0), 1)]
        p_filter, p_oee, p_mon = _patch_loss(mon_svc=_mon_svc(rows))
        with p_filter, p_oee, p_mon:
            out = await ep.analyze_equipment_losses(
                equipment_id=11,
                date_start="2026-01-05",
                date_end="2026-01-05",
                ctx=_ctx(),
            )
        assert "未配置计划窗口" in out

    @pytest.mark.asyncio
    async def test_non_sensor_rows_excluded(self):
        rows = [
            _mon_row(
                "故障", datetime(2026, 1, 5, 10, 0), 1, data_source="manual"
            )
        ]
        p_filter, p_oee, p_mon = _patch_loss(mon_svc=_mon_svc(rows))
        with p_filter, p_oee, p_mon:
            out = await ep.analyze_equipment_losses(
                equipment_id=11,
                date_start="2026-01-05",
                date_end="2026-01-05",
                ctx=_ctx(),
            )
        assert "期间内无损失记录" in out
        # OEE 三分量仍输出
        assert "OEE 57.6%" in out

    @pytest.mark.asyncio
    async def test_empty_monitors_and_unavailable_reasons(self):
        svc = _oee_svc(
            calculate_equipment_oee=AsyncMock(
                return_value=_oee_data(
                    oee={
                        "availability_rate": None,
                        "performance_rate": None,
                        "quality_rate": None,
                        "oee_value": None,
                    },
                    unavailable_reasons=["未维护理想节拍"],
                )
            )
        )
        p_filter, p_oee, p_mon = _patch_loss(
            mon_svc=_mon_svc([]), oee_svc=svc
        )
        with p_filter, p_oee, p_mon:
            out = await ep.analyze_equipment_losses(
                equipment_id=11,
                date_start="2026-01-05",
                date_end="2026-01-05",
                ctx=_ctx(),
            )
        assert "期间内无损失记录" in out
        assert "不可用" in out and "未维护理想节拍" in out

    @pytest.mark.asyncio
    async def test_monitor_cap_note(self):
        rows = [_mon_row("故障", datetime(2026, 1, 5, 10, 0), 1)]
        p_filter, p_oee, p_mon = _patch_loss(
            mon_svc=_mon_svc(rows, total=600)
        )
        with p_filter, p_oee, p_mon:
            out = await ep.analyze_equipment_losses(
                equipment_id=11,
                date_start="2026-01-05",
                date_end="2026-01-05",
                ctx=_ctx(),
            )
        assert "监控明细共 600 条" in out and "按最近 1 条统计" in out

    @pytest.mark.asyncio
    async def test_trend_sample_clipped_over_92_days(self):
        svc = _oee_svc()
        p_filter, p_oee, p_mon = _patch_loss(oee_svc=svc)
        with p_filter, p_oee, p_mon:
            out = await ep.analyze_equipment_losses(
                equipment_id=11,
                date_start="2026-01-01",
                date_end="2026-06-30",
                ctx=_ctx(),
            )
        kw = svc.get_equipment_oee_trend.await_args.kwargs
        # 趋势起点被截到 end-92d
        assert (kw["date_end"] - kw["date_start"]).days <= 92
        assert "趋势采样取最近 92 天" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = _oee_svc(
            calculate_equipment_oee=AsyncMock(
                side_effect=RuntimeError("boom")
            )
        )
        p_filter, p_oee, p_mon = _patch_loss(oee_svc=svc)
        with p_filter, p_oee, p_mon:
            out = await ep.analyze_equipment_losses(
                equipment_id=11,
                date_start="2026-01-05",
                date_end="2026-01-05",
                ctx=_ctx(),
            )
        assert out == "查询设备损失分析失败，请稍后重试"
        assert "boom" not in out
