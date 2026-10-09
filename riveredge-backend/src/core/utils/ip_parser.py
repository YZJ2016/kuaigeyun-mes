"""
IP地址解析工具模块

提供IP地址地理位置解析、User-Agent解析等功能。
支持通过免费API获取IP地理位置信息，以及从User-Agent解析浏览器和设备信息。

Author: Luigi Lu
Date: 2025-01-11
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import time
from collections import Counter
from typing import Any, Dict, Optional, Tuple

from loguru import logger

from infra.infrastructure.http import get_http_client

# 成功解析结果进程内缓存（多 worker 各自一份；登录同 IP 高频命中）
_LOCATION_CACHE: Dict[str, Tuple[float, str]] = {}
_LOCATION_CACHE_TTL_SEC = 24 * 3600
_LOCATION_CACHE_MAX = 4096


def is_private_ip(ip: str) -> bool:
    """
    判断IP地址是否为内网 / 环回 / 链路本地等不可用于公网地理解析的地址。

    须用标准库 ``ipaddress``：公网 IPv6 常含 ``::`` 压缩，不可再按子串误判为内网。
    """
    if not ip:
        return False
    text = str(ip).strip()
    if not text:
        return False
    # 去掉方括号包装（偶见于代理头）
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    try:
        addr = ipaddress.ip_address(text.split("%", 1)[0])
    except ValueError:
        return False
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def parse_user_agent(user_agent: str) -> Dict[str, Optional[str]]:
    """
    从User-Agent字符串解析浏览器和设备信息

    Args:
        user_agent: User-Agent字符串

    Returns:
        Dict[str, Optional[str]]: 包含浏览器和设备信息的字典
            - browser: 浏览器名称和版本（如 "Chrome 120.0"）
            - device: 设备类型（PC、Mobile、Tablet等）
    """
    if not user_agent:
        return {
            "browser": None,
            "device": None,
        }

    browser = None
    device = None

    # 解析浏览器（按优先级顺序，更具体的浏览器优先）
    # ⚠️ 重要修复：Edge 必须在 Chrome 之前检测，因为 Edge 的 User-Agent 也包含 Chrome
    # Edge (Chromium-based) - User-Agent 格式: "Edg/版本号"
    edge_match = re.search(r"Edg[^/]*/(\d+\.\d+)", user_agent, re.IGNORECASE)
    if edge_match:
        browser = f"Edge {edge_match.group(1)}"

    # Opera (Chromium-based) - User-Agent 格式: "OPR/版本号"
    opera_match = re.search(r"OPR/(\d+\.\d+)", user_agent, re.IGNORECASE)
    if opera_match:
        browser = f"Opera {opera_match.group(1)}"

    # Chrome (必须在 Edge 和 Opera 之后检测，因为它们也包含 Chrome)
    chrome_match = re.search(r"Chrome/(\d+\.\d+)", user_agent, re.IGNORECASE)
    if chrome_match and "Edg" not in user_agent and "OPR" not in user_agent:
        browser = f"Chrome {chrome_match.group(1)}"

    # Firefox
    firefox_match = re.search(r"Firefox/(\d+\.\d+)", user_agent, re.IGNORECASE)
    if firefox_match:
        browser = f"Firefox {firefox_match.group(1)}"

    # Safari (必须在 Chrome 之后检测，因为 Safari 的 User-Agent 也可能包含 Chrome)
    safari_match = re.search(r"Version/(\d+\.\d+).*Safari", user_agent, re.IGNORECASE)
    if safari_match and "Chrome" not in user_agent:
        browser = f"Safari {safari_match.group(1)}"

    # 如果没有匹配到，尝试提取更具体的浏览器标识
    if not browser:
        browser_patterns = [
            (r"MSIE (\d+\.\d+)", "Internet Explorer"),
            (r"Trident/.*rv:(\d+\.\d+)", "Internet Explorer"),
            (r"YaBrowser/(\d+\.\d+)", "Yandex Browser"),
            (r"Vivaldi/(\d+\.\d+)", "Vivaldi"),
            (r"Brave/(\d+\.\d+)", "Brave"),
        ]

        for pattern, name in browser_patterns:
            match = re.search(pattern, user_agent, re.IGNORECASE)
            if match:
                browser = f"{name} {match.group(1)}"
                break

        if not browser:
            browser_match = re.search(r"([A-Za-z]+)/(\d+\.\d+)", user_agent)
            if browser_match:
                browser = f"{browser_match.group(1)} {browser_match.group(2)}"

    user_agent_lower = user_agent.lower()

    if any(keyword in user_agent_lower for keyword in ["mobile", "android", "iphone", "ipod"]):
        device = "Mobile"
    elif any(keyword in user_agent_lower for keyword in ["tablet", "ipad"]):
        device = "Tablet"
    else:
        device = "PC"

    return {
        "browser": browser,
        "device": device,
    }


async def get_public_ip() -> Optional[str]:
    """
    获取本机的公网IP地址

    通过第三方API获取本机的外网IP地址。
    如果API调用失败，返回None。

    Returns:
        Optional[str]: 公网IP地址，失败时返回None
    """
    try:
        api_services = [
            "https://api.ipify.org?format=json",
            "https://api64.ipify.org?format=json",
            "https://ifconfig.me/ip",
        ]

        client = get_http_client()
        for api_url in api_services:
            try:
                response = await client.get(api_url, timeout=3.0)
                if response.status_code != 200:
                    continue
                if "ipify" in api_url:
                    data = response.json()
                    ip = data.get("ip")
                    if ip:
                        return ip.strip()
                else:
                    ip = response.text.strip()
                    if ip:
                        return ip
            except Exception:
                continue

        return None
    except Exception as e:
        logger.debug(f"获取公网IP失败: {e}")
        return None


async def _fetch_public_ip(timeout: float = 3.0) -> Optional[str]:
    """
    获取本机公网 IP（当客户端为内网 IP 时使用）
    依次尝试 ipify、icanhazip
    """
    urls = [
        "https://api.ipify.org?format=json",
        "https://icanhazip.com",
    ]
    client = get_http_client()
    for url in urls:
        try:
            r = await client.get(url, timeout=timeout)
            if r.status_code == 200:
                text = r.text.strip()
                if "ipify" in url:
                    data = r.json()
                    return data.get("ip")
                return text if text and len(text) < 50 else None
        except Exception:
            continue
    return None


def _parse_location_from_provider(
    data: dict,
    *,
    city_key: str = "city",
    region_key: str = "region",
    country_key: str = "country",
    lat_key: str = "lat",
    lon_key: str = "lon",
    loc_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """从各提供商返回中解析统一格式"""
    city = (data.get(city_key) or "").strip()
    region = (data.get(region_key) or "").strip()
    country = (data.get(country_key) or "").strip()
    lat, lon = None, None
    if loc_key:
        loc = (data.get(loc_key) or "").strip()
        if loc and "," in loc:
            parts = loc.split(",", 1)
            try:
                lat, lon = float(parts[0].strip()), float(parts[1].strip())
            except (ValueError, IndexError):
                pass
    else:
        lat_val, lon_val = data.get(lat_key), data.get(lon_key)
        if lat_val is not None:
            lat = float(lat_val) if not isinstance(lat_val, (int, float)) else lat_val
        if lon_val is not None:
            lon = float(lon_val) if not isinstance(lon_val, (int, float)) else lon_val
    if city or region or country:
        return {"city": city, "region": region, "country": country, "lat": lat, "lon": lon}
    return None


# 投票用行政区归一（英/中/带后缀 → 同一 token）；未收录的保留去后缀原文
_ADMIN_SUFFIXES = (
    "特别行政区",
    "壮族自治区",
    "回族自治区",
    "维吾尔自治区",
    "自治区",
    "自治州",
    "地区",
    "省",
    "市",
    "县",
    "盟",
    "州",
)
_REGION_VOTE_ALIASES = {
    "anhui": "安徽",
    "guangdong": "广东",
    "beijing": "北京",
    "shanghai": "上海",
    "jiangsu": "江苏",
    "zhejiang": "浙江",
    "shandong": "山东",
    "henan": "河南",
    "hebei": "河北",
    "hubei": "湖北",
    "hunan": "湖南",
    "fujian": "福建",
    "jiangxi": "江西",
    "sichuan": "四川",
    "chongqing": "重庆",
    "tianjin": "天津",
    "liaoning": "辽宁",
    "jilin": "吉林",
    "heilongjiang": "黑龙江",
    "shanxi": "山西",
    "shaanxi": "陕西",
    "gansu": "甘肃",
    "qinghai": "青海",
    "yunnan": "云南",
    "guizhou": "贵州",
    "hainan": "海南",
    "taiwan": "台湾",
    "neimenggu": "内蒙古",
    "inner mongolia": "内蒙古",
    "guangxi": "广西",
    "ningxia": "宁夏",
    "xinjiang": "新疆",
    "xizang": "西藏",
    "tibet": "西藏",
    "hong kong": "香港",
    "macao": "澳门",
    "macau": "澳门",
}
_CITY_VOTE_ALIASES = {
    "wuhu": "芜湖",
    "guangzhou": "广州",
    "hefei": "合肥",
    "beijing": "北京",
    "shanghai": "上海",
    "nanjing": "南京",
    "hangzhou": "杭州",
    "suzhou": "苏州",
    "wuxi": "无锡",
    "shenzhen": "深圳",
    "dongguan": "东莞",
    "foshan": "佛山",
    "chengdu": "成都",
    "chongqing": "重庆",
    "wuhan": "武汉",
    "xian": "西安",
    "xi'an": "西安",
    "tianjin": "天津",
    "qingdao": "青岛",
    "dalian": "大连",
    "xiamen": "厦门",
    "ningbo": "宁波",
    "zhengzhou": "郑州",
    "changsha": "长沙",
    "jinan": "济南",
    "fuzhou": "福州",
    "nanchang": "南昌",
    "kunming": "昆明",
    "guiyang": "贵阳",
    "nanning": "南宁",
    "haikou": "海口",
    "taoyuan": "桃园",
    "taipei": "台北",
}


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in (text or ""))


def _strip_admin_suffix(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    for suf in _ADMIN_SUFFIXES:
        if not s.endswith(suf) or len(s) <= len(suf):
            continue
        # 「州」是广州/杭州等市名用字，不是单字后缀；仅对三字及以上（如凉山州）去尾字
        if suf == "州" and len(s) <= 2:
            continue
        return s[: -len(suf)].strip()
    return s


def _admin_vote_token(text: str, *, aliases: Dict[str, str]) -> str:
    raw = _strip_admin_suffix(text)
    if not raw:
        return ""
    low = raw.lower()
    if low in aliases:
        return aliases[low]
    if raw in aliases.values():
        return raw
    return raw


def _country_vote_token(country: str) -> str:
    c = (country or "").strip()
    if not c:
        return ""
    low = c.lower()
    if low in {"cn", "chn", "china"} or c == "中国":
        return "中国"
    if low in {"tw", "twn", "taiwan"} or c in {"台湾", "台灣"}:
        return "中国"
    return c


def _localize_admin_label(text: str, *, aliases: Dict[str, str]) -> str:
    """展示用：英文行政区尽量落到中文常用名。"""
    token = _admin_vote_token(text, aliases=aliases)
    return token or (text or "").strip()


def vote_ip_location_details(candidates: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    多源地理解析投票：先省/州，再城市；坐标取胜出集合中位数。

    仅统计同时具备经纬度的候选；无城市名的源不参与城市票，避免空票干扰。
    """
    usable: list[Dict[str, Any]] = []
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        lat, lon = raw.get("lat"), raw.get("lon")
        if lat is None or lon is None:
            continue
        try:
            lat_f, lon_f = float(lat), float(lon)
        except (TypeError, ValueError):
            continue
        country = _country_vote_token(str(raw.get("country") or ""))
        region_token = _admin_vote_token(str(raw.get("region") or ""), aliases=_REGION_VOTE_ALIASES)
        city_token = _admin_vote_token(str(raw.get("city") or ""), aliases=_CITY_VOTE_ALIASES)
        usable.append(
            {
                "city": str(raw.get("city") or "").strip(),
                "region": str(raw.get("region") or "").strip(),
                "country": country or str(raw.get("country") or "").strip(),
                "lat": lat_f,
                "lon": lon_f,
                "region_token": region_token,
                "city_token": city_token,
            }
        )
    if not usable:
        return None
    if len(usable) == 1:
        only = usable[0]
        return {
            "city": only["city_token"]
            or _localize_admin_label(only["city"], aliases=_CITY_VOTE_ALIASES)
            or only["city"],
            "region": only["region_token"]
            or _localize_admin_label(only["region"], aliases=_REGION_VOTE_ALIASES)
            or only["region"],
            "country": only["country"],
            "lat": only["lat"],
            "lon": only["lon"],
        }

    region_counts = Counter(u["region_token"] for u in usable if u["region_token"])
    if not region_counts:
        # 无省名时退化为城市票
        city_counts = Counter(u["city_token"] for u in usable if u["city_token"])
        if not city_counts:
            lats = sorted(u["lat"] for u in usable)
            lons = sorted(u["lon"] for u in usable)
            mid = len(usable) // 2
            return {
                "city": "",
                "region": "",
                "country": usable[0]["country"],
                "lat": lats[mid],
                "lon": lons[mid],
            }
        win_city = max(city_counts.items(), key=lambda x: (x[1], len(x[0])))[0]
        winners = [u for u in usable if u["city_token"] == win_city]
    else:
        win_region = max(region_counts.items(), key=lambda x: (x[1], len(x[0])))[0]
        in_region = [u for u in usable if u["region_token"] == win_region]
        city_counts = Counter(u["city_token"] for u in in_region if u["city_token"])
        if city_counts:
            win_city = max(city_counts.items(), key=lambda x: (x[1], len(x[0])))[0]
            winners = [u for u in in_region if u["city_token"] == win_city]
        else:
            winners = in_region

    lats = sorted(u["lat"] for u in winners)
    lons = sorted(u["lon"] for u in winners)
    mid = len(winners) // 2
    # 展示：胜出集合内优先带汉字的原文，再落到投票 token / 别名中文
    best = max(
        winners,
        key=lambda u: (
            1 if _has_cjk(u["city"]) else 0,
            1 if _has_cjk(u["region"]) else 0,
            _login_location_quality(
                format_location_label(country=u["country"], region=u["region"], city=u["city"]) or ""
            ),
            1 if u["city_token"] else 0,
        ),
    )
    if _has_cjk(best["city"]):
        city = _strip_admin_suffix(best["city"]) or best["city"]
    else:
        city = best["city_token"] or _localize_admin_label(best["city"], aliases=_CITY_VOTE_ALIASES) or best["city"]
    if _has_cjk(best["region"]):
        region = _strip_admin_suffix(best["region"]) or best["region"]
    else:
        region = (
            best["region_token"]
            or _localize_admin_label(best["region"], aliases=_REGION_VOTE_ALIASES)
            or best["region"]
        )
    country = best["country"] or "中国"
    if not _has_cjk(country):
        country = _country_vote_token(country) or country
    return {
        "city": city,
        "region": region,
        "country": country,
        "lat": lats[mid],
        "lon": lons[mid],
    }


