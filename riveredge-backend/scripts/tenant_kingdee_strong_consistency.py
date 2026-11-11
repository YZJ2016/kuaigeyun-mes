#!/usr/bin/env python3
"""租户级金蝶强一致：审计仓储红灯、库位空串批次、仓库编码分叉；可选修复空仓位落账。

用法（生产机 riveredge-backend 目录）：
  TENANT_ID=2 PYTHONPATH=src .venv/bin/python scripts/tenant_kingdee_strong_consistency.py --audit
  TENANT_ID=2 PYTHONPATH=src .venv/bin/python scripts/tenant_kingdee_strong_consistency.py --repair-empty-locations
  TENANT_ID=2 PYTHONPATH=src .venv/bin/python scripts/tenant_kingdee_strong_consistency.py --repair-empty-locations --apply
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

_backend = Path(__file__).resolve().parents[1]
load_dotenv(_backend / ".env")
sys.path.insert(0, str(_backend / "src"))


async def _init_db() -> None:
    from tortoise import Tortoise
    from infra.database.tortoise_config import TORTOISE_ORM

    await Tortoise.init(config=TORTOISE_ORM)


async def _close_db() -> None:
    from tortoise import Tortoise

    await Tortoise.close_connections()


async def audit_warehouse_blockers(tenant_id: int) -> List[str]:
    from apps.kuaiconnect.services.document_push.warehouse_kingdee_alignment import (
        list_inventory_pull_blockers,
    )

    return await list_inventory_pull_blockers(tenant_id)


async def audit_duplicate_warehouse_names(tenant_id: int) -> List[Dict[str, Any]]:
    from apps.master_data.models.warehouse import Warehouse

    rows = await Warehouse.filter(tenant_id=tenant_id, deleted_at__isnull=True).values(
        "id", "code", "name", "is_active"
    )
    by_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        name = str(row.get("name") or "").strip()
        if name:
            by_name[name].append(row)
    out: List[Dict[str, Any]] = []
    for name, items in sorted(by_name.items()):
        codes = sorted({str(i.get("code") or "") for i in items})
        if len(codes) > 1:
            out.append({"name": name, "codes": codes, "rows": items})
    return out


async def audit_empty_location_batches(tenant_id: int) -> List[Dict[str, Any]]:
    from apps.master_data.models.material_batch import MaterialBatch
    from apps.master_data.models.warehouse import Warehouse
    from apps.master_data.services.warehouse_service import WarehouseService

    batches = await MaterialBatch.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        quantity__gt=0,
    ).values(
        "id",
        "material_id",
        "warehouse_id",
        "location_code",
        "batch_no",
        "quantity",
    )
    wh_ids = {int(b["warehouse_id"]) for b in batches if b.get("warehouse_id")}
    wh_map = {
        int(w.id): str(w.code or "")
        for w in await Warehouse.filter(tenant_id=tenant_id, id__in=list(wh_ids)).all()
    }
    out: List[Dict[str, Any]] = []
    default_cache: Dict[int, Tuple[int | None, str | None]] = {}
    for b in batches:
        loc = str(b.get("location_code") or "").strip()
        if loc:
            continue
        wh_id = int(b.get("warehouse_id") or 0)
        if wh_id <= 0:
            continue
        if wh_id not in default_cache:
            default_cache[wh_id] = await WarehouseService.resolve_kingdee_default_storage_location(
                tenant_id, wh_id
            )
        def_id, def_code = default_cache[wh_id]
        if not def_code:
            continue
        out.append(
            {
                "batch_id": int(b["id"]),
                "material_id": int(b.get("material_id") or 0),
                "warehouse_id": wh_id,
                "warehouse_code": wh_map.get(wh_id, ""),
                "qty": str(b.get("quantity")),
                "batch_no": b.get("batch_no"),
                "should_location_code": def_code,
                "should_location_id": def_id,
            }
        )
    return out


async def repair_empty_location_batches(
    tenant_id: int,
    *,
    apply: bool,
) -> Dict[str, Any]:
    from apps.master_data.models.material_batch import MaterialBatch
    from apps.kuaizhizao.services.inventory_service import InventoryService

    candidates = await audit_empty_location_batches(tenant_id)
    merged = 0
    moved = 0
    details: List[str] = []

    for item in candidates:
        batch_id = int(item["batch_id"])
        batch = await MaterialBatch.get_or_none(id=batch_id, tenant_id=tenant_id)
        if not batch or Decimal(str(batch.quantity or 0)) <= 0:
            continue
        loc_code = str(item["should_location_code"])
        loc_id = item.get("should_location_id")
        norm_batch = InventoryService._normalize_batch_no_for_ledger(str(batch.batch_no or ""))
        sibling = await MaterialBatch.filter(
            tenant_id=tenant_id,
            material_id=int(batch.material_id),
            warehouse_id=int(batch.warehouse_id),
            location_code=loc_code,
            batch_no=norm_batch,
            deleted_at__isnull=True,
        ).exclude(id=batch_id).first()

        if not apply:
            if sibling:
                details.append(
                    f"DRY batch={batch_id} → 合并 {loc_code} 到 batch={sibling.id} qty={batch.quantity}"
                )
            else:
                details.append(f"DRY batch={batch_id} → 改仓位 {loc_code}")
            continue

        if sibling:
            sibling.quantity = Decimal(str(sibling.quantity or 0)) + Decimal(str(batch.quantity or 0))
            if loc_id and not sibling.location_id:
                sibling.location_id = int(loc_id)
            await sibling.save()
            batch.quantity = Decimal("0")
            batch.status = "out_stock"
            await batch.save()
            merged += 1
            details.append(f"merged batch {batch_id} → {sibling.id} @ {loc_code}")
        else:
            batch.location_code = loc_code
            if loc_id:
                batch.location_id = int(loc_id)
            await batch.save()
            moved += 1
            details.append(f"moved batch {batch_id} → {loc_code}")

    return {
        "candidates": len(candidates),
        "merged": merged,
        "moved": moved,
        "apply": apply,
        "details": details[:50],
    }


def _print_section(title: str, lines: List[str]) -> None:
    print(f"\n=== {title} ===")
    if not lines:
        print("(无)")
        return
    for line in lines:
        print(line)


async def main() -> None:
    parser = argparse.ArgumentParser(description="租户金蝶强一致审计/修复")
    parser.add_argument("--tenant-id", type=int, default=int(os.environ.get("TENANT_ID") or 0))
    parser.add_argument("--audit", action="store_true", help="输出审计报告")
    parser.add_argument(
        "--repair-empty-locations",
        action="store_true",
        help="空仓位批次归并到金蝶默认无货架（默认 dry-run）",
    )
    parser.add_argument("--apply", action="store_true", help="与 --repair-empty-locations 联用才写库")
    args = parser.parse_args()
    tid = int(args.tenant_id or 0)
    if tid <= 0:
        print("请设置 TENANT_ID 或 --tenant-id", file=sys.stderr)
        sys.exit(2)

    await _init_db()
    try:
        from infra.models.tenant import Tenant

        tenant = await Tenant.get_or_none(id=tid)
        tname = str(tenant.name) if tenant else f"tenant={tid}"
        print(f"租户 {tid} {tname}")

        if args.audit or (not args.repair_empty_locations):
            blockers = await audit_warehouse_blockers(tid)
            _print_section(
                "仓储红灯（禁止灌库存，须先单据状态/金蝶关联对齐）",
                blockers[:30] if blockers else [],
            )
            if blockers and len(blockers) > 30:
                print(f"... 另有 {len(blockers) - 30} 条")

            dup_wh = await audit_duplicate_warehouse_names(tid)
            dup_lines = [
                f"{d['name']}: 编码 {', '.join(d['codes'])} ids={[r['id'] for r in d['rows']]}"
                for d in dup_wh
            ]
            _print_section("仓库同名多编码（治理：金蝶为准合并或停用重复仓）", dup_lines)

            empty_loc = await audit_empty_location_batches(tid)
            el_lines = [
                f"material_id={e.get('material_id')} wh={e.get('warehouse_code')} qty={e.get('qty')} "
                f"batch={e.get('batch_no')} → 应收 {e.get('should_location_code')}"
                for e in empty_loc[:40]
            ]
            _print_section("即时库存空仓位（与金蝶无货架维度不一致）", el_lines)
            if len(empty_loc) > 40:
                print(f"... 另有 {len(empty_loc) - 40} 条")

        if args.repair_empty_locations:
            result = await repair_empty_location_batches(tid, apply=bool(args.apply))
            _print_section(
                "空仓位修复" + ("（已写库）" if args.apply else "（dry-run）"),
                [f"candidates={result['candidates']} merged={result['merged']} moved={result['moved']}"]
                + list(result.get("details") or []),
            )
    finally:
        await _close_db()


if __name__ == "__main__":
    asyncio.run(main())
