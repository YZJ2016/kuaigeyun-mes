"""
自定义字段 config 契约校验（唯一真源）

与管理端表单规则对齐：
- associated_object：必须有 associatedTable；
  - 有 sourceField → XLOOKUP，须 matchField + returnField，displayMode∈{display,input,number}
  - 无 sourceField → 下拉选记录，须 associatedField，displayMode∈{select,multiselect,radio}
- associated_attribute：须 associatedTable + attributeField，displayMode∈{select,multiselect,radio}

非持久化约定（derived / non-stored）：
- associated_object + displayMode=display + 有 sourceField
  → 表单实时 XLOOKUP 展示；不写字段值表；不参与详情/列表/检索/必填
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

ASSOCIATED_OBJECT_XLOOKUP_DISPLAY_MODES = frozenset({"display", "input", "number"})
ASSOCIATED_OBJECT_SELECT_DISPLAY_MODES = frozenset({"select", "multiselect", "radio"})
ASSOCIATED_ATTRIBUTE_DISPLAY_MODES = frozenset({"select", "multiselect", "radio"})


def _cfg_str(config: Mapping[str, Any], key: str) -> str:
    raw = config.get(key)
    if raw is None:
        return ""
    return str(raw).strip()


def is_associated_object_non_persisted(
    field_type: str,
    config: Optional[Mapping[str, Any]],
) -> bool:
    """关联对象「只读展示」：派生字段，不落库。"""
    if (field_type or "").strip() != "associated_object":
        return False
    cfg = config or {}
    return bool(_cfg_str(cfg, "sourceField")) and _cfg_str(cfg, "displayMode") == "display"


def apply_non_persisted_field_flags(field_data: Dict[str, Any]) -> Dict[str, Any]:
    """非持久化字段强制关闭必填/检索/排序（避免无效门禁与空列）。"""
    if not is_associated_object_non_persisted(
        str(field_data.get("field_type") or ""),
        field_data.get("config") if isinstance(field_data.get("config"), Mapping) else None,
    ):
        return field_data
    field_data["is_required"] = False
    field_data["is_searchable"] = False
    field_data["is_sortable"] = False
    return field_data


def validate_custom_field_config(
    field_type: str,
    config: Optional[Mapping[str, Any]],
) -> None:
    """
    校验字段类型与 config 是否一致。

    Raises:
        ValueError: 配置不完整或不合法（消息可直接返回前端）
    """
    cfg: Dict[str, Any] = dict(config or {})
    ft = (field_type or "").strip()

    if ft == "associated_object":
        _validate_associated_object(cfg)
    elif ft == "associated_attribute":
        _validate_associated_attribute(cfg)


def _validate_associated_object(config: Dict[str, Any]) -> None:
    associated_table = _cfg_str(config, "associatedTable")
    if not associated_table:
        raise ValueError("关联对象字段必须配置关联表（associatedTable）")

    source_field = _cfg_str(config, "sourceField")
    display_mode = _cfg_str(config, "displayMode")
    match_field = _cfg_str(config, "matchField")
    return_field = _cfg_str(config, "returnField")
    associated_field = _cfg_str(config, "associatedField")

    if source_field:
        if not match_field:
            raise ValueError("关联对象（源字段 XLOOKUP）必须配置匹配字段（matchField）")
        if not return_field:
            raise ValueError("关联对象（源字段 XLOOKUP）必须配置返回字段（returnField）")
        if display_mode and display_mode not in ASSOCIATED_OBJECT_XLOOKUP_DISPLAY_MODES:
            raise ValueError(
                "关联对象（源字段 XLOOKUP）展示方式须为 display / input / number"
            )
        return

    # 无源字段：下拉选关联记录
    if match_field or return_field:
        raise ValueError(
            "未配置源字段时不能填写匹配/返回字段；请选择源字段启用 XLOOKUP，或改为配置关联显示字段"
        )
    if display_mode and display_mode not in ASSOCIATED_OBJECT_SELECT_DISPLAY_MODES:
        raise ValueError(
            "关联对象（下拉选记录）展示方式须为 select / multiselect / radio；"
            "display / input / number 仅在配置了源字段时可用"
        )
    if not associated_field:
        raise ValueError("关联对象（下拉选记录）必须配置关联显示字段（associatedField）")


def _validate_associated_attribute(config: Dict[str, Any]) -> None:
    if not _cfg_str(config, "associatedTable"):
        raise ValueError("关联属性字段必须配置关联表（associatedTable）")
    if not _cfg_str(config, "attributeField"):
        raise ValueError("关联属性字段必须配置属性字段（attributeField）")
    display_mode = _cfg_str(config, "displayMode")
    if display_mode and display_mode not in ASSOCIATED_ATTRIBUTE_DISPLAY_MODES:
        raise ValueError("关联属性展示方式须为 select / multiselect / radio")
