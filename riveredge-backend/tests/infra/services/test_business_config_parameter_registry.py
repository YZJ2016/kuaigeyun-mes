"""配置中心参数注册表回归：废弃 multi_unit、工具栏改角色权限、IMPLEMENTED 对齐。"""

from pathlib import Path
import re

import pytest

from infra.exceptions.exceptions import ValidationError
from infra.services.business_config_service import (
    DEFAULT_PARAMETERS,
    DEPRECATED_PARAMETER_KEYS,
    IMPLEMENTED_PARAMETER_KEYS,
    PARAMETER_KEYS,
    PROCESS_KEYS,
    BusinessConfigService,
    strip_deprecated_parameters,
)

TOOLBAR_KEYS = {
    "parameters.work_order.toolbar_sync_enabled",
    "parameters.work_order.toolbar_push_enabled",
    "parameters.reporting.toolbar_sync_enabled",
    "parameters.reporting.toolbar_push_enabled",
    "parameters.sales.toolbar_sync_enabled",
    "parameters.sales.toolbar_push_enabled",
    "parameters.purchase.toolbar_sync_enabled",
    "parameters.purchase.toolbar_push_enabled",
    "parameters.warehouse.toolbar_sync_enabled",
    "parameters.warehouse.toolbar_push_enabled",
}

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFIG_TREE = (
    REPO_ROOT
    / "riveredge-frontend"
    / "src"
    / "pages"
    / "system"
    / "config-center"
    / "configTree.ts"
)


def test_strip_deprecated_removes_multi_unit():
    params = {
        "warehouse": {"multi_unit": True, "fifo": True, "toolbar_sync_enabled": True},
        "sales": {
            "require_contract_before_order": True,
            "sales_review": {},
            "toolbar_push_enabled": False,
        },
    }
    strip_deprecated_parameters(params)
    assert "multi_unit" not in params["warehouse"]
    assert "toolbar_sync_enabled" not in params["warehouse"]
    assert params["warehouse"]["fifo"] is True
    assert "require_contract_before_order" not in params["sales"]
    assert "toolbar_push_enabled" not in params["sales"]
    assert "sales_review" in params["sales"]


def test_multi_unit_deprecated_and_not_registered():
    assert "multi_unit" in DEPRECATED_PARAMETER_KEYS.get("warehouse", frozenset())
    assert "parameters.warehouse.multi_unit" not in PARAMETER_KEYS
    assert "parameters.warehouse.multi_unit" not in IMPLEMENTED_PARAMETER_KEYS
    assert "multi_unit" not in DEFAULT_PARAMETERS.get("warehouse", {})


@pytest.mark.asyncio
async def test_update_process_parameter_rejects_multi_unit(monkeypatch):
    svc = BusinessConfigService()

    class _Tenant:
        id = 1
        settings = {"business_config": {"parameters": {"warehouse": {}}}}

    async def _get_or_none(**_kwargs):
        return _Tenant()

    monkeypatch.setattr(
        "infra.services.business_config_service.Tenant.get_or_none",
        _get_or_none,
    )
    with pytest.raises(ValidationError, match="已废弃"):
        await svc.update_process_parameter(1, "warehouse", "multi_unit", True)


def test_toolbar_keys_removed_from_business_config_registry():
    for key in TOOLBAR_KEYS:
        assert key not in PARAMETER_KEYS, key
        assert key not in IMPLEMENTED_PARAMETER_KEYS, key
        category, name = key.replace("parameters.", "").split(".", 1)
        assert name not in DEFAULT_PARAMETERS.get(category, {})
        assert name in DEPRECATED_PARAMETER_KEYS.get(category, frozenset())


def test_implemented_subset_of_registry():
    registry = PARAMETER_KEYS | PROCESS_KEYS
    orphan = IMPLEMENTED_PARAMETER_KEYS - registry
    assert not orphan, f"IMPLEMENTED 有未注册键: {sorted(orphan)}"


def test_config_tree_hides_toolbar_and_multi_unit():
    text = CONFIG_TREE.read_text(encoding="utf-8")
    for key in TOOLBAR_KEYS:
        assert f"sourcePath: '{key}'" not in text
        assert f'sourcePath: "{key}"' not in text
    assert "warehouse.multi_unit" not in text
    assert "parameters.warehouse.multi_unit" not in text


def test_config_tree_business_source_paths_are_registered():
    text = CONFIG_TREE.read_text(encoding="utf-8")
    paths = set(re.findall(r"sourcePath:\s*'(parameters\.[^']+)'", text))
    registry = PARAMETER_KEYS | PROCESS_KEYS
    missing = sorted(p for p in paths if p not in registry)
    assert not missing, f"configTree 有未注册 sourcePath: {missing}"
