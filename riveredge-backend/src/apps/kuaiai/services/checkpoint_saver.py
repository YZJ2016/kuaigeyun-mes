"""基于 Tortoise 的 LangGraph ``BaseCheckpointSaver``（spec 192 / SC-D8）。

为 HITL 确认闸持久化执行现场：中断等待确认期间服务重启或多实例部署，
待确认动作不丢失，确认后可续跑同一次运行。checkpoint 只存执行现场，
不作为审计或会话历史真源（消息表仍是真源，KR-G3 方案 C）。
不引入 langgraph-checkpoint-postgres / psycopg，不用 InMemorySaver。

约定：
- ``config["configurable"]`` 必含 ``tenant_id`` 与 ``thread_id``，缺失抛
  ``ValidationError``；``thread_id`` 形如 ``"{tenant}:{user}:{session}:{nonce}"``
  （nonce 为每次挂起运行的随机段），只由服务端生成，禁止客户端传入。
- 序列化沿用基类 ``serde``（``dumps_typed`` / ``loads_typed``），值以
  ``(type, bytes)`` 落库；channel_values 随整个 checkpoint 一并序列化
  （本表设计不分 blobs 表）。
- 同步接口（``get_tuple`` / ``list`` / ``put`` / ``put_writes`` /
  ``delete_thread``）沿用基类 ``NotImplementedError``——本仓 agent 全异步运行。
- 本仓不用的扩展接口（``aprune`` / ``acopy_thread`` / ``adelete_for_runs`` /
  delta channel history）不实现，调用时由基类抛 ``NotImplementedError``。

租户隔离沿用租户强制隔离机制：每次调用以 config 中的 ``tenant_id`` 进入
``with_tenant`` 声明执行域（无 ambient 上下文亦可运行，如任务队列内续跑）；
跨租户操作（未带 tenant_id 的 ``adelete_thread``、``purge_older_than(None)``）
显式 ``unscoped`` 并产生 scope 审计。所有查询同时显式 ``tenant_id=`` 过滤。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_serializable_checkpoint_metadata,
)
from tortoise.transactions import in_transaction

from apps.kuaiai.models.checkpoint import (
    KuaiaiAgentCheckpoint,
    KuaiaiAgentCheckpointWrite,
)
from infra.domain.tenant_context import TenantScope, unscoped, with_tenant
from infra.exceptions.exceptions import ValidationError


class TortoiseCheckpointSaver(BaseCheckpointSaver):
    """Tortoise/PostgreSQL 持久化 checkpointer。构造无参（连接由全局 Tortoise 提供）。"""

    @staticmethod
    def _locate(config: RunnableConfig) -> tuple[int, str, str]:
        """提取 (tenant_id, thread_id, checkpoint_ns)；缺 tenant_id/thread_id 抛错。"""
        configurable = (config or {}).get("configurable") or {}
        tenant_id = configurable.get("tenant_id")
        thread_id = configurable.get("thread_id")
        if tenant_id is None or not thread_id:
            raise ValidationError(
                "checkpointer config['configurable'] 必须包含 tenant_id 与 thread_id"
                "（thread_id 由服务端按 '{tenant}:{user}:{session}:{nonce}' 生成，禁止客户端传入）"
            )
        return (
            int(tenant_id),
            str(thread_id),
            str(configurable.get("checkpoint_ns") or ""),
        )

    @staticmethod
    def _locate_write(config: RunnableConfig) -> tuple[int, str, str, str]:
        """在 _locate 基础上追加必含的 checkpoint_id（put_writes 用）。"""
        tenant_id, thread_id, checkpoint_ns = TortoiseCheckpointSaver._locate(config)
        checkpoint_id = (config or {}).get("configurable", {}).get("checkpoint_id")
        if not checkpoint_id:
            raise ValidationError("checkpointer put_writes config 缺少 checkpoint_id")
        return tenant_id, thread_id, checkpoint_ns, str(checkpoint_id)

    @staticmethod
    def _config_for(
        tenant_id: int, thread_id: str, checkpoint_ns: str, checkpoint_id: str
    ) -> RunnableConfig:
        """构造带回 tenant_id 的 configurable（父链回走 / pregel 传递仍带租户）。"""
        return {
            "configurable": {
                "tenant_id": tenant_id,
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def _pending_writes(
        self, tenant_id: int, thread_id: str, checkpoint_ns: str, checkpoint_id: str
    ) -> list[tuple[str, str, Any]]:
        rows = (
            await KuaiaiAgentCheckpointWrite.filter(
                tenant_id=tenant_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint_id,
            )
            .order_by("task_id", "idx")
            .all()
        )
        return [
            (row.task_id, row.channel, self.serde.loads_typed((row.value_type, bytes(row.value_blob))))
            for row in rows
        ]

    def _tuple_from(
        self,
        row: KuaiaiAgentCheckpoint,
        config: RunnableConfig,
        pending_writes: list[tuple[str, str, Any]],
    ) -> CheckpointTuple:
        checkpoint: Checkpoint = self.serde.loads_typed(
            (row.checkpoint_type, bytes(row.checkpoint_blob))
        )
        metadata: CheckpointMetadata = self.serde.loads_typed(
            (row.metadata_type, bytes(row.metadata_blob))
        )
        parent_config = None
        if row.parent_checkpoint_id:
            parent_config = self._config_for(
                row.tenant_id, row.thread_id, row.checkpoint_ns, row.parent_checkpoint_id
            )
        return CheckpointTuple(
            config=config,
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=pending_writes,
        )

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """按 config 取 checkpoint；带 checkpoint_id 精确取，否则取最新。"""
        tenant_id, thread_id, checkpoint_ns = self._locate(config)
        with with_tenant(tenant_id, reason="checkpointer 读执行现场"):
            qs = KuaiaiAgentCheckpoint.filter(
                tenant_id=tenant_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
            )
            checkpoint_id = get_checkpoint_id(config)
            if checkpoint_id:
                row = await qs.filter(checkpoint_id=checkpoint_id).first()
            else:
                # uuid6 字符串字典序即生成时间序
                row = await qs.order_by("-checkpoint_id").first()
            if row is None:
                return None
            pending = await self._pending_writes(
                tenant_id, thread_id, checkpoint_ns, row.checkpoint_id
            )
        # 与 InMemorySaver 对齐：显式 id 取回时透传入参 config（已含 tenant_id 等键）；
        # 取最新时构造带 checkpoint_id 的最小 config（仍保留 tenant_id 供父链回走）。
        result_config = (
            config
            if checkpoint_id
            else self._config_for(tenant_id, thread_id, checkpoint_ns, row.checkpoint_id)
        )
        return self._tuple_from(row, result_config, pending)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """按 checkpoint_id 倒序列出；支持 checkpoint_ns/checkpoint_id/before/元数据 filter/limit。"""
        tenant_id, thread_id, _ = self._locate(config)
        configurable = config["configurable"]
        qs = KuaiaiAgentCheckpoint.filter(tenant_id=tenant_id, thread_id=thread_id)
        if (ns := configurable.get("checkpoint_ns")) is not None:
            qs = qs.filter(checkpoint_ns=ns)
        if (cid := get_checkpoint_id(config)) is not None:
            qs = qs.filter(checkpoint_id=cid)
        if before and (before_id := get_checkpoint_id(before)) is not None:
            qs = qs.filter(checkpoint_id__lt=before_id)
        qs = qs.order_by("-checkpoint_id")
        remaining = limit
        with with_tenant(tenant_id, reason="checkpointer 列出执行现场"):
            async for row in qs:
                metadata: CheckpointMetadata = self.serde.loads_typed(
                    (row.metadata_type, bytes(row.metadata_blob))
                )
                if filter and not all(
                    metadata.get(key) == value for key, value in filter.items()
                ):
                    continue
                if remaining is not None:
                    if remaining <= 0:
                        break
                    remaining -= 1
                checkpoint: Checkpoint = self.serde.loads_typed(
                    (row.checkpoint_type, bytes(row.checkpoint_blob))
                )
                pending = await self._pending_writes(
                    tenant_id, thread_id, row.checkpoint_ns, row.checkpoint_id
                )
                parent_config = None
                if row.parent_checkpoint_id:
                    parent_config = self._config_for(
                        tenant_id, thread_id, row.checkpoint_ns, row.parent_checkpoint_id
                    )
                yield CheckpointTuple(
                    config=self._config_for(
                        tenant_id, thread_id, row.checkpoint_ns, row.checkpoint_id
                    ),
                    checkpoint=checkpoint,
                    metadata=metadata,
                    parent_config=parent_config,
                    pending_writes=pending,
                )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """写入 checkpoint（幂等：同唯一键覆盖）；父链取入参 config 的 checkpoint_id。"""
        tenant_id, thread_id, checkpoint_ns = self._locate(config)
        checkpoint_type, checkpoint_blob = self.serde.dumps_typed(checkpoint)
        metadata_type, metadata_blob = self.serde.dumps_typed(
            get_serializable_checkpoint_metadata(config, metadata)
        )
        with with_tenant(tenant_id, reason="checkpointer 写执行现场"):
            await KuaiaiAgentCheckpoint.update_or_create(
                tenant_id=tenant_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint["id"],
                defaults={
                    "parent_checkpoint_id": config["configurable"].get("checkpoint_id"),
                    "checkpoint_type": checkpoint_type,
                    "checkpoint_blob": checkpoint_blob,
                    "metadata_type": metadata_type,
                    "metadata_blob": metadata_blob,
                },
            )
        return self._config_for(tenant_id, thread_id, checkpoint_ns, checkpoint["id"])

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """写入 pending writes，同事务；常规写入幂等插不覆盖，特殊写入（idx<0）覆盖。"""
        tenant_id, thread_id, checkpoint_ns, checkpoint_id = self._locate_write(config)
        with with_tenant(tenant_id, reason="checkpointer 写 pending writes"):
            async with in_transaction():
                for idx, (channel, value) in enumerate(writes):
                    mapped_idx = WRITES_IDX_MAP.get(channel, idx)
                    value_type, value_blob = self.serde.dumps_typed(value)
                    lookup = {
                        "tenant_id": tenant_id,
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                        "task_id": task_id,
                        "idx": mapped_idx,
                    }
                    defaults = {
                        "channel": channel,
                        "value_type": value_type,
                        "value_blob": value_blob,
                        "task_path": task_path or "",
                    }
                    if mapped_idx < 0:
                        # 特殊写入（ERROR/SCHEDULED/INTERRUPT/RESUME）：最新值覆盖
                        await KuaiaiAgentCheckpointWrite.update_or_create(
                            defaults=defaults, **lookup
                        )
                    else:
                        # 常规写入：已存在即跳过（与 InMemorySaver 语义一致）
                        await KuaiaiAgentCheckpointWrite.get_or_create(
                            defaults=defaults, **lookup
                        )

    async def adelete_thread(
        self, thread_id: str, *, tenant_id: int | None = None
    ) -> None:
        """删除 thread 全部 checkpoint 与 pending writes（硬删，两表同事务）。

        基类签名只有 ``thread_id``；调用方（spec 193）应显式携带 ``tenant_id``
        收窄到本租户。缺省时按全局唯一 thread_id 定位，经 ``unscoped`` 审计。
        """
        scope: TenantScope
        if tenant_id is not None:
            scope = with_tenant(int(tenant_id), reason="checkpointer 删除执行现场")
        else:
            scope = unscoped(
                reason="adelete_thread 未携带 tenant_id，按 thread_id 定位",
                resource="KuaiaiAgentCheckpoint",
            )
        with scope:
            filters: dict[str, Any] = {"thread_id": str(thread_id)}
            if tenant_id is not None:
                filters["tenant_id"] = int(tenant_id)
            async with in_transaction():
                await KuaiaiAgentCheckpointWrite.filter(**filters).delete()
                await KuaiaiAgentCheckpoint.filter(**filters).delete()

    async def purge_older_than(
        self, tenant_id: int | None, before: datetime
    ) -> int:
        """删除 ``created_at < before`` 的执行现场（两表），供 spec 193 过期策略调用。

        ``tenant_id=None`` 时跨租户清理（``unscoped``，产生 scope 审计）。
        返回两表合计删除行数。
        """
        scope: TenantScope
        filters: dict[str, Any] = {"created_at__lt": before}
        if tenant_id is not None:
            scope = with_tenant(int(tenant_id), reason="checkpointer 过期清理")
            filters["tenant_id"] = int(tenant_id)
        else:
            scope = unscoped(
                reason="checkpointer 跨租户过期清理",
                resource="KuaiaiAgentCheckpoint",
            )
        with scope:
            async with in_transaction():
                deleted_writes = await KuaiaiAgentCheckpointWrite.filter(**filters).delete()
                deleted_checkpoints = await KuaiaiAgentCheckpoint.filter(**filters).delete()
        return deleted_writes + deleted_checkpoints
