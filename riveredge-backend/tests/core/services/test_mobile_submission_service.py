"""Real ORM tests for submission replay and atomic rollback.

SQLite covers sequential storage semantics; PostgreSQL concurrency is a separate gate.
"""
import importlib.util
import json

import pytest
import pytest_asyncio
from tortoise import Tortoise

from infra.domain.tenant_context import with_tenant


@pytest_asyncio.fixture
async def storage():
    if importlib.util.find_spec("core.models.mobile_submission") is None:
        yield
        return
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["core.models.mobile_submission"]},
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


def service():
    assert importlib.util.find_spec("core.services.mobile_submission_service") is not None, "durable submission service is missing"
    from core.services.mobile_submission_service import execute_submission
    return execute_submission


@pytest.mark.asyncio
async def test_completed_submission_replays_without_running_business_again(storage):
    execute = service()
    calls = []

    async def business():
        calls.append(True)
        return {"id": 71, "status": "pending"}

    args = dict(tenant_id=1, user_id=7, operation_key="mob-op-one", method="POST",
                path="/reporting/quick", query="", body=b'{"quantity":2}', execute=business)
    first = await execute(**args)
    second = await execute(**args)
    assert json.loads(first.body) == {"id": 71, "status": "pending"}
    assert second.body == first.body
    assert second.replayed is True
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_reused_key_with_changed_payload_is_rejected(storage):
    from infra.exceptions.exceptions import ConflictError
    execute = service()

    async def business():
        return {"id": 71}

    args = dict(tenant_id=1, user_id=7, operation_key="mob-op-one", method="POST",
                path="/reporting/quick", query="", execute=business)
    await execute(**args, body=b'{"quantity":2}')
    with pytest.raises(ConflictError):
        await execute(**args, body=b'{"quantity":3}')


@pytest.mark.asyncio
async def test_failed_business_rolls_back_operation_and_task_intent(storage):
    from core.models.mobile_submission import MobileSubmission, MobileSubmissionEffect
    from core.services.mobile_submission_service import enqueue_effect
    execute = service()

    async def business():
        await enqueue_effect("reporting.backflush", 71, 7, {})
        raise ValueError("business rejected")

    with pytest.raises(ValueError, match="business rejected"):
        await execute(tenant_id=1, user_id=7, operation_key="mob-op-one", method="POST",
                      path="/reporting/quick", query="", body=b"{}", execute=business)
    async with with_tenant(1, reason="submission rollback test"):
        assert await MobileSubmission.all().count() == 0
        assert await MobileSubmissionEffect.all().count() == 0


@pytest.mark.asyncio
async def test_same_key_is_scoped_by_tenant_and_user(storage):
    execute = service()

    async def business():
        return {"id": 71}

    args = dict(operation_key="mob-op-one", method="POST", path="/reporting/quick",
                query="", body=b"{}", execute=business)
    assert not (await execute(**args, tenant_id=1, user_id=7)).replayed
    assert not (await execute(**args, tenant_id=2, user_id=7)).replayed
    assert not (await execute(**args, tenant_id=1, user_id=8)).replayed


@pytest.mark.asyncio
async def test_equivalent_json_replays_but_path_change_conflicts(storage):
    from infra.exceptions.exceptions import ConflictError
    execute = service()

    async def business():
        return {"id": 71}

    args = dict(tenant_id=1, user_id=7, operation_key="mob-op-one", method="POST",
                query="", execute=business)
    await execute(**args, path="/reporting/quick", body=b'{"a":1,"b":2}')
    replay = await execute(**args, path="/reporting/quick", body=b'{ "b": 2, "a": 1 }')
    assert replay.replayed
    with pytest.raises(ConflictError):
        await execute(**args, path="/reporting", body=b'{"a":1,"b":2}')


@pytest.mark.asyncio
async def test_task_intent_is_saved_with_completed_submission(storage):
    from core.models.mobile_submission import MobileSubmissionEffect
    from core.services.mobile_submission_service import enqueue_effect
    execute = service()

    async def business():
        await enqueue_effect("reporting.backflush", 71, 7, {"quantity": 2})
        return {"id": 71}

    await execute(tenant_id=1, user_id=7, operation_key="mob-op-one", method="POST",
                  path="/reporting/quick", query="", body=b"{}", execute=business)
    async with with_tenant(1, reason="submission outbox test"):
        row = await MobileSubmissionEffect.all().get()
        assert row.status == "pending"
        assert row.entity_id == 71
        assert row.payload == {"quantity": 2}


@pytest.mark.asyncio
async def test_completed_response_survives_database_connection_restart(tmp_path):
    execute = service()
    url = "sqlite://" + str(tmp_path / "submission.sqlite3")
    modules = {"models": ["core.models.mobile_submission"]}
    await Tortoise.init(db_url=url, modules=modules)
    await Tortoise.generate_schemas()

    async def business():
        return {"id": 71}

    args = dict(tenant_id=1, user_id=7, operation_key="mob-op-restart", method="POST",
                path="/reporting/quick", query="", body=b"{}")
    first = await execute(**args, execute=business)
    await Tortoise.close_connections()
    await Tortoise.init(db_url=url, modules=modules)

    async def must_not_run():
        raise AssertionError("restart must replay stored response, not run business")

    try:
        replay = await execute(**args, execute=must_not_run)
        assert replay.body == first.body
        assert replay.replayed
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_nested_business_transaction_rolls_back_with_submission(storage):
    from core.models.mobile_submission import MobileSubmission, MobileSubmissionEffect
    from core.services.mobile_submission_service import enqueue_effect
    from tortoise.transactions import in_transaction
    execute = service()

    async def business():
        async with in_transaction():
            await enqueue_effect("reporting.backflush", 71, 7, {})
        raise ValueError("failure outside nested transaction")

    with pytest.raises(ValueError):
        await execute(tenant_id=1, user_id=7, operation_key="mob-op-nested", method="POST",
                      path="/reporting/quick", query="", body=b"{}", execute=business)
    async with with_tenant(1, reason="nested transaction test"):
        assert await MobileSubmission.all().count() == 0
        assert await MobileSubmissionEffect.all().count() == 0
