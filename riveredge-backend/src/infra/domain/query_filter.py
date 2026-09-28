"""
查询过滤器模块（spec 143：兼容门面）

历史 ``TenantQuerySet`` / ``get_tenant_queryset`` / ``require_tenant_for_query``
保留为兼容 API，但真正的组织条件由 ORM 层强制隔离机制
（``infra.domain.tenant_isolation.TenantEnforcedQuerySet``）注入——
本模块只是在返回的 QuerySet 上「钉住」单链过滤态（``_tenant_override``），
不再自行拼接 tenant_id 条件，也不再提供静默旁路：

- ``tenant_id=tid``：该链固定查询指定组织（等价单链版 ``with_tenant``）。
- ``skip_tenant_filter=True``：该链固定为 unscoped（等价单链版 ``unscoped``），
  每次调用写结构化警告日志；新代码应改用
  ``unscoped(reason=...)`` 显式 scope（激活点统一审计）。
- 两者都不传：完全交给强制机制按三态上下文求值（无上下文则失败关闭）。
"""

from typing import Optional, TypeVar, Generic

from loguru import logger
from tortoise.models import Model
from tortoise.queryset import QuerySet

from infra.domain.tenant_context import (
    UNSCOPED,
    get_current_tenant_id,
    require_tenant_context,
)
from infra.domain.tenant_isolation import model_is_tenant_scoped

# 定义泛型类型变量
T = TypeVar("T", bound=Model)


class TenantQuerySet(Generic[T]):
    """
    组织查询集兼容门面

    委托 ``TenantEnforcedQuerySet`` 的强制隔离：本类的 tenant_id /
    skip_tenant_filter 参数通过 ``_tenant_override`` 钉住单链过滤态，
    底层条件注入仍由 ORM 机制统一完成。

    Attributes:
        model: 数据模型类
        tenant_id: 组织 ID（可选，钉住该链只查该组织）
        skip_tenant_filter: 该链放开组织过滤（兼容参数，建议使用 unscoped scope）
    """

    def __init__(
        self,
        model: type[T],
        tenant_id: Optional[int] = None,
        skip_tenant_filter: bool = False
    ):
        self.model = model
        self.tenant_id = tenant_id
        self.skip_tenant_filter = skip_tenant_filter

    def _pin(self, query: QuerySet[T]) -> QuerySet[T]:
        """
        在 QuerySet 上钉住单链过滤态（供强制注入点读取）。

        钉住发生在 QuerySet 物化/终态构造时（见
        ``TenantEnforcedQuerySet._inject_tenant_filter``），因此懒惰链上
        的任何后续 filter/clone 都继承该钉住态。``tenant_id`` 也可传
        组织 ID 集合——钉住为 ``tenant_id__in``（限定的组织集合，
        用于主/子组织共享池配额等组织树内聚合）。
        """
        if not model_is_tenant_scoped(self.model):
            # 非租户作用域模型（平台级 opt-out / 无 tenant_id）无注入面，
            # pin 无意义——忽略且不产生告警噪音（F5）。
            return query
        if self.skip_tenant_filter:
            logger.warning(
                "TenantQuerySet(skip_tenant_filter=True) 兼容旁路被调用 model={}，"
                "新代码应改用 unscoped(reason=...) 显式 scope",
                self.model.__name__,
            )
            query._tenant_override = UNSCOPED
        elif self.tenant_id is not None:
            if isinstance(self.tenant_id, (list, tuple, set, frozenset)):
                query._tenant_override = {int(t) for t in self.tenant_id}
            else:
                query._tenant_override = int(self.tenant_id)
        return query

    def _get_tenant_id(self) -> Optional[int]:
        """
        获取组织 ID（兼容语义：显式 tenant_id 优先，否则取当前上下文）。

        仅用于 ``create()`` 写入归属等历史语义；查询过滤本身由
        ``_tenant_override`` 钉住，不再依赖本方法拼接条件。
        """
        if self.skip_tenant_filter:
            return None
        if self.tenant_id is not None:
            return self.tenant_id
        return get_current_tenant_id()

    def filter(self, **kwargs) -> QuerySet[T]:
        """添加过滤条件（组织条件由强制机制注入）。"""
        return self._pin(self.model.filter(**kwargs))

    def all(self) -> QuerySet[T]:
        """获取所有记录（组织条件由强制机制注入）。"""
        return self._pin(self.model.all())

    def get(self, **kwargs):
        """获取单条记录（组织条件由强制机制注入）。"""
        return self._pin(self.model.get(**kwargs))

    def get_or_none(self, **kwargs):
        """获取单条记录或 None（组织条件由强制机制注入）。"""
        return self._pin(self.model.get_or_none(**kwargs))

    def create(self, **kwargs):
        """
        创建记录（自动设置 tenant_id）

        实例级 ``create()`` 不走 QuerySet 路径（spec 143 已知未覆盖面），
        因此这里保留「按上下文回填 tenant_id」的历史语义。
        """
        if "tenant_id" not in kwargs:
            tenant_id = self._get_tenant_id()
            if isinstance(tenant_id, (list, tuple, set, frozenset)):
                # 集合型 pin 只允许查询侧（tenant_id__in）；写进字段是 bug
                raise ValueError(
                    "TenantQuerySet.create() 不支持集合型组织 pin（仅限查询侧），"
                    "请显式传入单个 tenant_id"
                )
            if tenant_id is None and model_is_tenant_scoped(self.model):
                # 租户作用域模型不允许无归属创建（否则该行对所有组织不可见）
                raise ValueError(
                    f"TenantQuerySet.create() 无法为租户模型 {self.model.__name__} "
                    "解析组织归属：请显式传入 tenant_id，或先在上下文中设置组织"
                )
            if tenant_id is not None:
                kwargs["tenant_id"] = tenant_id
        return self.model.create(**kwargs)

    def count(self) -> int:
        """统计记录数量（组织条件由强制机制注入）。"""
        return self.all().count()


def get_tenant_queryset(
    model: type[T],
    tenant_id: Optional[int] = None,
    skip_tenant_filter: bool = False
) -> TenantQuerySet[T]:
    """
    获取组织查询集（兼容门面）

    底层强制隔离由 ``TenantEnforcedQuerySet`` 提供；tenant_id /
    skip_tenant_filter 仅钉住该返回对象的单链过滤态。

    Args:
        model: 数据模型类
        tenant_id: 组织 ID（可选，钉住该链只查该组织）
        skip_tenant_filter: 该链放开组织过滤（兼容参数，建议改用 unscoped scope）

    Returns:
        TenantQuerySet[T]: 组织查询集实例
    """
    return TenantQuerySet(model, tenant_id=tenant_id, skip_tenant_filter=skip_tenant_filter)


async def require_tenant_for_query() -> int:
    """
    要求必须有组织上下文才能执行查询

    用于需要组织隔离的查询场景。

    Returns:
        int: 当前组织 ID

    Raises:
        ValueError: 当组织上下文未设置时抛出
    """
    return await require_tenant_context()