# 第三方 IP 库常把台湾标成独立国家/地区；登录地点须统一写成「中国 …」
_TAIWAN_IN_LOCATION = re.compile(r"(台湾|台灣|Taiwan)", re.IGNORECASE)


def _zhou_two_char_city_repair_by_first_char() -> Dict[str, str]:
    """历史 bug：两字「*州」市名误去尾「州」后只剩首字；回填时按首字还原市名。"""
    repair: Dict[str, str] = {}
    ambiguous: set[str] = set()
    for city in {c for c in _CITY_VOTE_ALIASES.values() if len(c) == 2 and c.endswith("州")}:
        key = city[0]
        if key in repair:
            ambiguous.add(key)
        else:
            repair[key] = city
    for key in ambiguous:
        repair.pop(key, None)
    return repair


_ZHOU_CITY_REPAIR_BY_FIRST_CHAR = _zhou_two_char_city_repair_by_first_char()


def repair_truncated_zhou_city_login_location(label: Optional[str]) -> Optional[str]:
    """
    修复 login_location 中因误剥「州」导致的单字市名（如「中国 广东 广」→「中国 广东 广州」）。
    无法唯一还原时保持原文。
    """
    if label is None:
        return None
    normalized = normalize_login_location_label(str(label).strip())
    if not normalized:
        return normalized
    parts = normalized.split()
    if len(parts) < 3:
        return normalized
    city_fragment = parts[-1]
    if len(city_fragment) != 1 or not _has_cjk(city_fragment):
        return normalized
    repair_city = _ZHOU_CITY_REPAIR_BY_FIRST_CHAR.get(city_fragment)
    if not repair_city:
        return normalized
    parts[-1] = repair_city
    return normalize_login_location_label(" ".join(parts))


