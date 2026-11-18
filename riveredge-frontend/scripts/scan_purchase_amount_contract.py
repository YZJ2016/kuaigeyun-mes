#!/usr/bin/env python3
"""
采购价税契约守门：禁止把库内未税 total_price/total_amount 直传含税 item_amount；禁止页面旁路入库 settlement 唯一入口。

用法:
  python scripts/scan_purchase_amount_contract.py
  python scripts/scan_purchase_amount_contract.py --fail-on high

规则见 .cursor/memory/features/document-amount-unified-contract.md
真源: purchaseOrderAmounts.computePurchaseReceiptLineSettlementAmounts + purchaseStoredExclAsFormItemAmount
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

SKIP_PARTS = {"node_modules", "locales", "__snapshots__"}

# 库内 total_price/total_amount 为未税；含税 item_amount 表示价税合计
RAW_EXCL_AS_ITEM_AMOUNT = re.compile(
    r"item_amount\s*:\s*[^,\n}]*\b(?:total_price|poi\.total_price|row\.total_amount)\b",
    re.IGNORECASE,
)

# 采购入库/订单页禁止直接拆税或比例分摊（须走 settlement 唯一入口）
BYPASS_SETTLEMENT_IMPORT = re.compile(
    r"import\s*\{[^}]*\b(?:proportionalLineGross|resolvePurchaseReceiptLineExclAmount)\b",
)

CANONICAL_AMOUNT_FILE = "purchase-management/shared/purchaseOrderAmounts.ts"
CANONICAL_TEST = "purchaseOrderAmounts.test.ts"

ALLOW_ITEM_AMOUNT_LINE = re.compile(
    r"purchaseStoredExclAsFormItemAmount|itemAmount\s*!=\s*null\s*\?\s*\{\s*item_amount",
)


@dataclass
class Finding:
    severity: str
    rule: str
    path: str
    line: int
    snippet: str


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def iter_ts_files() -> list[Path]:
    out: list[Path] = []
    for path in SRC.rglob("*"):
        if path.suffix not in (".ts", ".tsx") or not path.is_file():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if ".test." in path.name and CANONICAL_TEST not in path.name:
            continue
        out.append(path)
    return out


def scan_file(path: Path) -> list[Finding]:
    text = path.read_text(encoding="utf-8", errors="replace")
    r = rel(path)
    findings: list[Finding] = []

    if CANONICAL_AMOUNT_FILE in r.replace("\\", "/"):
        return []

    for i, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("//") or line.startswith("*"):
            continue

        if RAW_EXCL_AS_ITEM_AMOUNT.search(raw_line):
            if ALLOW_ITEM_AMOUNT_LINE.search(raw_line):
                continue
            if "purchaseStoredExclAsFormItemAmount" in text and "item_amount" not in raw_line:
                continue
            findings.append(
                Finding(
                    "high",
                    "stored_excl_as_inclusive_item_amount",
                    r,
                    i,
                    line[:200],
                )
            )

    if BYPASS_SETTLEMENT_IMPORT.search(text):
        if ("warehouse-management/inbound" in r or "purchase-management/purchase-orders" in r) and (
            "computePurchaseReceiptLineSettlementAmounts" not in text
        ):
            m = BYPASS_SETTLEMENT_IMPORT.search(text)
            if m:
                line_no = text[: m.start()].count("\n") + 1
                findings.append(
                    Finding(
                        "high",
                        "bypass_purchase_receipt_settlement_entry",
                        r,
                        line_no,
                        m.group(0)[:200],
                    )
                )

    if "warehouse-management/inbound" in r and path.suffix == ".tsx":
        if "resolvePurchaseReceiptLineAmounts" in text and "computePurchaseReceiptLineSettlementAmounts" not in text:
            findings.append(
                Finding(
                    "high",
                    "purchase_receipt_page_must_use_settlement_entry",
                    r,
                    1,
                    "入库页须使用 computePurchaseReceiptLineSettlementAmounts，禁止直调 resolvePurchaseReceiptLineAmounts",
                )
            )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-on", choices=("high", "medium", "low"), default="high")
    args = parser.parse_args()
    rank = {"low": 0, "medium": 1, "high": 2}

    all_findings: list[Finding] = []
    for path in iter_ts_files():
        all_findings.extend(scan_file(path))

    for f in sorted(all_findings, key=lambda x: (x.path, x.line)):
        print(f"[{f.severity}] {f.rule} {f.path}:{f.line} {f.snippet}")

    failing = [f for f in all_findings if rank[f.severity] >= rank[args.fail_on]]
    if failing:
        print(f"\nscan_purchase_amount_contract: {len(failing)} finding(s) >= {args.fail_on}", file=sys.stderr)
        return 1
    print(f"scan_purchase_amount_contract: ok ({len(all_findings)} informational)")
    return 0


if __name__ == "__main__":
    sys.exit(main())