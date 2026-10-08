"""
工位操作员会话生命周期服务（spec 180 T4/T5）。

- 原始凭据由 ``secrets.token_urlsafe`` 生成，只在确认响应中返回一次；
  数据库仅存 SHA-256 hex，比较用 ``hmac.compare_digest`` 恒定时间。
- 确认成功在同一事务内关闭同租户 + 同终端账号的遗留 active 会话（reason=replaced）。
- 会话无固定 TTL、无闲置超时；last_seen_at 在状态查询/门禁校验时更新。
- 刷脸或员工码解析结果必须与候选操作员一致，否则抛统一通用失败，
  不区分"员工不存在/离职/未关联用户/用户停用/候选不一致"。
"""

import hashlib
import hmac
import secrets
from typing import Optional, Sequence, Tuple

from tortoise.transactions import in_transaction

from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError
from infra.models.user import User
from infra.services.face_template_service import FaceTemplateService
from apps.kuaioa.models.employee import KuaioaEmployeeProfile
from apps.kuaizhizao.models.station_operator_session import StationOperatorSession
from apps.master_data.models.factory import Workstation

CONFIRM_METHOD_FACE = "face"
CONFIRM_METHOD_EMPLOYEE_CODE = "employee_code"
CONFIRM_METHODS = {CONFIRM_METHOD_FACE, CONFIRM_METHOD_EMPLOYEE_CODE}

STATUS_ACTIVE = "active"
STATUS_CLOSED = "closed"

CLOSE_REASON_EXPLICIT_SWITCH = "explicit_switch"
CLOSE_REASON_TERMINAL_LOGOUT = "terminal_logout"
CLOSE_REASON_REPLACED = "replaced"
CLOSE_REASON_EXPLICIT_CLOSE = "explicit_close"

# 候选人一致性失败统一返回该文案，不区分失败原因（不泄露人员信息差异）
CONFIRM_FAILED_MESSAGE = "操作员身份确认失败，请重新选择人员后重试"


def generate_credential() -> str:
    """生成不透明会话凭据（仅内存持有，不落库）。"""
    return secrets.token_urlsafe(32)


def hash_credential(credential: str) -> str:
    """凭据 SHA-256 hex（唯一落库形态）。"""
    return hashlib.sha256(credential.encode("utf-8")).hexdigest()


