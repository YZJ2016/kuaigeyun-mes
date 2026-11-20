"""审批待办企微可更新卡片：发送落库、撤回/结束时更新或撤回。"""

from __future__ import annotations

import uuid
from typing import Any

from loguru import logger

from core.models.approval_wecom_card import ApprovalWecomCard
from core.services.messaging.wecom_message_service import (
    build_approval_invalidated_template_card,
    build_approval_pending_template_card,
    recall_wecom_message,
    resolve_wecom_recipient_userids,
    send_wecom_template_card_message,
    send_wecom_textcard_message_result,
    update_wecom_template_card,
)
async def send_and_track_approval_pending_card(
    *,
    tenant_id: int,
    approval_instance_id: int,
    recipient_user_id: int,
    subject: str,
    content: str,
    document_url: str,
) -> bool:
    """
    发送审批待办可更新卡并落库。
    优先 template_card；失败（如未配消息回调）回退 textcard + msgid 撤回。
    """
    user_ids, resolve_error = await resolve_wecom_recipient_userids(
        tenant_id=tenant_id,
        recipient=str(recipient_user_id),
    )
    if resolve_error or not user_ids:
        logger.debug(
            "审批企微卡片跳过：tenant={} user={} err={}",
            tenant_id,
            recipient_user_id,
            resolve_error or "无 userid",
        )
        return False

    wecom_userid = user_ids[0]
    link = str(document_url or "").strip()
    title = (subject or "待审批").strip()
    body = (content or title).strip()
    if not link:
        return False

    task_id = f"apr-{approval_instance_id}-{recipient_user_id}-{uuid.uuid4().hex[:12]}"

    # 同一实例同一人若已有 active 卡，先失效再发新卡（催办/重推）
    await invalidate_approval_wecom_cards_for_users(
        tenant_id=tenant_id,
        approval_instance_id=approval_instance_id,
        recipient_user_ids=[recipient_user_id],
        status_label="已更新",
        recall_if_no_response_code=False,
    )

    try:
        card = build_approval_pending_template_card(
            title=title,
            description=body,
            url=link,
            task_id=task_id,
        )
        result = await send_wecom_template_card_message(
            tenant_id=tenant_id,
            user_ids=user_ids,
            template_card=card,
        )
        if result.ok:
            if not result.response_code:
                logger.warning(
                    "审批模板卡无 response_code（可能未配消息回调），将仅用 msgid 撤回 "
                    "tenant={} instance={}",
                    tenant_id,
                    approval_instance_id,
                )
            await ApprovalWecomCard.create(
                tenant_id=tenant_id,
                approval_instance_id=approval_instance_id,
                recipient_user_id=recipient_user_id,
                wecom_userid=wecom_userid,
                msgid=result.msgid,
                response_code=result.response_code,
                card_kind="template_card",
                status="active",
                subject=title[:200],
                content=body,
                document_url=link[:2048],
                task_id=task_id,
            )
            return True
    except Exception as exc:
        logger.warning(
            "审批模板卡发送失败，回退 textcard tenant={} instance={} err={}",
            tenant_id,
            approval_instance_id,
            exc,
        )

    try:
        fallback = await send_wecom_textcard_message_result(
            tenant_id=tenant_id,
            user_ids=user_ids,
            title=title,
            description=body,
            url=link,
        )
        if not fallback.ok:
            return False
        await ApprovalWecomCard.create(
            tenant_id=tenant_id,
            approval_instance_id=approval_instance_id,
            recipient_user_id=recipient_user_id,
            wecom_userid=wecom_userid,
            msgid=fallback.msgid,
            response_code=None,
            card_kind="textcard",
            status="active",
            subject=title[:200],
            content=body,
            document_url=link[:2048],
            task_id=None,
        )
        return True
    except Exception as exc:
        logger.warning(
            "审批 textcard 回退失败 tenant={} instance={} err={}",
            tenant_id,
            approval_instance_id,
            exc,
        )
        return False


async def invalidate_approval_wecom_cards(
    *,
    tenant_id: int,
    approval_instance_id: int,
    status_label: str = "已撤回",
) -> int:
    """将该审批实例下全部 active 企微卡更新为失效或撤回。"""
    return await invalidate_approval_wecom_cards_for_users(
        tenant_id=tenant_id,
        approval_instance_id=approval_instance_id,
        recipient_user_ids=None,
        status_label=status_label,
    )


async def invalidate_approval_wecom_cards_for_users(
    *,
    tenant_id: int,
    approval_instance_id: int,
    recipient_user_ids: list[int] | None,
    status_label: str,
    recall_if_no_response_code: bool = True,
) -> int:
    query = ApprovalWecomCard.filter(
        tenant_id=tenant_id,
        approval_instance_id=approval_instance_id,
        status="active",
        deleted_at__isnull=True,
    )
    if recipient_user_ids is not None:
        if not recipient_user_ids:
            return 0
        query = query.filter(recipient_user_id__in=list(recipient_user_ids))

    rows = await query.all()
    done = 0
    for row in rows:
        ok = await _invalidate_one_card(
            row,
            status_label=status_label,
            recall_if_no_response_code=recall_if_no_response_code,
        )
        if ok:
            done += 1
    return done


async def _invalidate_one_card(
    row: ApprovalWecomCard,
    *,
    status_label: str,
    recall_if_no_response_code: bool = True,
) -> bool:
    label = (status_label or "已失效")[:16]
    try:
        if row.card_kind == "template_card" and row.response_code:
            task_id = row.task_id or f"apr-done-{row.id}"
            invalidated = build_approval_invalidated_template_card(
                title=row.subject or "",
                description=f"{label}，无需再审批",
                url=row.document_url,
                task_id=task_id,
                status_label=label,
            )
            try:
                await update_wecom_template_card(
                    tenant_id=int(row.tenant_id),
                    user_ids=[row.wecom_userid],
                    response_code=row.response_code,
                    template_card=invalidated,
                )
            except Exception:
                await update_wecom_template_card(
                    tenant_id=int(row.tenant_id),
                    user_ids=[row.wecom_userid],
                    response_code=row.response_code,
                    button_replace_name=label,
                )
            row.status = "updated"
            row.response_code = None
            row.invalidate_label = label
            await row.save()
            return True

        if row.card_kind == "template_card" and not row.response_code:
            if not recall_if_no_response_code:
                row.status = "superseded"
                row.invalidate_label = label
                await row.save()
                return True
            logger.warning(
                "审批企微模板卡无 response_code，撤回消息 card_id={} instance={} "
                "（请在企微后台配置接收消息 URL 与 Token 以启用可更新卡片）",
                row.id,
                row.approval_instance_id,
            )

        if row.msgid and recall_if_no_response_code:
            await recall_wecom_message(tenant_id=int(row.tenant_id), msgid=row.msgid)
            row.status = "recalled"
            row.invalidate_label = label
            await row.save()
            return True

        if row.msgid and not recall_if_no_response_code:
            row.status = "superseded"
            row.invalidate_label = label
            await row.save()
            return True

        row.status = "failed"
        row.invalidate_label = label
        await row.save()
        return False
    except Exception as exc:
        logger.warning(
            "失效审批企微卡失败 card_id={} instance={} err={}",
            row.id,
            row.approval_instance_id,
            exc,
        )
        row.status = "failed"
        row.invalidate_label = label
        try:
            await row.save()
        except Exception:
            pass
        return False


def parse_approval_instance_id(variables: dict[str, Any] | None) -> int | None:
    if not isinstance(variables, dict):
        return None
    raw = variables.get("approval_instance_id")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None
