"""扩展提供方：manifest 声明 industry_extensions 的已启用模块（行业插件或定制应用）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config.industry_extension_registry import parse_industry_extensions


def app_code_to_python_package(app_code: str) -> str:
    """manifest code → Python 包名（apps 目录下文件夹）。"""
    return str(app_code or "").strip().replace("-", "_")


def manifest_declares_extensions(manifest: Dict[str, Any]) -> bool:
    raw = manifest.get("industry_extensions")
    return isinstance(raw, list) and len(raw) > 0


def load_manifest_by_code(app_code: str) -> Optional[Dict[str, Any]]:
    apps_dir = Path(__file__).resolve().parents[2] / "apps"
    if not apps_dir.is_dir():
        return None
    target = str(app_code or "").strip()
    for plugin_dir in apps_dir.iterdir():
        if not plugin_dir.is_dir():
            continue
        manifest_file = plugin_dir / "manifest.json"
        if not manifest_file.exists():
            continue
        try:
            with open(manifest_file, encoding="utf-8") as handle:
                data = json.load(handle)
            if str(data.get("code") or "") == target:
                return data
        except (json.JSONDecodeError, OSError):
            continue
    return None


def is_extension_provider_manifest(manifest: Dict[str, Any] | None) -> bool:
    return bool(manifest and manifest_declares_extensions(manifest))


def is_extension_provider_app_code(app_code: str | None) -> bool:
    manifest = load_manifest_by_code(str(app_code or ""))
    return is_extension_provider_manifest(manifest)


def extension_declarations_for_app(app_code: str) -> List[Any]:
    manifest = load_manifest_by_code(app_code)
    if not manifest:
        return []
    return parse_industry_extensions(app_code, manifest)
