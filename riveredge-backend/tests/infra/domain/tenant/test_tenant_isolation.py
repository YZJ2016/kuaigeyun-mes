"""spec 143：租户查询强制隔离机制级测试。

覆盖：
- 无上下文读 / `.filter().update()` / `.filter().delete()` 失败关闭
- 租户上下文自动注入组织条件（含生成 SQL 证据）
- 错租户读 / queryset 写不可见
- `with_tenant` 切换与嵌套还原
- `unscoped` 显式跨组织 + 结构化日志/审计证据
- 平台级模型 opt-out
- `TenantQuerySet` 兼容门面
"""

import asyncio

import pytest
import pytest_asyncio
from loguru import logger
from tortoise import Tortoise, fields
from tortoise.models import Model

from infra.domain import tenant_context
from infra.domain.tenant_context import (
    TenantContextError,
    clear_tenant_context,
    clear_request_actor,
    get_current_tenant_id,
    set_current_tenant_id,
    set_request_actor,
    unscoped,
    with_tenant,
)
from infra.domain.tenant_isolation import TenantIsolationMixin, model_is_tenant_scoped
from infra.domain.query_filter import get_tenant_queryset


class IsoWidget(TenantIsolationMixin, Model):
    """强制隔离测试模型（租户作用域）。"""

    id = fields.IntField(pk=True)
    tenant_id = fields.IntField(null=True, index=True)
    name = fields.CharField(max_length=32)

    class Meta:
        table = "t_iso_widget"


class IsoPlatformThing(TenantIsolationMixin, Model):
    """平台级 opt-out 测试模型。"""

    id = fields.IntField(pk=True)
    tenant_id = fields.IntField(null=True)
    name = fields.CharField(max_length=32)

    class Meta:
        table = "t_iso_platform_thing"
        tenant_isolation = "platform"


class IsoPlainModel(TenantIsolationMixin, Model):
    """无 tenant_id 字段的模型：不属于强制隔离范围。"""

    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=32)

    class Meta:
        table = "t_iso_plain"


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def tortoise_db():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": [__name__]})
    await Tortoise.generate_schemas()
    # 实例级 create() 不经过 QuerySet 路径（已知未覆盖面），可直接播种
    await IsoWidget.create(tenant_id=1, name="w1-a")
    await IsoWidget.create(tenant_id=1, name="w1-b")
    await IsoWidget.create(tenant_id=2, name="w2-a")
    await IsoPlatformThing.create(tenant_id=None, name="p1")
    await IsoPlainModel.create(name="plain")
    yield
    await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_no_context_read_fails_closed(tortoise_db):
    for op in (
        lambda: IsoWidget.all(),
        lambda: IsoWidget.filter(name="w1-a"),
        lambda: IsoWidget.get_or_none(name="w1-a"),
        lambda: IsoWidget.filter(name="w1-a").exists(),
        lambda: IsoWidget.all().count(),
        lambda: IsoWidget.all().values("id"),
        lambda: IsoWidget.all().first(),
        lambda: IsoWidget.all().values_list("id", flat=True),
    ):
        with pytest.raises(TenantContextError):
            await op()


@pytest.mark.asyncio
async def test_no_context_queryset_write_fails_closed(tortoise_db):
    with pytest.raises(TenantContextError):
        await IsoWidget.filter(name="w1-a").update(name="x")
    with pytest.raises(TenantContextError):
        await IsoWidget.filter(name="w1-a").delete()
    with pytest.raises(TenantContextError):
        await IsoWidget.all().bulk_update([], fields=["name"])


@pytest.mark.asyncio
async def test_tenant_context_injects_condition_in_sql(tortoise_db):
    async with with_tenant(1):
        sql = IsoWidget.all().sql()
        # 断言注入的是 tenant_id=1 条件，而非仅某处出现数字 1
        compact = sql.replace(" ", "")
        assert '"tenant_id"' in sql and '"tenant_id"=1' in compact
        update_sql = IsoWidget.filter(name="w1-a").update(name="x").sql()
        assert '"tenant_id"' in update_sql
        delete_sql = IsoWidget.filter(name="w1-a").delete().sql()
        assert '"tenant_id"' in delete_sql


@pytest.mark.asyncio
async def test_ambient_context_injects_condition(tortoise_db):
    """ambient ``set_current_tenant_id`` 路径同样注入组织条件。"""
    set_current_tenant_id(1)
    try:
        sql = IsoWidget.all().sql()
        assert '"tenant_id"=1' in sql.replace(" ", "")
        assert await IsoWidget.filter(name="w1-a").exists()
        assert await IsoWidget.get_or_none(name="w2-a") is None
    finally:
        clear_tenant_context()


