"""钉钉 OAuth 登录（应用连接器 type=dingtalk 为唯一真源）。"""

from __future__ import annotations

import base64
import json
import re
import secrets
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import HTTPException, status
from loguru import logger

from core.services.integration.dingtalk_integration import get_dingtalk_credentials
from infra.infrastructure.http.client import get_http_client
from infra.models.user import User

DINGTALK_AUTHORIZE_URL = "https://login.dingtalk.com/oauth2/auth"
DINGTALK_USER_TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/userAccessToken"
DINGTALK_USER_ME_URL = "https://api.dingtalk.com/v1.0/contact/users/me"

_DINGTALK_UNIONID_KEYS = ("dingtalk_unionid", "ding_unionid")
_DINGTALK_OPENID_KEYS = ("dingtalk_openid", "ding_openid")
_DINGTALK_USERID_KEYS = ("dingtalk_userid", "ding_userid")


def encode_dingtalk_oauth_state(
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


def decode_dingtalk_oauth_state(state: str) -> dict[str, Any]:
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


async def build_dingtalk_oauth_authorize_url(
    *,
    tenant_id: int,
    redirect_uri: str,
    state: str,
) -> str:
    creds = await get_dingtalk_credentials(tenant_id)
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未配置启用的钉钉连接器，无法发起 OAuth",
        )
    query = urlencode(
        {
            "redirect_uri": redirect_uri.strip(),
            "response_type": "code",
            "client_id": creds.app_key,
            "scope": "openid",
            "state": state,
            "prompt": "consent",
        },
        quote_via=quote,
    )
    return f"{DINGTALK_AUTHORIZE_URL}?{query}"


async def exchange_dingtalk_code(*, tenant_id: int, code: str) -> dict[str, Any]:
    if not code or not str(code).strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少 OAuth code")
    creds = await get_dingtalk_credentials(tenant_id)
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未配置启用的钉钉连接器，无法发起 OAuth",
        )
    resp = await get_http_client().post(
        DINGTALK_USER_TOKEN_URL,
        json={
            "clientId": creds.app_key,
            "clientSecret": creds.app_secret,
            "code": str(code).strip(),
            "grantType": "authorization_code",
        },
        timeout=15.0,
    )
    try:
        data = resp.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="钉钉授权换票失败",
        ) from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="钉钉授权换票失败")
    access_token = data.get("accessToken")
    if not isinstance(access_token, str) or not access_token.strip():
        err = data.get("message") or data.get("errorMessage") or data.get("errmsg")
        logger.warning("钉钉 userAccessToken 失败 tenant={}: {}", tenant_id, data)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err) if err else "钉钉授权换票失败",
        )
    return data


async def fetch_dingtalk_user(*, access_token: str) -> dict[str, Any]:
    resp = await get_http_client().get(
        DINGTALK_USER_ME_URL,
        headers={"x-acs-dingtalk-access-token": access_token.strip()},
        timeout=15.0,
    )
    try:
        data = resp.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="获取钉钉用户信息失败",
        ) from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="获取钉钉用户信息失败")
    if data.get("code") and str(data.get("code")) not in ("0",):
        err = data.get("message") or data.get("errorMessage")
        logger.warning("钉钉 users/me 失败: {}", data)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err) if err else "获取钉钉用户信息失败",
        )
    return data


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


async def find_user_by_dingtalk_ids(
    *,
    tenant_id: int,
    unionid: str | None,
    openid: str | None,
    userid: str | None,
) -> User | None:
    users = await User.filter(
        tenant_id=tenant_id,
        is_active=True,
        deleted_at__isnull=True,
    )
    union_norm = unionid.strip() if unionid else ""
    open_norm = openid.strip() if openid else ""
    user_norm = userid.strip() if userid else ""
    if union_norm:
        for user in users:
            bound = _extract_contact_str(user, _DINGTALK_UNIONID_KEYS)
            if bound and bound == union_norm:
                return user
    if open_norm:
        for user in users:
            bound = _extract_contact_str(user, _DINGTALK_OPENID_KEYS)
            if bound and bound == open_norm:
                return user
    if user_norm:
        for user in users:
            bound = _extract_contact_str(user, _DINGTALK_USERID_KEYS)
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


