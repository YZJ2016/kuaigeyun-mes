#!/usr/bin/env python3
"""
前后端 manifest 镜像一致性扫描。

契约（.cursor/rules/manifest-unique-source.mdc）：
  后端 src/apps/<app>/manifest.json 是唯一真源；前端镜像由
  sync_frontend_manifests_from_backend.py 生成，禁止手改。

规则:
  high   — permissions 集合漂移（fe-only / be-only 权限码）
  medium — 其它顶层键内容不一致 / 前端镜像文件缺失
  info   — permissions 集合一致但顺序不同（sync 可消除）

用法:
  python scripts/scan_manifest_frontend_parity.py
  python scripts/scan_manifest_frontend_parity.py --fail-on high
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_APPS = REPO_ROOT / "riveredge-backend" / "src" / "apps"
FRONTEND_APPS = REPO_ROOT / "riveredge-frontend" / "src" / "apps"


@dataclass
class Finding:
    rule_id: str
    severity: str
    path: str
    message: str


def _frontend_manifest(backend_app: str) -> Path:
    return FRONTEND_APPS / backend_app.replace("_", "-") / "manifest.json"


def run_scan() -> list[Finding]:
    findings: list[Finding] = []
    for entry in sorted(BACKEND_APPS.iterdir()):
        be_path = entry / "manifest.json"
        if not entry.is_dir() or not be_path.exists():
            continue
        app = entry.name
        fe_path = _frontend_manifest(app)
        if not fe_path.parent.exists():
            continue  # 无前端应用目录（后端专属包）
        rel = str(fe_path.relative_to(REPO_ROOT))
        if not fe_path.exists():
            findings.append(
                Finding(
                    "frontend_manifest_missing",
                    "medium",
                    rel,
                    f"应用 {app} 存在前端目录但缺 manifest 镜像",
                )
            )
            continue
        try:
            be = json.loads(be_path.read_text(encoding="utf-8"))
            fe = json.loads(fe_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(Finding("manifest_json_invalid", "high", rel, str(exc)))
            continue

        be_perms = set(be.get("permissions") or [])
        fe_perms = set(fe.get("permissions") or [])
        fe_only = sorted(fe_perms - be_perms)
        be_only = sorted(be_perms - fe_perms)
        if fe_only:
            findings.append(
                Finding(
                    "frontend_only_permissions",
                    "high",
                    rel,
                    f"前端独有权限码（唯一源外漂移）: {', '.join(fe_only)}",
                )
            )
        if be_only:
            findings.append(
                Finding(
                    "backend_only_permissions",
                    "high",
                    rel,
                    f"前端镜像缺失权限码: {', '.join(be_only)}",
                )
            )
        if not fe_only and not be_only and (be.get("permissions") or []) != (
            fe.get("permissions") or []
        ):
            findings.append(
                Finding(
                    "permissions_order_drift",
                    "info",
                    rel,
                    "permissions 集合一致但顺序漂移（sync 可消除）",
                )
            )

        for key in sorted(set(be) | set(fe)):
            if key == "permissions":
                continue
            if be.get(key) != fe.get(key):
                findings.append(
                    Finding(
                        "manifest_field_drift",
                        "medium",
                        rel,
                        f"顶层键 `{key}` 与后端不一致",
                    )
                )
    return findings


def filter_findings(
    findings: list[Finding], *, min_severity: str | None = None
) -> list[Finding]:
    rank = {"high": 3, "medium": 2, "info": 1}
    min_rank = rank.get((min_severity or "").lower(), 0)
    return [f for f in findings if rank.get(f.severity, 0) >= min_rank]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="前后端 manifest 镜像一致性扫描")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument(
        "--fail-on",
        choices=("high", "medium", "info", "none"),
        default="high",
        help="违规达到该级别则退出码 1",
    )
    args = parser.parse_args(argv)

    all_findings = run_scan()
    fail_level = None if args.fail_on == "none" else args.fail_on
    active = filter_findings(all_findings, min_severity=fail_level)

    by_severity: dict[str, int] = {}
    for f in all_findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

    report = {
        "summary": {"total": len(all_findings), "active": len(active), "by_severity": by_severity},
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
                print(f"  {f.path} [{f.rule_id}] {f.message}")
        if active and fail_level:
            print(f"\n未通过: --fail-on {fail_level}")

    if fail_level and active:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
