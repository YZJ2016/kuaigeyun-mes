from core.utils.ip_parser import (
    _strip_admin_suffix,
    format_location_label,
    format_manual_user_location_label,
    merge_location_detail_with_zh_admin,
    normalize_login_location_label,
    pick_canonical_login_location,
    repair_truncated_zhou_city_login_location,
    vote_ip_location_details,
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


def test_pick_canonical_prefers_china_prefix_and_frequency():
    labels = (
        ["China Anhui Wuhu"] * 35
        + ["中国 广东 广州市"] * 74
        + ["CN Anhui Hefei"]
    )
    assert pick_canonical_login_location(labels) == "中国 广东 广州市"


def test_pick_canonical_prefers_chinese_when_counts_tie():
    labels = ["China Jiangsu Wuxi", "中国 江苏 无锡市"]
    assert pick_canonical_login_location(labels) == "中国 江苏 无锡市"


def test_pick_canonical_ignores_legacy_dash_format():
    assert pick_canonical_login_location(["中国-广东-广州", "中国 广东 广州市"]) == (
        "中国 广东 广州市"
    )


def test_vote_ip_location_prefers_region_then_city():
    """运营商段：广州 2 票 vs 安徽(芜湖2+合肥1)；先省后市应落芜湖。"""
    candidates = [
        {"city": "广州市", "region": "广东", "country": "中国", "lat": 23.1317, "lon": 113.266},
        {"city": "Guangzhou", "region": "Guangdong", "country": "China", "lat": 23.1317, "lon": 113.266},
        {"city": "Wuhu", "region": "Anhui", "country": "China", "lat": 31.146, "lon": 118.56455},
        {"city": "Hefei", "region": "Anhui", "country": "CN", "lat": 31.8639, "lon": 117.2808},
        {"city": "Wuhu", "region": "Anhui", "country": "China", "lat": 31.3522, "lon": 118.4451},
        {"city": "Beijing", "region": "Beijing", "country": "China", "lat": 39.9075, "lon": 116.3972},
    ]
    voted = vote_ip_location_details(candidates)
    assert voted is not None
    assert voted["city"] == "芜湖"
    assert voted["region"] == "安徽"
    assert voted["country"] == "中国"
    assert 31.1 <= float(voted["lat"]) <= 31.4
    assert 118.4 <= float(voted["lon"]) <= 118.6


def test_vote_ip_location_single_candidate():
    voted = vote_ip_location_details(
        [{"city": "无锡市", "region": "江苏", "country": "中国", "lat": 31.57, "lon": 120.3}]
    )
    assert voted == {
        "city": "无锡",
        "region": "江苏",
        "country": "中国",
        "lat": 31.57,
        "lon": 120.3,
    }


def test_merge_location_detail_prefers_zh_admin_keeps_coords():
    detail = {
        "city": "Wuhu",
        "region": "Anhui",
        "country": "China",
        "lat": 31.35,
        "lon": 118.45,
    }
    merged = merge_location_detail_with_zh_admin(
        detail,
        {"country": "中国", "region": "安徽省", "city": "芜湖市"},
    )
    assert merged == {
        "city": "芜湖",
        "region": "安徽",
        "country": "中国",
        "lat": 31.35,
        "lon": 118.45,
    }
    assert format_location_label(**{k: merged[k] for k in ("country", "region", "city")}) == (
        "中国 安徽 芜湖"
    )


def test_merge_location_detail_alias_when_no_admin():
    merged = merge_location_detail_with_zh_admin(
        {"city": "Wuxi", "region": "Jiangsu", "country": "CN", "lat": 1.0, "lon": 2.0},
        None,
    )
    assert merged["country"] == "中国"
    assert merged["region"] == "江苏"
    assert merged["city"] == "无锡"


def test_strip_admin_suffix_keeps_zhou_in_two_char_city_names():
    assert _strip_admin_suffix("广州") == "广州"
    assert _strip_admin_suffix("广州市") == "广州"
    assert _strip_admin_suffix("杭州") == "杭州"
    assert _strip_admin_suffix("郑州市") == "郑州"
    assert _strip_admin_suffix("凉山州") == "凉山"


def test_merge_location_detail_keeps_guangzhou_from_zh_api():
    merged = merge_location_detail_with_zh_admin(
        {"city": "广州", "region": "广东", "country": "中国", "lat": 23.13, "lon": 113.26},
        None,
    )
    assert merged["city"] == "广州"
    assert format_location_label(**{k: merged[k] for k in ("country", "region", "city")}) == (
        "中国 广东 广州"
    )


def test_repair_truncated_zhou_city_login_location():
    assert repair_truncated_zhou_city_login_location("中国 广东 广") == "中国 广东 广州"
    assert repair_truncated_zhou_city_login_location("中国 浙江 杭") == "中国 浙江 杭州"
    assert repair_truncated_zhou_city_login_location("中国 广东 广州") == "中国 广东 广州"
    assert repair_truncated_zhou_city_login_location("中国 江苏 无锡") == "中国 江苏 无锡"
