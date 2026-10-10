"""飞书 OAuth 登录（应用连接器 type=feishu 为唯一真源）。"""

from __future__ import annotations

import base64
import json
import re
import secrets
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import HTTPException, status
from loguru import logger

from core.services.integration.feishu_integration import get_feishu_credentials
from infra.infrastructure.http.client import get_http_client
from infra.models.user import User

FEISHU_AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
FEISHU_USERINFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"

_FEISHU_UNION_KEYS = ("feishu_union_id", "feishu_unionid")
_FEISHU_OPEN_KEYS = ("feishu_open_id", "feishu_openid")
_FEISHU_USER_KEYS = ("feishu_user_id", "feishu_userid")


def encode_feishu_oauth_state(
    *,
    tenant_id: int,
    redirect_uri: str,
    redirect: str | None = None,
) -> str:
    payload = {
        "t": tenant_id,
        "u": redirect_uri.strip(),
        "r": (redirect or "").strip(),
        "n": secrets.token_urlsafe(8),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_feishu_oauth_state(state: str) -> dict[str, Any]:
    if not state or not isinstance(state, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state 无效")
    padded = state + "=" * (-len(state) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state 无效") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state 无效")
    try:
        tenant_id_int = int(payload.get("t"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state 缺少组织") from exc
    redirect_uri = payload.get("u")
    if not isinstance(redirect_uri, str) or not redirect_uri.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state 缺少回调地址")
    redirect = payload.get("r")
    return {
        "tenant_id": tenant_id_int,
        "redirect_uri": redirect_uri.strip(),
        "redirect": redirect.strip() if isinstance(redirect, str) else "",
        "nonce": payload.get("n"),
    }


async def build_feishu_oauth_authorize_url(
    *,
    tenant_id: int,
    redirect_uri: str,
    state: str,
) -> str:
    creds = await get_feishu_credentials(tenant_id)
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未配置启用的飞书连接器，无法发起 OAuth",
        )
    query = urlencode(
        {
            "client_id": creds.app_id,
            "response_type": "code",
            "redirect_uri": redirect_uri.strip(),
            "state": state,
            "scope": "contact:user.base:readonly",
        },
        quote_via=quote,
    )
    return f"{FEISHU_AUTHORIZE_URL}?{query}"


async def exchange_feishu_code(*, tenant_id: int, code: str, redirect_uri: str) -> dict[str, Any]:
    if not code or not str(code).strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少 OAuth code")
    if not redirect_uri or not str(redirect_uri).strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少回调地址")
    creds = await get_feishu_credentials(tenant_id)
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未配置启用的飞书连接器，无法发起 OAuth",
        )
    resp = await get_http_client().post(
        FEISHU_TOKEN_URL,
        json={
            "grant_type": "authorization_code",
            "client_id": creds.app_id,
            "client_secret": creds.app_secret,
            "code": str(code).strip(),
            "redirect_uri": redirect_uri.strip(),
        },
        timeout=15.0,
    )
    try:
        data = resp.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="飞书授权换票失败",
        ) from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="飞书授权换票失败")
    if data.get("code") not in (0, None) and data.get("access_token") is None:
        err = data.get("error_description") or data.get("error") or data.get("msg")
        logger.warning("飞书 oauth token 失败 tenant={}: {}", tenant_id, data)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err) if err else "飞书授权换票失败",
        )
    access_token = data.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        err = data.get("error_description") or data.get("error") or data.get("msg")
        logger.warning("飞书 oauth token 无 access_token tenant={}: {}", tenant_id, data)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err) if err else "飞书授权换票失败",
        )
    return data


async def fetch_feishu_user(*, access_token: str) -> dict[str, Any]:
    resp = await get_http_client().get(
        FEISHU_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token.strip()}"},
        timeout=15.0,
    )
    try:
        data = resp.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="获取飞书用户信息失败",
        ) from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="获取飞书用户信息失败")
    if data.get("code") not in (0, None):
        err = data.get("msg") or data.get("message")
        logger.warning("飞书 user_info 失败: {}", data)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err) if err else "获取飞书用户信息失败",
        )
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="获取飞书用户信息失败")
    return payload


