"""Transactional local effects; external uncertain outcomes fail closed.

No HTTP request publishes a broker message before committing an effect intent.
The scheduled worker scans durable pending intents; delivery is only a wake-up.
"""
from datetime import datetime, timedelta, timezone

from tortoise.transactions import in_transaction

from core.models.mobile_submission import MobileSubmissionEffect
from infra.domain.tenant_context import with_tenant


async def _execute_effect(row: MobileSubmissionEffect) -> None:
    # Registration is deliberately closed until each domain action is audited.
    # An unsupported action must never be marked as completed.
    raise NotImplementedError("Mobile submission domain executor is not registered")


async def run_effect(tenant_id: int, effect_id: int) -> str:
    if tenant_id <= 0:
        raise ValueError("Invalid effect tenant")
    async with with_tenant(tenant_id, reason="mobile submission effect execution"):
        async with in_transaction():
            row = await MobileSubmissionEffect.filter(id=effect_id).select_for_update().first()
            now = datetime.now(timezone.utc)
            if row is None or row.status != "pending":
                return "skipped"
            if row.next_attempt_at is not None and row.next_attempt_at > now:
                return "skipped"
            external = row.effect_type == "reporting.kingdee"
            if external:
                row.status = "processing"
                row.claimed_at = now
                row.attempts += 1
                await row.save()
        if external:
            # A committed claim prevents concurrent calls and remains visible
            # across process death. A stale claim is for reconciliation, not retry.
            try:
                await _execute_effect(row)
            except Exception as exc:
                await MobileSubmissionEffect.filter(id=effect_id, status="processing").update(
                    status="needs_reconcile", last_error_code=type(exc).__name__[:64],
                )
                return "needs_reconcile"
            await MobileSubmissionEffect.filter(id=effect_id, status="processing").update(
                status="completed", completed_at=datetime.now(timezone.utc), last_error_code=None,
            )
            return "completed"
        try:
            async with in_transaction():
                row = await MobileSubmissionEffect.filter(id=effect_id).select_for_update().first()
                if row is None or row.status != "pending":
                    return "skipped"
                if row.next_attempt_at is not None and row.next_attempt_at > datetime.now(timezone.utc):
                    return "skipped"
                await _execute_effect(row)
                row.status = "completed"
                row.attempts += 1
                row.completed_at = datetime.now(timezone.utc)
                row.last_error_code = None
                await row.save()
            return "completed"
        except Exception as exc:
            # The previous transaction (including all local domain writes) has
            # rolled back. Keep only a safe error code, never exception text.
            async with in_transaction():
                row = await MobileSubmissionEffect.filter(id=effect_id).select_for_update().first()
                if row is None or row.status != "pending":
                    return "skipped"
                row.attempts += 1
                row.last_error_code = type(exc).__name__[:64]
                row.next_attempt_at = datetime.now(timezone.utc) + timedelta(minutes=min(60, 2 ** min(row.attempts, 6)))
                if isinstance(exc, NotImplementedError) or row.attempts >= 8:
                    row.status = "blocked"
                await row.save()
            return "blocked" if row.status == "blocked" else "retry"
