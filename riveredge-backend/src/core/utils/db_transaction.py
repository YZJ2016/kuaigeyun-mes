"""
跨层事务：避免 Tortoise 嵌套事务死锁拖死 API。

Tortoise 0.21 在已有事务上再 ``in_transaction()`` 会走 NestedTransactionPooledContext。
其 ``_trxlock`` 是不可重入的 ``asyncio.Lock``：同一任务里再进一层就会永远停在
``lock.acquire()``。外层事务仍占着连接和行锁，池子被占满后其它请求一起等到
请求时限，网关表现为 504「服务器暂时不可用」。

非池化的 ``NestedTransactionContext`` 本来就不抢这把锁。启动时把池化嵌套对齐到
同一行为（``install_reentrant_nested_transaction``）。``reuse_or_begin_transaction``
仍是业务代码显式加入外层事务的入口。
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from loguru import logger
from tortoise import connections
from tortoise.backends.base.client import BaseTransactionWrapper
from tortoise.transactions import in_transaction

_after_commit_hooks: dict[int, list[Callable[[], Awaitable[None]]]] = {}
_after_commit_tasks: set[asyncio.Task] = set()

_nested_transaction_reentry_installed = False


def install_reentrant_nested_transaction() -> None:
    """让池化嵌套事务与非池化嵌套一样，不再抢不可重入的 ``_trxlock``。"""
    global _nested_transaction_reentry_installed
    if _nested_transaction_reentry_installed:
        return

    from tortoise.backends.base.client import NestedTransactionPooledContext
    from tortoise.exceptions import TransactionManagementError

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if not self.connection._finalized:
            if exc_type and exc_type is not TransactionManagementError:
                await self.connection.rollback()

    NestedTransactionPooledContext.__aenter__ = __aenter__  # type: ignore[method-assign]
    NestedTransactionPooledContext.__aexit__ = __aexit__  # type: ignore[method-assign]
    _install_after_commit_hooks()
    _nested_transaction_reentry_installed = True


def schedule_after_commit(factory: Callable[[], Awaitable[None]]) -> bool:
    """当前若在业务事务里，等事务提交并归还连接后再执行。否则返回 False，由调用方立刻执行。

    报工、审核会在持有行锁时发站内信和群消息。消息查询和外部发送继续占着这条连接，
    同工单的下一次提交就堵在行锁上，并发一多就把连接池占满。
    """
    try:
        conn = connections.get("default")
    except Exception:
        return False
    if not isinstance(conn, BaseTransactionWrapper):
        return False
    _after_commit_hooks.setdefault(id(conn), []).append(factory)
    return True


def _drop_after_commit_hooks(conn: object) -> None:
    _after_commit_hooks.pop(id(conn), None)


def _schedule_hook_tasks(conn: object) -> None:
    factories = _after_commit_hooks.pop(id(conn), [])
    for factory in factories:
        task = asyncio.create_task(_run_after_commit(factory))
        _after_commit_tasks.add(task)
        task.add_done_callback(_after_commit_tasks.discard)


async def _run_after_commit(factory: Callable[[], Awaitable[None]]) -> None:
    try:
        await factory()
    except Exception:
        logger.exception("事务提交后的通知或回写失败")


def _install_after_commit_hooks() -> None:
    from tortoise.backends.base.client import TransactionContextPooled

    if getattr(TransactionContextPooled, "_riveredge_after_commit", False):
        return
    original_exit = TransactionContextPooled.__aexit__

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        conn = self.connection
        try:
            await original_exit(self, exc_type, exc_val, exc_tb)
        except BaseException:
            _drop_after_commit_hooks(conn)
            raise
        if exc_type:
            _drop_after_commit_hooks(conn)
            return
        _schedule_hook_tasks(conn)

    TransactionContextPooled.__aexit__ = __aexit__  # type: ignore[method-assign]
    TransactionContextPooled._riveredge_after_commit = True


install_reentrant_nested_transaction()


@asynccontextmanager
async def reuse_or_begin_transaction():
    """复用外层事务，否则开启新事务。"""
    conn = connections.get("default")
    if isinstance(conn, BaseTransactionWrapper):
        yield conn
    else:
        async with in_transaction() as conn:
            yield conn


@asynccontextmanager
async def independent_transaction():
    """在另一条池连接上提交，不并入当前业务事务。

    编码序号的 ``SELECT FOR UPDATE`` 若走 ``reuse_or_begin_transaction``，
    行锁会留到外层建单事务结束。同规则的其它提交会堵在这把锁上，每条都占着
    连接，池子很快被占满。这里在外层事务存在时向池再借一条连接，序号提交后
    立即放锁。没有外层事务时就是一次普通短事务。
    """
    conn = connections.get("default")
    if isinstance(conn, BaseTransactionWrapper):
        parent = getattr(conn, "_parent", None)
        begin = getattr(parent, "_in_transaction", None)
        if begin is None:
            raise RuntimeError("业务事务进行中，无法另开连接提交编码序号")
        async with begin():
            yield
        return
    async with in_transaction():
        yield
