"""KU-AI spec 215 单测：query_complaints / query_8d_reports / eight_d_draft。

全部 mock / 假数据，不需要真实数据库。覆盖：
- 闭集参数（status/date/id）非法回固定文案；
- query_complaints：service.list 无 customer_id/material_id/日期过滤键且
  ListItem 不含这些字段 → 适配层按 service 同口径基座谓词直查模型
  （query_ecn 先例），filter kwargs 精确透传断言；行级范围资源键
  kuaizhizao:quality-complaint；
- query_8d_reports：list_reports kwargs 透传（status/keyword/limit）；
  complaint_id → QualityComplaintService.get 解析 eight_d_report_id →
  Quality8DService.get_report；行级范围资源键
  kuaizhizao:quality-management-eight-d-reports；
- masking：客户/供应商联系人、电话、商务条款、金额、整改说明、人名不输出；
- eight_d_draft 画像：D0–D8 字段齐、draftNotice 固定标注、AI 生成声明；
- 空结果、底层异常、limit 截断与既有 Tool 口径一致。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.services.tools import complaint_8d as c8d
from core.ai.runtime.context import AiRuntimeContext
from core.utils.timezone_utils import to_api_isoformat

TENANT = 7
USER_ID = 5


def _ctx():
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
    )


def _complaint_row(**kw):
    base = dict(
        id=301,
        code="QC-2026-001",
        title="来料尺寸超差投诉",
        business_type="customer",
        status="processing",
        defect_category="structure",
        supplier_name="供应商甲",
        customer_name="客户乙",
        customer_id=3,
        material_id=11,
        material_code="M-001",
        material_name="物料一",
        batch_no="B2410-07",
        quantity=None,
        due_at=datetime(2026, 1, 20, 17, 0),
        created_at=datetime(2026, 1, 10, 9, 30),
        eight_d_report_id=55,
        source_inspection_type="iqc",
        source_inspection_id=88,
        # 敏感字段：不得出现在输出
        supplier_response="供方机密整改说明",
        revoke_reason="客户私了",
        extension_payload={"contact": "13800000000"},
        created_by_name="李四",
        updated_by_name="王五",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _8d_row(**kw):
    base = dict(
        id=55,
        report_code="8D-2026-001",
        title="尺寸超差 8D",
        status="d4_root_cause",
        severity="major",
        owner_name="王工",
        due_date=datetime(2026, 2, 1, 0, 0),
        closed_at=None,
        open_action_items_count=2,
        quality_exception_id=None,
        defect_record_id=None,
        # 敏感字段：不得出现在输出
        created_by_name="赵六",
        updated_by_name="钱七",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _qs(rows=()):
    """模拟 Tortoise QuerySet 链（filter/order_by/limit → all）。"""
    q = MagicMock()
    for m in ("filter", "order_by", "limit", "offset"):
        setattr(q, m, MagicMock(return_value=q))
    q.all = AsyncMock(return_value=list(rows))
    return q


def _scope_patch(visible):
    return patch(
        "apps.kuaiai.services.scene_tools._scoped_row_ids",
        new=AsyncMock(return_value=set(visible)),
    )


_COMPLAINT_MODEL = "apps.kuaizhizao.models.quality_complaint.QualityComplaint"
_COMPLAINT_SVC = (
    "apps.kuaizhizao.services.quality_complaint_service.QualityComplaintService"
)
_8D_SVC = (
    "apps.kuaizhizao.services.quality_improvement_service.Quality8DService"
)


class TestQueryComplaints:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await c8d.query_complaints(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_enums_and_ids(self):
        out = await c8d.query_complaints(status="bogus", ctx=_ctx())
        assert "status" in out and "draft" in out
        out = await c8d.query_complaints(date_start="2026/01/01", ctx=_ctx())
        assert "date_start" in out
        out = await c8d.query_complaints(date_end="abc", ctx=_ctx())
        assert "date_end" in out
        out = await c8d.query_complaints(customer_id=0, ctx=_ctx())
        assert "customer_id" in out
        out = await c8d.query_complaints(customer_id=-3, ctx=_ctx())
        assert "customer_id" in out
        out = await c8d.query_complaints(material_id="abc", ctx=_ctx())
        assert "material_id" in out

    @pytest.mark.asyncio
    async def test_filters_applied_on_model_query(self):
        qs = _qs([])
        # 站点日界由 site_day_bounds_utc 提供：start→当日初、end→次日初
        # （半开区间）；此处注入固定 UTC 界，断言接线而非时区换算本身
        fake_bounds = MagicMock(
            side_effect=[
                (datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc), None),
                (None, datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc)),
            ]
        )
        with patch(
            f"{_COMPLAINT_MODEL}.filter", MagicMock(return_value=qs)
        ) as mock_filter, patch(
            "core.utils.timezone_utils.site_day_bounds_utc", fake_bounds
        ):
            out = await c8d.query_complaints(
                customer_id=3,
                material_id=11,
                status="processing",
                date_start="2026-01-01",
                date_end="2026-01-31",
                ctx=_ctx(),
            )
        # 基座谓词与 service.list 同口径（tenant + 软删）
        mock_filter.assert_called_once_with(
            tenant_id=TENANT, deleted_at__isnull=True
        )
        call_kw = [c.kwargs for c in qs.filter.call_args_list]
        assert {"status": "processing"} in call_kw
        assert {"customer_id": 3} in call_kw
        assert {"material_id": 11} in call_kw
        # date_start/date_end 解析为 date 后交给 site_day_bounds_utc 转站点日界
        assert [c.args[0] for c in fake_bounds.call_args_list] == [
            date(2026, 1, 1),
            date(2026, 1, 31),
        ]
        # 谓词取半开区间 [start, end)：__gte=start、__lt=end（naive UTC）
        gte = [c["created_at__gte"] for c in call_kw if "created_at__gte" in c]
        lt = [c["created_at__lt"] for c in call_kw if "created_at__lt" in c]
        assert gte == [datetime(2026, 1, 1, 0, 0)]
        assert lt == [datetime(2026, 2, 1, 0, 0)]
        assert not any("created_at__lte" in c for c in call_kw)
        assert "未查询到" in out

    @pytest.mark.asyncio
    async def test_rows_scoped_and_summarized(self):
        qs = _qs([
            _complaint_row(id=301),
            _complaint_row(id=302, code="QC-2026-002", eight_d_report_id=None),
        ])
        with patch(
            f"{_COMPLAINT_MODEL}.filter", MagicMock(return_value=qs)
        ), _scope_patch({301}) as m:
            out = await c8d.query_complaints(ctx=_ctx())
        assert m.await_args.args[2] == "kuaizhizao:quality-complaint"
        assert "共 1 张质量投诉单" in out
        assert "QC-2026-001" in out and "QC-2026-002" not in out
        assert "客户 客户乙" in out
        assert "客户投诉" in out
        assert "M-001" in out and "物料一" in out
        assert "B2410-07" in out
        assert "状态 processing" in out
        # datetime 输出走 to_api_isoformat（站点时区，与 API 同口径）
        assert f"要求完成 {to_api_isoformat(datetime(2026, 1, 20, 17, 0))}" in out
        assert f"创建 {to_api_isoformat(datetime(2026, 1, 10, 9, 30))}" in out
        assert "关联8D id=55" in out
        # 敏感字段不输出：联系人/整改说明/商务/人名
        assert "供方机密整改说明" not in out
        assert "客户私了" not in out
        assert "13800000000" not in out
        assert "李四" not in out and "王五" not in out
        assert "联系人" not in out and "电话" not in out
        assert "金额" not in out and "单价" not in out

    @pytest.mark.asyncio
    async def test_all_out_of_scope_truthful_copy(self):
        qs = _qs([_complaint_row()])
        with patch(
            f"{_COMPLAINT_MODEL}.filter", MagicMock(return_value=qs)
        ), _scope_patch(set()):
            out = await c8d.query_complaints(ctx=_ctx())
        assert "数据范围内" in out and "未查询到" in out

    @pytest.mark.asyncio
    async def test_empty_result(self):
        qs = _qs([])
        with patch(
            f"{_COMPLAINT_MODEL}.filter", MagicMock(return_value=qs)
        ):
            out = await c8d.query_complaints(ctx=_ctx())
        assert "未查询到符合条件的质量投诉单" in out

    @pytest.mark.asyncio
    async def test_query_error_fixed_text(self):
        with patch(
            f"{_COMPLAINT_MODEL}.filter",
            MagicMock(side_effect=RuntimeError("db down")),
        ):
            out = await c8d.query_complaints(ctx=_ctx())
        assert out == "查询质量投诉单失败，请稍后重试"
        assert "db down" not in out

    @pytest.mark.asyncio
    async def test_scope_error_fixed_text(self):
        qs = _qs([_complaint_row()])
        with patch(
            f"{_COMPLAINT_MODEL}.filter", MagicMock(return_value=qs)
        ), patch(
            "apps.kuaiai.services.scene_tools._scoped_row_ids",
            new=AsyncMock(side_effect=RuntimeError("x")),
        ):
            out = await c8d.query_complaints(ctx=_ctx())
        assert out == "查询质量投诉单失败，请稍后重试"

    @pytest.mark.asyncio
    async def test_limit_clamped(self):
        rows = [
            _complaint_row(id=1000 + i, code=f"QC-{i}") for i in range(30)
        ]
        qs = _qs(rows)
        with patch(
            f"{_COMPLAINT_MODEL}.filter", MagicMock(return_value=qs)
        ), _scope_patch({r.id for r in rows}):
            out = await c8d.query_complaints(limit=99, ctx=_ctx())
        assert qs.limit.call_args.args[0] <= 100
        assert "返回前 20 张" in out

    def test_fmt_dt_uses_api_site_timezone(self):
        """datetime 展示委托 to_api_isoformat（站点时区口径，与 API 一致）。"""
        with patch(
            "core.utils.timezone_utils.to_api_isoformat",
            MagicMock(return_value="SITE-TZ-MARK"),
        ) as m:
            assert c8d._fmt_dt(datetime(2026, 1, 10, 9, 30)) == "SITE-TZ-MARK"
            m.assert_called_once_with(datetime(2026, 1, 10, 9, 30))
        # 缺省与异常回落不抛错
        assert c8d._fmt_dt(None) == ""
        assert c8d._fmt_dt("2026-01-10 09:30:00") == "2026-01-10 09:30"


class TestQuery8dReports:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await c8d.query_8d_reports(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_status_and_id(self):
        out = await c8d.query_8d_reports(status="bogus", ctx=_ctx())
        assert "status" in out and "d0_prepare" in out
        out = await c8d.query_8d_reports(complaint_id=0, ctx=_ctx())
        assert "complaint_id" in out
        out = await c8d.query_8d_reports(complaint_id="abc", ctx=_ctx())
        assert "complaint_id" in out

    @pytest.mark.asyncio
    async def test_list_kwargs_and_scope(self):
        svc = SimpleNamespace(
            list_reports=AsyncMock(
                return_value=SimpleNamespace(
                    items=[
                        _8d_row(
                            id=55,
                            quality_exception_id=77,
                            defect_record_id=88,
                        ),
                        _8d_row(id=56, report_code="8D-2026-002"),
                    ],
                    total=2,
                )
            )
        )
        with patch(_8D_SVC, return_value=svc), _scope_patch({55}) as m:
            out = await c8d.query_8d_reports(
                keyword="超差", status="d4_root_cause", limit=5, ctx=_ctx()
            )
        kw = svc.list_reports.await_args.kwargs
        assert svc.list_reports.await_args.args[0] == TENANT
        assert kw["skip"] == 0 and kw["limit"] <= 100
        assert kw["status"] == "d4_root_cause" and kw["keyword"] == "超差"
        assert m.await_args.args[2] == (
            "kuaizhizao:quality-management-eight-d-reports"
        )
        assert "共 1 张 8D 报告" in out
        # 计数披露：与 query_complaints 同款「前 N 条候选内计」口径
        assert f"前 {c8d._8D_OVERSAMPLE_LIMIT} 条候选内计" in out
        assert "8D-2026-001" in out and "8D-2026-002" not in out
        assert "阶段 D4 根因分析" in out
        assert "严重程度 major" in out
        assert f"截止 {to_api_isoformat(datetime(2026, 2, 1, 0, 0))}" in out
        assert "未闭环行动项 2" in out
        # 关联单非空标注（Quality8DResponse 仅 id 列，无 code 联查）
        assert "关联质量异常#77" in out
        assert "关联不合格台账#88" in out
        # 人名/敏感字段不输出
        assert "王工" not in out and "赵六" not in out and "钱七" not in out
        assert "联系人" not in out and "电话" not in out and "金额" not in out

    @pytest.mark.asyncio
    async def test_empty_result(self):
        svc = SimpleNamespace(
            list_reports=AsyncMock(
                return_value=SimpleNamespace(items=[], total=0)
            )
        )
        with patch(_8D_SVC, return_value=svc):
            out = await c8d.query_8d_reports(ctx=_ctx())
        assert "未查询到符合条件的 8D 报告" in out

    @pytest.mark.asyncio
    async def test_all_out_of_scope_truthful_copy(self):
        svc = SimpleNamespace(
            list_reports=AsyncMock(
                return_value=SimpleNamespace(items=[_8d_row()], total=1)
            )
        )
        with patch(_8D_SVC, return_value=svc), _scope_patch(set()):
            out = await c8d.query_8d_reports(ctx=_ctx())
        assert "数据范围内" in out and "未查询到" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(
            list_reports=AsyncMock(side_effect=RuntimeError("db down"))
        )
        with patch(_8D_SVC, return_value=svc):
            out = await c8d.query_8d_reports(ctx=_ctx())
        assert out == "查询 8D 报告失败，请稍后重试"
        assert "db down" not in out

    @pytest.mark.asyncio
    async def test_limit_clamped(self):
        rows = [
            _8d_row(id=2000 + i, report_code=f"8D-{i}") for i in range(30)
        ]
        svc = SimpleNamespace(
            list_reports=AsyncMock(
                return_value=SimpleNamespace(items=rows, total=30)
            )
        )
        with patch(_8D_SVC, return_value=svc), _scope_patch(
            {r.id for r in rows}
        ):
            out = await c8d.query_8d_reports(limit=99, ctx=_ctx())
        assert svc.list_reports.await_args.kwargs["limit"] <= 100
        assert "返回前 20 张" in out

    # ------------------------------------------------ complaint_id 解析路径

    @pytest.mark.asyncio
    async def test_complaint_id_resolves_linked_report(self):
        complaint = SimpleNamespace(id=123, eight_d_report_id=55)
        c_svc = SimpleNamespace(get=AsyncMock(return_value=complaint))
        d_svc = SimpleNamespace(
            get_report=AsyncMock(return_value=_8d_row(id=55)),
            list_reports=AsyncMock(),
        )
        # 行级范围复核两次：先客诉行（_SCOPE_COMPLAINT），后 8D 行（_SCOPE_8D）
        with patch(_COMPLAINT_SVC, return_value=c_svc), patch(
            _8D_SVC, return_value=d_svc
        ), _scope_patch({123, 55}) as m:
            out = await c8d.query_8d_reports(complaint_id=123, ctx=_ctx())
        assert c_svc.get.await_args.args == (TENANT, 123)
        assert d_svc.get_report.await_args.args == (TENANT, 55)
        assert not d_svc.list_reports.await_count
        first, last = m.await_args_list[0], m.await_args_list[-1]
        assert first.args[2] == "kuaizhizao:quality-complaint"
        assert first.args[3] == {123}
        assert last.args[2] == (
            "kuaizhizao:quality-management-eight-d-reports"
        )
        assert "8D-2026-001" in out and "D4 根因分析" in out

    @pytest.mark.asyncio
    async def test_complaint_not_found(self):
        from infra.exceptions.exceptions import NotFoundError

        c_svc = SimpleNamespace(
            get=AsyncMock(side_effect=NotFoundError("质量投诉单不存在"))
        )
        d_svc = SimpleNamespace(get_report=AsyncMock(), list_reports=AsyncMock())
        with patch(_COMPLAINT_SVC, return_value=c_svc), patch(
            _8D_SVC, return_value=d_svc
        ):
            out = await c8d.query_8d_reports(complaint_id=999, ctx=_ctx())
        assert out == "未查询到对应客诉单"
        assert not d_svc.get_report.await_count

    @pytest.mark.asyncio
    async def test_complaint_without_linked_8d(self):
        c_svc = SimpleNamespace(
            get=AsyncMock(
                return_value=SimpleNamespace(id=123, eight_d_report_id=None)
            )
        )
        d_svc = SimpleNamespace(get_report=AsyncMock(), list_reports=AsyncMock())
        with patch(_COMPLAINT_SVC, return_value=c_svc), patch(
            _8D_SVC, return_value=d_svc
        ), _scope_patch({123}):
            out = await c8d.query_8d_reports(complaint_id=123, ctx=_ctx())
        assert out == "该客诉单尚未关联 8D 报告"
        assert not d_svc.get_report.await_count

    @pytest.mark.asyncio
    async def test_complaint_id_out_of_scope_truthful_copy(self):
        """客诉行在数据范围外：不透存在性，归一「数据范围内未查询到」。"""
        c_svc = SimpleNamespace(
            get=AsyncMock(
                return_value=SimpleNamespace(id=123, eight_d_report_id=55)
            )
        )
        d_svc = SimpleNamespace(get_report=AsyncMock(), list_reports=AsyncMock())
        with patch(_COMPLAINT_SVC, return_value=c_svc), patch(
            _8D_SVC, return_value=d_svc
        ), _scope_patch(set()) as m:
            out = await c8d.query_8d_reports(complaint_id=123, ctx=_ctx())
        assert out == "当前用户数据范围内未查询到对应客诉单"
        assert not d_svc.get_report.await_count
        assert not d_svc.list_reports.await_count
        # 客诉行套的是 _SCOPE_COMPLAINT 资源键
        assert m.await_args.args[2] == "kuaizhizao:quality-complaint"
        assert m.await_args.args[3] == {123}

    @pytest.mark.asyncio
    async def test_complaint_scope_error_fixed_text(self):
        """客诉行范围复核失败：外层归一为固定失败文案，不泄露细节。"""
        c_svc = SimpleNamespace(
            get=AsyncMock(
                return_value=SimpleNamespace(id=123, eight_d_report_id=55)
            )
        )
        d_svc = SimpleNamespace(get_report=AsyncMock(), list_reports=AsyncMock())
        with patch(_COMPLAINT_SVC, return_value=c_svc), patch(
            _8D_SVC, return_value=d_svc
        ), patch(
            "apps.kuaiai.services.scene_tools._scoped_row_ids",
            new=AsyncMock(side_effect=RuntimeError("scope down")),
        ):
            out = await c8d.query_8d_reports(complaint_id=123, ctx=_ctx())
        assert out == "查询 8D 报告失败，请稍后重试"
        assert "scope down" not in out

    @pytest.mark.asyncio
    async def test_linked_8d_status_mismatch(self):
        c_svc = SimpleNamespace(
            get=AsyncMock(
                return_value=SimpleNamespace(id=123, eight_d_report_id=55)
            )
        )
        d_svc = SimpleNamespace(
            get_report=AsyncMock(return_value=_8d_row(status="closed")),
            list_reports=AsyncMock(),
        )
        with patch(_COMPLAINT_SVC, return_value=c_svc), patch(
            _8D_SVC, return_value=d_svc
        ), _scope_patch({123}):
            out = await c8d.query_8d_reports(
                complaint_id=123, status="d4_root_cause", ctx=_ctx()
            )
        assert "未查询到符合条件的 8D 报告" in out

    @pytest.mark.asyncio
    async def test_linked_8d_keyword_match_and_mismatch(self):
        """complaint_id 路径的 _8d_matches 关键词再过滤（report_code/title/
        owner_name 同 list_reports 口径）：命中与未命中两分支。"""
        c_svc = SimpleNamespace(
            get=AsyncMock(
                return_value=SimpleNamespace(id=123, eight_d_report_id=55)
            )
        )
        d_svc = SimpleNamespace(
            get_report=AsyncMock(return_value=_8d_row()),
            list_reports=AsyncMock(),
        )
        with patch(_COMPLAINT_SVC, return_value=c_svc), patch(
            _8D_SVC, return_value=d_svc
        ), _scope_patch({123, 55}):
            # 命中 title「尺寸超差 8D」
            out = await c8d.query_8d_reports(
                complaint_id=123, keyword="超差", ctx=_ctx()
            )
            assert "8D-2026-001" in out
            # 命中 report_code
            out = await c8d.query_8d_reports(
                complaint_id=123, keyword="8d-2026", ctx=_ctx()
            )
            assert "8D-2026-001" in out
            # 未命中
            out = await c8d.query_8d_reports(
                complaint_id=123, keyword="外观划伤", ctx=_ctx()
            )
            assert "未查询到符合条件的 8D 报告" in out

    @pytest.mark.asyncio
    async def test_linked_8d_out_of_scope(self):
        c_svc = SimpleNamespace(
            get=AsyncMock(
                return_value=SimpleNamespace(id=123, eight_d_report_id=55)
            )
        )
        d_svc = SimpleNamespace(
            get_report=AsyncMock(return_value=_8d_row()),
            list_reports=AsyncMock(),
        )
        # 客诉行在范围内、8D 行在范围外：两次范围复核返回不同集合
        with patch(_COMPLAINT_SVC, return_value=c_svc), patch(
            _8D_SVC, return_value=d_svc
        ), patch(
            "apps.kuaiai.services.scene_tools._scoped_row_ids",
            new=AsyncMock(side_effect=[{123}, set()]),
        ):
            out = await c8d.query_8d_reports(complaint_id=123, ctx=_ctx())
        assert "数据范围内" in out and "未查询到" in out


class TestEightDDraftProfile:
    def test_profile_registered_with_d_sections(self):
        from core.ai.draft_profiles import (
            _EIGHT_D_STAGE_KEYS,
            ensure_draft_profiles,
        )
        from core.ai.structured_draft import StructuredDraftService

        ensure_draft_profiles()
        profile = StructuredDraftService.get_profile("eight_d_draft")
        assert profile.schema_name == "eight_d_draft"
        # D0–D8 全段字段骨架
        for key in (
            "d0Prepare",
            "d1Team",
            "d2Problem",
            "d3Containment",
            "d4RootCause",
            "d5CorrectiveAction",
            "d6ImplementResult",
            "d7PreventRecurrence",
            "d8TeamCongratulation",
        ):
            assert key in profile.json_spec
            assert key in _EIGHT_D_STAGE_KEYS
        # 草稿标注 + AI 生成声明
        assert "draftNotice" in profile.json_spec
        assert "草稿待人工确认" in profile.json_spec
        assert "AI 生成" in profile.json_spec
        assert "草稿" in profile.system_prompt
        # 头字段与收尾段
        assert "title" in profile.json_spec
        assert "verificationResult" in profile.json_spec
        assert "remarks" in profile.json_spec

    def test_meaningful_validator(self):
        from core.ai.draft_profiles import _eight_d_meaningful

        assert _eight_d_meaningful({"d2Problem": "尺寸超差"})
        assert _eight_d_meaningful({"title": "8D 草稿"})
        assert not _eight_d_meaningful({})
        assert not _eight_d_meaningful({"d1Team": "   "})
        assert not _eight_d_meaningful(None)
        # pydantic 对象（_AnyModel 风格）亦可达
        from pydantic import BaseModel

        class _Any(BaseModel):
            model_config = {"extra": "allow"}

        assert _eight_d_meaningful(_Any(d4RootCause="根因"))
        assert not _eight_d_meaningful(_Any())
