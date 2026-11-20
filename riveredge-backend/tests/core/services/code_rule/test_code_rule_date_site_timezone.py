"""编码规则日期段须按站点日历日渲染，不能对 UTC instant 直接 strftime。"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from core.services.code_rule.code_rule_component_service import (
    CodeRuleComponentService,
    format_code_rule_date,
)


@pytest.mark.parametrize(
    "utc_instant, expected_yyyymmdd",
    [
        (datetime(2026, 11, 19, 16, 30, 0, tzinfo=timezone.utc), "20261120"),
        (datetime(2026, 11, 19, 15, 59, 59, tzinfo=timezone.utc), "20261119"),
    ],
)
def test_format_code_rule_date_uses_site_calendar(utc_instant, expected_yyyymmdd):
    with patch("core.utils.timezone_utils.infra_settings.TIMEZONE", "Asia/Shanghai"):
        assert format_code_rule_date(utc_instant, "%Y%m%d") == expected_yyyymmdd


def test_resolve_code_render_uses_requisition_date_context():
    from core.services.code_rule.code_rule_component_service import resolve_code_render_datetime
    from core.utils.timezone_utils import to_site_date

    with patch("core.utils.timezone_utils.infra_settings.TIMEZONE", "Asia/Shanghai"):
        dt = resolve_code_render_datetime({"requisition_date": "2026-06-15"})
        assert to_site_date(dt).isoformat() == "2026-06-15"


def test_render_components_date_segment_site_midnight_crossing():
    components = [
        {"type": "fixed_text", "text": "CGSQ", "order": 1},
        {"type": "date", "format_type": "preset", "preset_format": "YYYYMMDD", "order": 2},
        {"type": "auto_counter", "digits": 4, "fixed_width": True, "order": 3},
    ]
    utc_now = datetime(2026, 11, 19, 16, 30, 0, tzinfo=timezone.utc)
    with patch("core.utils.timezone_utils.infra_settings.TIMEZONE", "Asia/Shanghai"):
        with patch(
            "core.services.code_rule.code_rule_component_service.resolve_code_render_datetime",
            return_value=utc_now,
        ):
            code = CodeRuleComponentService.render_components(components, 5, None)
    assert code == "CGSQ202611200005"