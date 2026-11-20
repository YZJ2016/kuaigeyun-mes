"""
用户 contact_info 上的第三方扫码登录绑定标志（列表展示用）。

与个人资料/OAuth 服务写入的键一致；不含手动填写的 dingtalk/feishu 联系方式文本。
"""

from __future__ import annotations

from typing import Any, Mapping


_WECOM_KEYS = ("wecom_userid", "wecom_user_id", "wx_work_userid")
_DINGTALK_KEYS = (
    "dingtalk_unionid",
    "ding_unionid",
    "dingtalk_openid",
    "ding_openid",
    "dingtalk_userid",
    "ding_userid",
)
_FEISHU_KEYS = (
    "feishu_union_id",
    "feishu_unionid",
    "feishu_open_id",
    "feishu_openid",
    "feishu_user_id",
    "feishu_userid",
)


def _has_any(contact: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    for key in keys:
        raw = contact.get(key)
        if raw is None:
            continue
        if str(raw).strip():
            return True
    return False


def resolve_oauth_binding_flags(contact_info: Any) -> dict[str, bool]:
    contact = contact_info if isinstance(contact_info, Mapping) else {}
    return {
        "wecom": _has_any(contact, _WECOM_KEYS),
        "dingtalk": _has_any(contact, _DINGTALK_KEYS),
        "feishu": _has_any(contact, _FEISHU_KEYS),
    }
