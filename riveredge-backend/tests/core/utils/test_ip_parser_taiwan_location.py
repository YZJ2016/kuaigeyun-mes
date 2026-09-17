from core.utils.ip_parser import (
    format_location_label,
    format_manual_user_location_label,
    normalize_login_location_label,
)


def test_normalize_prefixes_taiwan_without_china():
    assert normalize_login_location_label("台湾 Taoyuan 桃園區") == "中国 台湾 Taoyuan 桃園區"
    assert normalize_login_location_label("Taiwan Taoyuan") == "中国 Taiwan Taoyuan"


def test_normalize_keeps_existing_china_prefix():
    assert normalize_login_location_label("中国 台湾 台北") == "中国 台湾 台北"


def test_normalize_rewrites_english_china_prefix():
    assert normalize_login_location_label("China Taiwan Taipei") == "中国 Taiwan Taipei"


def test_normalize_ignores_non_taiwan():
    assert normalize_login_location_label("中国 广东 深圳") == "中国 广东 深圳"
    assert normalize_login_location_label("China Jiangsu Wuxi") == "China Jiangsu Wuxi"


def test_format_location_label_applies_taiwan_rule():
    assert format_location_label(country="台湾", region="Taoyuan", city="桃園區") == (
        "中国 台湾 Taoyuan 桃園區"
    )


def test_format_manual_user_location_label():
    assert format_manual_user_location_label(["青海省", "西宁市", "城东区"]) == (
        "中国 青海省 西宁市 城东区"
    )
    assert format_manual_user_location_label(["北京市", "市辖区", "东城区"]) == (
        "中国 北京市 东城区"
    )
    assert format_manual_user_location_label(["台湾省", "台北市"]) == "中国 台湾省 台北市"
    assert format_manual_user_location_label([]) is None
    assert format_manual_user_location_label(None) is None