@pytest.mark.asyncio
async def test_retry_same_queryset_still_fails_closed(tortoise_db):
    """fail-open 回归：同一 QuerySet 对象首次 await 抛 TenantContextError 后，
    再次 await 仍须失败关闭——``_tenant_filter_done`` 不在 raise 前置位。"""
    qs = IsoWidget.filter(name="w1-a")
    with pytest.raises(TenantContextError):
        await qs
    with pytest.raises(TenantContextError):
        await qs
    # 补上上下文后同一对象重新求值并可正常执行
    async with with_tenant(1):
        assert {r.name for r in await qs} == {"w1-a"}


@pytest.mark.asyncio
async def test_concurrent_tasks_scopes_isolated(tortoise_db):
    """两个协程各自 with_tenant 并行执行互不串扰（ContextVar 按 task 快照隔离）。"""

    async def names_for(tid: int) -> set:
        async with with_tenant(tid):
            await asyncio.sleep(0)  # 让出事件循环制造交错
            return {r.name for r in await IsoWidget.all()}

    n1, n2 = await asyncio.gather(names_for(1), names_for(2))
    assert "w2-a" not in n1 and n1
    assert n2 == {"w2-a"}


@pytest.mark.asyncio
async def test_wrong_tenant_cannot_read_or_write(tortoise_db):
    async with with_tenant(1):
        names = {r.name for r in await IsoWidget.all()}
        assert names == {"w1-a", "w1-b"}
        # 错租户读 / 显式错组织过滤均不可见
        assert await IsoWidget.get_or_none(name="w2-a") is None
        assert await IsoWidget.filter(tenant_id=2).count() == 0
        # queryset update/delete 只命中本组织行
        await IsoWidget.filter(name="w2-a").update(name="hacked")
        await IsoWidget.filter(name="w2-a").delete()
    async with with_tenant(2):
        assert await IsoWidget.filter(name="w2-a").exists()


@pytest.mark.asyncio
async def test_tenant_bound_context_filters_and_writes(tortoise_db):
    async with with_tenant(1):
        await IsoWidget.filter(name="w1-a").update(name="w1-a2")
        assert await IsoWidget.filter(name="w1-a2").count() == 1
        await IsoWidget.filter(name="w1-b").delete()
        assert await IsoWidget.all().count() == 1


@pytest.mark.asyncio
async def test_with_tenant_switches_and_nests(tortoise_db):
    async with with_tenant(1):
        assert get_current_tenant_id() == 1
        async with with_tenant(2):
            assert get_current_tenant_id() == 2
            assert {r.name for r in await IsoWidget.all()} == {"w2-a"}
        assert get_current_tenant_id() == 1
        async with with_tenant(3):
            assert await IsoWidget.all().count() == 0


@pytest.mark.asyncio
async def test_unscoped_sees_all_and_audits(tortoise_db, monkeypatch):
    audits = []

    async def fake_audit(actor, kind, reason, target_tenant_id, resource=""):
        audits.append((actor, kind, reason, target_tenant_id, resource))

    monkeypatch.setattr(tenant_context, "_write_scope_audit_row", fake_audit)
    records = []
    sink_id = logger.add(lambda m: records.append(str(m)), level="WARNING")
    try:
        set_request_actor("user", 7, 1)
        async with unscoped(reason="test-cross-tenant", resource="IsoWidget"):
            # 跨组织可见：能看到两个组织的全部行（前置测试已删 w1-b、改名 w1-a）
            assert {r.name for r in await IsoWidget.all()} == {"w1-a2", "w2-a"}
        # create_task 调度的审计协程需要让出一次事件循环
        await asyncio.sleep(0)
    finally:
        clear_request_actor()
        logger.remove(sink_id)
    assert audits and audits[0][1] == "unscoped" and audits[0][2] == "test-cross-tenant"
    assert audits[0][4] == "IsoWidget"
    assert any("tenant_scope_unscoped" in r and "test-cross-tenant" in r for r in records)