async def bind_dingtalk_to_user(
    *,
    user: User,
    unionid: str | None = None,
    openid: str | None = None,
    userid: str | None = None,
    nickname: str | None = None,
) -> User:
    if not (unionid or openid or userid):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="钉钉用户标识无效")
    contact = dict(user.contact_info) if isinstance(user.contact_info, dict) else {}
    if unionid and str(unionid).strip():
        contact["dingtalk_unionid"] = str(unionid).strip()
    if openid and str(openid).strip():
        contact["dingtalk_openid"] = str(openid).strip()
    if userid and str(userid).strip():
        contact["dingtalk_userid"] = str(userid).strip()
    if nickname and isinstance(nickname, str) and nickname.strip():
        contact["dingtalk_nickname"] = nickname.strip()
    user.contact_info = contact
    await user.save(update_fields=["contact_info", "updated_at"])
    return user


async def unbind_dingtalk_from_user(*, user: User) -> User:
    contact = dict(user.contact_info) if isinstance(user.contact_info, dict) else {}
    for key in (
        *_DINGTALK_UNIONID_KEYS,
        *_DINGTALK_OPENID_KEYS,
        *_DINGTALK_USERID_KEYS,
        "dingtalk_nickname",
    ):
        contact.pop(key, None)
    user.contact_info = contact
    await user.save(update_fields=["contact_info", "updated_at"])
    return user


def _dingtalk_identity(dingtalk_user: dict[str, Any]) -> dict[str, str | None]:
    unionid = dingtalk_user.get("unionId") if isinstance(dingtalk_user.get("unionId"), str) else None
    openid = dingtalk_user.get("openId") if isinstance(dingtalk_user.get("openId"), str) else None
    userid = None
    for key in ("userId", "userid", "dingId"):
        value = dingtalk_user.get(key)
        if isinstance(value, str) and value.strip():
            userid = value.strip()
            break
    mobile = dingtalk_user.get("mobile") if isinstance(dingtalk_user.get("mobile"), str) else None
    email = dingtalk_user.get("email") if isinstance(dingtalk_user.get("email"), str) else None
    nick = dingtalk_user.get("nick") if isinstance(dingtalk_user.get("nick"), str) else None
    return {
        "unionid": unionid.strip() if unionid else None,
        "openid": openid.strip() if openid else None,
        "userid": userid,
        "mobile": mobile,
        "email": email,
        "nickname": nick,
    }


async def resolve_user_for_dingtalk_login(*, tenant_id: int, dingtalk_user: dict[str, Any]) -> User:
    identity = _dingtalk_identity(dingtalk_user)
    if not (identity["unionid"] or identity["openid"] or identity["userid"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未能获取钉钉用户标识")

    bound = await find_user_by_dingtalk_ids(
        tenant_id=tenant_id,
        unionid=identity["unionid"],
        openid=identity["openid"],
        userid=identity["userid"],
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
        return await bind_dingtalk_to_user(
            user=candidates[0],
            unionid=identity["unionid"],
            openid=identity["openid"],
            userid=identity["userid"],
            nickname=identity["nickname"],
        )
    if len(candidates) > 1:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="匹配到多个系统账号，请联系管理员处理后再使用钉钉登录",
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            "未能自动绑定钉钉账号，请确认系统用户手机号或邮箱与钉钉一致，"
            "或在个人资料中扫码绑定"
        ),
    )


async def bind_dingtalk_for_current_user(
    *,
    tenant_id: int,
    user: User,
    dingtalk_user: dict[str, Any],
) -> User:
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="组织上下文不匹配")
    identity = _dingtalk_identity(dingtalk_user)
    if not (identity["unionid"] or identity["openid"] or identity["userid"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未能获取钉钉用户标识")
    existing = await find_user_by_dingtalk_ids(
        tenant_id=tenant_id,
        unionid=identity["unionid"],
        openid=identity["openid"],
        userid=identity["userid"],
    )
    if existing and existing.id != user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该钉钉账号已绑定其他用户",
        )
    return await bind_dingtalk_to_user(
        user=user,
        unionid=identity["unionid"],
        openid=identity["openid"],
        userid=identity["userid"],
        nickname=identity["nickname"],
    )


async def unbind_dingtalk_for_current_user(*, tenant_id: int, user: User) -> User:
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="组织上下文不匹配")
    if not (
        _extract_contact_str(user, _DINGTALK_UNIONID_KEYS)
        or _extract_contact_str(user, _DINGTALK_OPENID_KEYS)
        or _extract_contact_str(user, _DINGTALK_USERID_KEYS)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前账号未绑定钉钉")
    return await unbind_dingtalk_from_user(user=user)


async def resolve_dingtalk_user_from_code(*, tenant_id: int, code: str) -> dict[str, Any]:
    token_data = await exchange_dingtalk_code(tenant_id=tenant_id, code=code)
    access_token = str(token_data["accessToken"]).strip()
    userinfo = await fetch_dingtalk_user(access_token=access_token)
    return userinfo
