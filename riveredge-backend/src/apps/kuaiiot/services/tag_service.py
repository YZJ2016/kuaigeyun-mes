"""点位映射与预填目标校验。"""

from typing import Optional

from apps.kuaiiot.constants import MONITOR_COLUMNS, OTHER_PARAMETERS_PREFIX
from infra.exceptions.exceptions import ValidationError

_FILL_PREFIXES = ("sop_parameters.", "spot_check.")


def _validate_map_target(map_target: str) -> str:
    text = (map_target or "").strip()
    if text in MONITOR_COLUMNS:
        return text
    if text.startswith(OTHER_PARAMETERS_PREFIX):
        key = text[len(OTHER_PARAMETERS_PREFIX) :]
        if key and "." not in key and key.replace("_", "").isalnum():
            return text
    raise ValidationError("点位只能映射到监控字段")


def _validate_fill_target(fill_target: Optional[str]) -> Optional[str]:
    if fill_target is None:
        return None
    text = str(fill_target).strip()
    if not text:
        return None
    for prefix in _FILL_PREFIXES:
        suffix = text[len(prefix) :] if text.startswith(prefix) else ""
        if suffix and " " not in suffix and "." not in suffix:
            return text
    raise ValidationError("fill_target 仅允许 sop_parameters.* 或 spot_check.*")


class TagService:
    _validate_map_target = staticmethod(_validate_map_target)
    _validate_fill_target = staticmethod(_validate_fill_target)