@pytest.mark.asyncio
async def test_unscoped_internal_no_audit_row(tortoise_db, monkeypatch):
    """无请求操作者时仍写审计行，字段含 reason 与资源。"""
    audits = []
    real_write = tenant_context._write_scope_audit_row

    async def fake_audit(actor, kind, reason, target_tenant_id, resource=""):
        audits.append(
            {"actor": actor, "kind": kind, "reason": reason, "resource": resource}
        )

    monkeypatch.setattr(tenant_context, "_write_scope_audit_row", fake_audit)
    async with unscoped(reason="internal-startup", resource="startup-scan"):
        pass
    await asyncio.sleep(0)
    assert audits
    assert audits[0]["reason"] == "internal-startup"
    assert audits[0]["resource"] == "startup-scan"
    assert audits[0]["actor"][0] == "system"

    created = []

    async def fake_create(**kwargs):
        created.append(kwargs)

    from core.models.operation_log import OperationLog

    monkeypatch.setattr(OperationLog, "create", fake_create)
    await real_write(
        ("system", 0, 0),
        "unscoped",
        "internal-startup",
        None,
        "startup-scan",
    )
    assert created[0]["operation_object_type"] == "startup-scan"
    assert created[0]["user_id"] == 0
    assert created[0]["tenant_id"] == 0
    assert "reason=internal-startup" in created[0]["operation_content"]
    assert "resource=startup-scan" in created[0]["operation_content"]
    assert "actor=system:startup-scan" in created[0]["operation_content"]


@pytest.mark.asyncio
async def test_unscoped_requires_reason(tortoise_db):
    with pytest.raises(ValueError):
        unscoped(reason="", resource="IsoWidget")
    with pytest.raises(ValueError):
        unscoped(reason="ok", resource="")


@pytest.mark.asyncio
async def test_platform_optout_queryable_without_context(tortoise_db):
    assert await IsoPlatformThing.all().count() == 1
    assert await IsoPlatformThing.filter(name="p1").exists()
    assert await IsoPlainModel.all().count() == 1


@pytest.mark.asyncio
async def test_model_classification(tortoise_db):
    assert model_is_tenant_scoped(IsoWidget) is True
    assert model_is_tenant_scoped(IsoPlatformThing) is False
    assert model_is_tenant_scoped(IsoPlainModel) is False


@pytest.mark.asyncio
async def test_datascope_style_filter_does_not_bypass_isolation(tortoise_db):
    """组织内行权限（DataScope 语义：如 created_by 过滤）不能替代组织间隔离。

    叠加「本人数据」式过滤后，强制注入的 tenant_id 条件仍然生效——
    组织内裁剪发生在组织间隔离之后，而不是替代它。
    """
    async with with_tenant(1):
        sql = IsoWidget.filter(name="w1-a2").sql()
        assert '"tenant_id"' in sql
        # 模拟 DataScope 组织内裁剪条件叠加：依然只见本组织行
        assert await IsoWidget.filter(name="w1-a2").count() == 1
        assert await IsoWidget.all().count() == 1  # w1-b 已在前置用例删除


@pytest.mark.asyncio
async def test_get_tenant_queryset_facade(tortoise_db, monkeypatch):
    async with with_tenant(1):
        qs = get_tenant_queryset(IsoWidget)
        assert await qs.count() == 1
        with pytest.raises(TenantContextError):
            await get_tenant_queryset(IsoWidget, tenant_id=2).count()
        assert await get_tenant_queryset(IsoWidget, tenant_id=1).count() == 1

        def fail_audit(*args, **kwargs):
            raise RuntimeError("audit-required")

        monkeypatch.setattr(
            "infra.domain.tenant_isolation._emit_scope_audit", fail_audit
        )
        with pytest.raises(RuntimeError):
            await get_tenant_queryset(IsoWidget, skip_tenant_filter=True).count()

    recorded = []

    def spy(kind, reason, target_tenant_id, resource=""):
        recorded.append((kind, reason, resource))
        return True

    monkeypatch.setattr("infra.domain.tenant_isolation._emit_scope_audit", spy)
    async with with_tenant(1):
        assert await get_tenant_queryset(IsoWidget, skip_tenant_filter=True).count() == 2
    assert any(
        item[0] == "skip_tenant_filter" and item[2] == "IsoWidget" for item in recorded
    )

    # 无当前组织、仅显式 tenant_id：限定到该组织并审计，不失败关闭。
    clear_tenant_context()
    recorded.clear()
    assert await get_tenant_queryset(IsoWidget, tenant_id=2).count() == 1
    assert any(item[0] == "explicit_tenant" and item[2] == "IsoWidget" for item in recorded)


@pytest.mark.asyncio
async def test_set_clear_compat_inside_scope(tortoise_db):
    async with with_tenant(1):
        set_current_tenant_id(5)
        # ambient 被显式 scope 覆盖：查询与身份仍以 scope 为准
        assert get_current_tenant_id() == 1
        assert await IsoWidget.all().count() == 1
        clear_tenant_context()
        assert get_current_tenant_id() == 1
    # 防 ambient 泄漏到其他用例
    clear_tenant_context()