def _extract_contact_str(user: User, keys: tuple[str, ...]) -> str | None:
    contact = user.contact_info if isinstance(user.contact_info, dict) else {}
    for key in keys:
        value = contact.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_phone(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    digits = re.sub(r"\D", "", value.strip())
    if len(digits) < 7:
        return None
    return digits


def _normalize_email(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


async def find_user_by_feishu_ids(
    *,
    tenant_id: int,
    union_id: str | None,
    open_id: str | None,
    user_id: str | None,
) -> User | None:
    users = await User.filter(
        tenant_id=tenant_id,
        is_active=True,
        deleted_at__isnull=True,
    )
    union_norm = union_id.strip() if union_id else ""
    open_norm = open_id.strip() if open_id else ""
    user_norm = user_id.strip() if user_id else ""
    if union_norm:
        for user in users:
            bound = _extract_contact_str(user, _FEISHU_UNION_KEYS)
            if bound and bound == union_norm:
                return user
    if open_norm:
        for user in users:
            bound = _extract_contact_str(user, _FEISHU_OPEN_KEYS)
            if bound and bound == open_norm:
                return user
    if user_norm:
        for user in users:
            bound = _extract_contact_str(user, _FEISHU_USER_KEYS)
            if bound and bound == user_norm:
                return user
    return None


async def _list_active_tenant_users(tenant_id: int) -> list[User]:
    return await User.filter(
        tenant_id=tenant_id,
        is_active=True,
        deleted_at__isnull=True,
    )


def _dedupe_users(users: list[User]) -> list[User]:
    seen: set[int] = set()
    result: list[User] = []
    for user in users:
        if user.id in seen:
            continue
        seen.add(user.id)
        result.append(user)
    return result


async def find_users_by_phone(*, tenant_id: int, phone: str | None) -> list[User]:
    normalized = _normalize_phone(phone)
    if not normalized:
        return []
    matched: list[User] = []
    for user in await _list_active_tenant_users(tenant_id):
        if _normalize_phone(user.phone) == normalized:
            matched.append(user)
    return matched


async def find_users_by_email(*, tenant_id: int, email: str | None) -> list[User]:
    normalized = _normalize_email(email)
    if not normalized:
        return []
    matched: list[User] = []
    for user in await _list_active_tenant_users(tenant_id):
        if _normalize_email(user.email) == normalized:
            matched.append(user)
    return matched


async def bind_feishu_to_user(
    *,
    user: User,
    union_id: str | None = None,
    open_id: str | None = None,
    user_id: str | None = None,
    name: str | None = None,
) -> User:
    if not (union_id or open_id or user_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="飞书用户标识无效")
    contact = dict(user.contact_info) if isinstance(user.contact_info, dict) else {}
    if union_id and str(union_id).strip():
        contact["feishu_union_id"] = str(union_id).strip()
    if open_id and str(open_id).strip():
        contact["feishu_open_id"] = str(open_id).strip()
    if user_id and str(user_id).strip():
        contact["feishu_user_id"] = str(user_id).strip()
    if name and isinstance(name, str) and name.strip():
        contact["feishu_name"] = name.strip()
    user.contact_info = contact
    await user.save(update_fields=["contact_info", "updated_at"])
    return user


async def unbind_feishu_from_user(*, user: User) -> User:
    contact = dict(user.contact_info) if isinstance(user.contact_info, dict) else {}
    for key in (*_FEISHU_UNION_KEYS, *_FEISHU_OPEN_KEYS, *_FEISHU_USER_KEYS, "feishu_name"):
        contact.pop(key, None)
    user.contact_info = contact
    await user.save(update_fields=["contact_info", "updated_at"])
    return user


def _feishu_identity(feishu_user: dict[str, Any]) -> dict[str, str | None]:
    union_id = feishu_user.get("union_id") if isinstance(feishu_user.get("union_id"), str) else None
    open_id = feishu_user.get("open_id") if isinstance(feishu_user.get("open_id"), str) else None
    user_id = feishu_user.get("user_id") if isinstance(feishu_user.get("user_id"), str) else None
    mobile = feishu_user.get("mobile") if isinstance(feishu_user.get("mobile"), str) else None
    email = feishu_user.get("email") if isinstance(feishu_user.get("email"), str) else None
    if not email and isinstance(feishu_user.get("enterprise_email"), str):
        email = feishu_user.get("enterprise_email")
    name = feishu_user.get("name") if isinstance(feishu_user.get("name"), str) else None
    return {
        "union_id": union_id.strip() if union_id else None,
        "open_id": open_id.strip() if open_id else None,
        "user_id": user_id.strip() if user_id else None,
        "mobile": mobile,
        "email": email,
        "name": name,
    }


async def resolve_user_for_feishu_login(*, tenant_id: int, feishu_user: dict[str, Any]) -> User:
    identity = _feishu_identity(feishu_user)
    if not (identity["union_id"] or identity["open_id"] or identity["user_id"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未能获取飞书用户标识")

    bound = await find_user_by_feishu_ids(
        tenant_id=tenant_id,
        union_id=identity["union_id"],
        open_id=identity["open_id"],
        user_id=identity["user_id"],
    )
    if bound:
        return bound

    candidates = _dedupe_users(
        [
            *(await find_users_by_phone(tenant_id=tenant_id, phone=identity["mobile"])),
            *(await find_users_by_email(tenant_id=tenant_id, email=identity["email"])),
        ]
    )
    if len(candidates) == 1:
        return await bind_feishu_to_user(
            user=candidates[0],
            union_id=identity["union_id"],
            open_id=identity["open_id"],
            user_id=identity["user_id"],
            name=identity["name"],
        )
    if len(candidates) > 1:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="匹配到多个系统账号，请联系管理员处理后再使用飞书登录",
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            "未能自动绑定飞书账号，请确认系统用户手机号或邮箱与飞书一致，"
            "或在个人资料中扫码绑定"
        ),
    )


async def bind_feishu_for_current_user(
    *,
    tenant_id: int,
    user: User,
    feishu_user: dict[str, Any],
) -> User:
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="组织上下文不匹配")
    identity = _feishu_identity(feishu_user)
    if not (identity["union_id"] or identity["open_id"] or identity["user_id"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未能获取飞书用户标识")
    existing = await find_user_by_feishu_ids(
        tenant_id=tenant_id,
        union_id=identity["union_id"],
        open_id=identity["open_id"],
        user_id=identity["user_id"],
    )
    if existing and existing.id != user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该飞书账号已绑定其他用户",
        )
    return await bind_feishu_to_user(
        user=user,
        union_id=identity["union_id"],
        open_id=identity["open_id"],
        user_id=identity["user_id"],
        name=identity["name"],
    )


async def unbind_feishu_for_current_user(*, tenant_id: int, user: User) -> User:
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="组织上下文不匹配")
    if not (
        _extract_contact_str(user, _FEISHU_UNION_KEYS)
        or _extract_contact_str(user, _FEISHU_OPEN_KEYS)
        or _extract_contact_str(user, _FEISHU_USER_KEYS)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前账号未绑定飞书")
    return await unbind_feishu_from_user(user=user)


async def resolve_feishu_user_from_code(
    *,
    tenant_id: int,
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    token_data = await exchange_feishu_code(
        tenant_id=tenant_id, code=code, redirect_uri=redirect_uri
    )
    access_token = str(token_data["access_token"]).strip()
    return await fetch_feishu_user(access_token=access_token)
