"""账表设计器：custom 配置、版本快照不覆盖、预览交给 executeReport。"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from copy import deepcopy

import pytest
from tortoise.exceptions import IntegrityError

from apps.kuaireport.slices import s147_designer as designer
from infra.domain.tenant_context import clear_tenant_context, set_current_tenant_id
from infra.exceptions.exceptions import NotFoundError, ValidationError


class _State:
    def __init__(self):
        self.sources: list[dict] = []
        self.reports: list[dict] = []
        self.versions: list[dict] = []
        self.queries: list[str] = []
        self.next_id = 1
        self.fail_version = False


class _Conn:
    def __init__(self, state: _State):
        self.state = state
        self._reports = deepcopy(state.reports)
        self._versions = deepcopy(state.versions)
        self._next_id = state.next_id

    def rollback(self) -> None:
        self.state.reports = self._reports
        self.state.versions = self._versions
        self.state.next_id = self._next_id

    async def execute_query_dict(self, sql: str, params=None):
        text = " ".join(sql.split()).lower()
        self.state.queries.append(text)
        if "dashboard_versions" in text or "share_password" in text:
            raise AssertionError(text)
        values = list(params or [])
        if "insert into apps_kuaireport_report_versions" in text:
            if self.state.fail_version:
                raise RuntimeError("version insert failed")
            snapshot = json.loads(values[4])
            self.state.versions.append(
                {
                    "tenant_id": values[1],
                    "report_id": values[2],
                    "version_no": values[3],
                    "snapshot": snapshot,
                    "note": values[5],
                    "created_by_user_id": values[6],
                }
            )
            return []
        if "insert into apps_kuaireport_reports" in text:
            tenant_id, code = values[1], values[2]
            if any(row["tenant_id"] == tenant_id and row["code"] == code for row in self.state.reports):
                raise IntegrityError("uid_apps_kuaireport_reports_tenant_code")
            if "'custom'" not in text:
                raise AssertionError("insert must set category custom")
            report_id = self.state.next_id
            self.state.next_id += 1
            row = {
                "id": report_id,
                "tenant_id": tenant_id,
                "code": code,
                "name": values[3],
                "category": "custom",
                "current_version": 1,
                "report_config": json.loads(values[4]),
            }
            self.state.reports.append(row)
            return [dict(row)]
        if text.startswith("update apps_kuaireport_reports"):
            config = json.loads(values[0])
            version_no, name, report_id, tenant_id = values[1], values[2], values[5], values[6]
            for row in self.state.reports:
                if row["id"] == report_id and row["tenant_id"] == tenant_id and row["category"] == "custom":
                    row["report_config"] = config
                    row["current_version"] = version_no
                    row["name"] = name
                    return [dict(row)]
            return []
        if "from apps_kuaireport_data_sources" in text:
            source_uuid, tenant_id = values
            return [
                {"id": row["id"], "uuid": row["uuid"], "type": row["type"]}
                for row in self.state.sources
                if row["uuid"] == source_uuid and row["tenant_id"] == tenant_id
            ]
        if "for update" in text:
            report_id, tenant_id = values
            return [
                {
                    "id": row["id"],
                    "category": row["category"],
                    "current_version": row["current_version"],
                    "code": row["code"],
                    "name": row["name"],
                }
                for row in self.state.reports
                if row["id"] == report_id and row["tenant_id"] == tenant_id
            ]
        if "from apps_kuaireport_reports" in text:
            report_id, tenant_id = values
            return [
                dict(row)
                for row in self.state.reports
                if row["id"] == report_id and row["tenant_id"] == tenant_id
            ]
        raise AssertionError(text)


def _install(monkeypatch, state: _State) -> None:
    @asynccontextmanager
    async def _tx():
        conn = _Conn(state)
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise

    monkeypatch.setattr(designer, "in_transaction", lambda: _tx())


@pytest.fixture
def tenant_id():
    set_current_tenant_id(3)
    yield 3
    clear_tenant_context()


SOURCE_UUID = "11111111-1111-4111-8111-111111111111"


def _source(
    state: _State,
    source_id: int = 4,
    tenant: int = 3,
    source_type: str = "static",
    source_uuid: str = SOURCE_UUID,
) -> None:
    state.sources.append(
        {"id": source_id, "uuid": source_uuid, "tenant_id": tenant, "type": source_type}
    )


def _payload(**overrides):
    body = {
        "code": "custom_qty",
        "name": "数量账",
        "page_size": 20,
        "data_source_uuid": SOURCE_UUID,
        "fields": [{"field": "qty", "label": "数量", "format": "number"}],
        "filters": [{"field": "biz_date", "label": "日期", "operator": "between"}],
        "summary_fields": ["qty"],
        "note": None,
        "created_by": 7,
        "created_by_name": "管理员",
        "created_by_user_id": 7,
    }
    body.update(overrides)
    return body


def test_report_config_matches_uni_report_schema():
    config = designer.build_report_config(
        page_size=20,
        fields=[{"field": "qty", "label": "数量", "format": "money", "width": 120, "visible": True}],
        filters=[{"field": "biz_date", "label": "日期", "operator": "between"}],
        summary_fields=["qty"],
    )
    assert config["page_size"] == 20
    assert config["fields"][0]["format"] == "money"
    assert config["filters"][0]["operator"] == "between"
    assert config["extra"]["uni_report"]["summaryFields"] == ["qty"]
    assert "select" not in json.dumps(config).lower()


def test_sql_in_column_is_rejected():
    with pytest.raises(ValidationError):
        designer.build_report_config(
            page_size=10,
            fields=[{"field": "qty", "label": "select * from t"}],
            filters=[],
            summary_fields=[],
        )


@pytest.mark.parametrize(
    "label",
    [
        "select * from t",
        "1; drop table apps_kuaireport_reports",
        "a union select b",
        "x' or delete from t",
        "insert into t values (1)",
        "alter table t add c int",
        "truncate table t",
        "exec sp_help(",
    ],
)
def test_sql_statement_shapes_are_still_rejected(label):
    with pytest.raises(ValidationError):
        designer.build_report_config(
            page_size=10,
            fields=[{"field": "qty", "label": label}],
            filters=[],
            summary_fields=[],
        )


def test_sql_like_words_in_names_are_allowed():
    """字段名 / 文案含 select、update、sql 字样不再是拒绝理由。"""
    config = designer.build_report_config(
        page_size=10,
        fields=[
            {"field": "selected_qty", "label": "已选数量"},
            {"field": "sql_text", "label": "SQL 备注"},
        ],
        filters=[{"field": "updated_at", "label": "更新时间", "operator": "between"}],
        summary_fields=["selected_qty"],
    )
    assert config["fields"][1]["field"] == "sql_text"
    assert config["filters"][0]["field"] == "updated_at"


@pytest.mark.asyncio
async def test_save_creates_custom_and_version_snapshot(monkeypatch, tenant_id):
    state = _State()
    _source(state)
    _install(monkeypatch, state)

    saved = await designer.save_custom_report(**_payload())

    assert saved["category"] == "custom"
    assert saved["current_version"] == 1
    assert saved["version_no"] == 1
    assert saved["report_config"]["extra"]["uni_report"]["summaryFields"] == ["qty"]
    assert saved["report_config"]["extra"]["data_source_uuid"] == SOURCE_UUID
    assert "data_source_id" not in saved["report_config"]
    assert state.reports[0]["category"] == "custom"
    assert state.versions[0]["version_no"] == 1
    assert state.versions[0]["tenant_id"] == tenant_id
    assert state.versions[0]["snapshot"] == saved["report_config"]
    assert state.versions[0]["note"] is None
    assert state.versions[0]["created_by_user_id"] == 7
    assert all("dashboard_versions" not in sql for sql in state.queries)
    assert all("share_password" not in sql for sql in state.queries)


@pytest.mark.asyncio
async def test_second_save_appends_version_and_keeps_previous_snapshot(monkeypatch, tenant_id):
    state = _State()
    _source(state)
    _install(monkeypatch, state)

    first = await designer.save_custom_report(**_payload())
    second = await designer.save_custom_report(
        **_payload(report_id=first["report_id"], name="数量账改", summary_fields=["qty", "amt"])
    )

    assert second["version_no"] == 2
    assert second["current_version"] == 2
    assert state.reports[0]["category"] == "custom"
    assert [row["version_no"] for row in state.versions] == [1, 2]
    assert state.versions[0]["snapshot"]["extra"]["uni_report"]["summaryFields"] == ["qty"]
    assert state.versions[1]["snapshot"]["extra"]["uni_report"]["summaryFields"] == ["qty", "amt"]
    assert not any(sql.startswith("update apps_kuaireport_report_versions") for sql in state.queries)
    assert not any("delete from apps_kuaireport_report_versions" in sql for sql in state.queries)


@pytest.mark.asyncio
async def test_version_insert_failure_leaves_transaction(monkeypatch, tenant_id):
    state = _State()
    _source(state)
    state.fail_version = True
    _install(monkeypatch, state)

    with pytest.raises(RuntimeError, match="version insert failed"):
        await designer.save_custom_report(**_payload())

    assert state.reports == []
    assert state.versions == []


@pytest.mark.asyncio
async def test_other_tenant_source_is_not_written(monkeypatch, tenant_id):
    state = _State()
    _source(state, source_id=9, tenant=8, source_uuid="22222222-2222-4222-8222-222222222222")
    _install(monkeypatch, state)

    with pytest.raises(NotFoundError):
        await designer.save_custom_report(
            **_payload(data_source_uuid="22222222-2222-4222-8222-222222222222")
        )

    assert state.reports == []
    assert state.versions == []


@pytest.mark.asyncio
@pytest.mark.parametrize("source_type", ["static", "dataset", "http"])
async def test_registered_source_types_can_save(monkeypatch, tenant_id, source_type):
    state = _State()
    _source(state, source_type=source_type)
    _install(monkeypatch, state)

    saved = await designer.save_custom_report(**_payload(code=f"c_{source_type}"))

    assert saved["category"] == "custom"
    assert len(state.versions) == 1


@pytest.mark.asyncio
async def test_unknown_source_type_is_rejected(monkeypatch, tenant_id):
    state = _State()
    _source(state, source_type="sql")
    _install(monkeypatch, state)

    with pytest.raises(ValidationError, match="static"):
        await designer.save_custom_report(**_payload())

    assert state.reports == []


@pytest.mark.asyncio
async def test_no_tenant_context_does_not_query(monkeypatch):
    clear_tenant_context()
    state = _State()
    entered = {"n": 0}

    @asynccontextmanager
    async def _tx():
        entered["n"] += 1
        yield _Conn(state)

    monkeypatch.setattr(designer, "in_transaction", lambda: _tx())

    with pytest.raises(designer.TenantContextError):
        await designer.save_custom_report(**_payload())

    assert entered["n"] == 0
    assert state.queries == []


@pytest.mark.asyncio
async def test_system_report_save_does_not_change_category(monkeypatch, tenant_id):
    state = _State()
    _source(state)
    state.reports.append(
        {
            "id": 5,
            "tenant_id": tenant_id,
            "code": "inv_ledger",
            "name": "库存台账",
            "category": "system",
            "current_version": 0,
            "report_config": {"page_size": 20, "fields": [], "filters": [], "extra": {"uni_report": {"summaryFields": []}}},
        }
    )
    state.next_id = 6
    _install(monkeypatch, state)

    with pytest.raises(ValidationError, match="只能查看"):
        await designer.save_custom_report(**_payload(report_id=5, code="inv_ledger"))

    assert state.reports[0]["category"] == "system"
    assert state.versions == []
    assert not any(sql.startswith("update apps_kuaireport_reports") for sql in state.queries)


@pytest.mark.asyncio
async def test_view_system_report_does_not_write_version(monkeypatch, tenant_id):
    state = _State()
    state.reports.append(
        {
            "id": 5,
            "tenant_id": tenant_id,
            "code": "inv_ledger",
            "name": "库存台账",
            "category": "system",
            "current_version": 0,
            "report_config": {
                "page_size": 20,
                "fields": [],
                "filters": [],
                "extra": {"uni_report": {"summaryFields": []}},
            },
        }
    )
    _install(monkeypatch, state)

    viewed = await designer.load_report_for_view(5)

    assert viewed["category"] == "system"
    assert viewed["version_no"] is None
    assert state.versions == []
    assert not any("insert into" in sql for sql in state.queries)


@pytest.mark.asyncio
async def test_duplicate_code_does_not_keep_a_new_version(monkeypatch, tenant_id):
    state = _State()
    _source(state)
    state.reports.append(
        {
            "id": 1,
            "tenant_id": tenant_id,
            "code": "custom_qty",
            "name": "已有",
            "category": "custom",
            "current_version": 3,
            "report_config": {},
        }
    )
    state.next_id = 2
    _install(monkeypatch, state)

    with pytest.raises(ValidationError, match="编码已存在"):
        await designer.save_custom_report(**_payload())

    assert len(state.reports) == 1
    assert state.versions == []


@pytest.mark.asyncio
async def test_update_rejects_code_change(monkeypatch, tenant_id):
    """code 是租户内唯一列：更新时传不同 code 明确报错，不静默忽略。"""
    state = _State()
    _source(state)
    _install(monkeypatch, state)

    first = await designer.save_custom_report(**_payload())

    with pytest.raises(ValidationError, match="编码"):
        await designer.save_custom_report(
            **_payload(report_id=first["report_id"], code="other_code")
        )

    assert state.reports[0]["code"] == "custom_qty"
    assert len(state.versions) == 1


def test_router_has_no_restore_share_or_dashboard():
    paths = [getattr(route, "path", "") for route in designer.router.routes]
    assert paths
    blob = " ".join(paths)
    assert "restore" not in blob
    assert "share" not in blob
    assert "dashboard" not in blob
