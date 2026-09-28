"""
租户查询强制隔离机制（spec 143 / KR-CL4，决策 D7+D9）。

一个机制收口：所有声明 ``tenant_id`` 字段的受管模型（继承
``infra.models.base.BaseModel`` / ``core.models.base.LogBaseModel``，
或显式 mixin ``TenantIsolationMixin`` 的直接 ``Model`` 子类），其默认 Manager
产出 ``TenantEnforcedQuerySet``，在查询物化时按三态上下文注入
``tenant_id=<ctx>`` 条件：

- ambient 上下文 / ``with_tenant(tid)`` → 注入 ``tenant_id=<tid>``
- ``unscoped(reason=...)`` → 不注入（激活点已审计）
- 无上下文且不在 scope 内 → ``TenantContextError`` 失败关闭

覆盖读（filter/all/get/get_or_none/first/count/exists/values/annotate 等一切
走 ``_make_query`` 的查询路径）与 queryset 写（``filter().update()`` /
``filter().delete()`` / ``bulk_update``——这些方法构造 ``UpdateQuery`` /
``DeleteQuery`` / ``BulkUpdateQuery`` 时携带本 QuerySet 的 ``_q_objects``，
因此在构造前注入条件即可被它们继承）。

平台级表（``tenant_id`` 恒为 NULL、跨组织共享）在模型 ``Meta`` 上声明
``tenant_isolation = "platform"`` 退出强制过滤。

非 queryset 路径（``raw()``、M2M through 表、实例级 ``save()/delete()``、
``create()`` 自动写 tenant_id）本期不罩，见 spec 143 §4 Known gaps。
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, TypeVar

from tortoise.manager import Manager
from tortoise.models import Model
from tortoise.queryset import Q, QuerySet

from infra.domain.tenant_context import (
    UNSCOPED,
    TenantContextError,
    resolve_tenant_for_query,
)

MODEL = TypeVar("MODEL", bound=Model)

# 平台级 opt-out 标记：class Meta: tenant_isolation = "platform"
TENANT_ISOLATION_PLATFORM = "platform"


def model_is_tenant_scoped(model: type[Model]) -> bool:
    """模型是否纳入租户强制隔离（有 tenant_id 字段且未 opt-out）。"""
    meta_cls = getattr(model, "Meta", None)
    if getattr(meta_cls, "tenant_isolation", None) == TENANT_ISOLATION_PLATFORM:
        return False
    return "tenant_id" in getattr(model._meta, "fields_map", {})


class TenantEnforcedQuerySet(QuerySet[MODEL]):
    """
    强制组织条件的 QuerySet。

    注入点统一在「查询物化/终态构造」时刻（``_make_query`` 与
    update/delete/count/exists/values/values_list/bulk_update），而不是
    ``filter()`` 链构造时——保证：

    - 懒惰链上每次执行都按「执行时」的三态上下文求值；
    - 仅构建不执行的 QuerySet 不会误触发失败关闭；
    - queryset 写（UpdateQuery/DeleteQuery）继承已注入的 ``_q_objects``。
    """

    def _inject_tenant_filter(self) -> None:
        if getattr(self, "_tenant_filter_done", False):
            return

        if not model_is_tenant_scoped(self.model):
            # 非租户作用域模型（平台级 opt-out / 无 tenant_id 字段）无注入面；
            # 单链 pin 只对作用域模型有意义，此时忽略（不产生 FieldError/空集）。
            self._tenant_filter_done = True
            return

        # 兼容门面可钉住单链的过滤态（见 query_filter.TenantQuerySet）
        override = getattr(self, "_tenant_override", None)
        if override is UNSCOPED:
            self._tenant_filter_done = True
            return
        if override is not None:
            # 钉住值支持集合（限定到指定组织集合，如主+子组织共享池配额）
            if isinstance(override, (list, tuple, set, frozenset)):
                self._q_objects.append(Q(tenant_id__in=list(override)))
            else:
                self._q_objects.append(Q(tenant_id=override))
            self._tenant_filter_done = True
            return

        state = resolve_tenant_for_query()
        if state is UNSCOPED:
            self._tenant_filter_done = True
            return
        if state is None:
            # 失败关闭且不置 _tenant_filter_done：同一 QuerySet 重试仍应
            # 重新求值上下文（防止「先抛错后放行」的 fail-open 重试漏洞）。
            raise TenantContextError(
                f"无组织上下文访问租户模型 {self.model.__name__}，查询已失败关闭。"
                "请在请求内设置组织上下文，或以 with_tenant(tid) / unscoped(reason=...) "
                "显式声明执行域。"
            )
        self._q_objects.append(Q(tenant_id=state))
        self._tenant_filter_done = True

    def _clone(self) -> "TenantEnforcedQuerySet[MODEL]":
        queryset = super()._clone()
        # 已注入的条件随 _q_objects 一并复制；克隆不再重复求值上下文
        queryset._tenant_filter_done = getattr(self, "_tenant_filter_done", False)
        queryset._tenant_override = getattr(self, "_tenant_override", None)
        return queryset

    # ---- 读路径（SELECT 统一走 _make_query：await / sql() / explain()）----

    def _make_query(self) -> None:
        self._inject_tenant_filter()
        super()._make_query()

    # ---- queryset 写 / 终态构造（各自构造专用 Query 对象，构造前先注入）----

    def update(self, **kwargs: Any):
        self._inject_tenant_filter()
        return super().update(**kwargs)

    def delete(self):
        self._inject_tenant_filter()
        return super().delete()

    def count(self):
        self._inject_tenant_filter()
        return super().count()

    def exists(self):
        self._inject_tenant_filter()
        return super().exists()

    def values(self, *args: str, **kwargs: str):
        self._inject_tenant_filter()
        return super().values(*args, **kwargs)

    def values_list(self, *fields_: str, flat: bool = False):
        self._inject_tenant_filter()
        return super().values_list(*fields_, flat=flat)

    def bulk_update(
        self,
        objects: Iterable[MODEL],
        fields: Iterable[str],
        batch_size: Optional[int] = None,
    ):
        self._inject_tenant_filter()
        return super().bulk_update(objects, fields, batch_size=batch_size)


class TenantEnforcedManager(Manager):
    """产出强制隔离 QuerySet 的默认 Manager。"""

    def get_queryset(self) -> TenantEnforcedQuerySet:
        return TenantEnforcedQuerySet(self._model)


class TenantIsolationMixin:
    """
    把默认 Manager 换成 ``TenantEnforcedManager`` 的挂载钩子。

    Tortoise 0.21.1 中 ``Meta.manager`` 只读取模型自己的 ``Meta`` 类，
    抽象基类上定义不会被子类继承（已实测），因此用 ``__init_subclass__``
    在类创建时替换 ``cls._meta.manager``——此时 ``MetaInfo`` 已建好
    （fields_map 就绪），替换后由 ORM 回填 ``manager._model``。
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        meta = getattr(cls, "_meta", None)
        if meta is not None and "tenant_id" in getattr(meta, "fields_map", {}):
            cls._meta.manager = TenantEnforcedManager()
