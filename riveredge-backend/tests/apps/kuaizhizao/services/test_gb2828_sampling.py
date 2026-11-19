"""GB/T 2828.1 抽检查表与方案类型短码。"""

from apps.kuaizhizao.services.gb2828_sampling import resolve_single_sampling_plan
from apps.kuaizhizao.services.inspection_policy_service import plan_type_short_code
from apps.kuaizhizao.services.inspection_step_spec import (
    normalize_sampling_spec,
    resolve_effective_sampling_spec,
)


def test_plan_type_short_code_mapping():
    assert plan_type_short_code("incoming") == "IQC"
    assert plan_type_short_code("process") == "IPQC"
    assert plan_type_short_code("patrol") == "PATROL"
    assert plan_type_short_code("unknown") == ""


def test_gb2828_lot_100_level_ii_aql_25_normal():
    resolved = resolve_single_sampling_plan(
        lot_size=100,
        level="II",
        aql=2.5,
        strictness="normal",
    )
    assert resolved["code_letter"] == "F"
    assert resolved["sample_size"] == 20
    assert resolved["accept_num"] == 1
    assert resolved["reject_num"] == 2


def test_normalize_gb2828_sampling_spec():
    spec = normalize_sampling_spec(
        {"mode": "gb2828_single", "level": "II", "aql": 2.5, "strictness": "normal"}
    )
    assert spec["mode"] == "gb2828_single"
    assert spec["level"] == "II"


def test_resolve_effective_gb2828_with_lot():
    spec = normalize_sampling_spec({"mode": "gb2828_single", "level": "II", "aql": 2.5})
    effective = resolve_effective_sampling_spec(spec, 100)
    assert effective["sample_size"] == 20
    assert effective["accept_num"] == 1
    assert effective.get("resolved_gb2828")
