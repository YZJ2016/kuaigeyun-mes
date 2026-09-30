"""快捷登录渠道开关（微信 / QQ / 企业微信 / 钉钉 / 飞书）。"""

from typing import Any, Mapping, Optional

LOGIN_QUICK_PROVIDER_IDS = (
    "wechat",
    "qq",
    "wechat_work",
    "dingtalk",
    "feishu",
)


def default_login_quick_providers() -> dict[str, bool]:
    return {provider_id: True for provider_id in LOGIN_QUICK_PROVIDER_IDS}


def normalize_login_quick_providers(raw: Any) -> dict[str, bool]:
    """合并缺省：未出现的渠道视为开启（与历史行为一致）。"""
    merged = default_login_quick_providers()
    if not isinstance(raw, Mapping):
        return merged
    for provider_id in LOGIN_QUICK_PROVIDER_IDS:
        if provider_id in raw and raw[provider_id] is not None:
            merged[provider_id] = bool(raw[provider_id])
    return merged


def merge_login_quick_providers(
    platform_raw: Any,
    site_raw: Optional[Any],
) -> dict[str, bool]:
    """租户未配置时使用平台级；租户有 dict 时以租户为准（整对象覆盖）。"""
    if site_raw is not None and isinstance(site_raw, Mapping) and len(site_raw) > 0:
        return normalize_login_quick_providers(site_raw)
    return normalize_login_quick_providers(platform_raw)


def is_login_quick_provider_enabled(
    providers: Any,
    provider_id: str,
) -> bool:
    normalized = normalize_login_quick_providers(providers)
    return normalized.get(provider_id, True)
