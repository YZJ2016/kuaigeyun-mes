"""研发交付物目录与文件名校验（26.9.1 P1）。

失败即报 ValidationError，禁止静默改名或读侧补丁。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from infra.exceptions.exceptions import ValidationError

# 交付物类型 → 命名规则 profile key
PART_SPEC_TYPES = frozenset({"part_spec", "component_spec"})
SOFTWARE_SPEC_TYPES = frozenset({"software_spec", "sw_spec"})
SCHEMATIC_GERBER_TYPES = frozenset(
    {
        "schematic",
        "gerber",
        "schematic_gerber",
        "layout",
        "panelization",
        "panel",
    }
)
DRAWING_3D_TYPES = frozenset({"drawing_3d", "3d_drawing"})
DRAWING_2D_TYPES = frozenset({"drawing_2d", "2d_drawing", "drawing_cad", "drawing_pdf"})
STRUCTURE_DRAWING_TYPES = DRAWING_3D_TYPES | DRAWING_2D_TYPES
STRUCTURE_DRAWING_BUSINESS_TYPE = "structure_drawing"
STRUCTURE_CATALOG_TYPES = frozenset(
    {
        "mold_dfm",
        "mold_drawing",
        "mold_acceptance",
        "reliability_report",
        "mold_repair",
    }
)
MOLD_REPAIR_TYPES = frozenset({"mold_repair"})
TEST_REPORT_PART_TYPES = frozenset({"test_report_part", "test_report", "test"})
TEST_REPORT_COMPLETE_TYPES = frozenset({"test_report_complete"})
TEST_REPORT_TYPES = TEST_REPORT_PART_TYPES | TEST_REPORT_COMPLETE_TYPES

_VERSION_SUFFIX_RE = re.compile(
    r"[_\-\s]?[vV]?([A-Z]\d{1,2}|[Rr]\d{1,3}|\d+\.\d+)\s*$"
)
_MATERIAL_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-\.]{2,79}$")
# 版本段：A1 / R02 / 1.0 / V1.05
_VERSION_TOKEN_RE = re.compile(
    r"^[Vv]?([A-Z]\d{1,2}|[Rr]\d{1,3}|\d+(?:\.\d+)*)$",
    re.IGNORECASE,
)
_DATE_TOKEN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}|\d{8})$")


def is_part_spec_type(
    deliverable_type: Optional[str],
    naming_rules: Optional[Dict[str, Any]] = None,
) -> bool:
    dtype = (deliverable_type or "").strip().lower()
    if not dtype:
        return False
    rules = naming_rules or {}
    extra = rules.get("part_spec_types") if isinstance(rules, dict) else None
    return dtype in PART_SPEC_TYPES or dtype in (extra or [])


def is_software_spec_type(
    deliverable_type: Optional[str],
    naming_rules: Optional[Dict[str, Any]] = None,
) -> bool:
    dtype = (deliverable_type or "").strip().lower()
    if not dtype:
        return False
    rules = naming_rules or {}
    extra = rules.get("software_spec_types") if isinstance(rules, dict) else None
    return dtype in SOFTWARE_SPEC_TYPES or dtype in (extra or [])


def is_test_report_part_type(
    deliverable_type: Optional[str],
    naming_rules: Optional[Dict[str, Any]] = None,
) -> bool:
    dtype = (deliverable_type or "").strip().lower()
    if not dtype:
        return False
    rules = naming_rules or {}
    extra = rules.get("test_report_part_types") if isinstance(rules, dict) else None
    return dtype in TEST_REPORT_PART_TYPES or dtype in (extra or [])


def is_test_report_complete_type(
    deliverable_type: Optional[str],
    naming_rules: Optional[Dict[str, Any]] = None,
) -> bool:
    dtype = (deliverable_type or "").strip().lower()
    if not dtype:
        return False
    rules = naming_rules or {}
    extra = rules.get("test_report_complete_types") if isinstance(rules, dict) else None
    return dtype in TEST_REPORT_COMPLETE_TYPES or dtype in (extra or [])


def is_schematic_gerber_type(
    deliverable_type: Optional[str],
    naming_rules: Optional[Dict[str, Any]] = None,
) -> bool:
    dtype = (deliverable_type or "").strip().lower()
    if not dtype:
        return False
    rules = naming_rules or {}
    extra = rules.get("schematic_gerber_types") if isinstance(rules, dict) else None
    return dtype in SCHEMATIC_GERBER_TYPES or dtype in (extra or [])


def _require_material_code(material_code: Optional[str], *, label: str) -> str:
    code = (material_code or "").strip()
    if not code:
        raise ValidationError(f"{label}须填写关联料号")
    if not _MATERIAL_CODE_RE.match(code):
        raise ValidationError(f"{label}料号格式不合法: {code}")
    return code


def is_structure_drawing_type(deliverable_type: Optional[str]) -> bool:
    dtype = (deliverable_type or "").strip().lower()
    return bool(dtype) and dtype in STRUCTURE_DRAWING_TYPES


def skips_deliverable_signoff(deliverable_type: Optional[str]) -> bool:
    """模具资料、可靠性报告、修模资料：上传即生效，不走交付物会签。"""
    dtype = (deliverable_type or "").strip().lower()
    return bool(dtype) and dtype in STRUCTURE_CATALOG_TYPES


def deliverable_approval_business_type(deliverable_type: Optional[str]) -> str:
    if is_structure_drawing_type(deliverable_type):
        return STRUCTURE_DRAWING_BUSINESS_TYPE
    return (deliverable_type or "").strip().lower()


def _require_version_suffix(file_name: Optional[str], *, label: str) -> None:
    name = (file_name or "").strip()
    if not name:
        raise ValidationError(f"{label}须上传文件并填写文件名")
    base = name.rsplit(".", 1)[0] if "." in name else name
    if not _VERSION_SUFFIX_RE.search(base):
        raise ValidationError(f"{label}文件名须带版本后缀（如 _A1 / _R02 / _1.0）: {name}")


def _require_prefix_version_date_filename(
    file_name: Optional[str],
    *,
    prefix: Optional[str],
    label: str,
    prefix_label: str,
) -> None:
    """「前缀_版本号_更新日期」（例：PCB001_A1_20260926.zip）。"""
    name = (file_name or "").strip()
    if not name:
        raise ValidationError(f"{label}须上传文件并填写文件名")
    code = (prefix or "").strip()
    if not code:
        raise ValidationError(f"{label}须填写{prefix_label}")
    if not name.startswith(code):
        raise ValidationError(f"{label}文件名须以{prefix_label} {code} 开头")
    base = name.rsplit(".", 1)[0] if "." in name else name
    remainder = base[len(code) :]
    example = f"{code}_A1_20260926"
    if not remainder.startswith("_"):
        raise ValidationError(
            f"{label}文件名须为「{prefix_label}_版本号_更新日期」格式（例：{example}.pdf）"
        )
    parts = [p for p in remainder.lstrip("_").split("_") if p]
    if len(parts) < 2:
        raise ValidationError(
            f"{label}文件名须为「{prefix_label}_版本号_更新日期」格式（例：{example}.pdf）"
        )
    version_token = parts[0]
    date_token = parts[-1]
    if not _VERSION_TOKEN_RE.match(version_token):
        raise ValidationError(f"{label}版本段不合法（如 A1 / R02 / 1.0）: {version_token}")
    if not _DATE_TOKEN_RE.match(date_token):
        raise ValidationError(
            f"{label}更新日期须为 YYYYMMDD 或 YYYY-MM-DD: {date_token}"
        )


def _require_date_suffix(file_name: Optional[str], *, label: str) -> None:
    name = (file_name or "").strip()
    if not name:
        raise ValidationError(f"{label}须上传文件并填写文件名")
    base = name.rsplit(".", 1)[0] if "." in name else name
    if not re.search(r"(?:^|[_-])(\d{4}-\d{2}-\d{2}|\d{8})$", base):
        raise ValidationError(
            f"{label}文件名须带日期后缀（如 _20261004 或 _2026-10-04）: {name}"
        )


def _require_software_spec_filename(
    file_name: Optional[str],
    *,
    project_code: Optional[str],
) -> None:
    _require_prefix_version_date_filename(
        file_name,
        prefix=project_code,
        label="软件规格书",
        prefix_label="项目代号",
    )


def _require_schematic_gerber_filename(
    file_name: Optional[str],
    *,
    pcb_code: Optional[str],
) -> None:
    _require_prefix_version_date_filename(
        file_name,
        prefix=pcb_code,
        label="原理图/Layout/Gerber",
        prefix_label="PCB料号",
    )


def validate_deliverable_catalog(
    *,
    deliverable_type: Optional[str],
    material_code: Optional[str],
    legacy_material_code: Optional[str],
    file_name: Optional[str],
    project_code: Optional[str] = None,
    naming_rules: Optional[Dict[str, Any]] = None,
) -> None:
    """按交付物类型校验料号目录与文件名；naming_rules 来自行业 profile。"""
    dtype = (deliverable_type or "").strip().lower()
    if not dtype:
        return

    rules = naming_rules or {}
    if dtype in PART_SPEC_TYPES or dtype in rules.get("part_spec_types", []):
        _require_material_code(material_code, label="部品规格书")
        if legacy_material_code:
            legacy = legacy_material_code.strip()
            if legacy and not _MATERIAL_CODE_RE.match(legacy):
                raise ValidationError(f"沿用旧料号格式不合法: {legacy}")
        if file_name:
            code = material_code.strip()
            if code not in file_name and not file_name.startswith(code):
                raise ValidationError(f"部品规格书文件名须以料号 {code} 开头或在路径中包含该料号")
        return

    if is_test_report_part_type(dtype, rules):
        _require_material_code(material_code, label="部品测试报告")
        if legacy_material_code:
            legacy = legacy_material_code.strip()
            if legacy and not _MATERIAL_CODE_RE.match(legacy):
                raise ValidationError(f"沿用旧料号格式不合法: {legacy}")
        return

    if is_test_report_complete_type(dtype, rules):
        _require_material_code(material_code, label="整机测试报告")
        return

    if dtype in SOFTWARE_SPEC_TYPES or dtype in rules.get("software_spec_types", []):
        if file_name:
            _require_software_spec_filename(file_name, project_code=project_code)
        elif not (project_code or "").strip():
            raise ValidationError("软件规格书须关联有项目代号的研发项目")
        return

    if dtype in SCHEMATIC_GERBER_TYPES or dtype in rules.get("schematic_gerber_types", []):
        pcb = _require_material_code(material_code, label="原理图/Layout/Gerber（PCB料号）")
        if file_name:
            _require_schematic_gerber_filename(file_name, pcb_code=pcb)
        return

    if dtype in MOLD_REPAIR_TYPES:
        _require_date_suffix(file_name, label="修模资料")
        return

    if dtype in DRAWING_3D_TYPES or dtype in DRAWING_2D_TYPES:
        _require_version_suffix(file_name, label="结构图纸")
