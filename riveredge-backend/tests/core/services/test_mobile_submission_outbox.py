"""Outbox state tests, with only the domain/external executor replaced."""
import pytest
import pytest_asyncio
from tortoise import Tortoise

from infra.domain.tenant_context import with_tenant


@pytest_asyncio.fixture
async def effect():
    from core.models.mobile_submission import MobileSubmission, MobileSubmissionEffect
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["core.models.mobile_submission"]})
    await Tortoise.generate_schemas()
    async with with_tenant(1, reason="outbox test"):
        op = await MobileSubmission.create(tenant_id=1, user_id=7, operation_key="mob-op-test",
                                           fingerprint="a" * 64, method="POST", path="/reporting")
        row = await MobileSubmissionEffect.create(tenant_id=1, submission_id=op.id,
                  effect_type="reporting.backflush", entity_id=71, acting_user_id=7, payload={})
    yield row
    await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_completed_effect_does_not_execute_twice(effect, monkeypatch):
    from core.services import mobile_submission_outbox_service as service
    from core.models.mobile_submission import MobileSubmissionEffect
    executed = []

    async def domain(row):
        executed.append(row.entity_id)

    monkeypatch.setattr(service, "_execute_effect", domain)
    assert await service.run_effect(1, effect.id) == "completed"
    assert await service.run_effect(1, effect.id) == "skipped"
    assert executed == [71]
    async with with_tenant(1, reason="outbox test"):
        fresh = await MobileSubmissionEffect.get(id=effect.id)
        assert fresh.status == "completed"
        assert fresh.completed_at is not None


@pytest.mark.asyncio
async def test_failed_local_effect_rolls_back_domain_writes(effect, monkeypatch):
    from core.services import mobile_submission_outbox_service as service
    from core.models.mobile_submission import MobileSubmissionEffect

    async def domain(row):
        await MobileSubmissionEffect.create(tenant_id=1, submission_id=row.submission_id,
                    effect_type="reporting.mold", entity_id=99, acting_user_id=7, payload={})
        raise RuntimeError("credential must not be persisted")

    monkeypatch.setattr(service, "_execute_effect", domain)
    assert await service.run_effect(1, effect.id) == "retry"
    async with with_tenant(1, reason="outbox test"):
        assert await MobileSubmissionEffect.all().count() == 1
        fresh = await MobileSubmissionEffect.get(id=effect.id)
        assert fresh.attempts == 1
        assert fresh.status == "pending"
        assert fresh.last_error_code == "RuntimeError"
        assert fresh.next_attempt_at is not None


@pytest.mark.asyncio
async def test_remote_unknown_is_not_blindly_retried(effect, monkeypatch):
    from core.services import mobile_submission_outbox_service as service
    from core.models.mobile_submission import MobileSubmissionEffect
    executed = []
    async with with_tenant(1, reason="outbox test"):
        effect.effect_type = "reporting.kingdee"
        await effect.save()

    async def remote(row):
        executed.append(row.id)
        raise TimeoutError("remote may have succeeded")

    monkeypatch.setattr(service, "_execute_effect", remote)
    assert await service.run_effect(1, effect.id) == "needs_reconcile"
    assert await service.run_effect(1, effect.id) == "skipped"
    assert executed == [effect.id]
    async with with_tenant(1, reason="outbox test"):
        assert (await MobileSubmissionEffect.get(id=effect.id)).status == "needs_reconcile"
