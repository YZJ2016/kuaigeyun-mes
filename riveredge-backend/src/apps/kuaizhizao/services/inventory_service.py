"""
统一库存服务

为领料、退料、入库、出库、盘点、调拨、组装、拆解等业务提供统一的库存增减接口。

业务逻辑：
- 主仓（normal/wip，如原材料仓、成品仓）：使用 MaterialBatch（按 warehouse_id 拆分余额）
- 线边仓（line_side）：使用 LineSideInventory，仅发料/配料时写入

采购入库、成品入库等入库操作 → 主仓 MaterialBatch（写入单据仓库）
发料/配料到线边仓 → LineSideInventory

Author: RiverEdge Team
Date: 2026-02-28
"""

from apps.kuaizhizao.utils.stock_posting import atomic_stock_change, idempotent_stock_change

import hashlib
from contextvars import ContextVar
from decimal import Decimal
from typing import Optional, Dict, Any
from datetime import date
from loguru import logger
from tortoise.transactions import in_transaction
from tortoise.queryset import Q
from tortoise.exceptions import IntegrityError

from apps.kuaizhizao.models.material_stock_movement import MaterialStockMovement
from apps.kuaizhizao.utils.inventory_helper import get_material_inventory_info
from apps.master_data.constants.batch_quality_status import QUALIFIED
from infra.services.business_config_service import BusinessConfigService
from infra.exceptions.exceptions import BusinessLogicError, ValidationError

# 按原单批号追溯的逆向扣减：不适用 FIFO/LIFO「须先领更早/更新批次」防呆
_BATCH_ORDER_ENFORCEMENT_EXEMPT_SOURCE_TYPES = frozenset({
    "purchase_return",
})

# 入库确认撤回：冲减原过账台账。原单无批号时落 DEFAULT；中途启用批号后不得按「出库须指定批号」拦截
_INBOUND_REVOKE_ALLOW_DEFAULT_BATCH_SOURCE_TYPES = frozenset({
    "purchase_receipt_revoke",
    "finished_goods_receipt_revoke",
    "semi_finished_goods_receipt_revoke",
    "other_inbound_revoke",
    "customer_material_inbound_revoke",
    "production_return_revoke",
})


def resolve_managed_decrease_batch_no(
    batch_no: Optional[str],
    source_type: Optional[str],
) -> Optional[str]:
    """批号管理物料扣减用批号。

    返回非空批号；返回 None 表示调用方应报「出库必须指定批号」。
    入库撤回且原单无批号时回落 DEFAULT（与入库过账对称）。
    """
    raw = str(batch_no or "").strip()
    if raw:
        return raw
    if str(source_type or "").strip() in _INBOUND_REVOKE_ALLOW_DEFAULT_BATCH_SOURCE_TYPES:
        return "DEFAULT"
    return None


def split_manual_aux_deduct_share(
    total_quantity: Decimal,
    aux_quantity_delta: Optional[Decimal],
    deduct_quantity: Decimal,
    remaining_aux: Optional[Decimal],
    *,
    finishes_quantity: bool,
) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """按已扣主数量比例分摊手录辅数量；最后一笔吃掉余数。"""
    if aux_quantity_delta is None or remaining_aux is None:
        return None, remaining_aux
    from apps.kuaizhizao.utils.inventory_posting_utils import (
        split_base_deduct_for_inventory_deduct,
    )

    deduct_q = Decimal(str(deduct_quantity or 0))
    if deduct_q <= 0:
        return Decimal("0"), remaining_aux
    if finishes_quantity:
        share = remaining_aux
    else:
        share = split_base_deduct_for_inventory_deduct(
            Decimal(str(total_quantity or 0)),
            Decimal(str(aux_quantity_delta)),
            deduct_q,
        )
        if share > remaining_aux:
            share = remaining_aux
    next_remaining = remaining_aux - share
    if next_remaining < 0:
        next_remaining = Decimal("0")
    return share, next_remaining


def stamp_negative_batch_manual_aux(stub, material, aux_quantity_delta: Optional[Decimal]) -> None:
    """负库存新建批次：手录辅数量写入本次增量，禁止校正把负数钳成 0。"""
    InventoryService._sync_batch_ledger_quantities(stub, material)
    if aux_quantity_delta is None or material is None:
        return
    from apps.kuaizhizao.utils.ledger_dual_quantity_utils import (
        material_ledger_uses_manual_aux_quantity,
    )

    if not material_ledger_uses_manual_aux_quantity(material):
        return
    delta = Decimal(str(aux_quantity_delta))
    if delta == 0:
        return
    stub.aux_quantity = -delta

# 再确认放行映射（spec 141 review）：撤回曾冲减数量但未回冲序列号台账的存量单据，
# 再确认入库时序列号仍停在 in_stock → 凭同单已存在的撤回流水放行，对齐台账。
# 键 = 正向入库 source_type；值 = 对应撤回流水的 source_type。
_RECONFIRM_TOLERANT_REVOKE_SOURCE_TYPES = {
    "purchase_receipt": "purchase_receipt_revoke",
    "finished_goods_receipt": "finished_goods_receipt_revoke",
    "semi_finished_goods_receipt": "semi_finished_goods_receipt_revoke",
    "sales_return": "sales_return_withdraw",
    "customer_material_inbound": "customer_material_inbound_revoke",
    # other_inbound 明细的 serial_numbers 字段系后补，字段落地前已确认/撤回的存量单据
    # 序列号仍滞留 in_stock，其再确认必须容忍
    "other_inbound": "other_inbound_revoke",
    # production_return 明细的 serial_numbers 字段同为后补，存量已撤回单据同理须容忍
    "production_return": "production_return_revoke",
}

# A 案包装层合成键的行内序号（spec 141 KR-CL2）：同一调用上下文（同一请求/事务内的
# 批量过账）里，判别字段完全相同的明细行须拿到不同键；重试按相同顺序重放得到同一组键。
_synth_stock_key_counter: ContextVar = ContextVar(
    "inventory_synth_stock_key_seq", default=None
)


