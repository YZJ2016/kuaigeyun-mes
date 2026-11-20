"""企业微信应用消息（文本 / textcard / 可更新 template_card）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from core.services.integration.wecom_integration import (
    WECOM_API_BASE,
    fetch_wecom_access_token,
    get_wecom_credentials,
)
from core.services.integration.wecom_oauth_service import extract_wecom_user_id
from infra.infrastructure.http.client import get_http_client
from infra.models.user import User


@dataclass(frozen=True)
class WeComMessageSendResult:
    ok: bool
    msgid: str | None = None
    response_code: str | None = None


def _parse_recipient_tokens(recipient: str) -> list[str]:
    return [v.strip() for v in str(recipient or "").replace(",", "|").split("|") if v.strip()]


def _is_platform_user_id_token(token: str) -> bool:
    return token.isdigit() and int(token) > 0


async def resolve_wecom_recipient_userids(
    *,
    tenant_id: int,
    recipient: str,
) -> tuple[list[str], str | None]:
    """
    将推送 recipient 解析为企业微信 userid。
    纯数字 token 视为平台 user_id；其余 token 原样当作企微 userid（测试或手工填写）。
    """
    tokens = _parse_recipient_tokens(recipient)
    if not tokens:
        return [], "缺少推送接收人"

    resolved: list[str] = []
    errors: list[str] = []
    for token in tokens:
        if _is_platform_user_id_token(token):
            user = await User.filter(tenant_id=tenant_id, id=int(token)).first()
            if not user:
                errors.append(f"用户 {token} 不存在")
                continue
            wecom_uid = extract_wecom_user_id(user)
            if not wecom_uid:
                errors.append(f"用户 {token} 未绑定企业微信")
                continue
            resolved.append(wecom_uid)
        else:
            resolved.append(token)

    if errors:
        return [], "; ".join(errors)
    return resolved, None


async def _post_wecom_message(tenant_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    creds = await get_wecom_credentials(tenant_id)
    if not creds:
        raise ValueError("未配置启用的企业微信连接器")
    token = await fetch_wecom_access_token(creds.corp_id, creds.corp_secret)
    body = {**payload, "agentid": creds.agent_id}
    resp = await get_http_client().post(
        f"{WECOM_API_BASE}/message/send",
        params={"access_token": token},
        json=body,
        timeout=10.0,
    )
    data = resp.json()
    if data.get("errcode") != 0:
        raise ValueError(data.get("errmsg") or "企业微信消息发送失败")
    return data if isinstance(data, dict) else {}


async def send_wecom_text_message(
    *,
    tenant_id: int,
    user_ids: list[str],
    content: str,
) -> bool:
    """向企业微信用户发送文本消息；未配置连接器或无 userid 时返回 False。"""
    touser = "|".join([uid.strip() for uid in user_ids if uid and str(uid).strip()])
    if not touser or not content.strip():
        return False

    creds = await get_wecom_credentials(tenant_id)
    if not creds:
        logger.info("租户 {} 未配置启用的企业微信连接器，跳过 WeCom 通知", tenant_id)
        return False

    await _post_wecom_message(
        tenant_id,
        {
            "touser": touser,
            "msgtype": "text",
            "text": {"content": content[:2048]},
            "safe": 0,
        },
    )
    return True


async def send_wecom_textcard_message(
    *,
    tenant_id: int,
    user_ids: list[str],
    title: str,
    description: str,
    url: str,
) -> bool:
    """向企业微信用户发送 textcard；url 须为完整 https 链接。"""
    result = await send_wecom_textcard_message_result(
        tenant_id=tenant_id,
        user_ids=user_ids,
        title=title,
        description=description,
        url=url,
    )
    return result.ok


async def send_wecom_textcard_message_result(
    *,
    tenant_id: int,
    user_ids: list[str],
    title: str,
    description: str,
    url: str,
) -> WeComMessageSendResult:
    """textcard 发送并返回 msgid（供撤回）。"""
    touser = "|".join([uid.strip() for uid in user_ids if uid and str(uid).strip()])
    link = str(url or "").strip()
    if not touser or not link:
        return WeComMessageSendResult(ok=False)

    creds = await get_wecom_credentials(tenant_id)
    if not creds:
        logger.info("租户 {} 未配置启用的企业微信连接器，跳过 WeCom 卡片", tenant_id)
        return WeComMessageSendResult(ok=False)

    data = await _post_wecom_message(
        tenant_id,
        {
            "touser": touser,
            "msgtype": "textcard",
            "textcard": {
                "title": (title or "新消息")[:128],
                "description": (description or "")[:512],
                "url": link[:2048],
                "btntxt": "查看详情",
            },
        },
    )
    msgid = str(data.get("msgid") or "").strip() or None
    return WeComMessageSendResult(ok=True, msgid=msgid)


def build_approval_pending_template_card(
    *,
    title: str,
    description: str,
    url: str,
    task_id: str,
) -> dict[str, Any]:
    """审批待办：按钮交互型模板卡（可更新；「查看详情」跳转 H5）。"""
    link = str(url or "").strip()
    return {
        "card_type": "button_interaction",
        "source": {"desc": "待审批", "desc_color": 2},
        "main_title": {
            "title": (title or "待审批")[:36],
            "desc": (description or "")[:44],
        },
        "sub_title_text": (description or "")[:160],
        "task_id": task_id[:128],
        "button_list": [
            {
                "text": "查看详情",
                "style": 1,
                "type": 1,
                "url": link[:2048],
            }
        ],
    }


def build_approval_invalidated_template_card(
    *,
    title: str,
    description: str,
    url: str | None,
    task_id: str,
    status_label: str,
) -> dict[str, Any]:
    """撤回/结束后的文本通知卡（替换原可回调卡）。"""
    link = str(url or "").strip()
    label = (status_label or "已处理")[:16]
    card: dict[str, Any] = {
        "card_type": "text_notice",
        "source": {"desc": label, "desc_color": 3},
        "main_title": {
            "title": (f"【{label}】" + (title or "审批待办"))[:36],
            "desc": (description or "此待办已处理，无需再操作")[:44],
        },
        "sub_title_text": (description or "此待办已处理，无需再操作")[:160],
        "task_id": task_id[:128],
        "horizontal_content_list": [
            {"type": 0, "keyname": "状态", "value": label},
        ],
        "card_action": {"type": 1, "url": link[:2048]} if link else {"type": 1, "url": "https://work.weixin.qq.com"},
    }
    return card


async def send_wecom_template_card_message(
    *,
    tenant_id: int,
    user_ids: list[str],
    template_card: dict[str, Any],
) -> WeComMessageSendResult:
    """发送模板卡片；成功时返回 msgid 与 response_code（可更新卡）。"""
    touser = "|".join([uid.strip() for uid in user_ids if uid and str(uid).strip()])
    if not touser or not template_card:
        return WeComMessageSendResult(ok=False)

    creds = await get_wecom_credentials(tenant_id)
    if not creds:
        logger.info("租户 {} 未配置启用的企业微信连接器，跳过 WeCom 模板卡", tenant_id)
        return WeComMessageSendResult(ok=False)

    data = await _post_wecom_message(
        tenant_id,
        {
            "touser": touser,
            "msgtype": "template_card",
            "template_card": template_card,
            "enable_id_trans": 0,
        },
    )
    return WeComMessageSendResult(
        ok=True,
        msgid=str(data.get("msgid") or "").strip() or None,
        response_code=str(data.get("response_code") or "").strip() or None,
    )


async def update_wecom_template_card(
    *,
    tenant_id: int,
    user_ids: list[str],
    response_code: str,
    button_replace_name: str | None = None,
    template_card: dict[str, Any] | None = None,
) -> bool:
    """
    消费 response_code 更新模板卡（72 小时内、一次性）。
    可传 button.replace_name，或整卡 template_card 替换。
    """
    code = str(response_code or "").strip()
    if not code:
        return False
    creds = await get_wecom_credentials(tenant_id)
    if not creds:
        return False

    payload: dict[str, Any] = {
        "userids": [uid.strip() for uid in user_ids if uid and str(uid).strip()],
        "agentid": creds.agent_id,
        "response_code": code,
    }
    if template_card:
        payload["template_card"] = template_card
    elif button_replace_name:
        payload["button"] = {"replace_name": str(button_replace_name)[:16]}
    else:
        return False

    token = await fetch_wecom_access_token(creds.corp_id, creds.corp_secret)
    resp = await get_http_client().post(
        f"{WECOM_API_BASE}/message/update_template_card",
        params={"access_token": token},
        json=payload,
        timeout=10.0,
    )
    data = resp.json()
    if data.get("errcode") != 0:
        raise ValueError(data.get("errmsg") or "企业微信更新模板卡失败")
    return True


async def recall_wecom_message(
    *,
    tenant_id: int,
    msgid: str,
) -> bool:
    """撤回应用消息（依赖 msgid）。"""
    mid = str(msgid or "").strip()
    if not mid:
        return False
    creds = await get_wecom_credentials(tenant_id)
    if not creds:
        return False
    token = await fetch_wecom_access_token(creds.corp_id, creds.corp_secret)
    resp = await get_http_client().post(
        f"{WECOM_API_BASE}/message/recall",
        params={"access_token": token},
        json={"msgid": mid},
        timeout=10.0,
    )
    data = resp.json()
    if data.get("errcode") != 0:
        raise ValueError(data.get("errmsg") or "企业微信撤回消息失败")
    return True
