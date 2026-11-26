"""企业微信应用「接收消息」回调（模板卡可更新前置条件）。"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Any

from fastapi import APIRouter, Query, Request, Response
from loguru import logger

from core.models.integration_config import IntegrationConfig
from core.services.integration.wecom_callback_crypto import (
    WeComCryptoError,
    build_wecom_encrypted_response,
    decrypt_wecom_cipher,
    verify_wecom_signature,
)

router = APIRouter(prefix="/integrations/wecom", tags=["Integrations - WeCom"])


def _xml_text(root: ET.Element, tag: str) -> str:
    node = root.find(tag)
    if node is None or node.text is None:
        return ""
    return str(node.text).strip()


async def _load_wecom_callback_secrets(tenant_id: int) -> tuple[str, str, str] | None:
    """返回 (token, encoding_aes_key, corp_id)。"""
    row = (
        await IntegrationConfig.filter(
            tenant_id=tenant_id,
            type="wecom",
            is_active=True,
            deleted_at__isnull=True,
        )
        .order_by("-updated_at")
        .first()
    )
    if not row:
        return None
    cfg: dict[str, Any] = row.get_config() if hasattr(row, "get_config") else (row.config or {})
    if not isinstance(cfg, dict):
        cfg = {}
    token = str(cfg.get("token") or "").strip()
    aes_key = str(cfg.get("encoding_aes_key") or "").strip()
    corp_id = str(cfg.get("corp_id") or "").strip()
    if not token or not aes_key or not corp_id:
        return None
    return token, aes_key, corp_id


@router.api_route("/receive/{tenant_id}", methods=["GET", "POST"])
async def wecom_receive_callback(
    tenant_id: int,
    request: Request,
    msg_signature: str = Query(default=""),
    timestamp: str = Query(default=""),
    nonce: str = Query(default=""),
    echostr: str = Query(default=""),
) -> Response:
    """
    企微管理后台「接收消息」URL：
    `{origin}/api/v1/integrations/wecom/receive/{tenant_id}`

    GET：URL 验证；POST：事件/消息 ACK（模板卡点击等）。
    须在连接器填写 Token、EncodingAESKey，并与企微后台一致。
    """
    secrets = await _load_wecom_callback_secrets(int(tenant_id))
    if not secrets:
        logger.warning("企微回调未配置 token/aes tenant={}", tenant_id)
        return Response(content="wecom callback not configured", status_code=400)

    token, aes_key, corp_id = secrets

    if request.method == "GET":
        try:
            verify_wecom_signature(
                token=token,
                timestamp=timestamp,
                nonce=nonce,
                encrypt=echostr,
                msg_signature=msg_signature,
            )
            plain = decrypt_wecom_cipher(
                encoding_aes_key=aes_key,
                encrypt=echostr,
                receive_id=corp_id,
            )
            return Response(content=plain, media_type="text/plain")
        except WeComCryptoError as exc:
            logger.warning("企微回调 URL 验证失败 tenant={} err={}", tenant_id, exc)
            return Response(content="invalid signature", status_code=403)
        except Exception as exc:
            logger.exception("企微回调 URL 验证异常 tenant={} err={}", tenant_id, exc)
            return Response(content="error", status_code=500)

    # POST：解密后 ACK；模板卡交互不阻塞业务（更新码已在发送时落库）
    try:
        raw = (await request.body()).decode("utf-8", errors="ignore")
        encrypt_match = re.search(r"<Encrypt><!\[CDATA\[(.*?)\]\]></Encrypt>", raw, re.S)
        if not encrypt_match:
            encrypt_match = re.search(r"<Encrypt>(.*?)</Encrypt>", raw, re.S)
        encrypt = (encrypt_match.group(1).strip() if encrypt_match else "")
        if not encrypt:
            return Response(content="success", media_type="text/plain")

        verify_wecom_signature(
            token=token,
            timestamp=timestamp,
            nonce=nonce,
            encrypt=encrypt,
            msg_signature=msg_signature,
        )
        plain = decrypt_wecom_cipher(
            encoding_aes_key=aes_key,
            encrypt=encrypt,
            receive_id=corp_id,
        )
        try:
            root = ET.fromstring(plain)
            event = _xml_text(root, "Event")
            if event:
                logger.info(
                    "企微回调事件 tenant={} event={} key={}",
                    tenant_id,
                    event,
                    _xml_text(root, "EventKey"),
                )
        except ET.ParseError:
            logger.debug("企微回调明文非 XML tenant={}", tenant_id)

        # 被动回复空成功（加密）
        reply_ts = timestamp or str(int(time.time()))
        reply_nonce = nonce or str(int(time.time()))
        encrypted = build_wecom_encrypted_response(
            token=token,
            encoding_aes_key=aes_key,
            receive_id=corp_id,
            plain="success",
            nonce=reply_nonce,
            timestamp=reply_ts,
        )
        return Response(content=encrypted, media_type="application/xml")
    except WeComCryptoError as exc:
        logger.warning("企微回调 POST 验签/解密失败 tenant={} err={}", tenant_id, exc)
        return Response(content="invalid signature", status_code=403)
    except Exception as exc:
        logger.exception("企微回调 POST 异常 tenant={} err={}", tenant_id, exc)
        return Response(content="success", media_type="text/plain")
