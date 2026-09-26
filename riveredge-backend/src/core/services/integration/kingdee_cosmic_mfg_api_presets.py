"""
金蝶AI苍穹 · 制造链路 OpenAPI 预设（销售→生产→库存出入库→即时库存）。

数据文件：core/config/kingdee_cosmic_mfg_api_presets.json
由目标环境探活后的可用接口导出；换票仍由应用连接器自动完成，不含 getToken。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from core.services.integration.kingdee_cosmic_api_presets import KingdeeCosmicApiPreset

_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "kingdee_cosmic_mfg_api_presets.json"
)


@lru_cache(maxsize=1)
def _load_pack() -> Dict[str, Any]:
    if not _CONFIG_PATH.is_file():
        return {"presets": []}
    raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {"presets": []}


def list_kingdee_cosmic_mfg_api_presets() -> List[KingdeeCosmicApiPreset]:
    """返回制造链路接口预设（只读副本）。"""
    presets = _load_pack().get("presets") or []
    items: List[KingdeeCosmicApiPreset] = []
    for row in presets:
        if not isinstance(row, dict):
            continue
        code_suffix = str(row.get("code_suffix") or "").strip()
        path = str(row.get("path") or "").strip()
        name = str(row.get("name") or "").strip()
        if not code_suffix or not path or not name:
            continue
        item: KingdeeCosmicApiPreset = {
            "code_suffix": code_suffix,
            "name": name,
            "description": str(row.get("description") or name),
            "path": path,
            "method": str(row.get("method") or "POST").upper(),
            "request_body": row.get("request_body")
            if isinstance(row.get("request_body"), dict)
            else {},
        }
        params = row.get("request_params")
        if isinstance(params, dict) and params:
            item["request_params"] = params
        items.append(item)
    return items


def get_kingdee_cosmic_mfg_pack_meta() -> Dict[str, str]:
    pack = _load_pack()
    return {
        "pack_id": str(pack.get("pack_id") or "kingdee_cosmic_mfg"),
        "title": str(pack.get("title") or "金蝶AI苍穹·制造链路"),
        "description": str(
            pack.get("description")
            or "销售订单到出库及即时库存的苍穹 OpenAPI（已探活可用）。"
        ),
    }


__all__ = [
    "get_kingdee_cosmic_mfg_pack_meta",
    "list_kingdee_cosmic_mfg_api_presets",
]
