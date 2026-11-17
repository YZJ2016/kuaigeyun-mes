#!/usr/bin/env python3
"""
扫描路由显式权限码 ↔ manifest permissions[] 对齐。

require_permission_codes("app:module:action") 引用的码必须已在以下来源声明：
  - 任一应用 manifest permissions[]
  - 应用入口码 {app}:entry:read（与 scan_manifest_permissions 一致）
  - reference display 码 {permission_prefix}:display（非 sensitive 引用资源）
  - 基线 system:* 权限（PermissionRegistryService.BASELINE_PERMISSION_CODES）

未声明的码在 RBAC 层无法被任何角色授予 → 路由恒 403，或存在拼写漂移。

用法:
  python scripts/scan_route_manifest_alignment.py
  python scripts/scan_route_manifest_alignment.py --fail-on high

规则:
  high   — 路由权限码未在任何已声明集合中 / 码格式非法
  medium — 扫描依赖导入失败（结果可能不完整）
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = REPO_ROOT / "riveredge-backend" / "src"
APPS_DIR = BACKEND_SRC / "apps"
SCAN_DIRS = ("apps", "core", "infra")

if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

# 引用 display 码与 require_permission_codes 同样可授予（ReferenceRegistryService）
DISPLAY_ACTION = "display"


@dataclass
class Finding:
    rule_id: str
    severity: str
    path: str
    line: int
    message: str
    snippet: str


def normalize_permission_code(code: str) -> str:
    """与 menu_resource_resolver 一致：trim + lower。"""
    return (code or "").strip().lower()


def _iter_string_args(node: ast.AST) -> list[tuple[str, int]]:
    """收集 Call.args 中的字符串常量（含 *[*codes] 展开的列表/元组）。"""
    out: list[tuple[str, int]] = []

    def visit(n: ast.AST) -> None:
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append((n.value, getattr(n, "lineno", 0)))
        elif isinstance(n, (ast.List, ast.Tuple, ast.Set)):
            for elt in n.elts:
                visit(elt)
        elif isinstance(n, ast.Starred):
            visit(n.value)

    if isinstance(node, ast.Call):
        for arg in node.args:
            visit(arg)
    return out


def _is_require_permission_codes(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "require_permission_codes"
    ) or (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "require_permission_codes"
    )


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _line_snippet(text: str, line: int) -> str:
    lines = text.splitlines()
    if 1 <= line <= len(lines):
        return lines[line - 1].strip()
    return ""


def _collect_reference_display_codes(manifest_data: dict) -> set[str]:
    """manifest reference_resources 非敏感资源派生 {permission_prefix}:display。"""
    out: set[str] = set()
    ref_block = manifest_data.get("reference_resources")
    if not isinstance(ref_block, dict):
        return out
    for raw in ref_block.values():
        if not isinstance(raw, dict):
            continue
        if bool(raw.get("sensitive", False)):
            continue
        prefix = normalize_permission_code(str(raw.get("permission_prefix") or ""))
        if prefix:
            out.add(f"{prefix}:{DISPLAY_ACTION}")
    return out


def _build_declared_codes(findings: list[Finding]) -> set[str]:
    """已声明权限码全集：manifest + 入口码 + reference display + 基线 system:*。"""
    declared: set[str] = set()
    for manifest_path in sorted(APPS_DIR.glob("*/manifest.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        app_code = str(data.get("code") or manifest_path.parent.name).strip().lower()
        if app_code:
            declared.add(f"{app_code}:entry:read")
        raw_permissions = data.get("permissions")
        if isinstance(raw_permissions, list):
            for item in raw_permissions:
                if isinstance(item, str):
                    norm = normalize_permission_code(item)
                    if norm:
                        declared.add(norm)
        declared.update(_collect_reference_display_codes(data))

    try:
        from core.config.core_reference_resources import CORE_REFERENCE_RESOURCES

        for spec in CORE_REFERENCE_RESOURCES.values():
            if not isinstance(spec, dict) or bool(spec.get("sensitive", False)):
                continue
            prefix = normalize_permission_code(str(spec.get("permission_prefix") or ""))
            if prefix:
                declared.add(f"{prefix}:{DISPLAY_ACTION}")
    except Exception as exc:
        findings.append(
            Finding(
                rule_id="route_manifest_scan_error",
                severity="medium",
                path="core/config/core_reference_resources.py",
                line=0,
                message=f"core 引用资源导入失败，display 码集合不完整: {exc}",
                snippet="",
            )
        )

    try:
        from core.services.authorization.permission_registry_service import (
            PermissionRegistryService,
        )

        declared.update(
            normalize_permission_code(code)
            for code in (
                *PermissionRegistryService.BASELINE_PERMISSION_CODES,
                *PermissionRegistryService.CORE_PERMISSION_CODES,
            )
        )
    except Exception as exc:
        # 基线导入失败时把 system:* 视为已声明，避免大面积误报；结果不完整须提示。
        findings.append(
            Finding(
                rule_id="route_manifest_scan_error",
                severity="medium",
                path="core/services/authorization/permission_registry_service.py",
                line=0,
                message=f"基线权限导入失败，system:* 未参与校验: {exc}",
                snippet="",
            )
        )
    return declared


def run_scan() -> list[Finding]:
    findings: list[Finding] = []
    declared = _build_declared_codes(findings)
    baseline_import_failed = any(
        f.rule_id == "route_manifest_scan_error" for f in findings
    )

    for top in SCAN_DIRS:
        scan_root = BACKEND_SRC / top
        if not scan_root.is_dir():
            continue
        for py_path in sorted(scan_root.rglob("*.py")):
            try:
                text = py_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            try:
                tree = ast.parse(text, filename=str(py_path))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not _is_require_permission_codes(node):
                    continue
                for lit, lit_line in _iter_string_args(node):
                    code = normalize_permission_code(lit)
                    if not code or "{" in code or "}" in code:
                        continue
                    line = lit_line or getattr(node, "lineno", 0)
                    parts = [p for p in code.split(":") if p]
                    if len(parts) < 3 or "*" in code:
                        findings.append(
                            Finding(
                                rule_id="route_permission_code_malformed",
                                severity="high",
                                path=_rel(py_path),
                                line=line,
                                message=f"路由权限码格式非法（须为 app:module:action 完整码）: {lit!r}",
                                snippet=_line_snippet(text, line),
                            )
                        )
                        continue
                    if baseline_import_failed and parts[0] == "system":
                        continue
                    if code in declared:
                        continue
                    # manifest 允许 app:module:* 通配声明时视为已声明
                    if f"{parts[0]}:{parts[1]}:*" in declared:
                        continue
                    findings.append(
                        Finding(
                            rule_id="route_permission_code_not_declared",
                            severity="high",
                            path=_rel(py_path),
                            line=line,
                            message=f"路由权限码未在任何 manifest/基线/引用资源声明: {code}",
                            snippet=_line_snippet(text, line),
                        )
                    )
    return findings


def filter_findings(
    findings: list[Finding],
    *,
    min_severity: str | None = None,
) -> list[Finding]:
    severity_rank = {"high": 3, "medium": 2, "info": 1}
    min_rank = severity_rank.get((min_severity or "").lower(), 0)
    return [f for f in findings if severity_rank.get(f.severity, 0) >= min_rank]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="扫描路由权限码 ↔ manifest 声明对齐")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument(
        "--fail-on",
        choices=("high", "medium", "info", "none"),
        default="high",
        help="违规达到该级别则退出码 1",
    )
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    all_findings = run_scan()
    fail_level = None if args.fail_on == "none" else args.fail_on
    active = filter_findings(all_findings, min_severity=fail_level)

    by_severity: dict[str, int] = {}
    for f in all_findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

    report = {
        "summary": {
            "total": len(all_findings),
            "active": len(active),
            "by_severity": by_severity,
        },
        "active": [asdict(f) for f in active],
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"扫描完成: 共 {len(all_findings)} 条, 待处理 {len(active)}")
        for sev in ("high", "medium", "info"):
            items = [f for f in active if f.severity == sev]
            if not items:
                continue
            print(f"\n[{sev.upper()}] {len(items)}")
            for f in items:
                print(f"  {f.path}:{f.line} [{f.rule_id}] {f.message}")
        if active and fail_level:
            print(f"\n未通过: --fail-on {fail_level}")

    if fail_level and active:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
