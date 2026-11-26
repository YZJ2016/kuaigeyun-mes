"""装箱 Profile 与 Cartonization 占位算法单元测试。"""

from decimal import Decimal
from types import SimpleNamespace

from apps.kuaizhizao.services.packing_profile_service import PackingProfileService


def test_suggest_cartonization_ceil_by_capacity():
    svc = PackingProfileService()
    profile = SimpleNamespace(max_quantity=Decimal("8"))
    result = svc.suggest_cartonization(profile, line_count=3, total_quantity=Decimal("17"))
    assert result["suggested_box_count"] == 3
    assert result["algorithm"] == "profile_max_quantity_ceil"


def test_suggest_cartonization_unset_capacity():
    svc = PackingProfileService()
    profile = SimpleNamespace(max_quantity=None)
    result = svc.suggest_cartonization(profile, line_count=2, total_quantity=Decimal("10"))
    assert result["suggested_box_count"] == 2
    assert result["algorithm"] == "profile_capacity_unset"