@pytest.mark.asyncio
async def test_bulk_update_inherits_tenant_condition(tortoise_db):
    """spec 143 F3 实测：Tortoise 0.21.1 ``BulkUpdateQuery._make_query`` 将
    queryset ``_q_objects`` 并入 WHERE（``resolve_filters``）——注入的组织
    条件对 bulk_update 生效，他组织对象不会被命中。"""
    async with unscoped(reason="test-seed", resource="IsoWidget"):
        t1 = await IsoWidget.create(tenant_id=1, name="bulk-t1")
        t2 = await IsoWidget.create(tenant_id=2, name="bulk-t2")
    try:
        async with with_tenant(1):
            sql = IsoWidget.all().bulk_update([t1], fields=["name"]).sql()
            assert '"tenant_id"' in sql
            # 本组织对象生效
            t1.name = "bulk-t1x"
            await IsoWidget.all().bulk_update([t1], fields=["name"])
            # 他组织对象被注入的 tenant_id 条件挡掉，不生效
            t2.name = "bulk-t2x"
            await IsoWidget.all().bulk_update([t2], fields=["name"])
            assert await IsoWidget.filter(name="bulk-t1x").count() == 1
            assert await IsoWidget.filter(name="bulk-t2x").count() == 0
        async with unscoped(reason="test-verify", resource="IsoWidget"):
            assert (await IsoWidget.get(id=t2.id)).name == "bulk-t2"
    finally:
        async with unscoped(reason="test-cleanup", resource="IsoWidget"):
            await IsoWidget.filter(id__in=[t1.id, t2.id]).delete()


@pytest.mark.asyncio
async def test_facade_pin_ignored_on_non_scoped_models(tortoise_db):
    """spec 143 F5：非租户作用域模型忽略单链 pin——不注入恒空条件、
    不对无 tenant_id 字段模型产生 FieldError。"""
    assert await get_tenant_queryset(IsoPlatformThing, tenant_id=99).all().count() == 1
    assert await get_tenant_queryset(IsoPlainModel, tenant_id=99).all().count() == 1
    assert (
        await get_tenant_queryset(IsoPlatformThing, skip_tenant_filter=True).all().count()
        == 1
    )


@pytest.mark.asyncio
async def test_facade_create_rejects_ambiguous_tenant(tortoise_db):
    """spec 143 F5：集合型 pin 仅查询侧可用；作用域模型无归属 create 失败关闭。"""
    async with with_tenant(1):
        with pytest.raises(ValueError):
            await get_tenant_queryset(IsoWidget, tenant_id=[1, 2]).create(name="bad-set")
        with pytest.raises(ValueError):
            await get_tenant_queryset(IsoWidget, skip_tenant_filter=True).create(name="bad-none")
        # 显式单值 pin 仍可正常创建
        obj = await get_tenant_queryset(IsoWidget, tenant_id=1).create(name="facade-ok")
        assert obj.tenant_id == 1
        async with unscoped(reason="test-cleanup", resource="IsoWidget"):
            await IsoWidget.filter(id=obj.id).delete()


def test_registered_tenant_models_have_enforced_manager():
    """spec 143 F6 漏挂扫描回归：真实 TORTOISE_ORM 注册清单中，凡有
    ``tenant_id`` 字段且未声明 ``Meta.tenant_isolation="platform"`` 的模型，
    默认 manager 必须是 ``TenantEnforcedManager``——挡住未来
    「直接继承 Model + tenant_id 字段」的静默逃逸。"""
    import importlib

    from tortoise.models import Model as TortoiseModel

    from infra.infrastructure.database.database import TORTOISE_ORM
    from infra.domain.tenant_isolation import (
        TENANT_ISOLATION_PLATFORM,
        TenantEnforcedManager,
    )

    modules = TORTOISE_ORM["apps"]["models"]["models"]
    violations: list[str] = []
    scoped = 0
    opt_out: list[str] = []
    for module_path in modules:
        module = importlib.import_module(module_path)
        for name, obj in vars(module).items():
            if not (
                isinstance(obj, type)
                and issubclass(obj, TortoiseModel)
                and obj is not TortoiseModel
            ):
                continue
            meta = getattr(obj, "_meta", None)
            if meta is None or getattr(meta, "abstract", False):
                continue
            if "tenant_id" not in getattr(meta, "fields_map", {}):
                continue
            if (
                getattr(getattr(obj, "Meta", None), "tenant_isolation", None)
                == TENANT_ISOLATION_PLATFORM
            ):
                opt_out.append(f"{module_path}.{name}")
                continue
            scoped += 1
            if not isinstance(meta.manager, TenantEnforcedManager):
                violations.append(f"{module_path}.{name}")
    assert scoped > 0, "注册清单中未发现任何租户作用域模型——扫描失效"
    assert violations == [], (
        f"{len(violations)} 个租户模型未挂 TenantEnforcedManager: {violations}"
    )