class InventoryService:
    """
    统一库存服务

    提供 increase_stock、decrease_stock、get_quantity、adjust_inventory 等接口，
    供 warehouse_service、stocktaking_service、assembly_order_service 等调用。
    """

    @staticmethod
    async def _get_warehouse_management_flags(tenant_id: int) -> tuple[bool, bool]:
        """读取仓储批号/序列号管理开关。"""
        from infra.services.business_config_service import BusinessConfigService

        cfg = await BusinessConfigService().get_business_config(tenant_id)
        wh = cfg.get("parameters", {}).get("warehouse", {})
        return bool(wh.get("batch_management", False)), bool(wh.get("serial_management", False))

    @staticmethod
    def _normalize_location_kwargs(
        location_id: Optional[int] = None,
        location_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if location_id is not None:
            try:
                payload["location_id"] = int(location_id)
            except (TypeError, ValueError):
                pass
        code = str(location_code or "").strip()
        if code:
            payload["location_code"] = code
        return payload

    @staticmethod
    def location_kwargs_from_line_item(item: Any) -> Dict[str, Any]:
        return InventoryService._normalize_location_kwargs(
            getattr(item, "location_id", None),
            getattr(item, "location_code", None),
        )

    def line_item_location_scoped(item: Any) -> bool:
        """明细已选库位时扣减须 location_scoped，未选则允许同批号跨库位分摊。"""
        if str(getattr(item, "location_code", None) or "").strip():
            return True
        return getattr(item, "location_id", None) is not None

    @staticmethod
    def _movement_location_kwargs(
        batch: Any = None,
        *,
        location_code: Optional[str] = None,
        location_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """把本次余额行的库位写入流水。

        空串是未分库位键。批次 location_code 为 NULL 时流水也记 NULL，不收成空串。
        这种已记录的 NULL 键用 location_id=0 标出，与「库位字段本身为空」的历史流水区分。
        """
        if batch is not None:
            location_code = getattr(batch, "location_code", None)
            location_id = getattr(batch, "location_id", None)
            if location_code is None:
                payload: Dict[str, Any] = {"location_code": None, "location_id": 0}
                if location_id is not None:
                    try:
                        payload["location_id"] = int(location_id)
                    except (TypeError, ValueError):
                        payload["location_id"] = 0
                return payload
        payload = {"location_code": None if location_code is None else str(location_code)[:50]}
        if location_code is None and batch is None:
            payload["location_code"] = ""
        if location_id is not None:
            try:
                payload["location_id"] = int(location_id)
            except (TypeError, ValueError):
                pass
        return payload

    @staticmethod
    def _idempotency_key_matches_line(stored: Optional[str], line_key: str) -> bool:
        key = str(stored or "")
        prefix = str(line_key or "")
        if not prefix or not key.startswith(prefix):
            return False
        if len(key) == len(prefix):
            return True
        return key[len(prefix)] in "@#"

    @staticmethod
    def _movement_posting_scope(stored: Optional[str], line_key: str) -> str:
        rest = str(stored or "")[len(line_key):]
        if rest.startswith("@"):
            return rest[1:].split("#", 1)[0]
        return ""

    @staticmethod
    def _withdraw_location_idempotency_key(
        base_key: str,
        location_code: str,
        batch_no: Optional[str] = None,
    ) -> str:
        from urllib.parse import quote

        token = quote(str(location_code or ""), safe="")
        suffix = f"#loc={token}"
        if batch_no is not None:
            suffix += "#bn=" + quote(str(batch_no), safe="")
        if len(base_key) + len(suffix) > 200:
            raw = f"{location_code}\0{'' if batch_no is None else batch_no}"
            suffix = "#loc=" + hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{base_key}{suffix}"

    @staticmethod
    def _posted_restore_batch_no(row: Any) -> str:
        """确认流水上的批号。空值保持空串，不收成 DEFAULT。"""
        raw = getattr(row, "batch_no", None)
        if raw is None:
            return ""
        return str(raw).strip()

    @staticmethod
    def _group_posted_restore_rows(rows: list) -> Dict[tuple, Dict[str, Any]]:
        grouped: Dict[tuple, Dict[str, Any]] = {}
        for row in rows:
            code = getattr(row, "location_code", None)
            batch_no = InventoryService._posted_restore_batch_no(row)
            key = (code, batch_no)
            bucket = grouped.setdefault(
                key,
                {"qty": Decimal("0"), "base": Decimal("0"), "location_id": None, "batch_no": batch_no},
            )
            piece = abs(Decimal(str(row.quantity or 0)))
            base_raw = getattr(row, "base_quantity", None)
            base_piece = abs(Decimal(str(base_raw if base_raw is not None else row.quantity or 0)))
            bucket["qty"] += piece
            bucket["base"] += base_piece
            loc_id = getattr(row, "location_id", None)
            if bucket["location_id"] is None and loc_id not in (None, 0):
                bucket["location_id"] = int(loc_id)
        return grouped

    @staticmethod
    async def _null_location_restore_kind(
        *,
        tenant_id: int,
        material_id: int,
        warehouse_id: Optional[int],
        batch_no: str,
    ) -> str:
        """NULL 库位键能加回原行时返回 line_side 或 batch，否则是未记录库位。"""
        from apps.master_data.models.material_batch import MaterialBatch
        from apps.master_data.models.warehouse import Warehouse

        wh = None
        if warehouse_id:
            wh = await Warehouse.get_or_none(
                id=warehouse_id,
                tenant_id=tenant_id,
                deleted_at__isnull=True,
            )
        bn = str(batch_no or "").strip()
        if wh and wh.warehouse_type == "line_side":
            from apps.kuaizhizao.models.line_side_inventory import LineSideInventory

            query = LineSideInventory.filter(
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                material_id=material_id,
                deleted_at__isnull=True,
            )
            if bn:
                query = query.filter(batch_no=bn)
            else:
                query = query.filter(Q(batch_no__isnull=True) | Q(batch_no=""))
            if await query.first():
                return "line_side"
            return "unrecorded"

        query = MaterialBatch.filter(
            tenant_id=tenant_id,
            material_id=material_id,
            deleted_at__isnull=True,
            location_code__isnull=True,
        )
        wh_id = InventoryService._normalize_main_warehouse_id(warehouse_id)
        if wh_id > 0:
            query = query.filter(Q(warehouse_id=wh_id) | Q(warehouse_id=0))
        else:
            query = query.filter(warehouse_id=0)
        if bn and bn != "DEFAULT":
            query = query.filter(batch_no=bn)
        else:
            query = query.filter(Q(batch_no="") | Q(batch_no="DEFAULT") | Q(batch_no__isnull=True))
        if await query.first():
            return "batch"
        return "unrecorded"

    @staticmethod
    async def restore_unscoped_outbound_by_posted_locations(
        *,
        tenant_id: int,
        material_id: int,
        quantity: Decimal,
        confirm_source_type: str,
        line_idempotency_key: str,
        withdraw_idempotency_key: str,
        base_quantity: Optional[Decimal] = None,
        aux_quantity_delta: Optional[Decimal] = None,
        serial_nos: Optional[list] = None,
        **increase_kwargs: Any,
    ) -> None:
        """行上无库位时，按本次确认出库流水的库位把数量加回。没有可用流水则失败。"""
        del base_quantity
        rows = await MaterialStockMovement.filter(
            tenant_id=tenant_id,
            source_doc_type=confirm_source_type,
            source_doc_id=increase_kwargs.get("source_doc_id"),
            idempotency_key__startswith=line_idempotency_key,
        ).all()
        matched = [
            row
            for row in rows
            if InventoryService._idempotency_key_matches_line(
                getattr(row, "idempotency_key", None),
                line_idempotency_key,
            )
        ]
        if not matched:
            raise BusinessLogicError("确认出库没有库存流水，无法按原库位撤回")
        latest_id = max(int(getattr(row, "id", 0) or 0) for row in matched)
        latest_scope = InventoryService._movement_posting_scope(
            next(
                getattr(row, "idempotency_key", None)
                for row in matched
                if int(getattr(row, "id", 0) or 0) == latest_id
            ),
            line_idempotency_key,
        )
        deductions = []
        for row in matched:
            if InventoryService._movement_posting_scope(
                getattr(row, "idempotency_key", None),
                line_idempotency_key,
            ) != latest_scope:
                continue
            qty = Decimal(str(getattr(row, "quantity", 0) or 0))
            if qty >= 0:
                continue
            deductions.append(row)
        if not deductions:
            raise BusinessLogicError("确认出库没有库存流水，无法按原库位撤回")

        located_rows = []
        null_location_rows = []
        for row in deductions:
            if getattr(row, "location_code", None) is not None:
                located_rows.append(row)
                continue
            # location_id=0 是本次从 NULL 库位批次写下的键；其它空值仍是未记录库位
            if getattr(row, "location_id", None) == 0:
                null_location_rows.append(row)
                continue
            raise BusinessLogicError("确认出库流水未记录库位，无法按原库位撤回")

        grouped = InventoryService._group_posted_restore_rows(located_rows)
        null_grouped = InventoryService._group_posted_restore_rows(null_location_rows)
        for bucket in null_grouped.values():
            kind = await InventoryService._null_location_restore_kind(
                tenant_id=tenant_id,
                material_id=material_id,
                warehouse_id=increase_kwargs.get("warehouse_id"),
                batch_no=bucket["batch_no"],
            )
            if kind == "unrecorded":
                raise BusinessLogicError("确认出库流水未记录库位，无法按原库位撤回")
            bucket["kind"] = kind

        posted_qty = sum(
            (bucket["qty"] for bucket in list(grouped.values()) + list(null_grouped.values())),
            Decimal("0"),
        )
        need = Decimal(str(quantity or 0))
        qty_scale = Decimal("0.0001")
        if posted_qty.quantize(qty_scale) != need.quantize(qty_scale):
            raise BusinessLogicError(
                f"确认出库流水数量 {posted_qty} 与明细 {need} 不一致，无法按原库位撤回"
            )

        increase_kwargs.pop("location_code", None)
        increase_kwargs.pop("location_id", None)
        increase_kwargs.pop("batch_no", None)
        increase_kwargs.pop("idempotency_key", None)
        increase_kwargs.pop("quantity", None)
        increase_kwargs.pop("base_quantity", None)
        increase_kwargs.pop("aux_quantity_delta", None)
        increase_kwargs.pop("serial_nos", None)

        aux_total = (
            Decimal(str(aux_quantity_delta)) if aux_quantity_delta is not None else None
        )
        aux_left = aux_total
        ordered = sorted(grouped.items(), key=lambda pair: (str(pair[0][0]), pair[0][1]))
        null_ordered = sorted(null_grouped.items(), key=lambda pair: pair[0][1])
        steps = [("located", key, bucket) for key, bucket in ordered]
        steps.extend(("null", key, bucket) for key, bucket in null_ordered)
        for idx, (kind_step, key, bucket) in enumerate(steps):
            call = dict(increase_kwargs)
            posted_batch = bucket["batch_no"]
            call.update(
                tenant_id=tenant_id,
                material_id=material_id,
                quantity=bucket["qty"],
                base_quantity=bucket["base"],
                batch_no=posted_batch,
                exact_batch_no=True,
                idempotency_key=InventoryService._withdraw_location_idempotency_key(
                    withdraw_idempotency_key,
                    "" if kind_step == "null" else str(key[0] or ""),
                    posted_batch,
                ),
            )
            if kind_step == "null":
                if bucket.get("kind") == "batch":
                    call["match_null_location"] = True
            else:
                call["location_code"] = str(key[0] or "")
                if bucket["location_id"] is not None:
                    call["location_id"] = bucket["location_id"]
            if aux_total is not None:
                if idx == len(steps) - 1:
                    aux_share = aux_left
                else:
                    aux_share = (aux_total * bucket["qty"] / posted_qty).quantize(
                        Decimal("0.0001")
                    )
                    aux_left -= aux_share
                call["aux_quantity_delta"] = aux_share
            if idx == 0 and serial_nos:
                call["serial_nos"] = serial_nos
            await InventoryService.increase_stock(**call)


    @staticmethod
    def _apply_location_fields(target: Any, location_id: Optional[int], location_code: Optional[str]) -> None:
        loc = InventoryService._normalize_location_kwargs(location_id, location_code)
        if not loc:
            return
        if "location_id" in loc:
            target.location_id = loc["location_id"]
        if "location_code" in loc:
            target.location_code = loc["location_code"]

    @staticmethod
    async def _get_allow_negative_inventory(tenant_id: int) -> bool:
        """租户仓存参数：是否允许出库将账面扣为负数。"""
        cfg = await BusinessConfigService().get_business_config(tenant_id)
        wh = cfg.get("parameters", {}).get("warehouse", {})
        return bool(wh.get("allow_negative_inventory", False))

    @staticmethod
    def _sync_material_batch_status_after_qty_change(batch) -> None:
        qty = batch.quantity or Decimal(0)
        if qty > 0:
            batch.status = "in_stock"
        elif qty == 0:
            batch.status = "out_stock"
        else:
            batch.status = "in_stock"

    @staticmethod
    def _ownership_filter(
        ownership_type: Optional[str] = None,
        customer_id: Optional[int] = None,
    ) -> dict:
        ot = ownership_type or "company_owned"
        cid = customer_id if customer_id is not None else 0
        return {"ownership_type": ot, "customer_id": cid}

    @staticmethod
    def _normalize_batch_no_for_ledger(batch_no: Optional[str]) -> str:
        bn = str(batch_no or "").strip()
        return bn if bn else "DEFAULT"

    @staticmethod
    def format_batch_no_for_display(batch_no: Optional[str]) -> Optional[str]:
        """用户可见批号：空值与过账占位 DEFAULT 不展示。"""
        bn = str(batch_no or "").strip()
        if not bn or bn.upper() == "DEFAULT":
            return None
        return bn

    async def heal_duplicate_default_batch_rows(
        tenant_id: int,
        material_ids: Optional[list[int]] = None,
    ) -> int:
        """
        合并同物料+仓+库位下 batch_no 为空与 DEFAULT 的重复行（金蝶同步与采购入库口径不一）。
        """
        from collections import defaultdict

        from tortoise.expressions import Q

        from apps.kuaizhizao.utils.ledger_dual_quantity_utils import (
            sync_material_batch_ledger_quantities,
        )
        from apps.master_data.models.material import Material
        from apps.master_data.models.material_batch import MaterialBatch
        from core.utils.timezone_utils import resolve_business_datetime

        q = MaterialBatch.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            quality_status=QUALIFIED,
        ).filter(Q(batch_no="") | Q(batch_no="DEFAULT"))
        if material_ids:
            q = q.filter(material_id__in=list({int(mid) for mid in material_ids}))
        rows = await q.all()
        if len(rows) < 2:
            return 0
        groups: dict[tuple, list[MaterialBatch]] = defaultdict(list)
        for batch in rows:
            groups[
                (
                    int(batch.material_id),
                    int(batch.warehouse_id or 0),
                    str(batch.location_code or "").strip(),
                    str(batch.ownership_type or "company_owned"),
                    int(batch.customer_id or 0),
                )
            ].append(batch)
        merged = 0
        now = resolve_business_datetime()
        for group in groups.values():
            if len(group) < 2:
                continue
            canonical = sorted(
                group,
                key=lambda b: (
                    0 if InventoryService._normalize_batch_no_for_ledger(b.batch_no) == "DEFAULT" else 1,
                    -int(b.id),
                ),
            )[0]
            material = await Material.get_or_none(
                tenant_id=tenant_id, id=canonical.material_id, deleted_at__isnull=True
            )
            for other in group:
                if other.id == canonical.id:
                    continue
                canonical.quantity = (canonical.quantity or Decimal(0)) + (other.quantity or Decimal(0))
                canonical.base_quantity = (canonical.base_quantity or Decimal(0)) + (
                    other.base_quantity or Decimal(0)
                )
                if other.aux_quantity is not None:
                    canonical.aux_quantity = (canonical.aux_quantity or Decimal(0)) + other.aux_quantity
                other.deleted_at = now
                await other.save(update_fields=["deleted_at"])
                merged += 1
            canonical.batch_no = InventoryService._normalize_batch_no_for_ledger(canonical.batch_no)
            sync_material_batch_ledger_quantities(canonical, material)
            await canonical.save(
                update_fields=[
                    "quantity",
                    "base_quantity",
                    "aux_quantity",
                    "batch_no",
                    "status",
                ]
            )
        return merged


    @staticmethod
    async def _resolve_warehouse_name(warehouse_id: Optional[int]) -> Optional[str]:
        if warehouse_id is None:
            return None
        from apps.master_data.models.warehouse import Warehouse

        wh = await Warehouse.get_or_none(id=warehouse_id, deleted_at__isnull=True)
        return (wh.name or "").strip() or None if wh else None

    @staticmethod
    async def _resolve_operator_name(
        tenant_id: int,
        operator_id: Optional[int],
        operator_name: Optional[str],
    ) -> tuple[Optional[int], Optional[str]]:
        name = (operator_name or "").strip() or None
        oid = int(operator_id) if operator_id is not None else None
        if oid is not None and oid <= 0:
            oid = None
        if oid is not None and not name:
            from infra.models.user import User

            user = await User.get_or_none(id=oid, tenant_id=tenant_id)
            if user is None:
                user = await User.get_or_none(id=oid)
            if user is not None:
                name = (
                    (getattr(user, "full_name", None) or "").strip()
                    or (getattr(user, "username", None) or "").strip()
                    or None
                )
        return oid, name

    @staticmethod
    async def _record_stock_movement(
        *,
        tenant_id: int,
        material_id: int,
        quantity: Decimal,
        qty_before: Optional[Decimal],
        qty_after: Optional[Decimal],
        base_quantity: Optional[Decimal] = None,
        base_qty_before: Optional[Decimal] = None,
        base_qty_after: Optional[Decimal] = None,
        batch_no: Optional[str] = None,
        movement_type: Optional[str] = None,
        from_warehouse_id: Optional[int] = None,
        from_warehouse_name: Optional[str] = None,
        to_warehouse_id: Optional[int] = None,
        to_warehouse_name: Optional[str] = None,
        balance_warehouse_id: Optional[int] = None,
        source_type: Optional[str] = None,
        source_doc_id: Optional[int] = None,
        source_doc_code: Optional[str] = None,
        work_order_id: Optional[int] = None,
        work_order_code: Optional[str] = None,
        operator_id: Optional[int] = None,
        operator_name: Optional[str] = None,
        remark: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        location_id: Optional[int] = None,
        location_code: Optional[str] = None,
    ) -> None:
        """追加库存流水；写入失败必须回滚余额，由事务入口统一处理幂等。"""
        from infra.exceptions.exceptions import ValidationError
        from apps.master_data.models.material import Material

        mt = (movement_type or "").strip()
        if not mt:
            raise ValidationError(
                f"库存流水缺少 movement_type: material={material_id} "
                f"source={source_type}/{source_doc_id}"
            )
        if not material_id:
            raise ValidationError(
                f"库存流水缺少 material_id: source={source_type}/{source_doc_id}"
            )

        operator_id, operator_name = await InventoryService._resolve_operator_name(
            tenant_id, operator_id, operator_name
        )
        if source_doc_id is not None and operator_id is None and not operator_name:
            raise ValidationError(
                f"单据库存过账必须指定操作人: source={source_type}/{source_doc_id} "
                f"doc={source_doc_code or ''}"
            )

        mat = await Material.get_or_none(
            tenant_id=tenant_id, id=material_id, deleted_at__isnull=True
        )
        if mat is None:
            raise ValidationError(
                f"库存过账物料不存在或已删除: material_id={material_id} "
                f"source={source_type}/{source_doc_id}"
            )
        material_code = (
            (getattr(mat, "main_code", None) or getattr(mat, "code", None) or "")
        ).strip()
        material_name = (getattr(mat, "name", None) or "").strip()
        if not material_code or not material_name:
            raise ValidationError(
                f"物料主数据缺少编码或名称: material_id={material_id} "
                f"code={material_code!r} name={material_name!r}"
            )

        if from_warehouse_id is not None and not from_warehouse_name:
            from_warehouse_name = await InventoryService._resolve_warehouse_name(
                from_warehouse_id
            )
        if to_warehouse_id is not None and not to_warehouse_name:
            to_warehouse_name = await InventoryService._resolve_warehouse_name(
                to_warehouse_id
            )

        signed_base = (
            Decimal(str(base_quantity))
            if base_quantity is not None
            else Decimal(str(quantity))
        )
        await MaterialStockMovement.create(
            tenant_id=tenant_id,
            material_id=material_id,
            material_code=material_code,
            material_name=material_name,
            batch_no=batch_no,
            movement_type=mt,
            quantity=Decimal(str(quantity)),
            base_quantity=signed_base,
            qty_before=qty_before,
            qty_after=qty_after,
            base_qty_before=base_qty_before,
            base_qty_after=base_qty_after,
            from_warehouse_id=from_warehouse_id,
            from_warehouse_name=from_warehouse_name,
            to_warehouse_id=to_warehouse_id,
            to_warehouse_name=to_warehouse_name,
            balance_warehouse_id=balance_warehouse_id,
            source_doc_type=source_type,
            source_doc_id=source_doc_id,
            source_doc_code=source_doc_code,
            work_order_id=work_order_id,
            work_order_code=work_order_code,
            operator_id=operator_id,
            operator_name=operator_name,
            remark=remark,
            idempotency_key=idempotency_key,
            location_id=int(location_id) if location_id is not None else None,
            location_code=None if location_code is None else str(location_code)[:50],
            created_by=operator_id,
            created_by_name=operator_name,
        )

    @staticmethod
    def _material_batch_no_lookup_q(batch_no: Optional[str]):
        from tortoise.expressions import Q

        bn = InventoryService._normalize_batch_no_for_ledger(batch_no)
        if bn == "DEFAULT":
            return Q(batch_no="DEFAULT") | Q(batch_no="")
        return Q(batch_no=bn)

    @staticmethod
    def _normalize_main_warehouse_id(warehouse_id: Optional[int]) -> int:
        """主仓余额键：未传仓记为 0（报表展示为未配置仓库）。"""
        try:
            wid = int(warehouse_id) if warehouse_id is not None else 0
        except (TypeError, ValueError):
            return 0
        return wid if wid > 0 else 0

    @staticmethod
    def _main_warehouse_balance_q(warehouse_id: Optional[int]):
        """主仓扣减/查找：精确仓 + 历史未归属(0)。"""
        from tortoise.expressions import Q

        wh_id = InventoryService._normalize_main_warehouse_id(warehouse_id)
        if wh_id > 0:
            return Q(warehouse_id=wh_id) | Q(warehouse_id=0)
        return Q(warehouse_id=0)

    @staticmethod
    async def _find_in_stock_material_batch(
        tenant_id: int,
        material_id: int,
        batch_no: Optional[str],
        ownership_type: Optional[str] = None,
        customer_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        *,
        for_update: bool = False,
        include_unassigned: bool = False,
        quality_status: str = QUALIFIED,
    ):
        from apps.master_data.models.material_batch import MaterialBatch

        own = InventoryService._ownership_filter(ownership_type, customer_id)
        q = InventoryService._material_batch_no_lookup_q(batch_no)
        filters = dict(
            tenant_id=tenant_id,
            material_id=material_id,
            deleted_at__isnull=True,
            status="in_stock",
            quality_status=quality_status,
            **own,
        )
        query = MaterialBatch.filter(**filters).filter(q)
        if warehouse_id is not None:
            wh_id = InventoryService._normalize_main_warehouse_id(warehouse_id)
            if include_unassigned and wh_id > 0:
                query = query.filter(InventoryService._main_warehouse_balance_q(wh_id))
            else:
                query = query.filter(warehouse_id=wh_id)
            # 优先精确仓，再历史未归属
            query = query.order_by("-warehouse_id")
        if for_update:
            query = query.select_for_update()
        return await query.first()

    @staticmethod
    def _scoped_location_filter(location_code: Optional[str]):
        code = str(location_code or "").strip()
        if code:
            return Q(location_code=code)
        return Q(location_code="") | Q(location_code__isnull=True)

    @staticmethod
    async def _lock_location_key_tail(
        *,
        tenant_id: int,
        material_id: int,
        warehouse_id: int,
        location_code: str,
        ownership_type: Optional[str],
        customer_id: Optional[int],
        quality_status: str,
    ):
        """本库位键的最后一行（含数量为 0 / 已出库）。不跨到其它库位。"""
        from apps.master_data.models.material_batch import MaterialBatch

        own = InventoryService._ownership_filter(ownership_type, customer_id)
        return await (
            MaterialBatch.filter(
                tenant_id=tenant_id,
                material_id=material_id,
                deleted_at__isnull=True,
                quality_status=quality_status,
                **own,
            )
            .filter(InventoryService._main_warehouse_balance_q(warehouse_id))
            .filter(InventoryService._scoped_location_filter(location_code))
            .order_by("-id")
            .select_for_update()
            .first()
        )

    async def _list_in_stock_material_batches(
        tenant_id: int,
        material_id: int,
        batch_no: Optional[str],
        ownership_type: Optional[str] = None,
        customer_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        *,
        for_update: bool = False,
        include_unassigned: bool = False,
        quality_status: str = QUALIFIED,
        require_positive_qty: bool = True,
        location_code: Optional[str] = None,
        location_scoped: bool = False,
    ) -> list:
        """同仓（含未归属）下同一批号的全部在库台账行。

        批号管理物料确认出库未指定库位时，同批号跨库位加总后一次扣减；必须按多行分摊，
        禁止只取 `.first()` 导致「合计够、单行不够」误报库存不足。
        明细已选库位时传 location_scoped=True，仅扣该 location_code 台账，禁止跨库位误扣。
        """
        from apps.master_data.models.material_batch import MaterialBatch

        own = InventoryService._ownership_filter(ownership_type, customer_id)
        q = InventoryService._material_batch_no_lookup_q(batch_no)
        filters = dict(
            tenant_id=tenant_id,
            material_id=material_id,
            deleted_at__isnull=True,
            status="in_stock",
            quality_status=quality_status,
            **own,
        )
        if require_positive_qty:
            filters["quantity__gt"] = 0
        query = MaterialBatch.filter(**filters).filter(q)
        if location_scoped:
            query = query.filter(InventoryService._scoped_location_filter(location_code))
        if warehouse_id is not None:
            wh_id = InventoryService._normalize_main_warehouse_id(warehouse_id)
            if include_unassigned and wh_id > 0:
                query = query.filter(InventoryService._main_warehouse_balance_q(wh_id))
            else:
                query = query.filter(warehouse_id=wh_id)
            # 优先精确仓，再历史未归属
            query = query.order_by("-warehouse_id", "id")
        else:
            query = query.order_by("id")
        if for_update:
            query = query.select_for_update()
        return await query.all()


    @staticmethod
    async def _resolve_ledger_production_date(
        tenant_id: int,
        material_id: int,
        batch_no: Optional[str],
        ownership_type: Optional[str] = None,
        customer_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
    ) -> Optional[date]:
        """
        出库撤回等回冲场景：未显式传入入库日期时，从既有批次台账读取 production_date。
        批号行在扣至 0 后仍为 out_stock，production_date 保留原入库确认日。
        """
        if not batch_no or not str(batch_no).strip():
            return None
        bn = InventoryService._normalize_batch_no_for_ledger(batch_no)
        if bn == "DEFAULT":
            return None
        from apps.master_data.models.material_batch import MaterialBatch

        own = InventoryService._ownership_filter(ownership_type, customer_id)
        q = InventoryService._material_batch_no_lookup_q(batch_no)
        filters = dict(
            tenant_id=tenant_id,
            material_id=material_id,
            deleted_at__isnull=True,
            **own,
        )
        if warehouse_id is not None:
            filters["warehouse_id"] = InventoryService._normalize_main_warehouse_id(warehouse_id)
        batch = await MaterialBatch.filter(**filters).filter(q).first()
        if batch and batch.production_date is not None:
            return batch.production_date
        return None

    @staticmethod
    async def _apply_batch_ledger_dates(
        batch,
        *,
        material,
        ledger_production_date: Optional[date],
        ledger_expiry_date: Optional[date],
    ) -> None:
        """首次写入生产日/有效期至；已有值不覆盖。有效期按单据显式值、同批号已维护值或物料保质期解析。"""
        from apps.master_data.services.material_batch_service import MaterialBatchService

        if ledger_production_date is not None and batch.production_date is None:
            batch.production_date = ledger_production_date
        if batch.expiry_date is None:
            explicit_expiry = MaterialBatchService.coerce_optional_date(ledger_expiry_date)
            if explicit_expiry is None and material is not None:
                sibling = await MaterialBatchService.lookup_sibling_batch_expiry(
                    int(batch.tenant_id),
                    int(batch.material_id),
                    str(batch.batch_no or ""),
                    exclude_batch_id=int(batch.id) if getattr(batch, "id", None) else None,
                )
                explicit_expiry = sibling
            resolved = MaterialBatchService.resolve_inbound_item_expiry_date(
                material=material,
                production_date=batch.production_date,
                explicit_expiry=explicit_expiry,
            )
            if resolved is not None:
                batch.expiry_date = resolved

    @staticmethod
    async def _lock_material_batch_for_increase(
        *,
        tenant_id: int,
        material_id: int,
        batch_no: str,
        warehouse_id: int,
        location_code: str,
        quality_status: str,
        own: Dict[str, Any],
        match_null_location: bool,
    ):
        """锁定要加回的批次行。NULL 库位只匹配 NULL，找不到时不新建空串行。"""
        from apps.master_data.models.material_batch import MaterialBatch

        base = dict(
            tenant_id=tenant_id,
            material_id=material_id,
            warehouse_id=warehouse_id,
            quality_status=quality_status,
            **own,
        )
        if batch_no == "":
            batch_q = Q(batch_no="") | Q(batch_no="DEFAULT") | Q(batch_no__isnull=True)
        else:
            batch_q = Q(batch_no=batch_no)

        async def _first(location_q):
            return await (
                MaterialBatch.filter(**base)
                .filter(batch_q)
                .filter(location_q)
                .select_for_update()
                .first()
            )

        if match_null_location:
            return await _first(Q(location_code__isnull=True))
        code = str(location_code or "")
        if code:
            return await _first(Q(location_code=code))
        found = await _first(Q(location_code=""))
        if found:
            return found
        return await _first(Q(location_code__isnull=True))

    @staticmethod
    async def _material_batch_increase_or_restore(
        tenant_id: int,
        material_id: int,
        batch_no: str,
        quantity: Decimal,
        base_quantity: Optional[Decimal] = None,
        ownership_type: Optional[str] = None,
        customer_id: Optional[int] = None,
        customer_name: Optional[str] = None,
        source_doc_id: Optional[int] = None,
        source_doc_code: Optional[str] = None,
        ledger_production_date: Optional[date] = None,
        ledger_expiry_date: Optional[date] = None,
        material=None,
        warehouse_id: Optional[int] = None,
        warehouse_name: Optional[str] = None,
        location_id: Optional[int] = None,
        location_code: Optional[str] = None,
        quality_status: str = QUALIFIED,
        aux_quantity_delta: Optional[Decimal] = None,
        exact_batch_no: bool = False,
        match_null_location: bool = False,
    ) -> None:
        """
        主仓批次数量增加（按 warehouse_id 拆分）。包含软删行：若唯一键已存在但 deleted_at 有值，
        仅查未删行会误判为不存在，insert 会撞唯一约束。
        """
        base_q = Decimal(str(base_quantity if base_quantity is not None else quantity))
        from apps.kuaizhizao.utils.ledger_dual_quantity_utils import (
            ledger_aux_delta_from_base_delta,
            ledger_aux_quantity_from_base,
        )
        from apps.master_data.models.material_batch import MaterialBatch
        from apps.master_data.models.material import Material
        from apps.master_data.services.material_batch_service import MaterialBatchService

        if exact_batch_no:
            bn = str(batch_no or "").strip()
        else:
            bn = InventoryService._normalize_batch_no_for_ledger(batch_no)
        own = InventoryService._ownership_filter(ownership_type, customer_id)
        wh_id = InventoryService._normalize_main_warehouse_id(warehouse_id)
        wh_name = (str(warehouse_name or "").strip() or None)
        loc_kwargs = InventoryService._normalize_location_kwargs(location_id, location_code)
        loc_code = str(loc_kwargs.get("location_code") or "")
        if wh_id > 0 and not wh_name:
            wh_name = await InventoryService._resolve_warehouse_name(wh_id)
        if material is None:
            material = await Material.get_or_none(
                tenant_id=tenant_id, id=material_id, deleted_at__isnull=True
            )

        batch = await InventoryService._lock_material_batch_for_increase(
            tenant_id=tenant_id,
            material_id=material_id,
            batch_no=bn,
            warehouse_id=wh_id,
            location_code=loc_code,
            quality_status=quality_status,
            own=own,
            match_null_location=match_null_location,
        )
        # 历史未归属行（warehouse_id=0）：首次带仓入库时认领，避免同批双行
        if not batch and wh_id > 0:
            batch = await InventoryService._lock_material_batch_for_increase(
                tenant_id=tenant_id,
                material_id=material_id,
                batch_no=bn,
                warehouse_id=0,
                location_code=loc_code,
                quality_status=quality_status,
                own=own,
                match_null_location=match_null_location,
            )
            if batch:
                batch.warehouse_id = wh_id
                batch.warehouse_name = wh_name
        if batch:
            if batch.deleted_at is not None:
                batch.deleted_at = None
            batch.quantity = (batch.quantity or Decimal(0)) + quantity
            batch.base_quantity = (batch.base_quantity or Decimal(0)) + base_q
            batch.status = "in_stock"
            if wh_name and not str(batch.warehouse_name or "").strip():
                batch.warehouse_name = wh_name
            if customer_name:
                batch.customer_name = customer_name
            if source_doc_id:
                batch.source_doc_id = source_doc_id
            if source_doc_code:
                batch.source_doc_code = source_doc_code
            InventoryService._apply_location_fields(batch, location_id, location_code)
            await InventoryService._apply_batch_ledger_dates(
                batch,
                material=material,
                ledger_production_date=ledger_production_date,
                ledger_expiry_date=ledger_expiry_date,
            )
            InventoryService._apply_manual_aux_delta(batch, material, aux_quantity_delta)
            InventoryService._sync_batch_ledger_quantities(batch, material)
            await batch.save()
            return
        if match_null_location:
            raise BusinessLogicError("确认出库流水未记录库位，无法按原库位撤回")
        create_production_date = ledger_production_date
        explicit_create_expiry = MaterialBatchService.coerce_optional_date(ledger_expiry_date)
        if explicit_create_expiry is None and material is not None and bn:
            explicit_create_expiry = await MaterialBatchService.lookup_sibling_batch_expiry(
                tenant_id,
                material_id,
                bn,
            )
        create_expiry_date = MaterialBatchService.resolve_inbound_item_expiry_date(
            material=material,
            production_date=create_production_date,
            explicit_expiry=explicit_create_expiry,
        )
        from apps.kuaizhizao.utils.ledger_dual_quantity_utils import (
            material_ledger_uses_manual_aux_quantity,
        )

        if material and material_ledger_uses_manual_aux_quantity(material):
            create_aux = Decimal(str(aux_quantity_delta or 0))
        else:
            create_aux = ledger_aux_quantity_from_base(material, base_q) if material else base_q
        create_stub = type("BatchQtyStub", (), {})()
        create_stub.quantity = quantity
        create_stub.base_quantity = base_q
        create_stub.aux_quantity = create_aux
        InventoryService._sync_batch_ledger_quantities(create_stub, material)
        try:
            await MaterialBatch.create(
                tenant_id=tenant_id,
                material_id=material_id,
                batch_no=bn,
                quantity=create_stub.quantity,
                base_quantity=create_stub.base_quantity,
                aux_quantity=create_stub.aux_quantity,
                status="in_stock",
                quality_status=quality_status,
                production_date=create_production_date,
                expiry_date=create_expiry_date,
                ownership_type=own["ownership_type"],
                customer_id=own["customer_id"],
                customer_name=customer_name,
                source_doc_id=source_doc_id,
                source_doc_code=source_doc_code,
                warehouse_id=wh_id,
                warehouse_name=wh_name,
                **loc_kwargs,
            )
        except IntegrityError:
            batch = await MaterialBatch.filter(
                tenant_id=tenant_id,
                material_id=material_id,
                batch_no=bn,
                warehouse_id=wh_id,
                location_code=loc_code,
                quality_status=quality_status,
                **own,
            ).select_for_update().first()
            if not batch:
                from infra.exceptions.exceptions import BusinessLogicError

                legacy = await MaterialBatch.filter(
                    tenant_id=tenant_id,
                    material_id=material_id,
                    batch_no=bn,
                    warehouse_id=wh_id,
                    location_code=loc_code,
                    deleted_at__isnull=True,
                ).first()
                if legacy and (
                    legacy.ownership_type != own["ownership_type"]
                    or int(legacy.customer_id or 0) != int(own["customer_id"])
                ):
                    raise BusinessLogicError(
                        f"批号 {bn} 已存在其他归属的库存记录"
                        f"（现有：{legacy.ownership_type or 'company_owned'}"
                        f"{f'，客户 {legacy.customer_name}' if legacy.customer_name else ''}；"
                        f"本次：{own['ownership_type']}）。"
                        f"自购入库与客供库存请分别记账；若系统仍报唯一约束冲突，"
                        f"请执行数据库迁移 396/490（批次归属与仓库唯一索引）。"
                    )
                raise
            if batch.deleted_at is not None:
                batch.deleted_at = None
            batch.quantity = (batch.quantity or Decimal(0)) + quantity
            batch.base_quantity = (batch.base_quantity or Decimal(0)) + base_q
            batch.status = "in_stock"
            if wh_name and not str(batch.warehouse_name or "").strip():
                batch.warehouse_name = wh_name
            InventoryService._apply_location_fields(batch, location_id, location_code)
            await InventoryService._apply_batch_ledger_dates(
                batch,
                material=material,
                ledger_production_date=ledger_production_date,
                ledger_expiry_date=ledger_expiry_date,
            )
            InventoryService._apply_manual_aux_delta(batch, material, aux_quantity_delta)
            InventoryService._sync_batch_ledger_quantities(batch, material)
            await batch.save()

    def _ledger_aux_delta_from_base(material, base_delta: Decimal) -> Decimal:
        from apps.kuaizhizao.utils.ledger_dual_quantity_utils import (
            ledger_aux_delta_from_base_delta,
        )

        base_d = Decimal(str(base_delta or 0))
        if material is None:
            return base_d
        return ledger_aux_delta_from_base_delta(material, base_d)

    @staticmethod
    def _sync_batch_ledger_quantities(batch, material) -> None:
        from apps.kuaizhizao.utils.ledger_dual_quantity_utils import (
            sync_material_batch_ledger_quantities,
        )

        sync_material_batch_ledger_quantities(batch, material)

    @staticmethod
    def _apply_manual_aux_delta(
        batch,
        material,
        aux_quantity_delta: Optional[Decimal],
    ) -> None:
        from apps.kuaizhizao.utils.ledger_dual_quantity_utils import (
            material_ledger_uses_manual_aux_quantity,
        )

        if (
            aux_quantity_delta is None
            or material is None
            or not material_ledger_uses_manual_aux_quantity(material)
        ):
            return
        delta = Decimal(str(aux_quantity_delta))
        if delta == 0:
            return
        batch.aux_quantity = (batch.aux_quantity or Decimal(0)) + delta

    @staticmethod
    def _apply_material_batch_aux_deduct(
        batch,
        material,
        base_deduct: Decimal,
        *,
        aux_quantity_delta: Optional[Decimal] = None,
    ) -> None:
        """扣减后统一走三量校正；无固定换算时可选冲减手录副数量。"""
        del base_deduct
        from apps.kuaizhizao.utils.ledger_dual_quantity_utils import (
            material_ledger_uses_manual_aux_quantity,
        )

        if (
            aux_quantity_delta is not None
            and material is not None
            and material_ledger_uses_manual_aux_quantity(material)
        ):
            delta = Decimal(str(aux_quantity_delta))
            if delta != 0:
                batch.aux_quantity = (batch.aux_quantity or Decimal(0)) - delta
        InventoryService._sync_batch_ledger_quantities(batch, material)


    @staticmethod
    async def _material_batch_adjust_set(
        tenant_id: int,
        material_id: int,
        batch_no: str,
        quantity: Decimal,
        base_quantity: Optional[Decimal] = None,
        warehouse_id: Optional[int] = None,
        warehouse_name: Optional[str] = None,
    ) -> None:
        """盘点等场景直接设定批次数量；与 increase 相同需处理软删行与并发 insert。"""
        from apps.kuaizhizao.utils.ledger_dual_quantity_utils import ledger_aux_quantity_from_base
        from apps.master_data.models.material_batch import MaterialBatch
        from apps.master_data.models.material import Material

        bn = InventoryService._normalize_batch_no_for_ledger(batch_no)
        wh_id = InventoryService._normalize_main_warehouse_id(warehouse_id)
        wh_name = (str(warehouse_name or "").strip() or None)
        if wh_id > 0 and not wh_name:
            wh_name = await InventoryService._resolve_warehouse_name(wh_id)
        batch = await MaterialBatch.filter(
            tenant_id=tenant_id,
            material_id=material_id,
            batch_no=bn,
            warehouse_id=wh_id,
        ).select_for_update().first()
        base_q = base_quantity if base_quantity is not None else quantity
        material = await Material.get_or_none(
            tenant_id=tenant_id, id=material_id, deleted_at__isnull=True
        )
        if batch:
            if batch.deleted_at is not None:
                batch.deleted_at = None
            batch.quantity = quantity
            batch.base_quantity = base_q
            batch.status = "in_stock" if quantity > 0 else "out_stock"
            if wh_name and not str(batch.warehouse_name or "").strip():
                batch.warehouse_name = wh_name
            InventoryService._sync_batch_ledger_quantities(batch, material)
            await batch.save()
            return
        adj_stub = type("BatchQtyStub", (), {})()
        adj_stub.quantity = quantity
        adj_stub.base_quantity = base_q
        adj_stub.aux_quantity = Decimal(0)
        InventoryService._sync_batch_ledger_quantities(adj_stub, material)
        try:
            async with in_transaction():
                await MaterialBatch.create(
                    tenant_id=tenant_id,
                    material_id=material_id,
                    batch_no=bn,
                    quantity=adj_stub.quantity,
                    base_quantity=adj_stub.base_quantity,
                    aux_quantity=adj_stub.aux_quantity,
                    status="in_stock" if quantity > 0 else "out_stock",
                    warehouse_id=wh_id,
                    warehouse_name=wh_name,
                )
        except IntegrityError:
            batch = await MaterialBatch.filter(
                tenant_id=tenant_id,
                material_id=material_id,
                batch_no=bn,
                warehouse_id=wh_id,
            ).select_for_update().first()
            if not batch:
                raise
            if batch.deleted_at is not None:
                batch.deleted_at = None
            batch.quantity = quantity
            batch.base_quantity = base_q
            batch.status = "in_stock" if quantity > 0 else "out_stock"
            if wh_name and not str(batch.warehouse_name or "").strip():
                batch.warehouse_name = wh_name
            InventoryService._sync_batch_ledger_quantities(batch, material)
            await batch.save()

    @staticmethod
    @idempotent_stock_change
    async def _increase_stock_no_atomic(
        tenant_id: int,
        material_id: int,
        quantity: Decimal,
        base_quantity: Optional[Decimal] = None,
        warehouse_id: Optional[int] = None,
        batch_no: Optional[str] = None,
        serial_nos: Optional[list[str]] = None,
        source_type: Optional[str] = None,
        source_doc_id: Optional[int] = None,
        source_doc_code: Optional[str] = None,
        work_order_id: Optional[int] = None,
        work_order_code: Optional[str] = None,
        ownership_type: Optional[str] = None,
        customer_id: Optional[int] = None,
        customer_name: Optional[str] = None,
        ledger_production_date: Optional[date] = None,
        ledger_expiry_date: Optional[date] = None,
        movement_type: Optional[str] = None,
        from_warehouse_id: Optional[int] = None,
        from_warehouse_name: Optional[str] = None,
        to_warehouse_id: Optional[int] = None,
        to_warehouse_name: Optional[str] = None,
        operator_id: Optional[int] = None,
        operator_name: Optional[str] = None,
        remark: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        location_id: Optional[int] = None,
        location_code: Optional[str] = None,
        quality_status: str = QUALIFIED,
        aux_quantity_delta: Optional[Decimal] = None,
        exact_batch_no: bool = False,
        match_null_location: bool = False,
    ) -> bool:
        """
        增加库存（不开启独立事务）。

        spec 141（KR-CL2）：``idempotency_key`` 在本入口签名级强制——缺失/空白即拒绝，
        禁止无键静默过账；有键时 ``@idempotent_stock_change`` 负责 advisory lock + 流水查重。
        """
        if not (idempotency_key and str(idempotency_key).strip()):
            # 函数体内另有同名局部 import，必须用别名避免局部遮蔽
            from infra.exceptions.exceptions import ValidationError as _ValidationError

            raise _ValidationError(
                "库存过账缺少幂等键 idempotency_key: _increase_stock_no_atomic"
            )
        try:
            from apps.master_data.services.material_batch_service import MaterialBatchService
            from apps.kuaizhizao.utils.inventory_posting_utils import (
                normalize_inventory_posting_quantities,
            )
            from tortoise.exceptions import IntegrityError

            quantity = Decimal(str(quantity or 0))
            from infra.exceptions.exceptions import BusinessLogicError, ValidationError

            try:
                batch_management_enabled, serial_management_enabled = await InventoryService._get_warehouse_management_flags(tenant_id)
            except Exception:
                raise BusinessLogicError("读取仓库批号或序列号管理开关失败，拒绝本笔入库")
            from apps.master_data.models.material import Material

            material = await Material.get_or_none(
                tenant_id=tenant_id, id=material_id, deleted_at__isnull=True
            )
            quantity, base_qty_post = normalize_inventory_posting_quantities(
                material,
                quantity,
                base_quantity=base_quantity,
            )
            to_wh_id = to_warehouse_id if to_warehouse_id is not None else warehouse_id
            to_wh_name = to_warehouse_name
            from_wh_id = from_warehouse_id
            from_wh_name = from_warehouse_name
            ledger_expiry_date = MaterialBatchService.coerce_optional_date(ledger_expiry_date)
            # 根据 warehouse_type 决定写入目标
            use_line_side = False
            wh = None
            if warehouse_id is not None:
                from apps.master_data.models.warehouse import Warehouse
                wh = await Warehouse.get_or_none(
                    id=warehouse_id,
                    tenant_id=tenant_id,
                    deleted_at__isnull=True,
                )
                if wh and wh.warehouse_type == "line_side":
                    use_line_side = True

            if (
                not exact_batch_no
                and material
                and getattr(material, "batch_managed", False)
                and not (batch_no and str(batch_no).strip())
            ):
                batch_no = await MaterialBatchService.generate_batch_no(
                    tenant_id=tenant_id,
                    material_uuid=str(material.uuid),
                )

            if ledger_production_date is None and batch_no:
                ledger_production_date = await InventoryService._resolve_ledger_production_date(
                    tenant_id=tenant_id,
                    material_id=material_id,
                    batch_no=batch_no,
                    ownership_type=ownership_type,
                    customer_id=customer_id,
                    warehouse_id=warehouse_id,
                )

            if not use_line_side:
                # 批号管理校验
                if batch_management_enabled:
                    if material and getattr(material, "batch_managed", False) and not (batch_no and str(batch_no).strip()):
                        material_code = getattr(material, "main_code", None) or getattr(material, "code", "")
                        raise BusinessLogicError(f"物料 {material.name}（{material_code}）启用了批号管理，入库必须提供批号")

                # 序列号管理校验
                if serial_management_enabled:
                    if material and getattr(material, "serial_managed", False):
                        if not serial_nos or len(serial_nos) <= 0:
                            material_code = getattr(material, "main_code", None) or getattr(material, "code", "")
                            raise BusinessLogicError(f"物料 {material.name}（{material_code}）启用了序列号管理，入库必须提供序列号")
                        expected = Decimal(len(serial_nos))
                        if abs(Decimal(str(base_qty_post)) - expected) > Decimal("0.001"):
                            raise BusinessLogicError(
                                f"入库基本数量（{base_qty_post}）与序列号数量（{len(serial_nos)}）不一致"
                            )

                if (
                    material
                    and getattr(material, "batch_managed", False)
                    and batch_no
                    and str(batch_no).strip()
                    and str(batch_no).strip() != "DEFAULT"
                    and ledger_production_date is None
                ):
                    raise BusinessLogicError("批号管理物料入库必须提供入库日期（来自入库单确认时间）")
                if serial_nos and ledger_production_date is None:
                    raise BusinessLogicError("序列号入库必须提供入库日期（来自入库单确认时间）")

                main_wh_id = InventoryService._normalize_main_warehouse_id(warehouse_id)
                main_wh_name = to_wh_name or await InventoryService._resolve_warehouse_name(
                    main_wh_id if main_wh_id > 0 else None
                )
                logger.info(f"Adding stock for material_id={material_id}, batch_no={batch_no}, qty={quantity}")
                if exact_batch_no:
                    bn_norm = str(batch_no or "").strip()
                else:
                    bn_norm = InventoryService._normalize_batch_no_for_ledger(batch_no or "DEFAULT")
                existing_batch = await InventoryService._find_in_stock_material_batch(
                    tenant_id=tenant_id,
                    material_id=material_id,
                    batch_no=bn_norm,
                    ownership_type=ownership_type,
                    customer_id=customer_id,
                    warehouse_id=main_wh_id,
                    for_update=True,
                    quality_status=quality_status,
                )
                qty_before = Decimal(str(existing_batch.quantity or 0)) if existing_batch else Decimal(0)
                base_qty_before = (
                    Decimal(str(existing_batch.base_quantity or 0)) if existing_batch else Decimal(0)
                )
                await InventoryService._material_batch_increase_or_restore(
                    tenant_id=tenant_id,
                    material_id=material_id,
                    batch_no=bn_norm if exact_batch_no else (batch_no or "DEFAULT"),
                    quantity=quantity,
                    base_quantity=base_qty_post,
                    ownership_type=ownership_type,
                    customer_id=customer_id,
                    customer_name=customer_name,
                    source_doc_id=source_doc_id,
                    source_doc_code=source_doc_code,
                    ledger_production_date=ledger_production_date,
                    ledger_expiry_date=ledger_expiry_date,
                    material=material,
                    warehouse_id=main_wh_id,
                    warehouse_name=main_wh_name,
                    location_id=location_id,
                    location_code=location_code,
                    quality_status=quality_status,
                    aux_quantity_delta=aux_quantity_delta,
                    exact_batch_no=exact_batch_no,
                    match_null_location=match_null_location,
                )
                qty_after = qty_before + quantity
                base_qty_after = base_qty_before + base_qty_post
                await InventoryService._record_stock_movement(
                    tenant_id=tenant_id,
                    material_id=material_id,
                    quantity=quantity,
                    qty_before=qty_before,
                    qty_after=qty_after,
                    base_quantity=base_qty_post,
                    base_qty_before=base_qty_before,
                    base_qty_after=base_qty_after,
                    batch_no=bn_norm,
                    movement_type=movement_type,
                    from_warehouse_id=from_wh_id,
                    from_warehouse_name=from_wh_name,
                    to_warehouse_id=to_wh_id if to_wh_id is not None else (main_wh_id or None),
                    to_warehouse_name=to_wh_name or main_wh_name,
                    balance_warehouse_id=main_wh_id or warehouse_id,
                    source_type=source_type,
                    source_doc_id=source_doc_id,
                    source_doc_code=source_doc_code,
                    work_order_id=work_order_id,
                    work_order_code=work_order_code,
                    operator_id=operator_id,
                    operator_name=operator_name,
                    remark=remark,
                    idempotency_key=idempotency_key,
                )

                # 记录序列号
                if serial_nos:
                    from apps.master_data.models.material_serial import MaterialSerial
                    from apps.kuaizhizao.models.material_stock_movement import MaterialStockMovement
                    from apps.kuaizhizao.services.material_serial_document_ledger_service import (
                        DIRECTION_IN,
                        record_serial_document_ledger,
                    )

                    # 锁序约定（spec 141 KR-CL2）：先批次行锁（上方
                    # _find_in_stock_material_batch for_update），再按序列号排序
                    # 逐条 select_for_update；序列号与批次在同一 DB 事务、同成败。
                    # 全路径统一该锁序，避免并发互锁。查询显式带 tenant_id 仅为
                    # 业务定位；组织隔离由 spec 143 ORM 强制机制注入保证。
                    # 留痕写在序列号创建/更新之后、同一事务内；写入失败由外层回滚整笔过账。
                    for s_no in sorted(serial_nos, key=lambda v: str(v or "")):
                        existing = await MaterialSerial.filter(tenant_id=tenant_id, serial_no=s_no).select_for_update().first()
                        reconfirm_tolerant = False
                        if existing:
                            if existing.status == "in_stock":
                                if source_type and str(source_type).endswith("_withdraw"):
                                    await record_serial_document_ledger(
                                        tenant_id=tenant_id,
                                        serial_no=s_no,
                                        material_id=material_id,
                                        direction=DIRECTION_IN,
                                        movement_type=movement_type,
                                        source_type=source_type,
                                        source_doc_id=source_doc_id,
                                        source_doc_code=source_doc_code,
                                        idempotency_key=idempotency_key,
                                        operator_id=operator_id,
                                        operator_name=operator_name,
                                    )
                                    continue
                                # 同单撤回曾冲数量但未回冲序列号台账时，允许再确认入库对齐台账
                                _revoke_src = _RECONFIRM_TOLERANT_REVOKE_SOURCE_TYPES.get(
                                    str(source_type or "")
                                )
                                if (
                                    _revoke_src
                                    and source_doc_id
                                    and await MaterialStockMovement.filter(
                                        tenant_id=tenant_id,
                                        source_type=_revoke_src,
                                        source_doc_id=int(source_doc_id),
                                    ).exists()
                                ):
                                    reconfirm_tolerant = True
                                else:
                                    raise BusinessLogicError(f"序列号 {s_no} 已在库，不可重复入库")
                            else:
                                existing.status = "in_stock"
                                existing.material_id = material_id
                                if existing.production_date is None and ledger_production_date is not None:
                                    existing.production_date = ledger_production_date
                                await existing.save()
                        else:
                            await MaterialSerial.create(
                                tenant_id=tenant_id,
                                material_id=material_id,
                                serial_no=s_no,
                                production_date=ledger_production_date,
                                status="in_stock",
                            )
                        await record_serial_document_ledger(
                            tenant_id=tenant_id,
                            serial_no=s_no,
                            material_id=material_id,
                            direction=DIRECTION_IN,
                            movement_type=movement_type,
                            source_type=source_type,
                            source_doc_id=source_doc_id,
                            source_doc_code=source_doc_code,
                            idempotency_key=idempotency_key,
                            operator_id=operator_id,
                            operator_name=operator_name,
                            reconfirm_tolerant=reconfirm_tolerant,
                        )

                logger.info(
                    f"InventoryService.increase_stock: tenant={tenant_id} material={material_id} "
                    f"qty={quantity} warehouse={warehouse_id} batch={batch_no} source={source_type}"
                )
            else:
                # 线边仓处理
                from apps.kuaizhizao.models.line_side_inventory import LineSideInventory

                wh_name = str(wh.name if wh else "").strip()
                inv_filter = dict(
                    tenant_id=tenant_id,
                    warehouse_id=warehouse_id,
                    material_id=material_id,
                    deleted_at__isnull=True,
                    status="available",
                )
                if batch_no:
                    inv_filter["batch_no"] = batch_no
                inv = await LineSideInventory.filter(**inv_filter).select_for_update().first()
                qty_before = Decimal(str(inv.quantity or 0)) if inv else Decimal(0)
                base_qty_before = Decimal(str(inv.base_quantity or 0)) if inv else Decimal(0)
                loc_kwargs = InventoryService._normalize_location_kwargs(location_id, location_code)
                if inv:
                    inv.quantity = qty_before + quantity
                    inv.base_quantity = base_qty_before + base_qty_post
                    if work_order_id and not inv.work_order_id:
                        inv.work_order_id = work_order_id
                        inv.work_order_code = work_order_code
                    if wh_name and not str(inv.warehouse_name or "").strip():
                        inv.warehouse_name = wh_name
                    InventoryService._apply_location_fields(inv, location_id, location_code)
                    await inv.save()
                else:
                    mat = material or await Material.get_or_none(id=material_id)
                    await LineSideInventory.create(
                        tenant_id=tenant_id,
                        warehouse_id=warehouse_id,
                        warehouse_name=wh_name or None,
                        material_id=material_id,
                        material_code=mat.code if mat else "",
                        material_name=mat.name if mat else "",
                        batch_no=batch_no or "",
                        quantity=quantity,
                        base_quantity=base_qty_post,
                        reserved_quantity=Decimal(0),
                        status="available",
                        source_type=source_type or "direct",
                        source_doc_id=source_doc_id,
                        source_doc_code=source_doc_code or "",
                        work_order_id=work_order_id,
                        work_order_code=work_order_code,
                        **loc_kwargs,
                    )
                await InventoryService._record_stock_movement(
                    tenant_id=tenant_id,
                    material_id=material_id,
                    quantity=quantity,
                    qty_before=qty_before,
                    qty_after=qty_before + quantity,
                    base_quantity=base_qty_post,
                    base_qty_before=base_qty_before,
                    base_qty_after=base_qty_before + base_qty_post,
                    batch_no=batch_no,
                    movement_type=movement_type,
                    from_warehouse_id=from_wh_id,
                    from_warehouse_name=from_wh_name,
                    to_warehouse_id=to_wh_id if to_wh_id is not None else warehouse_id,
                    to_warehouse_name=to_wh_name or wh_name or None,
                    balance_warehouse_id=warehouse_id,
                    source_type=source_type,
                    source_doc_id=source_doc_id,
                    source_doc_code=source_doc_code,
                    work_order_id=work_order_id,
                    work_order_code=work_order_code,
                    operator_id=operator_id,
                    operator_name=operator_name,
                    remark=remark,
                    idempotency_key=idempotency_key,
                )
            from apps.kuaizhizao.services.work_order_readiness_service import notify_inventory_changed

            notify_inventory_changed(tenant_id, material_id)
            return True
        except (BusinessLogicError, ValidationError, IntegrityError) as e:
            logger.error(f"InventoryService.increase_stock 失败: {e}")
            raise
        except Exception as e:
            # 库存变动必须回滚，不可静默
            logger.error(f"InventoryService.increase_stock 失败: {e}")
            raise

    @staticmethod
    def _synthesize_idempotency_key(
        action: str,
        *,
        source_type: Optional[str],
        source_doc_id: Optional[int],
        material_id: Optional[int] = None,
        batch_no: Optional[str] = None,
        warehouse_id: Optional[int] = None,
        from_warehouse_id: Optional[int] = None,
        to_warehouse_id: Optional[int] = None,
        quantity: Optional[Decimal] = None,
        movement_type: Optional[str] = None,
        work_order_id: Optional[int] = None,
        serial_nos: Optional[list] = None,
    ) -> str:
        """
        包装层缺键时的确定性幂等键（spec 141 KR-CL2，A 案）。

        基键为 单据类型 + 单据ID + 动作 + 明细判别摘要（material/batch/warehouse/qty/
        movement/serial）：同一单据多行明细各自过账需不同键，逐行循环调用方不能只靠
        单据级键；判别字段完全相同的重复明细按本调用上下文内出现序号 ``#s{n}`` 区分，
        重试按相同顺序重放得到同一组键 → 同键去重不加量。source_type/source_doc_id
        任一缺失即拒绝（失败关闭）。
        """
        st = str(source_type or "").strip()
        try:
            doc_id = int(source_doc_id) if source_doc_id is not None else 0
        except (TypeError, ValueError):
            doc_id = 0
        if not st or doc_id <= 0:
            raise ValidationError(
                f"无法合成库存幂等键：缺少 source_type/source_doc_id（action={action}）"
            )
        discriminator = "|".join(
            [
                str(material_id or ""),
                str(batch_no or ""),
                str(warehouse_id or ""),
                str(from_warehouse_id or ""),
                str(to_warehouse_id or ""),
                str(quantity or ""),
                str(movement_type or ""),
                str(work_order_id or ""),
                ",".join(str(s) for s in (serial_nos or [])),
            ]
        )
        digest = hashlib.sha256(discriminator.encode()).hexdigest()[:16]
        base = f"{st}:{doc_id}:{action}:{digest}"
        seqs = _synth_stock_key_counter.get()
        if seqs is None:
            seqs = {}
            _synth_stock_key_counter.set(seqs)
        occurrence = seqs.get(base, 0)
        seqs[base] = occurrence + 1
        return base if occurrence == 0 else f"{base}#s{occurrence}"

    @staticmethod
    @atomic_stock_change
    async def increase_stock(
        tenant_id: int,
        material_id: int,
        quantity: Decimal,
        base_quantity: Optional[Decimal] = None,
        warehouse_id: Optional[int] = None,
        batch_no: Optional[str] = None,
        serial_nos: Optional[list[str]] = None,
        source_type: Optional[str] = None,
        source_doc_id: Optional[int] = None,
        source_doc_code: Optional[str] = None,
        work_order_id: Optional[int] = None,
        work_order_code: Optional[str] = None,
        ownership_type: Optional[str] = None,
        customer_id: Optional[int] = None,
        customer_name: Optional[str] = None,
        ledger_production_date: Optional[date] = None,
        ledger_expiry_date: Optional[date] = None,
        movement_type: Optional[str] = None,
        from_warehouse_id: Optional[int] = None,
        from_warehouse_name: Optional[str] = None,
        to_warehouse_id: Optional[int] = None,
        to_warehouse_name: Optional[str] = None,
        operator_id: Optional[int] = None,
        operator_name: Optional[str] = None,
        remark: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        location_id: Optional[int] = None,
        location_code: Optional[str] = None,
        quality_status: str = QUALIFIED,
        aux_quantity_delta: Optional[Decimal] = None,
        exact_batch_no: bool = False,
        match_null_location: bool = False,
    ) -> bool:
        """
        增加库存（独立事务包装）。

        调用方未传 ``idempotency_key`` 时按 A 案合成确定性键
        （``source_type`` + ``source_doc_id`` + 动作 + 明细判别），
        字段不足无法合成则拒绝；显式传键的调用方沿用原键。
        """
        if not (idempotency_key and str(idempotency_key).strip()):
            idempotency_key = InventoryService._synthesize_idempotency_key(
                "increase",
                source_type=source_type,
                source_doc_id=source_doc_id,
                material_id=material_id,
                batch_no=batch_no,
                warehouse_id=warehouse_id,
                from_warehouse_id=from_warehouse_id,
                to_warehouse_id=to_warehouse_id,
                quantity=quantity,
                movement_type=movement_type,
                work_order_id=work_order_id,
                serial_nos=serial_nos,
            )
        return await InventoryService._increase_stock_no_atomic(
            tenant_id=tenant_id,
            material_id=material_id,
            quantity=quantity,
            base_quantity=base_quantity,
            warehouse_id=warehouse_id,
            batch_no=batch_no,
            serial_nos=serial_nos,
            source_type=source_type,
            source_doc_id=source_doc_id,
            source_doc_code=source_doc_code,
            work_order_id=work_order_id,
            work_order_code=work_order_code,
            ownership_type=ownership_type,
            customer_id=customer_id,
            customer_name=customer_name,
            ledger_production_date=ledger_production_date,
            ledger_expiry_date=ledger_expiry_date,
            movement_type=movement_type,
            from_warehouse_id=from_warehouse_id,
            from_warehouse_name=from_warehouse_name,
            to_warehouse_id=to_warehouse_id,
            to_warehouse_name=to_warehouse_name,
            operator_id=operator_id,
            operator_name=operator_name,
            remark=remark,
            idempotency_key=idempotency_key,
            location_id=location_id,
            location_code=location_code,
            quality_status=quality_status,
            aux_quantity_delta=aux_quantity_delta,
            exact_batch_no=exact_batch_no,
            match_null_location=match_null_location,
        )

    @staticmethod
    async def _mark_serials_out_stock(
        tenant_id: int,
        material_id: int,
        serial_nos: Optional[list[str]],
        *,
        source_type: Optional[str] = None,
        source_doc_id: Optional[int] = None,
        source_doc_code: Optional[str] = None,
        movement_type: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        operator_id: Optional[int] = None,
        operator_name: Optional[str] = None,
    ) -> None:
        """出库扣减后同步序列号为已出库，并在同一事务写出入库留痕。

        锁序约定（spec 141 KR-CL2）：与入库一致——先批次行锁（扣减分支已对批次
        ``select_for_update``），再按序列号排序逐条 ``select_for_update``；
        序列号与批次扣减在同一 DB 事务提交，任一侧失败全滚。
        查询显式带 ``tenant_id`` 仅为业务定位；组织隔离由 spec 143
        ORM 强制机制注入保证。无序列号直接返回，不记台账。
        """
        if not serial_nos:
            return
        from apps.master_data.models.material_serial import MaterialSerial
        from apps.kuaizhizao.services.material_serial_document_ledger_service import (
            DIRECTION_OUT,
            record_serial_document_ledger,
        )

        for s_no in sorted(serial_nos, key=lambda v: str(v or "")):
            sn = str(s_no or "").strip()
            if not sn:
                continue
            existing = await MaterialSerial.filter(
                tenant_id=tenant_id,
                serial_no=sn,
                deleted_at__isnull=True,
            ).select_for_update().first()
            if not existing:
                raise BusinessLogicError(f"序列号 {sn} 不存在，无法出库")
            if int(existing.material_id) != int(material_id):
                raise BusinessLogicError(f"序列号 {sn} 不属于当前物料，无法出库")
            if existing.status != "in_stock":
                raise BusinessLogicError(f"序列号 {sn} 不在库，无法出库")
            existing.status = "out_stock"
            await existing.save()
            await record_serial_document_ledger(
                tenant_id=tenant_id,
                serial_no=sn,
                material_id=material_id,
                direction=DIRECTION_OUT,
                movement_type=movement_type,
                source_type=source_type,
                source_doc_id=source_doc_id,
                source_doc_code=source_doc_code,
                idempotency_key=idempotency_key,
                operator_id=operator_id,
                operator_name=operator_name,
            )

    @staticmethod
    @idempotent_stock_change

    async def _decrease_stock_no_atomic(
        tenant_id: int,
        material_id: int,
        quantity: Decimal,
        base_quantity: Optional[Decimal] = None,
        warehouse_id: Optional[int] = None,
        batch_no: Optional[str] = None,
        serial_nos: Optional[list[str]] = None,
        source_type: Optional[str] = None,
        source_doc_id: Optional[int] = None,
        source_doc_code: Optional[str] = None,
        enforce_fifo: bool = False,
        ownership_type: Optional[str] = None,
        customer_id: Optional[int] = None,
        work_order_id: Optional[int] = None,
        work_order_code: Optional[str] = None,
        movement_type: Optional[str] = None,
        from_warehouse_id: Optional[int] = None,
        from_warehouse_name: Optional[str] = None,
        to_warehouse_id: Optional[int] = None,
        to_warehouse_name: Optional[str] = None,
        operator_id: Optional[int] = None,
        operator_name: Optional[str] = None,
        remark: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        stock_quality_status: str = QUALIFIED,
        aux_quantity_delta: Optional[Decimal] = None,
        location_id: Optional[int] = None,
        location_code: Optional[str] = None,
        *,
        location_scoped: bool = False,
    ) -> bool:
        """
        扣减库存（不开启独立事务）。见 `_increase_stock_no_atomic` 说明。

        ``idempotency_key`` 在本入口签名级强制：缺失/空白即拒绝（spec 141 KR-CL2）。

        location_scoped=True：仅扣减指定库位台账（明细已选库位时必开，避免跨库位误扣）。
        """
        if not (idempotency_key and str(idempotency_key).strip()):
            # 函数体内另有同名局部 import，必须用别名避免局部遮蔽
            from infra.exceptions.exceptions import ValidationError as _ValidationError

            raise _ValidationError(
                "库存过账缺少幂等键 idempotency_key: _decrease_stock_no_atomic"
            )
        try:
            from infra.exceptions.exceptions import BusinessLogicError
            from apps.kuaizhizao.utils.inventory_posting_utils import (
                normalize_inventory_posting_quantities,
            )
            from apps.master_data.models.material import Material

            quantity = Decimal(str(quantity or 0))
            if quantity <= 0:
                raise BusinessLogicError(f"扣减数量必须大于0: {quantity}")

            batch_management_enabled, _ = await InventoryService._get_warehouse_management_flags(tenant_id)
            material = await Material.get_or_none(
                tenant_id=tenant_id, id=material_id, deleted_at__isnull=True
            )
            quantity, base_qty_post = normalize_inventory_posting_quantities(
                material,
                quantity,
                base_quantity=base_quantity,
            )

            from_wh_id = from_warehouse_id if from_warehouse_id is not None else warehouse_id
            from_wh_name = from_warehouse_name
            to_wh_id = to_warehouse_id
            to_wh_name = to_warehouse_name
            loc_kwargs = InventoryService._normalize_location_kwargs(location_id, location_code)
            scoped_location_code = str(loc_kwargs.get("location_code") or "")

            # 根据 warehouse_type 决定扣减目标：line_side → LineSideInventory，否则 → MaterialBatch
            use_line_side = False
            if warehouse_id is not None:
                from apps.master_data.models.warehouse import Warehouse
                wh = await Warehouse.get_or_none(
                    id=warehouse_id,
                    tenant_id=tenant_id,
                    deleted_at__isnull=True,
                )
                if wh and wh.warehouse_type == "line_side":
                    use_line_side = True

            allow_negative = await InventoryService._get_allow_negative_inventory(tenant_id)

            if warehouse_id is not None and not allow_negative:
                if location_scoped:
                    available = await InventoryService.get_quantity(
                        tenant_id,
                        material_id,
                        warehouse_id=int(warehouse_id),
                        batch_no=batch_no,
                        location_code=scoped_location_code,
                    )
                    if available < quantity:
                        loc_hint = scoped_location_code or "（未分库位）"
                        raise BusinessLogicError(
                            f"库存不足：库位 {loc_hint} 需求 {quantity}，可用 {available}"
                        )
                else:
                    from apps.kuaizhizao.utils.inventory_helper import (
                        assert_outbound_warehouse_stock_available,
                    )

                    await assert_outbound_warehouse_stock_available(
                        tenant_id=tenant_id,
                        material_id=material_id,
                        warehouse_id=int(warehouse_id),
                        quantity=quantity,
                        batch_no=batch_no,
                        ownership_type=ownership_type,
                        customer_id=customer_id,
                    )

            if not use_line_side:
                from apps.master_data.models.material_batch import MaterialBatch
                from apps.master_data.models.material import Material

                cfg = await BusinessConfigService().get_business_config(tenant_id)
                wh_cfg = cfg.get("parameters", {}).get("warehouse", {})
                lifo_enabled = bool(wh_cfg.get("lifo", False))
                from apps.kuaizhizao.services.fifo_policy import (
                    fifo_mode_label,
                    normalize_fifo_mode,
                    pick_blocking_older_batch,
                    batch_fifo_sort_key,
                )

                fifo_mode = normalize_fifo_mode(wh_cfg.get("fifo_mode"))
                skip_batch_order_enforcement = (
                    str(source_type or "").strip() in _BATCH_ORDER_ENFORCEMENT_EXEMPT_SOURCE_TYPES
                )
                is_batch_managed = bool(
                    batch_management_enabled
                    and material
                    and getattr(material, "batch_managed", False)
                )
                src_type = str(source_type or "").strip()
                if is_batch_managed:
                    resolved_batch = resolve_managed_decrease_batch_no(batch_no, source_type)
                    if resolved_batch is None:
                        material_code = getattr(material, "main_code", None) or getattr(
                            material, "code", ""
                        )
                        raise BusinessLogicError(
                            f"物料 {material.name}（{material_code}）启用了批号管理，出库必须指定批号"
                        )
                    raw_batch = resolved_batch
                else:
                    raw_batch = str(batch_no or "").strip()

                own = InventoryService._ownership_filter(ownership_type, customer_id)
                main_wh_id = InventoryService._normalize_main_warehouse_id(warehouse_id)
                stock_qs_filter = {"quality_status": stock_quality_status}
                # 非批号管理物料：空批号或 DEFAULT 表示未指定，按 FIFO/LIFO 跨批扣减。
                # 禁止把 DEFAULT 当成真实批号去查（前端曾把空串 normalize 成 DEFAULT 导致误报库存不足）。
                # 入库撤回允许显式 DEFAULT：中途启用批号后仍须冲掉原无批号台账。
                ledger_bn = InventoryService._normalize_batch_no_for_ledger(raw_batch) if raw_batch else ""
                use_specific_batch = bool(raw_batch) and (
                    is_batch_managed
                    or ledger_bn != "DEFAULT"
                    or src_type in _INBOUND_REVOKE_ALLOW_DEFAULT_BATCH_SOURCE_TYPES
                )
                if use_specific_batch:
                    from apps.kuaizhizao.utils.inventory_posting_utils import (
                        split_base_deduct_for_inventory_deduct,
                    )

                    matched = await InventoryService._list_in_stock_material_batches(
                        tenant_id=tenant_id,
                        material_id=material_id,
                        batch_no=raw_batch,
                        ownership_type=ownership_type,
                        customer_id=customer_id,
                        warehouse_id=main_wh_id,
                        for_update=True,
                        include_unassigned=True,
                        quality_status=stock_quality_status,
                        require_positive_qty=True,
                        location_code=scoped_location_code if location_scoped else None,
                        location_scoped=location_scoped,
                    )
                    if lifo_enabled and not enforce_fifo:
                        matched = sorted(
                            matched,
                            key=lambda b: (
                                0 if int(getattr(b, "warehouse_id", 0) or 0) == int(main_wh_id or 0) else 1,
                                -int(getattr(b, "id", 0) or 0),
                            ),
                        )
                    else:
                        matched = sorted(
                            matched,
                            key=lambda b: (
                                0 if int(getattr(b, "warehouse_id", 0) or 0) == int(main_wh_id or 0) else 1,
                                batch_fifo_sort_key(b, fifo_mode),
                            ),
                        )
                    have_same_batch = sum((b.quantity or Decimal(0)) for b in matched)
                    available_rows = await MaterialBatch.filter(
                        tenant_id=tenant_id,
                        material_id=material_id,
                        deleted_at__isnull=True,
                        status="in_stock",
                        quantity__gt=0,
                        **own,
                        **stock_qs_filter,
                    ).filter(
                        InventoryService._main_warehouse_balance_q(main_wh_id)
                    ).values_list("batch_no", "quantity")
                    available_hint = "、".join(
                        f"{InventoryService._normalize_batch_no_for_ledger(str(bn))}({qty})"
                        for bn, qty in available_rows
                    ) or "无"

                    if not matched:
                        if not allow_negative:
                            raise BusinessLogicError(
                                f"库存不足：批号 {ledger_bn} 需求 {quantity}，可用 0；"
                                f"其他可用：{available_hint}（截至查询时刻）"
                            )
                        wh_name = (
                            from_wh_name
                            or await InventoryService._resolve_warehouse_name(main_wh_id)
                        )
                        qty_before = Decimal(0)
                        next_qty = -quantity
                        neg_stub = type("BatchQtyStub", (), {})()
                        neg_stub.quantity = next_qty
                        neg_stub.base_quantity = -base_qty_post
                        neg_stub.aux_quantity = Decimal(0)
                        stamp_negative_batch_manual_aux(neg_stub, material, aux_quantity_delta)
                        create_kw: Dict[str, Any] = dict(
                            tenant_id=tenant_id,
                            material_id=material_id,
                            batch_no=ledger_bn,
                            quantity=neg_stub.quantity,
                            base_quantity=neg_stub.base_quantity,
                            aux_quantity=neg_stub.aux_quantity,
                            status="in_stock",
                            quality_status=stock_quality_status,
                            ownership_type=own["ownership_type"],
                            customer_id=own["customer_id"],
                            warehouse_id=main_wh_id,
                            warehouse_name=wh_name,
                            location_code=scoped_location_code if location_scoped else "",
                        )
                        if location_scoped and loc_kwargs.get("location_id") is not None:
                            create_kw["location_id"] = loc_kwargs["location_id"]
                        await MaterialBatch.create(**create_kw)
                        await InventoryService._record_stock_movement(
                            tenant_id=tenant_id,
                            material_id=material_id,
                            quantity=-quantity,
                            qty_before=qty_before,
                            qty_after=next_qty,
                            base_quantity=-base_qty_post,
                            base_qty_before=Decimal(0),
                            base_qty_after=-base_qty_post,
                            batch_no=ledger_bn,
                            movement_type=movement_type,
                            from_warehouse_id=from_wh_id,
                            from_warehouse_name=from_wh_name,
                            to_warehouse_id=to_wh_id,
                            to_warehouse_name=to_wh_name,
                            balance_warehouse_id=main_wh_id or warehouse_id,
                            source_type=source_type,
                            source_doc_id=source_doc_id,
                            source_doc_code=source_doc_code,
                            work_order_id=work_order_id,
                            work_order_code=work_order_code,
                            operator_id=operator_id,
                            operator_name=operator_name,
                            remark=remark,
                            idempotency_key=idempotency_key,
                            **InventoryService._movement_location_kwargs(
                                location_code=scoped_location_code if location_scoped else "",
                                location_id=loc_kwargs.get("location_id") if location_scoped else None,
                            ),
                        )
                    elif have_same_batch < quantity and not allow_negative:
                        raise BusinessLogicError(
                            f"库存不足：批号 {ledger_bn} 需求 {quantity}，可用 "
                            f"{have_same_batch}；其他可用：{available_hint}"
                        )
                    else:
                        # 同批号多库位台账按 FIFO/LIFO 分摊扣减；防呆只对照「其他批号」
                        current_for_order = matched[0]
                        if enforce_fifo and not skip_batch_order_enforcement:
                            siblings = await MaterialBatch.filter(
                                tenant_id=tenant_id,
                                material_id=material_id,
                                deleted_at__isnull=True,
                                status="in_stock",
                                quantity__gt=0,
                                **stock_qs_filter,
                            ).filter(
                                InventoryService._main_warehouse_balance_q(main_wh_id)
                            ).all()
                            siblings_other_bn = [
                                s
                                for s in siblings
                                if InventoryService._normalize_batch_no_for_ledger(
                                    str(getattr(s, "batch_no", "") or "")
                                )
                                != ledger_bn
                            ]
                            older_batch = pick_blocking_older_batch(
                                current_for_order, siblings_other_bn, fifo_mode
                            )
                            if older_batch:
                                raise BusinessLogicError(
                                    f"【防呆拦截】当前物料不符合先入先出"
                                    f"（判定：{fifo_mode_label(fifo_mode)}）！"
                                    f"系统内仍存在应优先领用的批次 (批号:{older_batch.batch_no}) 未用完！"
                                    f"请优先领用该批次以防产品滞留过期。"
                                )
                        if lifo_enabled and not enforce_fifo and not skip_batch_order_enforcement:
                            newer_batch = await MaterialBatch.filter(
                                tenant_id=tenant_id,
                                material_id=material_id,
                                deleted_at__isnull=True,
                                status="in_stock",
                                quantity__gt=0,
                                id__gt=current_for_order.id,
                                **stock_qs_filter,
                            ).filter(
                                InventoryService._main_warehouse_balance_q(main_wh_id)
                            ).order_by("-id").first()
                            if newer_batch and InventoryService._normalize_batch_no_for_ledger(
                                str(getattr(newer_batch, "batch_no", "") or "")
                            ) != ledger_bn:
                                raise BusinessLogicError(
                                    f"【防呆拦截】当前物料不符合后进先出！"
                                    f"系统内仍存在更新批次 (批号:{newer_batch.batch_no}) 未用完！"
                                    f"请优先领用最新批次。"
                                )

                        remaining = quantity
                        remaining_base = base_qty_post
                        remaining_aux = (
                            Decimal(str(aux_quantity_delta))
                            if aux_quantity_delta is not None
                            else None
                        )
                        part_idx = 0
                        for idx, batch in enumerate(matched):
                            if remaining <= 0:
                                break
                            if int(getattr(batch, "warehouse_id", 0) or 0) == 0 and main_wh_id > 0:
                                batch.warehouse_id = main_wh_id
                                batch.warehouse_name = (
                                    from_wh_name
                                    or await InventoryService._resolve_warehouse_name(main_wh_id)
                                )
                            is_last = idx == len(matched) - 1
                            if allow_negative and is_last:
                                deduct = remaining
                            else:
                                deduct = min(remaining, batch.quantity or Decimal(0))
                            if deduct <= 0:
                                continue
                            qty_before = Decimal(str(batch.quantity or 0))
                            base_qty_before = Decimal(str(batch.base_quantity or 0))
                            deduct_base = split_base_deduct_for_inventory_deduct(
                                quantity,
                                base_qty_post,
                                deduct,
                                remaining_base=remaining_base if remaining - deduct <= 0 else None,
                            )
                            next_qty = qty_before - deduct
                            next_base_qty = base_qty_before - deduct_base
                            if next_qty < 0 and not allow_negative:
                                raise BusinessLogicError(
                                    f"并发扣减导致库存不足: material={material_id} batch={ledger_bn} "
                                    f"need={quantity} have={have_same_batch}"
                                )
                            batch.quantity = next_qty
                            batch.base_quantity = next_base_qty
                            finishes_qty = remaining - deduct <= 0
                            aux_share, remaining_aux = split_manual_aux_deduct_share(
                                quantity,
                                aux_quantity_delta,
                                deduct,
                                remaining_aux,
                                finishes_quantity=finishes_qty,
                            )
                            InventoryService._apply_material_batch_aux_deduct(
                                batch,
                                material,
                                deduct_base,
                                aux_quantity_delta=aux_share,
                            )
                            InventoryService._sync_material_batch_status_after_qty_change(batch)
                            await batch.save()
                            key = idempotency_key
                            if key and part_idx > 0:
                                key = f"{key}#p{part_idx}"
                            await InventoryService._record_stock_movement(
                                tenant_id=tenant_id,
                                material_id=material_id,
                                quantity=-deduct,
                                qty_before=qty_before,
                                qty_after=next_qty,
                                base_quantity=-deduct_base,
                                base_qty_before=base_qty_before,
                                base_qty_after=next_base_qty,
                                batch_no=ledger_bn,
                                movement_type=movement_type,
                                from_warehouse_id=from_wh_id,
                                from_warehouse_name=from_wh_name,
                                to_warehouse_id=to_wh_id,
                                to_warehouse_name=to_wh_name,
                                balance_warehouse_id=main_wh_id or warehouse_id,
                                source_type=source_type,
                                source_doc_id=source_doc_id,
                                source_doc_code=source_doc_code,
                                work_order_id=work_order_id,
                                work_order_code=work_order_code,
                                operator_id=operator_id,
                                operator_name=operator_name,
                                remark=remark,
                                idempotency_key=key,
                                **InventoryService._movement_location_kwargs(batch),
                            )
                            remaining -= deduct
                            remaining_base -= deduct_base
                            part_idx += 1
                        if remaining > 0 and not allow_negative:
                            raise BusinessLogicError(
                                f"并发扣减导致库存不足: material={material_id} batch={ledger_bn} "
                                f"need={quantity} have={have_same_batch}"
                            )
                else:
                    # 默认 FIFO（按 fifo_mode）；若开启 LIFO 且未开启 FIFO，则按最新批次扣减
                    # 同仓优先于历史未归属(warehouse_id=0)
                    cross_loc_filters: Dict[str, Any] = dict(
                        tenant_id=tenant_id,
                        material_id=material_id,
                        deleted_at__isnull=True,
                        status="in_stock",
                        quantity__gt=0,
                        **own,
                        **stock_qs_filter,
                    )
                    batch_query = (
                        MaterialBatch.filter(**cross_loc_filters)
                        .filter(InventoryService._main_warehouse_balance_q(main_wh_id))
                    )
                    if location_scoped:
                        batch_query = batch_query.filter(
                            InventoryService._scoped_location_filter(scoped_location_code)
                        )
                    batches = await batch_query.select_for_update().all()
                    if lifo_enabled and not enforce_fifo:
                        batches = sorted(
                            batches,
                            key=lambda b: (
                                0 if int(getattr(b, "warehouse_id", 0) or 0) == int(main_wh_id or 0) else 1,
                                -int(getattr(b, "id", 0) or 0),
                            ),
                        )
                    else:
                        batches = sorted(
                            batches,
                            key=lambda b: (
                                0 if int(getattr(b, "warehouse_id", 0) or 0) == int(main_wh_id or 0) else 1,
                                batch_fifo_sort_key(b, fifo_mode),
                            ),
                        )
                    remaining = quantity
                    remaining_base = base_qty_post
                    remaining_aux = (
                        Decimal(str(aux_quantity_delta))
                        if aux_quantity_delta is not None
                        else None
                    )
                    from apps.kuaizhizao.utils.inventory_posting_utils import (
                        split_base_deduct_for_inventory_deduct,
                    )

                    have_before = sum((b.quantity or Decimal(0)) for b in batches)
                    available_hint = "、".join(
                        f"{InventoryService._normalize_batch_no_for_ledger(str(b.batch_no))}({b.quantity})"
                        for b in batches
                    ) or "无"
                    part_idx = 0
                    for b in batches:
                        if remaining <= 0:
                            break
                        if int(getattr(b, "warehouse_id", 0) or 0) == 0 and main_wh_id > 0:
                            b.warehouse_id = main_wh_id
                            b.warehouse_name = (
                                from_wh_name
                                or await InventoryService._resolve_warehouse_name(main_wh_id)
                            )
                        deduct = min(remaining, b.quantity or Decimal(0))
                        if deduct > 0:
                            qty_before = Decimal(str(b.quantity or 0))
                            base_qty_before = Decimal(str(b.base_quantity or 0))
                            deduct_base = split_base_deduct_for_inventory_deduct(
                                quantity,
                                base_qty_post,
                                deduct,
                                remaining_base=remaining_base if remaining - deduct <= 0 else None,
                            )
                            b.quantity = qty_before - deduct
                            b.base_quantity = base_qty_before - deduct_base
                            finishes_qty = remaining - deduct <= 0
                            aux_share, remaining_aux = split_manual_aux_deduct_share(
                                quantity,
                                aux_quantity_delta,
                                deduct,
                                remaining_aux,
                                finishes_quantity=finishes_qty,
                            )
                            InventoryService._apply_material_batch_aux_deduct(
                                b,
                                material,
                                deduct_base,
                                aux_quantity_delta=aux_share,
                            )
                            InventoryService._sync_material_batch_status_after_qty_change(b)
                            await b.save()
                            key = idempotency_key
                            if key and part_idx > 0:
                                key = f"{key}#p{part_idx}"
                            await InventoryService._record_stock_movement(
                                tenant_id=tenant_id,
                                material_id=material_id,
                                quantity=-deduct,
                                qty_before=qty_before,
                                qty_after=Decimal(str(b.quantity or 0)),
                                base_quantity=-deduct_base,
                                base_qty_before=base_qty_before,
                                base_qty_after=Decimal(str(b.base_quantity or 0)),
                                batch_no=InventoryService._normalize_batch_no_for_ledger(
                                    str(b.batch_no)
                                ),
                                movement_type=movement_type,
                                from_warehouse_id=from_wh_id,
                                from_warehouse_name=from_wh_name,
                                to_warehouse_id=to_wh_id,
                                to_warehouse_name=to_wh_name,
                                balance_warehouse_id=main_wh_id or warehouse_id,
                                source_type=source_type,
                                source_doc_id=source_doc_id,
                                source_doc_code=source_doc_code,
                                work_order_id=work_order_id,
                                work_order_code=work_order_code,
                                operator_id=operator_id,
                                operator_name=operator_name,
                                remark=remark,
                                idempotency_key=key,
                                **InventoryService._movement_location_kwargs(b),
                            )
                            remaining -= deduct
                            remaining_base -= deduct_base
                            part_idx += 1
                    if remaining > 0:
                        if not allow_negative:
                            raise BusinessLogicError(
                                f"库存不足：需求 {quantity}，可用 {have_before}"
                                + (f"（{available_hint}）" if available_hint != "无" else "")
                            )
                        tail = batches[-1] if batches else None
                        if not tail and location_scoped:
                            tail = await InventoryService._lock_location_key_tail(
                                tenant_id=tenant_id,
                                material_id=material_id,
                                warehouse_id=main_wh_id,
                                location_code=scoped_location_code,
                                ownership_type=own["ownership_type"],
                                customer_id=own["customer_id"],
                                quality_status=stock_quality_status,
                            )
                        elif not tail:
                            tail = await InventoryService._find_in_stock_material_batch(
                                tenant_id=tenant_id,
                                material_id=material_id,
                                batch_no="DEFAULT",
                                ownership_type=own["ownership_type"],
                                customer_id=own["customer_id"],
                                warehouse_id=main_wh_id,
                                for_update=True,
                                include_unassigned=True,
                                quality_status=stock_quality_status,
                            )
                        wh_name = (
                            from_wh_name
                            or await InventoryService._resolve_warehouse_name(main_wh_id)
                        )
                        if tail:
                            if int(getattr(tail, "warehouse_id", 0) or 0) == 0 and main_wh_id > 0:
                                tail.warehouse_id = main_wh_id
                                tail.warehouse_name = wh_name
                            qty_before = Decimal(str(tail.quantity or 0))
                            base_qty_before = Decimal(str(tail.base_quantity or 0))
                            tail.quantity = qty_before - remaining
                            tail.base_quantity = base_qty_before - remaining_base
                            InventoryService._apply_material_batch_aux_deduct(
                                tail,
                                material,
                                remaining_base,
                                aux_quantity_delta=remaining_aux,
                            )
                            if remaining_aux is not None:
                                remaining_aux = Decimal("0")
                            InventoryService._sync_material_batch_status_after_qty_change(tail)
                            await tail.save()
                            tail_bn = InventoryService._normalize_batch_no_for_ledger(
                                str(tail.batch_no)
                            )
                            await InventoryService._record_stock_movement(
                                tenant_id=tenant_id,
                                material_id=material_id,
                                quantity=-remaining,
                                qty_before=qty_before,
                                qty_after=Decimal(str(tail.quantity or 0)),
                                base_quantity=-remaining_base,
                                base_qty_before=base_qty_before,
                                base_qty_after=Decimal(str(tail.base_quantity or 0)),
                                batch_no=tail_bn,
                                movement_type=movement_type,
                                from_warehouse_id=from_wh_id,
                                from_warehouse_name=from_wh_name,
                                to_warehouse_id=to_wh_id,
                                to_warehouse_name=to_wh_name,
                                balance_warehouse_id=main_wh_id or warehouse_id,
                                source_type=source_type,
                                source_doc_id=source_doc_id,
                                source_doc_code=source_doc_code,
                                work_order_id=work_order_id,
                                work_order_code=work_order_code,
                                operator_id=operator_id,
                                operator_name=operator_name,
                                remark=remark,
                                idempotency_key=(
                                    f"{idempotency_key}#neg{part_idx}"
                                    if idempotency_key
                                    else None
                                ),
                                **InventoryService._movement_location_kwargs(tail),
                            )
                        else:
                            qty_before = Decimal(0)
                            next_qty = -remaining
                            neg_stub = type("BatchQtyStub", (), {})()
                            neg_stub.quantity = next_qty
                            neg_stub.base_quantity = -remaining_base
                            neg_stub.aux_quantity = Decimal(0)
                            stamp_negative_batch_manual_aux(neg_stub, material, remaining_aux)
                            await MaterialBatch.create(
                                tenant_id=tenant_id,
                                material_id=material_id,
                                batch_no="DEFAULT",
                                quantity=neg_stub.quantity,
                                base_quantity=neg_stub.base_quantity,
                                aux_quantity=neg_stub.aux_quantity,
                                status="in_stock",
                                quality_status=stock_quality_status,
                                ownership_type=own["ownership_type"],
                                customer_id=own["customer_id"],
                                warehouse_id=main_wh_id,
                                warehouse_name=wh_name,
                                location_code=scoped_location_code if location_scoped else "",
                                **(
                                    {"location_id": loc_kwargs["location_id"]}
                                    if location_scoped and loc_kwargs.get("location_id") is not None
                                    else {}
                                ),
                            )
                            await InventoryService._record_stock_movement(
                                tenant_id=tenant_id,
                                material_id=material_id,
                                quantity=-remaining,
                                qty_before=qty_before,
                                qty_after=next_qty,
                                base_quantity=-remaining_base,
                                base_qty_before=Decimal(0),
                                base_qty_after=-remaining_base,
                                batch_no="DEFAULT",
                                movement_type=movement_type,
                                from_warehouse_id=from_wh_id,
                                from_warehouse_name=from_wh_name,
                                to_warehouse_id=to_wh_id,
                                to_warehouse_name=to_wh_name,
                                balance_warehouse_id=main_wh_id or warehouse_id,
                                source_type=source_type,
                                source_doc_id=source_doc_id,
                                source_doc_code=source_doc_code,
                                work_order_id=work_order_id,
                                work_order_code=work_order_code,
                                operator_id=operator_id,
                                operator_name=operator_name,
                                remark=remark,
                                idempotency_key=(
                                    f"{idempotency_key}#neg{part_idx}"
                                    if idempotency_key
                                    else None
                                ),
                                **InventoryService._movement_location_kwargs(
                                    location_code=scoped_location_code if location_scoped else "",
                                    location_id=loc_kwargs.get("location_id") if location_scoped else None,
                                ),
                            )
                logger.info(
                    f"InventoryService.decrease_stock: tenant={tenant_id} material={material_id} "
                    f"qty={quantity} warehouse={warehouse_id} batch={batch_no}"
                )
            else:
                # 线边仓（warehouse_type=line_side）：扣减 LineSideInventory
                from apps.kuaizhizao.models.line_side_inventory import LineSideInventory

                inv_filter = dict(
                    tenant_id=tenant_id,
                    warehouse_id=warehouse_id,
                    material_id=material_id,
                    deleted_at__isnull=True,
                    status="available",
                )
                # P2-16：空串与 None 同义，禁止 batch_no="" 与 None 双口径漏命中
                _bn = (str(batch_no).strip() if batch_no is not None else "") or None
                if _bn:
                    inv_filter["batch_no"] = _bn
                    inv = await LineSideInventory.filter(**inv_filter).select_for_update().first()
                else:
                    inv = await LineSideInventory.filter(**inv_filter).filter(
                        Q(batch_no__isnull=True) | Q(batch_no="")
                    ).select_for_update().first()
                if not inv:
                    if not allow_negative:
                        raise BusinessLogicError(
                            f"线边仓无库存: warehouse={warehouse_id} material={material_id}"
                        )
                    from apps.master_data.models.material import Material

                    mat = await Material.get_or_none(
                        tenant_id=tenant_id,
                        id=material_id,
                        deleted_at__isnull=True,
                    )
                    wh_name = (
                        from_wh_name
                        or await InventoryService._resolve_warehouse_name(warehouse_id)
                    )
                    qty_before = Decimal(0)
                    next_qty = -quantity
                    next_base_qty = -base_qty_post
                    created_line = await LineSideInventory.create(
                        tenant_id=tenant_id,
                        warehouse_id=warehouse_id,
                        warehouse_name=wh_name,
                        material_id=material_id,
                        material_code=(
                            (getattr(mat, "main_code", None) or getattr(mat, "code", ""))
                            if mat
                            else ""
                        ),
                        material_name=getattr(mat, "name", "") if mat else "",
                        batch_no=_bn,
                        quantity=next_qty,
                        base_quantity=next_base_qty,
                        reserved_quantity=Decimal(0),
                        status="available",
                        source_type=source_type or "direct",
                        source_doc_id=source_doc_id,
                        source_doc_code=source_doc_code or "",
                        work_order_id=work_order_id,
                        work_order_code=work_order_code,
                    )
                    await InventoryService._record_stock_movement(
                        tenant_id=tenant_id,
                        material_id=material_id,
                        quantity=-quantity,
                        **InventoryService._movement_location_kwargs(created_line),
                        qty_before=qty_before,
                        qty_after=next_qty,
                        base_quantity=-base_qty_post,
                        base_qty_before=Decimal(0),
                        base_qty_after=next_base_qty,
                        batch_no=batch_no,
                        movement_type=movement_type,
                        from_warehouse_id=from_wh_id,
                        from_warehouse_name=from_wh_name,
                        to_warehouse_id=to_wh_id,
                        to_warehouse_name=to_wh_name,
                        balance_warehouse_id=warehouse_id,
                        source_type=source_type,
                        source_doc_id=source_doc_id,
                        source_doc_code=source_doc_code,
                        work_order_id=work_order_id,
                        work_order_code=work_order_code,
                        operator_id=operator_id,
                        operator_name=operator_name,
                        remark=remark,
                        idempotency_key=idempotency_key,
                    )
                else:
                    available = (inv.quantity or Decimal(0)) - (
                        inv.reserved_quantity or Decimal(0)
                    )
                    if available < quantity and not allow_negative:
                        raise BusinessLogicError(
                            f"线边仓库存不足: warehouse={warehouse_id} material={material_id} "
                            f"need={quantity} available={available}"
                        )
                    qty_before = Decimal(str(inv.quantity or 0))
                    base_qty_before = Decimal(str(getattr(inv, "base_quantity", None) or 0))
                    next_qty = qty_before - quantity
                    next_base_qty = base_qty_before - base_qty_post
                    if next_qty < 0 and not allow_negative:
                        raise BusinessLogicError(
                            f"并发扣减导致线边仓负库存: warehouse={warehouse_id} material={material_id} "
                            f"need={quantity} have={inv.quantity or 0}"
                        )
                    inv.quantity = next_qty
                    inv.base_quantity = next_base_qty
                    await inv.save()
                    await InventoryService._record_stock_movement(
                        tenant_id=tenant_id,
                        material_id=material_id,
                        quantity=-quantity,
                        **InventoryService._movement_location_kwargs(inv),
                        qty_before=qty_before,
                        qty_after=next_qty,
                        base_quantity=-base_qty_post,
                        base_qty_before=base_qty_before,
                        base_qty_after=next_base_qty,
                        batch_no=batch_no or getattr(inv, "batch_no", None),
                        movement_type=movement_type,
                        from_warehouse_id=from_wh_id,
                        from_warehouse_name=from_wh_name,
                        to_warehouse_id=to_wh_id,
                        to_warehouse_name=to_wh_name,
                        balance_warehouse_id=warehouse_id,
                        source_type=source_type,
                        source_doc_id=source_doc_id,
                        source_doc_code=source_doc_code,
                        work_order_id=work_order_id,
                        work_order_code=work_order_code,
                        operator_id=operator_id,
                        operator_name=operator_name,
                        remark=remark,
                        idempotency_key=idempotency_key,
                    )
                logger.info(
                    f"InventoryService.decrease_stock(line_side): tenant={tenant_id} "
                    f"warehouse={warehouse_id} material={material_id} qty={quantity}"
                )
            await InventoryService._mark_serials_out_stock(
                tenant_id=tenant_id,
                material_id=material_id,
                serial_nos=serial_nos,
                source_type=source_type,
                source_doc_id=source_doc_id,
                source_doc_code=source_doc_code,
                movement_type=movement_type,
                idempotency_key=idempotency_key,
                operator_id=operator_id,
                operator_name=operator_name,
            )
            from apps.kuaizhizao.services.work_order_readiness_service import notify_inventory_changed

            notify_inventory_changed(tenant_id, material_id)
            return True
        except (BusinessLogicError, ValidationError, IntegrityError) as e:
            logger.error(f"InventoryService.decrease_stock 失败: {e}")
            raise
        except Exception as e:
            logger.error(f"InventoryService.decrease_stock 失败: {e}")
            raise

    @staticmethod
    @atomic_stock_change
    async def decrease_stock(
        tenant_id: int,
        material_id: int,
        quantity: Decimal,
        base_quantity: Optional[Decimal] = None,
        warehouse_id: Optional[int] = None,
        batch_no: Optional[str] = None,
        serial_nos: Optional[list[str]] = None,
        source_type: Optional[str] = None,
        source_doc_id: Optional[int] = None,
        source_doc_code: Optional[str] = None,
        enforce_fifo: bool = False,
        ownership_type: Optional[str] = None,
        customer_id: Optional[int] = None,
        work_order_id: Optional[int] = None,
        work_order_code: Optional[str] = None,
        movement_type: Optional[str] = None,
        from_warehouse_id: Optional[int] = None,
        from_warehouse_name: Optional[str] = None,
        to_warehouse_id: Optional[int] = None,
        to_warehouse_name: Optional[str] = None,
        operator_id: Optional[int] = None,
        operator_name: Optional[str] = None,
        remark: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        stock_quality_status: str = QUALIFIED,
        aux_quantity_delta: Optional[Decimal] = None,
        location_id: Optional[int] = None,
        location_code: Optional[str] = None,
        *,
        location_scoped: bool = False,
    ) -> bool:
        """
        扣减库存（独立事务包装）。

        若调用方已在 `in_transaction()` 内，请改用 `_decrease_stock_no_atomic`。
        调用方未传 ``idempotency_key`` 时按 A 案合成确定性键，字段不足则拒绝。
        """
        if not (idempotency_key and str(idempotency_key).strip()):
            idempotency_key = InventoryService._synthesize_idempotency_key(
                "decrease",
                source_type=source_type,
                source_doc_id=source_doc_id,
                material_id=material_id,
                batch_no=batch_no,
                warehouse_id=warehouse_id,
                from_warehouse_id=from_warehouse_id,
                to_warehouse_id=to_warehouse_id,
                quantity=quantity,
                movement_type=movement_type,
                work_order_id=work_order_id,
                serial_nos=serial_nos,
            )
        return await InventoryService._decrease_stock_no_atomic(
            tenant_id=tenant_id,
            material_id=material_id,
            quantity=quantity,
            base_quantity=base_quantity,
            warehouse_id=warehouse_id,
            batch_no=batch_no,
            serial_nos=serial_nos,
            source_type=source_type,
            source_doc_id=source_doc_id,
            source_doc_code=source_doc_code,
            enforce_fifo=enforce_fifo,
            ownership_type=ownership_type,
            customer_id=customer_id,
            work_order_id=work_order_id,
            work_order_code=work_order_code,
            movement_type=movement_type,
            from_warehouse_id=from_warehouse_id,
            from_warehouse_name=from_warehouse_name,
            to_warehouse_id=to_warehouse_id,
            to_warehouse_name=to_warehouse_name,
            operator_id=operator_id,
            operator_name=operator_name,
            remark=remark,
            idempotency_key=idempotency_key,
            stock_quality_status=stock_quality_status,
            aux_quantity_delta=aux_quantity_delta,
            location_id=location_id,
            location_code=location_code,
            location_scoped=location_scoped,
        )

    @staticmethod
    async def get_quantity(
        tenant_id: int,
        material_id: int,
        warehouse_id: Optional[int] = None,
        batch_no: Optional[str] = None,
        *,
        location_code: Optional[str] = None,
    ) -> Decimal:
        """
        获取库存数量

        Returns:
            可用数量
        """
        info = await get_material_inventory_info(
            tenant_id=tenant_id,
            material_id=material_id,
            warehouse_id=warehouse_id,
            location_code=location_code,
        )
        return Decimal(str(info["available_quantity"]))

    @staticmethod
    @atomic_stock_change
    async def adjust_inventory(
        tenant_id: int,
        material_id: int,
        quantity: Decimal,
        base_quantity: Optional[Decimal] = None,
        warehouse_id: Optional[int] = None,
        batch_no: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> bool:
        """
        盘点调整库存（直接设置为指定数量，或增减）

        Args:
            quantity: 调整后数量（或调整量，由 reason 语义决定，此处为调整后数量）
            reason: 调整原因（如 stocktaking）

        Returns:
            是否成功
        """
        try:
            # 根据 warehouse_type 决定调整目标：line_side → LineSideInventory，否则 → MaterialBatch
            use_line_side = False
            if warehouse_id is not None:
                from apps.master_data.models.warehouse import Warehouse
                wh = await Warehouse.get_or_none(
                    id=warehouse_id,
                    tenant_id=tenant_id,
                    deleted_at__isnull=True,
                )
                if wh and wh.warehouse_type == "line_side":
                    use_line_side = True

            from apps.kuaizhizao.utils.inventory_posting_utils import (
                normalize_inventory_posting_quantities,
            )
            from apps.master_data.models.material import Material

            material = await Material.get_or_none(
                tenant_id=tenant_id, id=material_id, deleted_at__isnull=True
            )
            inv_qty, base_qty = normalize_inventory_posting_quantities(
                material,
                quantity,
                base_quantity=base_quantity,
            )

            if not use_line_side:
                await InventoryService._material_batch_adjust_set(
                    tenant_id=tenant_id,
                    material_id=material_id,
                    batch_no=batch_no or "DEFAULT",
                    quantity=inv_qty,
                    base_quantity=base_qty,
                    warehouse_id=warehouse_id,
                )
                logger.info(
                    f"InventoryService.adjust_inventory: tenant={tenant_id} "
                    f"material={material_id} qty={quantity} warehouse={warehouse_id} reason={reason}"
                )
            else:
                from apps.kuaizhizao.models.line_side_inventory import LineSideInventory

                inv = await LineSideInventory.filter(
                    tenant_id=tenant_id,
                    warehouse_id=warehouse_id,
                    material_id=material_id,
                    deleted_at__isnull=True,
                ).select_for_update().first()
                if inv:
                    inv.quantity = inv_qty
                    inv.base_quantity = base_qty
                    await inv.save()
                else:
                    mat = material
                    await LineSideInventory.create(
                        tenant_id=tenant_id,
                        warehouse_id=warehouse_id,
                        material_id=material_id,
                        material_code=mat.code if mat else "",
                        material_name=mat.name if mat else "",
                        batch_no=batch_no or "",
                        quantity=inv_qty,
                        base_quantity=base_qty,
                        reserved_quantity=Decimal(0),
                        status="available",
                        source_type="stocktaking",
                    )
                logger.info(
                    f"InventoryService.adjust_inventory(line_side): tenant={tenant_id} "
                    f"warehouse={warehouse_id} material={material_id} qty={quantity}"
                )
            from apps.kuaizhizao.services.work_order_readiness_service import notify_inventory_changed

            notify_inventory_changed(tenant_id, material_id)
            return True
        except (BusinessLogicError, ValidationError, IntegrityError) as e:
            logger.error(f"InventoryService.adjust_inventory 失败: {e}")
            raise
        except Exception as e:
            logger.error(f"InventoryService.adjust_inventory 失败: {e}")
            raise
