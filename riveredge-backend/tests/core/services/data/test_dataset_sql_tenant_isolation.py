"""数据集 SQL 租户隔离：忽略 tenant_isolation=false，并外包组织条件。"""

from core.services.data.dataset_service import DatasetService


class _Config:
    def __init__(self, code: str, config: dict | None = None):
        self.code = code
        self._config = config or {}

    def get_config(self):
        return self._config


def test_system_default_ignores_tenant_isolation_false():
    cfg = _Config("system_default", {"_system_default": True})
    assert DatasetService._should_apply_sql_tenant_isolation(
        cfg, {"tenant_isolation": False}
    ) is True
    assert DatasetService._should_apply_sql_tenant_isolation(cfg, {}) is True


def test_third_party_without_tenant_column_stays_uninjected():
    """第三方连接没有明确的平台数据集分支：未标系统默认且未显式 true 时不外包。"""
    cfg = _Config("kingdee", {})
    assert DatasetService._should_apply_sql_tenant_isolation(
        cfg, {"tenant_isolation": False}
    ) is False
    assert DatasetService._should_apply_sql_tenant_isolation(cfg, {}) is False
    assert DatasetService._should_apply_sql_tenant_isolation(
        cfg, {"tenant_isolation": True}
    ) is True


def test_selected_columns_gain_tenant_id_before_outer_filter():
    sql = "SELECT code, name, type, supplier, brand FROM public.apps_kuaizhizao_equipment LIMIT 100"
    projected, injected = DatasetService._project_tenant_id_for_filter(sql)
    assert injected is True
    assert "brand, tenant_id FROM" in projected
    wrapped = DatasetService._inject_tenant_filter_sql(projected)
    inner, outer = wrapped.split(") AS dataset_q", 1)
    assert "tenant_id" in inner
    assert "LIMIT 100" in inner
    assert "WHERE dataset_q.tenant_id = :tenant_id" in outer


def test_star_and_existing_tenant_column_are_not_duplicated():
    star, injected_star = DatasetService._project_tenant_id_for_filter("SELECT * FROM equipment")
    assert injected_star is False
    assert star == "SELECT * FROM equipment"
    named, injected_named = DatasetService._project_tenant_id_for_filter(
        "SELECT code, tenant_id FROM equipment"
    )
    assert injected_named is False
    assert "tenant_id, tenant_id" not in named


def test_or_predicate_stays_inside_outer_tenant_filter():
    sql = "SELECT id, tenant_id FROM materials WHERE 1=1 OR tenant_id = 9 ORDER BY id LIMIT 5;"
    wrapped = DatasetService._inject_tenant_filter_sql(sql)
    inner, outer = wrapped.split(") AS dataset_q", 1)
    assert "WHERE 1=1 OR tenant_id = 9" in inner
    assert "ORDER BY id LIMIT 5" in inner
    assert not inner.strip().endswith(";")
    assert "WHERE dataset_q.tenant_id = :tenant_id" in outer
    assert "OR" not in outer


def test_param_name_avoids_user_sql_collision_and_binds_current_tenant():
    sql = "SELECT * FROM materials WHERE tenant_id = :tenant_id OR 1=1"
    name = DatasetService._tenant_filter_param_name(sql)
    assert name == "dataset_tenant_id"
    wrapped = DatasetService._inject_tenant_filter_sql(sql, param_name=name)
    params = DatasetService._build_sql_query_parameters(
        wrapped,
        {"parameters": {name: 8}},
        {"tenant_id": 9, name: 8},
        tenant_id=3,
        apply_tenant_isolation=True,
        fill_missing_sql_parameters=False,
        tenant_param_name=name,
    )
    assert f"dataset_q.tenant_id = :{name}" in wrapped
    assert params[name] == 3
    assert params["tenant_id"] == 9