class StationOperatorSessionService:
    """工位操作员会话：确认签发、状态查询、幂等关闭。"""

    # ---- 身份解析（候选人一致性） ----

    async def _active_linked_user(self, tenant_id: int, user_id: Optional[int]) -> Optional[User]:
        if not user_id:
            return None
        return await User.get_or_none(
            id=user_id,
            tenant_id=tenant_id,
            is_active=True,
            deleted_at__isnull=True,
        )

    async def _profile_by_employee_code(
        self, tenant_id: int, employee_code: str
    ) -> Optional[KuaioaEmployeeProfile]:
        """员工码 → 员工档案。租户内唯一、active、未删除、关联同租户启用用户。"""
        code = (employee_code or "").strip()
        if not code:
            return None
        profile = await KuaioaEmployeeProfile.filter(
            tenant_id=tenant_id,
            employee_code=code,
            status="active",
            deleted_at__isnull=True,
            user_id__not_isnull=True,
        ).first()
        if profile is None:
            return None
        if await self._active_linked_user(tenant_id, profile.user_id) is None:
            return None
        return profile

    async def _profile_by_user(
        self, tenant_id: int, user_id: int
    ) -> Optional[KuaioaEmployeeProfile]:
        """系统用户 → 在职员工档案（刷脸识别结果的反向解析）。"""
        if await self._active_linked_user(tenant_id, user_id) is None:
            return None
        return await KuaioaEmployeeProfile.filter(
            tenant_id=tenant_id,
            user_id=user_id,
            status="active",
            deleted_at__isnull=True,
        ).first()

    async def _resolve_confirmed_profile(
        self,
        *,
        tenant_id: int,
        confirm_method: str,
        face_descriptor: Optional[Sequence[float]],
        employee_code: Optional[str],
    ) -> Optional[KuaioaEmployeeProfile]:
        """按确认方式解析出员工档案；任何解析失败统一返回 None。"""
        if confirm_method == CONFIRM_METHOD_EMPLOYEE_CODE:
            return await self._profile_by_employee_code(tenant_id, employee_code or "")
        if confirm_method == CONFIRM_METHOD_FACE:
            if not face_descriptor:
                return None
            try:
                result = await FaceTemplateService.identify(tenant_id, list(face_descriptor))
            except BusinessLogicError:
                return None
            user_id = (result or {}).get("user_id")
            if not (result or {}).get("matched") or not user_id:
                return None
            return await self._profile_by_user(tenant_id, int(user_id))
        return None

    # ---- 生命周期 ----

    async def confirm(
        self,
        *,
        tenant_id: int,
        terminal_user: User,
        workstation_id: int,
        candidate_user_id: int,
        confirm_method: str,
        face_descriptor: Optional[Sequence[float]] = None,
        employee_code: Optional[str] = None,
    ) -> Tuple[StationOperatorSession, str]:
        """确认候选人并签发会话；同一事务关闭该终端账号遗留 active 会话。

        Returns:
            (session, credential)：credential 为原始凭据，仅此一次返回。
        """
        if confirm_method not in CONFIRM_METHODS:
            raise BusinessLogicError(CONFIRM_FAILED_MESSAGE)
        workstation = await Workstation.get_or_none(
            id=workstation_id,
            tenant_id=tenant_id,
            is_active=True,
            deleted_at__isnull=True,
        )
        if workstation is None:
            raise BusinessLogicError("工位不存在或已停用")

        profile = await self._resolve_confirmed_profile(
            tenant_id=tenant_id,
            confirm_method=confirm_method,
            face_descriptor=face_descriptor,
            employee_code=employee_code,
        )
        if profile is None or int(profile.user_id or 0) != int(candidate_user_id):
            raise BusinessLogicError(CONFIRM_FAILED_MESSAGE)

        credential = generate_credential()
        credential_hash = hash_credential(credential)
        now = resolve_business_datetime()
        async with in_transaction():
            await StationOperatorSession.filter(
                tenant_id=tenant_id,
                terminal_user_id=terminal_user.id,
                status=STATUS_ACTIVE,
            ).update(
                status=STATUS_CLOSED,
                closed_at=now,
                close_reason=CLOSE_REASON_REPLACED,
            )
            session = await StationOperatorSession.create(
                tenant_id=tenant_id,
                terminal_user_id=terminal_user.id,
                workstation_id=workstation.id,
                workstation_name=workstation.name,
                operator_employee_id=profile.id,
                operator_user_id=profile.user_id,
                operator_name=profile.full_name,
                confirm_method=confirm_method,
                credential_hash=credential_hash,
                status=STATUS_ACTIVE,
                issued_at=now,
                last_seen_at=now,
            )
        return session, credential

    async def resolve_active_session(
        self,
        *,
        tenant_id: int,
        terminal_user_id: int,
        credential: Optional[str],
        workstation_id: Optional[int] = None,
    ) -> Optional[StationOperatorSession]:
        """按凭据解析当前有效会话；不更新 last_seen_at。

        凭据绑定租户 + 终端账号；传入 workstation_id 时同时校验工位绑定。
        任何不匹配统一返回 None（不泄露他人会话信息）。
        """
        if not credential:
            return None
        credential_hash = hash_credential(credential.strip())
        session = await StationOperatorSession.filter(
            tenant_id=tenant_id,
            terminal_user_id=terminal_user_id,
            status=STATUS_ACTIVE,
            credential_hash=credential_hash,
        ).first()
        if session is None:
            return None
        if not hmac.compare_digest(session.credential_hash or "", credential_hash):
            return None
        if workstation_id is not None and session.workstation_id != workstation_id:
            return None
        return session

    async def get_current_session(
        self,
        *,
        tenant_id: int,
        terminal_user_id: int,
        credential: Optional[str],
        workstation_id: Optional[int] = None,
    ) -> Optional[StationOperatorSession]:
        """状态查询入口：解析有效会话并刷新 last_seen_at。"""
        session = await self.resolve_active_session(
            tenant_id=tenant_id,
            terminal_user_id=terminal_user_id,
            credential=credential,
            workstation_id=workstation_id,
        )
        if session is None:
            return None
        session.last_seen_at = resolve_business_datetime()
        await session.save(update_fields=["last_seen_at", "updated_at"])
        return session

    async def close_session(
        self,
        *,
        tenant_id: int,
        terminal_user_id: int,
        credential: Optional[str],
        reason: str = CLOSE_REASON_EXPLICIT_CLOSE,
    ) -> bool:
        """关闭当前会话；幂等——无有效会话时返回 False 不抛错。"""
        session = await self.resolve_active_session(
            tenant_id=tenant_id,
            terminal_user_id=terminal_user_id,
            credential=credential,
        )
        if session is None:
            return False
        now = resolve_business_datetime()
        session.status = STATUS_CLOSED
        session.closed_at = now
        session.close_reason = reason
        await session.save(update_fields=["status", "closed_at", "close_reason", "updated_at"])
        return True
