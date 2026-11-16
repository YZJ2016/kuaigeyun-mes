#!/usr/bin/env python3
"""上游同步回归扫描：宿主财务路径不得回流到本仓。

本仓财务权威实现是 ``apps.kuaicaiwu``（上游已迁往 ``apps.kuaizhizao.finance``）。
上游同步时若整段粘贴上游代码，容易把下列仅存在于上游的模块路径带进来，
运行期会 ImportError：

- ``apps.kuaizhizao.finance``（宿主财务包，本仓不存在）
- ``apps.common.optional_pro``（上游 optional_pro 门禁抽象，本仓用
  ``apps.common.app_orm`` 的 ``finance_orm_ready``/``require_app_orm``）

发现即失败。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

PATTERN = re.compile(
    r"(?:from|import)\s+apps\.kuaizhizao\.finance\b|"
    r"(?:from|import)\s+apps\.common\.optional_pro\b|"
    r"import_pro_attr\(|import_pro_module\(|pro_orm_ready\(|pro_app_available\("
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-on", choices=("high", "medium", "low"), default="high")
    args = parser.parse_args()
    if args.fail_on != "high":
        print("only --fail-on high is supported", file=sys.stderr)
        return 2

    hits: list[str] = []
    for path in SRC.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if PATTERN.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{i}:{line.strip()[:120]}")

    if hits:
        print(
            "上游宿主财务路径回流；本仓财务实现为 apps.kuaicaiwu，"
            "门禁请用 apps.common.app_orm：\n"
        )
        print("\n".join(hits))
        return 1
    print("scan_host_finance_path_leaks: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