def normalize_login_location_label(label: Optional[str]) -> Optional[str]:
    """登录地点人为规范：涉及台湾且未冠「中国」时，在前补「中国」。"""
    if label is None:
        return None
    text = " ".join(str(label).split())
    if not text:
        return None
    if not _TAIWAN_IN_LOCATION.search(text):
        return text
    if text.startswith("中国"):
        return text
    if text[:5].lower() == "china" and (len(text) == 5 or text[5].isspace()):
        rest = text[5:].lstrip()
        return f"中国 {rest}" if rest else "中国"
    return f"中国 {text}"


_SKIP_ADMIN_LABELS = frozenset({"市辖区", "县"})


def format_manual_user_location_label(labels: Optional[Any]) -> Optional[str]:
    """将站点「用户位置」手工行政区标签格式化为登录地点文案。"""
    if not isinstance(labels, (list, tuple)) or not labels:
        return None
    parts = [
        str(x).strip()
        for x in labels
        if x is not None and str(x).strip() and str(x).strip() not in _SKIP_ADMIN_LABELS
    ]
    if not parts:
        parts = [str(x).strip() for x in labels if x is not None and str(x).strip()]
    if not parts:
        return None
    text = " ".join(parts)
    if not text.startswith("中国") and not (
        text[:5].lower() == "china" and (len(text) == 5 or text[5].isspace())
    ):
        text = f"中国 {text}"
    return normalize_login_location_label(text)


