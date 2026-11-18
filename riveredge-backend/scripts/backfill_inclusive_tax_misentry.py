#!/usr/bin/env python3
"""
历史价税误存修正：用户按含税单价录入，系统按未税 qty×单价 再叠加税率。

默认（波次 1）：
- 采购入库行：purchase_order_item_id 为空、display_unit_price 为空、错账指纹匹配
- 采购订单行：price_type=tax_inclusive、display_unit_price 为空、错账指纹匹配
- 不修改已标记 frozen 的单据（状态含已审核/已完成等，或行 settlement 与应付占用由 --include-frozen 放开）

修正后：sync 行 settlement + 头表 rollup（与 purchase_settlement 同源）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

_backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_backend_root / "src"))

from dotenv import load_dotenv

load_dotenv(_backend_root / ".env")

FROZEN_RECEIPT_STATUSES = frozenset(
    {"已入库", "已完成", "已确认", "已过账", "已审核", "CONFIRMED", "COMPLETED"}
)
FROZEN_PO_STATUSES = frozenset(
    {"已审核", "已完成", "已确认", "AUDITED", "CONFIRMED", "COMPLETED"}
)


@dataclass
class LineSnapshot:
    kind: str
    tenant_id: int
    header_id: int
    line_id: int
    before: dict[str, Any]


def _money(d: Decimal) -> float:
    return float(d.quantize(Decimal("0.01")))


def _tax_pct(line_tax: Any, header_tax: Any) -> Decimal:
    from apps.kuaicaiwu.services.purchase_settlement import (
        normalize_po_tax_rate_to_percent,
    )

    from_line = normalize_po_tax_rate_to_percent(line_tax)
    if from_line > 0:
        return from_line
    return normalize_po_tax_rate_to_percent(header_tax)


def _looks_like_excl_plus_tax_pattern(
    excl: Decimal, gross: Decimal, tax_pct: Decimal, *, tol: Decimal = Decimal("0.02"),
) -> bool:
    if excl <= 0 or gross <= 0 or tax_pct <= 0:
        return False
    factor = Decimal("1") + tax_pct / Decimal("100")
    expected = (excl * factor).quantize(Decimal("0.01"))
    return abs(gross - expected) <= tol


def _receipt_line_gross_from_stored(line: Any) -> Decimal:
    net = Decimal(str(getattr(line, "net_amount", 0) or 0))
    if net > 0:
        return net
    excl = Decimal(str(getattr(line, "total_amount", 0) or 0))
    tax = Decimal(str(getattr(line, "tax_amount", 0) or 0))
    if excl > 0 and tax > 0:
        return excl + tax
    qty = Decimal(str(getattr(line, "receipt_quantity", 0) or 0))
    unit = Decimal(str(getattr(line, "unit_price", 0) or 0))
    return (qty * unit).quantize(Decimal("0.01"))


def _receipt_line_total_still_qty_times_display(
    line: Any, *, tol: Decimal = Decimal("0.02"),
) -> bool:
    """已写 display_unit_price，但未税额仍等于 qty×含税展示价。"""
    display_raw = getattr(line, "display_unit_price", None)
    if display_raw is None:
        return False
    qty = Decimal(str(getattr(line, "receipt_quantity", 0) or 0))
    display = Decimal(str(display_raw))
    if qty <= 0 or display <= 0:
        return False
    excl = Decimal(str(getattr(line, "total_amount", 0) or 0))
    implied = (qty * display).quantize(Decimal("0.01"))
    return abs(excl - implied) <= tol


def _po_line_looks_misentered_inclusive(item: Any, order: Any, *, tol: Decimal = Decimal("0.05")) -> bool:
    """含税价类下行未税金额≈数量×录入单价 → 录入价被当未税存了。"""
    qty = Decimal(str(getattr(item, "ordered_quantity", 0) or 0))
    unit = Decimal(str(getattr(item, "unit_price", 0) or 0))
    if qty <= 0 or unit <= 0:
        return False
    tax_pct = _tax_pct(getattr(item, "tax_rate", None), getattr(order, "tax_rate", None))
    if tax_pct <= 0:
        return False
    excl = Decimal(str(getattr(item, "total_price", 0) or 0))
    implied = (qty * unit).quantize(Decimal("0.01"))
    if excl <= 0:
        excl = implied
    if abs(excl - implied) > tol:
        return False
    wrong_gross = (excl * (Decimal("1") + tax_pct / Decimal("100"))).quantize(Decimal("0.01"))
    return wrong_gross > excl


async def _load_place(tenant_id: int) -> tuple[int, int]:
    from infra.services.business_config_service import BusinessConfigService

    svc = BusinessConfigService()
    amount_places = await svc.get_amount_decimal_places(tenant_id)
    price_places = await svc.get_price_decimal_places(tenant_id)
    return amount_places, price_places


def _convert_inclusive_entry(
    qty: Decimal,
    entered_unit: Decimal,
    tax_pct: Decimal,
    *,
    price_places: int,
    amount_places: int,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    from apps.kuaizhizao.utils.document_line_amounts import calc_document_line_amounts
    from core.utils.price_precision import quantize_business_price

    display = quantize_business_price(entered_unit, price_places)
    excl, tax, incl = calc_document_line_amounts(
        qty,
        display,
        tax_pct,
        "tax_inclusive",
        amount_places,
    )
    stored_unit = (
        quantize_business_price(excl / qty, price_places)
        if qty > 0
        else quantize_business_price(
            display / (Decimal("1") + tax_pct / Decimal("100")), price_places
        )
    )
    return display, stored_unit, excl, incl


async def run(args: argparse.Namespace) -> int:
    from tortoise import Tortoise

    from infra.infrastructure.database.database import TORTOISE_ORM

    await Tortoise.init(config=TORTOISE_ORM)

    snapshots: list[LineSnapshot] = []
    stats = {
        "po_lines_fixed": 0,
        "receipt_lines_fixed": 0,
        "receipt_headers_synced": 0,
        "po_headers_synced": 0,
        "skipped_frozen": 0,
        "skipped_no_pattern": 0,
        "receipt_lines_display_as_excl_fixed": 0,
        "receipts_settlement_resynced": 0,
    }

    from apps.kuaizhizao.constants.price_type import DEFAULT_PURCHASE_PRICE_TYPE
    from apps.kuaicaiwu.services.purchase_settlement import (
        sync_purchase_order_header_amounts,
        sync_purchase_receipt_header_amounts,
        sync_purchase_receipt_line_settlement_amounts,
    )
    from apps.kuaizhizao.models.purchase_order import PurchaseOrder, PurchaseOrderItem
    from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
    from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem

    tenant_filter = {}
    if args.tenant_id is not None:
        tenant_filter["tenant_id"] = args.tenant_id

    amount_places, price_places = await _load_place(
        args.tenant_id if args.tenant_id is not None else 1
    )

    # --- Purchase order lines ---
    po_items = await PurchaseOrderItem.filter(
        deleted_at__isnull=True, **tenant_filter
    ).all()
    po_by_id: dict[int, PurchaseOrder] = {}
    if po_items:
        order_ids = {int(i.order_id) for i in po_items}
        orders = await PurchaseOrder.filter(
            id__in=list(order_ids), deleted_at__isnull=True, **tenant_filter
        ).all()
        po_by_id = {int(o.id): o for o in orders}

    touched_po_orders: set[tuple[int, int]] = set()

    for item in po_items:
        order = po_by_id.get(int(item.order_id))
        if order is None:
            continue
        pt = str(getattr(order, "price_type", None) or DEFAULT_PURCHASE_PRICE_TYPE)
        if pt != "tax_inclusive" and not args.fix_po_exclusive_misentry:
            continue
        if getattr(item, "display_unit_price", None) is not None:
            continue
        if not args.include_frozen and str(getattr(order, "status", "") or "") in FROZEN_PO_STATUSES:
            stats["skipped_frozen"] += 1
            continue

        if not _po_line_looks_misentered_inclusive(item, order):
            stats["skipped_no_pattern"] += 1
            continue
        tax_pct = _tax_pct(item.tax_rate, order.tax_rate)

        qty = Decimal(str(item.ordered_quantity or 0))
        entered = Decimal(str(item.unit_price or 0))
        if qty <= 0 or entered <= 0:
            continue

        display, stored_unit, line_excl, _incl = _convert_inclusive_entry(
            qty, entered, tax_pct, price_places=price_places, amount_places=amount_places
        )

        snapshots.append(
            LineSnapshot(
                kind="purchase_order_item",
                tenant_id=int(item.tenant_id),
                header_id=int(item.order_id),
                line_id=int(item.id),
                before={
                    "unit_price": str(item.unit_price),
                    "display_unit_price": getattr(item, "display_unit_price", None),
                    "total_price": str(item.total_price),
                },
            )
        )

        if not args.dry_run:
            await PurchaseOrderItem.filter(
                tenant_id=item.tenant_id, id=item.id
            ).update(
                display_unit_price=display,
                unit_price=stored_unit,
                total_price=line_excl,
            )
            if pt != "tax_inclusive" and args.fix_po_exclusive_misentry:
                await PurchaseOrder.filter(tenant_id=item.tenant_id, id=item.order_id).update(
                    price_type="tax_inclusive",
                )
        stats["po_lines_fixed"] += 1
        touched_po_orders.add((int(item.tenant_id), int(item.order_id)))

    for tid, oid in touched_po_orders:
        _, _, _, changed = await sync_purchase_order_header_amounts(
            tid, oid, persist=not args.dry_run
        )
        if changed:
            stats["po_headers_synced"] += 1

    # --- Purchase receipt lines (blank PO source) ---
    pr_lines = await PurchaseReceiptItem.filter(
        deleted_at__isnull=True,
        purchase_order_item_id__isnull=True,
        **tenant_filter,
    ).all()
    if not args.only_blank_po:
        pr_lines = await PurchaseReceiptItem.filter(
            deleted_at__isnull=True, **tenant_filter
        ).all()

    receipt_ids = {int(x.receipt_id) for x in pr_lines}
    receipts = await PurchaseReceipt.filter(
        id__in=list(receipt_ids), deleted_at__isnull=True, **tenant_filter
    ).all()
    receipt_by_id = {int(r.id): r for r in receipts}

    touched_receipts: set[tuple[int, int]] = set()

    for line in pr_lines:
        if args.only_blank_po and line.purchase_order_item_id:
            continue
        receipt = receipt_by_id.get(int(line.receipt_id))
        if receipt is None:
            continue
        if _receipt_line_total_still_qty_times_display(line):
            tax_pct = _tax_pct(line.tax_rate, receipt.tax_rate)
            qty = Decimal(str(line.receipt_quantity or 0))
            entered = Decimal(str(getattr(line, "display_unit_price", 0) or 0))
            if qty > 0 and entered > 0 and tax_pct > 0:
                display, stored_unit, line_excl, _incl = _convert_inclusive_entry(
                    qty, entered, tax_pct, price_places=price_places, amount_places=amount_places
                )
                snapshots.append(
                    LineSnapshot(
                        kind="purchase_receipt_item_display_as_excl",
                        tenant_id=int(line.tenant_id),
                        header_id=int(line.receipt_id),
                        line_id=int(line.id),
                        before={
                            "unit_price": str(line.unit_price),
                            "display_unit_price": str(line.display_unit_price),
                            "total_amount": str(line.total_amount),
                        },
                    )
                )
                if not args.dry_run:
                    await PurchaseReceiptItem.filter(
                        tenant_id=line.tenant_id, id=line.id
                    ).update(
                        unit_price=stored_unit,
                        total_amount=line_excl,
                    )
                    line.unit_price = stored_unit
                    line.total_amount = line_excl
                stats["receipt_lines_display_as_excl_fixed"] += 1
                stats["receipt_lines_fixed"] += 1
                touched_receipts.add((int(line.tenant_id), int(line.receipt_id)))
            continue

        if getattr(line, "display_unit_price", None) is not None:
            if args.resync_settlement:
                touched_receipts.add((int(line.tenant_id), int(line.receipt_id)))
            continue
        if not args.include_frozen and str(getattr(receipt, "status", "") or "") in FROZEN_RECEIPT_STATUSES:
            stats["skipped_frozen"] += 1
            continue

        excl = Decimal(str(line.total_amount or 0))
        gross = _receipt_line_gross_from_stored(line)
        tax_pct = _tax_pct(line.tax_rate, receipt.tax_rate)
        if not _looks_like_excl_plus_tax_pattern(excl, gross, tax_pct):
            stats["skipped_no_pattern"] += 1
            continue

        qty = Decimal(str(line.receipt_quantity or 0))
        entered = Decimal(str(line.unit_price or 0))
        if qty <= 0 or entered <= 0:
            continue

        display, stored_unit, line_excl, _incl = _convert_inclusive_entry(
            qty, entered, tax_pct, price_places=price_places, amount_places=amount_places
        )

        snapshots.append(
            LineSnapshot(
                kind="purchase_receipt_item",
                tenant_id=int(line.tenant_id),
                header_id=int(line.receipt_id),
                line_id=int(line.id),
                before={
                    "unit_price": str(line.unit_price),
                    "display_unit_price": getattr(line, "display_unit_price", None),
                    "total_amount": str(line.total_amount),
                    "tax_amount": str(getattr(line, "tax_amount", None)),
                    "net_amount": str(getattr(line, "net_amount", None)),
                },
            )
        )

        if not args.dry_run:
            await PurchaseReceiptItem.filter(
                tenant_id=line.tenant_id, id=line.id
            ).update(
                display_unit_price=display,
                unit_price=stored_unit,
                total_amount=line_excl,
            )
            line.display_unit_price = display
            line.unit_price = stored_unit
            line.total_amount = line_excl

        stats["receipt_lines_fixed"] += 1
        touched_receipts.add((int(line.tenant_id), int(line.receipt_id)))

    # Resync settlement for touched receipts (+ optional all mismatch)
    for tid, rid in touched_receipts:
        receipt = receipt_by_id.get(rid)
        if receipt is None:
            receipt = await PurchaseReceipt.get_or_none(tenant_id=tid, id=rid)
        if receipt is None:
            continue
        lines = await PurchaseReceiptItem.filter(
            tenant_id=tid, receipt_id=rid, deleted_at__isnull=True
        ).all()
        poi_ids = {
            int(x.purchase_order_item_id)
            for x in lines
            if x.purchase_order_item_id
        }
        poi_by_id: dict[int, Any] = {}
        po_by_id_for_receipt: dict[int, Any] = {}
        if poi_ids:
            pois = await PurchaseOrderItem.filter(
                tenant_id=tid, id__in=list(poi_ids), deleted_at__isnull=True
            ).all()
            poi_by_id = {int(p.id): p for p in pois}
            order_ids = {int(p.order_id) for p in pois}
            orders = await PurchaseOrder.filter(
                tenant_id=tid, id__in=list(order_ids), deleted_at__isnull=True
            ).all()
            po_by_id_for_receipt = {int(o.id): o for o in orders}

        await sync_purchase_receipt_line_settlement_amounts(
            tid,
            receipt,
            lines,
            poi_by_id,
            purchase_order_by_id=po_by_id_for_receipt,
            persist=not args.dry_run,
            amount_places=amount_places,
        )
        _, _, _, changed = await sync_purchase_receipt_header_amounts(
            tid, rid, receipt=receipt, lines=lines, poi_by_id=poi_by_id, persist=not args.dry_run
        )
        if changed:
            stats["receipt_headers_synced"] += 1
        stats["receipts_settlement_resynced"] += 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.snapshot_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    snap_path = out_dir / f"inclusive_tax_backfill_{stamp}.json"
    payload = {
        "dry_run": args.dry_run,
        "tenant_id": args.tenant_id,
        "stats": stats,
        "snapshots": [asdict(s) for s in snapshots],
    }
    snap_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    await Tortoise.close_connections()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"snapshot written: {snap_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only-blank-po", action="store_true", default=True)
    parser.add_argument("--all-receipt-lines", action="store_true", help="含 PO 下推行")
    parser.add_argument("--include-frozen", action="store_true")
    parser.add_argument(
        "--fix-po-exclusive-misentry",
        action="store_true",
        help="价类为未税但行指纹为含税误存时仍修正，并将单头价类改为含税",
    )
    parser.add_argument(
        "--resync-settlement",
        action="store_true",
        help="凡已有 display_unit_price 的入库行所属单据，按新 settlement 重算税额/价税合计",
    )
    parser.add_argument(
        "--snapshot-dir",
        type=str,
        default=str(_backend_root / ".logs" / "tax_backfill_snapshots"),
    )
    args = parser.parse_args()
    if args.all_receipt_lines:
        args.only_blank_po = False
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
