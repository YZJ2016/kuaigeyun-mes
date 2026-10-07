"""扩展提供方判定与 hooks 加载。"""

import json
from pathlib import Path

from core.config.extension_hooks_loader import resolve_profile_seed_from_hooks
from core.config.extension_provider import (
    is_extension_provider_app_code,
    manifest_declares_extensions,
)


def _electronics_manifest() -> dict:
    path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "apps"
        / "ind_electronics"
        / "manifest.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_ind_electronics_is_extension_provider():
    manifest = _electronics_manifest()
    assert manifest_declares_extensions(manifest)
    assert is_extension_provider_app_code("ind-electronics")


def test_kuaiplm_is_not_extension_provider():
    assert not is_extension_provider_app_code("kuaiplm")


def test_hooks_resolve_sample_process_seed():
    seed = resolve_profile_seed_from_hooks("ind-electronics", "kuaiplm.sample_process")
    assert seed is not None
    kinds = {x["code"] for x in seed.get("request_kinds") or []}
    assert "stencil" in kinds or "smt" in kinds or "gerber" in kinds or "general" in kinds


def test_hooks_resolve_trial_flow_seed():
    seed = resolve_profile_seed_from_hooks("ind-electronics", "kuaiplm.trial_flow")
    assert seed is not None
    component = seed.get("step_templates", {}).get("component") or []
    keys = [x.get("step_key") for x in component]
    assert keys == [
        "rd_manager",
        "purchasing",
        "production_trial",
        "production_feedback",
    ]
    header_keys = {x.get("key") for x in seed.get("header_fields") or []}
    assert "designator" in header_keys
    assert "urgency_level" in header_keys


def test_hooks_resolve_rd_deliverable_seed():
    seed = resolve_profile_seed_from_hooks("ind-electronics", "kuaiplm.rd_deliverable")
    assert seed is not None
    rules = seed.get("naming_rules") or {}
    assert "part_spec" in (rules.get("part_spec_types") or [])
    assert "component_spec" in (rules.get("part_spec_types") or [])
    drawing_codes = {x.get("code") for x in seed.get("drawing_types") or []}
    assert "drawing_silkscreen" in drawing_codes
    customer_codes = {x.get("code") for x in seed.get("customer_doc_types") or []}
    assert "customer_spec" in customer_codes
