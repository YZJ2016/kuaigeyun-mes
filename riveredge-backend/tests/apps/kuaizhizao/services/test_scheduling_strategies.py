"""排产策略目录与产线绑定硬门禁。"""

import pytest

from apps.kuaizhizao.services.scheduling_engine.strategies import (
    STRATEGY_CATALOG,
    STRATEGY_CODES,
    normalize_strategy,
    strategy_label,
)
from apps.kuaizhizao.services.line_product_lookup import (
    eligible_line_ids_for_product,
    line_accepts_product,
)


def test_normalize_strategy_defaults_to_due_date():
    assert normalize_strategy(None) == "due_date"
    assert normalize_strategy("  ") == "due_date"


@pytest.mark.parametrize("code", list(STRATEGY_CODES))
def test_normalize_strategy_accepts_catalog_codes(code):
    assert normalize_strategy(code) == code
    assert normalize_strategy(code.upper()) == code


def test_normalize_strategy_rejects_unknown_code():
    with pytest.raises(ValueError):
        normalize_strategy("random_solver")


def test_catalog_covers_all_codes():
    assert {item["code"] for item in STRATEGY_CATALOG} == set(STRATEGY_CODES)
    assert strategy_label("changeover_min") == "换线最少"


def test_line_accepts_product_requires_binding():
    allow = {7: {100, 200}}
    assert line_accepts_product(7, 100, allow) is True
    assert line_accepts_product(7, 300, allow) is False
    assert line_accepts_product(8, 100, allow) is False
    assert line_accepts_product(0, 100, allow) is False


def test_eligible_line_ids_intersects_configured():
    allow = {7: {100}, 8: {100, 200}}
    assert eligible_line_ids_for_product(100, allow_map=allow) == {7, 8}
    assert eligible_line_ids_for_product(
        100, configured_line_ids={7}, allow_map=allow
    ) == {7}
    assert eligible_line_ids_for_product(999, allow_map=allow) == set()