async def resolve_login_location_for_tenant(
    tenant_id: Optional[int],
    ip_location: Optional[str],
) -> Optional[str]:
    """登录地点：站点手工用户位置优先，否则用 IP 解析结果。"""
    if tenant_id:
        try:
            from core.services.system.site_setting_service import SiteSettingService

            site = await SiteSettingService.get_settings(int(tenant_id))
            raw = (site.settings or {}).get("user_location") if site else None
            if isinstance(raw, dict) and raw.get("mode") == "manual":
                manual = format_manual_user_location_label(raw.get("region_labels"))
                if manual:
                    return manual
        except Exception as e:
            logger.debug(f"读取站点用户位置失败 tenant_id={tenant_id}: {e}")
    return normalize_login_location_label(ip_location)


def format_location_label(
    country: Optional[str] = None,
    region: Optional[str] = None,
    city: Optional[str] = None,
) -> Optional[str]:
    """登录日志地点展示：空格拼接（与 ip-api zh-CN 一致），禁止横杠造数格式。"""
    c = (country or "").strip()
    r = (region or "").strip()
    city_s = (city or "").strip()
    parts: list[str] = []
    if c:
        parts.append(c)
    if r and r != city_s and r != c:
        parts.append(r)
    if city_s and city_s != c:
        parts.append(city_s)
    return normalize_login_location_label(" ".join(parts) if parts else None)


