"""Durable writes. Call only after existing authentication and permission checks.

Business writes and effect intents use the same default Tortoise transaction.
PostgreSQL's transaction advisory lock serializes a key across API processes.
"""
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
from typing import Awaitable, Callable
from urllib.parse import parse_qsl

from fastapi.encoders import jsonable_encoder
from tortoise.transactions import in_transaction

from core.models.mobile_submission import MobileSubmission, MobileSubmissionEffect
from infra.domain.tenant_context import with_tenant
from infra.exceptions.exceptions import ConflictError, ValidationError

_submission: ContextVar[MobileSubmission | None] = ContextVar("mobile_submission", default=None)


@dataclass(frozen=True)
class SubmissionResult:
    body: bytes
    status_code: int = 200
    replayed: bool = False


def submission_active() -> bool:
    return _submission.get() is not None


def request_fingerprint(method: str, path: str, query: str, body: bytes) -> str:
    if len(body) > 256 * 1024:
        raise ValidationError("提交内容超过恢复容量，请减少内容后重试")
    try:
        payload = json.loads(body) if body else None
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (ValueError, UnicodeError):
        raise ValidationError("提交内容格式无效") from None
    material = json.dumps([method.upper(), path, sorted(parse_qsl(query, keep_blank_values=True)), canonical],
                          ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest()


async def execute_submission(
    *, tenant_id: int, user_id: int, operation_key: str, method: str,
    path: str, query: str, body: bytes, execute: Callable[[], Awaitable[object]],
) -> SubmissionResult:
    if tenant_id <= 0 or user_id <= 0:
        raise ValidationError("提交恢复需要有效的账号和组织")
    if not operation_key.startswith("mob-op-") or len(operation_key) > 128:
        raise ValidationError("提交操作标识无效")
    fingerprint = request_fingerprint(method, path, query, body)
    async with with_tenant(tenant_id, reason="authenticated mobile submission"):
        async with in_transaction() as connection:
            if connection.capabilities.dialect == "postgres":
                lock_material = f"{tenant_id}:{user_id}:{operation_key}".encode()
                lock_id = int.from_bytes(hashlib.sha256(lock_material).digest()[:8], "big", signed=True)
                await connection.execute_query("SELECT pg_advisory_xact_lock($1)", [lock_id])
            elif connection.capabilities.dialect != "sqlite":
                raise RuntimeError("Unsupported submission storage")
            row = await MobileSubmission.get_or_none(user_id=user_id, operation_key=operation_key)
            if row is not None:
                if row.fingerprint != fingerprint:
                    raise ConflictError("同一操作标识不能提交不同内容")
                if row.response_body is None:
                    raise ConflictError("原操作尚未完成，请稍后恢复")
                return SubmissionResult(row.response_body.encode(), row.response_status, True)
            row = await MobileSubmission.create(
                tenant_id=tenant_id, user_id=user_id, operation_key=operation_key,
                fingerprint=fingerprint, method=method.upper(), path=path,
                created_by=user_id,
            )
            token = _submission.set(row)
            try:
                result = jsonable_encoder(await execute())
                response = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                # No partial result is committed if encoding or the business function fails.
                row.response_body = response
                if isinstance(result, dict) and isinstance(result.get("id"), int):
                    row.entity_id = result["id"]
                await row.save()
            finally:
                _submission.reset(token)
            return SubmissionResult(response.encode())


async def enqueue_effect(effect_type: str, entity_id: int, acting_user_id: int, payload: dict) -> None:
    row = _submission.get()
    if row is None:
        raise RuntimeError("Effect intent requires an active durable submission transaction")
    await MobileSubmissionEffect.get_or_create(
        tenant_id=row.tenant_id, submission_id=row.id, effect_type=effect_type, entity_id=entity_id,
        defaults={"acting_user_id": acting_user_id, "payload": payload, "created_by": acting_user_id},
    )
