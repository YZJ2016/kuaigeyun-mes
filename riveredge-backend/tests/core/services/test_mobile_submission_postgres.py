"""Opt-in PostgreSQL gate; never connect to an application database by default."""
import asyncio
import os
from urllib.parse import urlparse
import uuid

import pytest
import pytest_asyncio
from tortoise import Tortoise
from tortoise.transactions import in_transaction

from infra.domain.tenant_context import with_tenant


@pytest_asyncio.fixture
async def postgres():
    url = os.environ.get("MOBILE_SUBMISSION_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("requires disposable PostgreSQL MOBILE_SUBMISSION_TEST_DATABASE_URL")
    parsed = urlparse(url)
    if parsed.scheme not in ("postgres", "postgresql") or not parsed.path.startswith("/codex_mobile_test"):
        pytest.fail("test database must have a codex_mobile_test name")
    await Tortoise.init(db_url=url, modules={"models": ["core.models.mobile_submission"]})
    await Tortoise.generate_schemas(safe=True)
    yield
    await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_postgres_two_connections_run_business_once(postgres):
    from core.services.mobile_submission_service import execute_submission
    key = "mob-op-" + uuid.uuid4().hex
    executions = []

    async def business():
        value = uuid.uuid4().hex
        executions.append(value)
        await asyncio.sleep(0.05)
        return {"value": value}

    args = dict(tenant_id=98101, user_id=7, operation_key=key, method="POST",
                path="/reporting/quick", query="", body=b"{}", execute=business)
    first, second = await asyncio.gather(execute_submission(**args), execute_submission(**args))
    assert first.body == second.body
    assert len(executions) == 1
    assert sorted([first.replayed, second.replayed]) == [False, True]


@pytest.mark.asyncio
async def test_postgres_nested_business_transaction_rolls_back_with_operation(postgres):
    from core.models.mobile_submission import MobileSubmission, MobileSubmissionEffect
    from core.services.mobile_submission_service import enqueue_effect, execute_submission
    key = "mob-op-" + uuid.uuid4().hex

    async def business():
        async with in_transaction():
            await enqueue_effect("reporting.backflush", 91, 7, {})
        raise ValueError("failure after nested transaction")

    with pytest.raises(ValueError):
        await execute_submission(tenant_id=98101, user_id=7, operation_key=key, method="POST",
                                 path="/reporting/quick", query="", body=b"{}", execute=business)
    async with with_tenant(98101, reason="disposable PostgreSQL rollback verification"):
        assert not await MobileSubmission.filter(operation_key=key).exists()
        # An orphan effect would prove the inner transaction committed independently.
        assert not await MobileSubmissionEffect.filter(entity_id=91).exists()