def _format_location_from_detail(detail: Dict[str, Any]) -> Optional[str]:
    return format_location_label(
        country=detail.get("country"),
        region=detail.get("region"),
        city=detail.get("city"),
    )


def _cache_get_location(ip: str) -> Optional[str]:
    entry = _LOCATION_CACHE.get(ip)
    if not entry:
        return None
    expires_at, label = entry
    if expires_at < time.monotonic():
        _LOCATION_CACHE.pop(ip, None)
        return None
    return label


def _cache_set_location(ip: str, label: str) -> None:
    if len(_LOCATION_CACHE) >= _LOCATION_CACHE_MAX:
        now = time.monotonic()
        expired = [k for k, (exp, _) in _LOCATION_CACHE.items() if exp < now]
        for k in expired:
            _LOCATION_CACHE.pop(k, None)
        if len(_LOCATION_CACHE) >= _LOCATION_CACHE_MAX:
            for k in list(_LOCATION_CACHE.keys())[: _LOCATION_CACHE_MAX // 2]:
                _LOCATION_CACHE.pop(k, None)
    _LOCATION_CACHE[ip] = (time.monotonic() + _LOCATION_CACHE_TTL_SEC, label)


def _login_location_quality(label: str) -> int:
    """地点文案质量分：中文「中国」优先，避免同 IP 粘到英文混标。"""
    text = (label or "").strip()
    if not text or text.startswith("中国-"):
        return -1
    if text.startswith("中国"):
        return 3
    lower = text.lower()
    if lower.startswith("china") and (len(text) == 5 or text[5].isspace()):
        return 1
    if text.startswith("CN ") or text.startswith("CN-"):
        return 1
    return 0


def pick_canonical_login_location(labels: list[str] | tuple[str, ...] | None) -> Optional[str]:
    """
    同 IP 多条文案时选规范地点：优先「中国 …」，再按出现次数，避免中英混标。
    """
    counts: Counter[str] = Counter()
    for raw in labels or ():
        text = normalize_login_location_label(str(raw).strip() if raw is not None else "")
        if not text or _login_location_quality(text) < 0:
            continue
        counts[text] += 1
    if not counts:
        return None
    return max(
        counts.items(),
        key=lambda item: (_login_location_quality(item[0]), item[1], len(item[0])),
    )[0]


async def _lookup_geo_from_login_logs(
    ip: str,
    *,
    tenant_id: int | None = None,
) -> tuple[Optional[float], Optional[float]]:
    """同 IP 首次已写入的经纬度（避免重复外网解析）。"""
    try:
        from core.models.login_log import LoginLog

        query = LoginLog.filter(login_ip=ip).exclude(login_latitude__isnull=True).exclude(
            login_longitude__isnull=True
        )
        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)
        # 首次落库为准（created_at 升序）
        row = await query.order_by("created_at").only("login_latitude", "login_longitude").first()
        if row and row.login_latitude is not None and row.login_longitude is not None:
            return float(row.login_latitude), float(row.login_longitude)
    except Exception as e:
        # spec 143：无组织上下文时此处会抛 TenantContextError，geo 回查被跳过——
        # 必须 warning 级留痕，不能静默吞掉
        logger.warning(f"从登录日志回查坐标失败: {ip}, {e}")
    return None, None


async def _lookup_paired_geo_location_from_login_logs(
    ip: str,
    *,
    tenant_id: int | None = None,
) -> tuple[Optional[str], Optional[float], Optional[float]]:
    """
    同 IP 首次成对落库的地点与坐标（写路径真源）。

    契约：新 IP 仅首次多源投票；第二次及以后登录直接复用本结果，不再重投、不取最新行。
    """
    try:
        from core.models.login_log import LoginLog

        query = (
            LoginLog.filter(login_ip=ip)
            .exclude(login_latitude__isnull=True)
            .exclude(login_longitude__isnull=True)
            .exclude(login_location=None)
            .exclude(login_location="")
        )
        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)
        row = (
            await query.order_by("created_at")
            .only("login_location", "login_latitude", "login_longitude")
            .first()
        )
        if not row or row.login_latitude is None or row.login_longitude is None:
            return None, None, None
        label = str(row.login_location or "").strip()
        if not label or label.startswith("中国-"):
            return None, float(row.login_latitude), float(row.login_longitude)
        return (
            normalize_login_location_label(label),
            float(row.login_latitude),
            float(row.login_longitude),
        )
    except Exception as e:
        # spec 143：无组织上下文时此处会抛 TenantContextError，geo 回查被跳过——
        # 必须 warning 级留痕，不能静默吞掉
        logger.warning(f"从登录日志成对回查地理信息失败: {ip}, {e}")
    return None, None, None


