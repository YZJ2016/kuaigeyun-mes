from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from apps.kuaizhizao.services.qms_clause_presets.iatf16949 import (
    IATF16949_2016_PRESET,
    IATF16949_2016_STANDARD,
)
from apps.kuaizhizao.services.qms_clause_presets.iso14001 import (
    ISO14001_2015_PRESET,
    ISO14001_2015_STANDARD,
)
from apps.kuaizhizao.services.qms_clause_presets.iso45001 import (
    ISO45001_2018_PRESET,
    ISO45001_2018_STANDARD,
)
from apps.kuaizhizao.services.qms_clause_presets.iso9001 import (
    ISO9001_2015_PRESET,
    ISO9001_2015_STANDARD,
)
from apps.kuaizhizao.services.qms_clause_presets.types import ClausePresetItem

PRESET_REGISTRY: Dict[str, Tuple[str, str, List[ClausePresetItem]]] = {
    ISO9001_2015_STANDARD: ("ISO 9001:2015 质量管理体系", "iso9001", ISO9001_2015_PRESET),
    ISO14001_2015_STANDARD: ("ISO 14001:2015 环境管理体系", "iso14001", ISO14001_2015_PRESET),
    ISO45001_2018_STANDARD: ("ISO 45001:2018 职业健康安全管理体系", "iso45001", ISO45001_2018_PRESET),
    IATF16949_2016_STANDARD: ("IATF 16949:2016 汽车质量管理体系", "iatf16949", IATF16949_2016_PRESET),
}


def resolve_preset(standard_code: str) -> Optional[Tuple[str, str, List[ClausePresetItem]]]:
    key = (standard_code or "").strip()
    if not key:
        return None
    return PRESET_REGISTRY.get(key)
