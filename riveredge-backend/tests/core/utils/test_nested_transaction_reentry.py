"""池化嵌套事务不再因不可重入锁永久等待。"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

from tortoise import connections
from tortoise.backends.base.client import BaseTransactionWrapper, NestedTransactionPooledContext

from core.utils.db_transaction import independent_transaction, install_reentrant_nested_transaction


class _Conn:
    def __init__(self) -> None:
        self._trxlock = asyncio.Lock()
        self.connection_name = "default"
        self._finalized = False
        self.rollbacks = 0

    async def rollback(self) -> None:
        self.rollbacks += 1
        self._finalized = True


def test_triple_nested_transaction_returns():
    install_reentrant_nested_transaction()
    conn = _Conn()

    async def run() -> str:
        async with NestedTransactionPooledContext(conn):
            async with NestedTransactionPooledContext(conn):
                async with NestedTransactionPooledContext(conn):
                    return "ok"

    assert asyncio.run(asyncio.wait_for(run(), 1)) == "ok"
    assert conn.rollbacks == 0


def test_nested_transaction_exception_rolls_back_once():
    install_reentrant_nested_transaction()
    conn = _Conn()

    async def run() -> None:
        async with NestedTransactionPooledContext(conn):
            async with NestedTransactionPooledContext(conn):
                raise RuntimeError("inner")

    try:
        asyncio.run(run())
    except RuntimeError as exc:
        assert str(exc) == "inner"
    else:
        raise AssertionError("expected RuntimeError")
    assert conn.rollbacks == 1


class _Parent:
    def __init__(self) -> None:
        self.entered = 0

    def _in_transaction(self):
        parent = self

        class _Ctx:
            async def __aenter__(self_ctx):
                parent.entered += 1
                return self_ctx

            async def __aexit__(self_ctx, exc_type, exc, tb):
                return False

        return _Ctx()


class _Wrapper(BaseTransactionWrapper):
    def __init__(self) -> None:
        self._parent = _Parent()

    async def start(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def commit(self) -> None:
        return None


def test_independent_transaction_uses_another_connection_inside_outer():
    wrapper = _Wrapper()

    async def run() -> None:
        with patch.object(connections, "get", return_value=wrapper):
            async with independent_transaction():
                pass

    asyncio.run(run())
    assert wrapper._parent.entered == 1


def test_after_commit_hook_runs_after_flush_and_drops_on_rollback():
    from core.utils.db_transaction import (
        _drop_after_commit_hooks,
        _schedule_hook_tasks,
        schedule_after_commit,
    )

    ran: list[str] = []

    async def _mark() -> None:
        ran.append("ok")

    wrapper = _Wrapper()

    async def run() -> None:
        with patch.object(connections, "get", return_value=wrapper):
            assert schedule_after_commit(_mark) is True
        _drop_after_commit_hooks(wrapper)
        _schedule_hook_tasks(wrapper)
        await asyncio.sleep(0)
        assert ran == []

        with patch.object(connections, "get", return_value=wrapper):
            assert schedule_after_commit(_mark) is True
        _schedule_hook_tasks(wrapper)
        await asyncio.sleep(0)

    asyncio.run(run())
    assert ran == ["ok"]


def test_independent_transaction_begins_when_no_outer():
    entered = {"n": 0}

    @asynccontextmanager
    async def fake_in_transaction():
        entered["n"] += 1
        yield

    async def run() -> None:
        with patch.object(connections, "get", return_value=object()):
            with patch("core.utils.db_transaction.in_transaction", fake_in_transaction):
                async with independent_transaction():
                    pass

    asyncio.run(run())
    assert entered["n"] == 1