async def _lookup_location_from_login_logs(ip: str) -> Optional[str]:
    """同 IP 首次成功解析过的地点（填补 API 瞬时失败，不造假）。"""
    try:
        from core.models.login_log import LoginLog

        row = (
            await LoginLog.filter(login_ip=ip)
            .exclude(login_location=None)
            .exclude(login_location="")
            .order_by("created_at")
            .only("login_location")
            .first()
        )
        if row and row.login_location:
            label = str(row.login_location).strip()
            # 拒绝历史虚拟横杠格式
            if label and not label.startswith("中国-"):
                return normalize_login_location_label(label)
    except Exception as e:
        # spec 143：无组织上下文时此处会抛 TenantContextError，geo 回查被跳过——
        # 必须 warning 级留痕，不能静默吞掉
        logger.warning(f"从登录日志回查地点失败: {ip}, {e}")
    return None


async def _fetch_ip_location_candidates(
    resolve_ip: str,
    *,
    timeout: float = 3.0,
) -> list[Dict[str, Any]]:
    """并行拉取各免费地理源；失败源跳过，不做串行首个命中。"""
    headers = {"User-Agent": "RiverEdge/1.0"}
    client = get_http_client()

    async def _ip_api() -> Optional[Dict[str, Any]]:
        try:
            r = await client.get(
                f"http://ip-api.com/json/{resolve_ip}?lang=zh-CN&fields=status,country,regionName,city,lat,lon,message",
                timeout=timeout,
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if data.get("status") != "success":
                if data.get("message"):
                    logger.debug(f"ip-api.com 未成功: ip={resolve_ip}, message={data.get('message')}")
                return None
            return _parse_location_from_provider(data, region_key="regionName")
        except Exception as e:
            logger.debug(f"ip-api.com 请求失败: ip={resolve_ip}, {e}")
            return None

    async def _ipapi_co() -> Optional[Dict[str, Any]]:
        try:
            r = await client.get(
                f"https://ipapi.co/{resolve_ip}/json/",
                headers=headers,
                timeout=timeout,
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if data.get("error"):
                return None
            return _parse_location_from_provider(
                data,
                country_key="country_name",
                lat_key="latitude",
                lon_key="longitude",
            )
        except Exception as e:
            logger.debug(f"ipapi.co 请求失败: ip={resolve_ip}, {e}")
            return None

    async def _ipinfo() -> Optional[Dict[str, Any]]:
        try:
            r = await client.get(
                f"https://ipinfo.io/{resolve_ip}/json",
                headers=headers,
                timeout=timeout,
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if data.get("bogon"):
                return None
            return _parse_location_from_provider(data, loc_key="loc")
        except Exception as e:
            logger.debug(f"ipinfo.io 请求失败: ip={resolve_ip}, {e}")
            return None

    async def _ipwho() -> Optional[Dict[str, Any]]:
        try:
            r = await client.get(
                f"https://ipwho.is/{resolve_ip}",
                headers=headers,
                timeout=timeout,
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if not data.get("success"):
                return None
            result = _parse_location_from_provider(
                data,
                lat_key="latitude",
                lon_key="longitude",
            )
            if result and result.get("lat") is not None and result.get("lon") is not None:
                return result
        except Exception as e:
            logger.debug(f"ipwho.is 请求失败: ip={resolve_ip}, {e}")
        return None

    async def _ip_sb() -> Optional[Dict[str, Any]]:
        try:
            r = await client.get(
                f"https://api.ip.sb/geoip/{resolve_ip}",
                headers=headers,
                timeout=timeout,
            )
            if r.status_code != 200:
                return None
            result = _parse_location_from_provider(
                r.json(),
                lat_key="latitude",
                lon_key="longitude",
            )
            if result and result.get("lat") is not None and result.get("lon") is not None:
                return result
        except Exception as e:
            logger.debug(f"ip.sb 请求失败: ip={resolve_ip}, {e}")
        return None

    async def _geojs() -> Optional[Dict[str, Any]]:
        try:
            r = await client.get(
                f"https://get.geojs.io/v1/ip/geo/{resolve_ip}.json",
                headers=headers,
                timeout=timeout,
            )
            if r.status_code != 200:
                return None
            result = _parse_location_from_provider(
                r.json(),
                lat_key="latitude",
                lon_key="longitude",
            )
            if result and result.get("lat") is not None and result.get("lon") is not None:
                return result
        except Exception as e:
            logger.debug(f"geojs.io 请求失败: ip={resolve_ip}, {e}")
        return None

    async def _freeipapi() -> Optional[Dict[str, Any]]:
        try:
            r = await client.get(
                f"https://www.freeipapi.com/api/json/{resolve_ip}",
                headers=headers,
                timeout=timeout,
                follow_redirects=True,
            )
            if r.status_code != 200:
                return None
            result = _parse_location_from_provider(
                r.json(),
                city_key="cityName",
                region_key="regionName",
                country_key="countryName",
                lat_key="latitude",
                lon_key="longitude",
            )
            if result and result.get("lat") is not None and result.get("lon") is not None:
                return result
        except Exception as e:
            logger.debug(f"freeipapi.com 请求失败: ip={resolve_ip}, {e}")
        return None

    results = await asyncio.gather(
        _ip_api(),
        _ipapi_co(),
        _ipinfo(),
        _ipwho(),
        _ip_sb(),
        _geojs(),
        _freeipapi(),
    )
    return [item for item in results if item]


def merge_location_detail_with_zh_admin(
    detail: Dict[str, Any],
    admin: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    """
    将投票得到的坐标结果与中文行政区合并：坐标以投票为准，文案优先中文逆地理。
    """
    out = {
        "city": str(detail.get("city") or "").strip(),
        "region": str(detail.get("region") or "").strip(),
        "country": str(detail.get("country") or "").strip(),
        "lat": detail.get("lat"),
        "lon": detail.get("lon"),
    }
    if admin:
        if admin.get("country"):
            out["country"] = admin["country"]
        if admin.get("region"):
            out["region"] = admin["region"]
        if admin.get("city"):
            out["city"] = admin["city"]
    # 逆地理失败或字段不全时：别名表中文化（不另造地名）
    out["country"] = _country_vote_token(out["country"]) or out["country"]
    if out["region"] and not _has_cjk(out["region"]):
        out["region"] = _localize_admin_label(out["region"], aliases=_REGION_VOTE_ALIASES) or out["region"]
    if out["city"] and not _has_cjk(out["city"]):
        out["city"] = _localize_admin_label(out["city"], aliases=_CITY_VOTE_ALIASES) or out["city"]
    if out["region"]:
        out["region"] = _strip_admin_suffix(out["region"]) or out["region"]
    if out["city"]:
        out["city"] = _strip_admin_suffix(out["city"]) or out["city"]
    return out


async def reverse_geocode_admin(
    lat: float,
    lon: float,
    *,
    language: str = "zh",
    timeout: float = 3.0,
) -> Optional[Dict[str, str]]:
    """
    按经纬度反查行政区（国家/省/市），供登录地点写成中文地址。

    使用 Nominatim；仅应在新 IP 首次投票后调用（粘性复用不再请求）。
    """
    accept_lang = "zh-CN,zh" if str(language).lower().startswith("zh") else "en"
    headers = {"User-Agent": "RiverEdge/1.0 (login-geo; https://riveredge.local)"}
    try:
        r = await get_http_client().get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": lat,
                "lon": lon,
                "format": "json",
                "accept-language": accept_lang,
                "zoom": 10,
                "addressdetails": 1,
            },
            headers=headers,
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        address = data.get("address") or {}
        if not isinstance(address, dict):
            return None

        country = str(address.get("country") or "").strip()
        region = str(
            address.get("state")
            or address.get("province")
            or address.get("region")
            or ""
        ).strip()
        city = ""
        for key in (
            "city",
            "town",
            "municipality",
            "county",
            "city_district",
            "suburb",
            "village",
        ):
            val = str(address.get(key) or "").strip()
            if val:
                city = val
                break
        if not (country or region or city):
            return None
        country = _country_vote_token(country) or country
        if region:
            region = _strip_admin_suffix(region) or region
        if city:
            city = _strip_admin_suffix(city) or city
        return {"country": country, "region": region, "city": city}
    except Exception as e:
        logger.debug(f"逆地理行政区失败: lat={lat}, lon={lon}, 错误: {e}")
    return None


async def localize_voted_location_to_zh(
    detail: Dict[str, Any],
    *,
    timeout: float = 2.0,
) -> Dict[str, Any]:
    """
    投票结果 → 中文地址：坐标以投票为准。

    1) 别名表把英/代码行政区转为中文（离线、稳定）
    2) 若市/省仍无汉字，再短超时逆地理补全（国内 Nominatim 常不可达，失败不阻塞）
    """
    aliased = merge_location_detail_with_zh_admin(detail, None)
    city = str(aliased.get("city") or "")
    region = str(aliased.get("region") or "")
    country = str(aliased.get("country") or "")
    if _has_cjk(city) and _has_cjk(region) and _has_cjk(country):
        return aliased

    lat, lon = aliased.get("lat"), aliased.get("lon")
    if lat is None or lon is None:
        return aliased
    try:
        admin = await reverse_geocode_admin(float(lat), float(lon), language="zh", timeout=timeout)
    except (TypeError, ValueError):
        return aliased
    if not admin:
        return aliased
    return merge_location_detail_with_zh_admin(detail, admin)


async def get_ip_location_detail(ip: str, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
    """
    获取IP地址的详细地理位置信息（含经纬度，供前端天气组件 / 登录日志使用）

    当客户端 IP 为内网时，先获取本机公网 IP 再解析位置。
    并行多源按「省 → 市」投票定坐标，再逆地理转为中文地址落库。

    Args:
        ip: IP地址字符串
        timeout: 单源请求超时时间（秒）

    Returns:
        Optional[Dict]: {"city","region","country","lat","lon"} 或 None
    """
    resolve_ip = ip
    if not ip or is_private_ip(ip):
        public = await _fetch_public_ip(timeout)
        if not public:
            return None
        resolve_ip = public

    candidates = await _fetch_ip_location_candidates(resolve_ip, timeout=timeout)
    if not candidates:
        return None
    voted = vote_ip_location_details(candidates)
    if not voted:
        return None
    localized = await localize_voted_location_to_zh(voted, timeout=timeout)
    logger.debug(
        f"IP 多源投票+中文地址: ip={resolve_ip}, sources={len(candidates)}, "
        f"city={localized.get('city')}, region={localized.get('region')}, "
        f"country={localized.get('country')}"
    )
    return localized


async def reverse_geocode_label(
    lat: float,
    lon: float,
    language: str = "zh",
    timeout: float = 3.0,
) -> Optional[str]:
    """
    按经纬度反查地名（供天气组件按界面语言显示城市名）。

    使用 Nominatim（OpenStreetMap）；须在后端调用以满足其 Usage Policy 与避免浏览器 CORS。
    Open-Meteo Geocoding API 仅提供 /v1/search，无 reverse 端点。
    """
    admin = await reverse_geocode_admin(lat, lon, language=language, timeout=timeout)
    if not admin:
        return None
    for key in ("city", "region", "country"):
        val = (admin.get(key) or "").strip()
        if val:
            return val
    return None


async def get_ip_location(ip: str, timeout: float = 2.5) -> Optional[str]:
    """
    获取IP地址的地理位置文案（登录日志用）。

    路径：进程缓存 → 同 IP 首次成对地点 → 多源投票（仅新 IP）→ 仅地点的首次回查。
    失败返回 None，不阻塞登录。
    """
    if not ip or is_private_ip(ip):
        return None

    cached = _cache_get_location(ip)
    if cached:
        return normalize_login_location_label(cached)

    sticky_loc, _, _ = await _lookup_paired_geo_location_from_login_logs(ip)
    if sticky_loc:
        _cache_set_location(ip, sticky_loc)
        return sticky_loc

    detail = await get_ip_location_detail(ip, timeout=timeout)
    if detail:
        label = _format_location_from_detail(detail)
        if label:
            _cache_set_location(ip, label)
            return label

    from_log = await _lookup_location_from_login_logs(ip)
    if from_log:
        _cache_set_location(ip, from_log)
        return from_log

    return None


async def parse_ip_info(ip: str, user_agent: str = "") -> Dict[str, Any]:
    """
    解析IP地址和User-Agent的完整信息

    Args:
        ip: IP地址字符串
        user_agent: User-Agent字符串（可选）

    Returns:
        Dict: location / latitude / longitude / browser / device
    """
    ua_info = parse_user_agent(user_agent)
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    if ip and not is_private_ip(ip):
        # 首次投票落库后，第二次及以后登录只复用首次成对结果，不再重投
        sticky_loc, sticky_lat, sticky_lon = await _lookup_paired_geo_location_from_login_logs(ip)
        if sticky_lat is not None and sticky_lon is not None and sticky_loc:
            location = sticky_loc
            latitude = sticky_lat
            longitude = sticky_lon
            _cache_set_location(ip, sticky_loc)
        else:
            detail = await get_ip_location_detail(ip, timeout=2.5)
            if detail:
                label = _format_location_from_detail(detail)
                if label:
                    location = normalize_login_location_label(label)
                    _cache_set_location(ip, label)
                lat_val = detail.get("lat")
                lon_val = detail.get("lon")
                if lat_val is not None and lon_val is not None:
                    latitude = float(lat_val)
                    longitude = float(lon_val)
            elif sticky_lat is not None and sticky_lon is not None:
                # 仅有历史坐标、尚无文案时保留坐标，不混源拼地点
                latitude = sticky_lat
                longitude = sticky_lon
                if sticky_loc:
                    location = sticky_loc
                    _cache_set_location(ip, sticky_loc)

    return {
        "location": location,
        "latitude": latitude,
        "longitude": longitude,
        "browser": ua_info.get("browser"),
        "device": ua_info.get("device"),
    }
