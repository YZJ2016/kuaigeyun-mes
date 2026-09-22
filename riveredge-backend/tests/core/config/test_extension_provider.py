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
