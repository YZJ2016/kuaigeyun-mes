"""序列号出入库留痕的写入与当前单据。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from tortoise.exceptions import IntegrityError

from apps.kuaizhizao.models.material_serial_document_ledger import MaterialSerialDocumentLedger
from core.utils.timezone_utils import now_utc
from infra.exceptions.exceptions import ValidationError


DIRECTION_IN = "in"
DIRECTION_OUT = "out"
_REVERSAL_SUFFIXES = ("_revoke", "_withdraw")


def posting_is_reversal(source_type: Optional[str]) -> bool:
    """现网撤回：``source_type`` 以 ``_revoke`` / ``_withdraw`` 结尾（含出库冲入库）。"""
    text = str(source_type or "").strip()
    return text.endswith(_REVERSAL_SUFFIXES)


def forward_source_type(source_type: Optional[str]) -> str:
    text = str(source_type or "").strip()
    for suffix in _REVERSAL_SUFFIXES:
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def ledger_row_for_trace(row: Any) -> dict[str, Any]:
    """追溯展示。只含单据与操作人，不含凭据或内部路径。"""
    return {
        "serial_no": row.serial_no,
        "material_id": row.material_id,
        "direction": row.direction,
        "movement_type": row.movement_type,
        "source_type": row.source_type,
        "source_doc_id": row.source_doc_id,
        "source_doc_code": row.source_doc_code,
        "idempotency_key": row.idempotency_key,
        "occurred_at": _iso(row.occurred_at),
        "operator_id": row.operator_id,
        "operator_name": row.operator_name,
        "reverses_id": row.reverses_id,
    }


def current_document_from_rows(rows: list[Any]) -> Optional[dict[str, Any]]:
    """时间序上，跳过已被反向指针指到的正向行，取最后一笔正向行的来源单据。

    撤回行即使 ``reverses_id`` 为空，也不进入正向集合。历史列表仍返回这些行。
    """
    ordered = sorted(rows, key=lambda row: (row.occurred_at, int(row.id or 0)))
    pointed = {int(row.reverses_id) for row in ordered if row.reverses_id}
    forward = [
        row
        for row in ordered
        if not row.reverses_id
        and int(row.id) not in pointed
        and not posting_is_reversal(row.source_type)
    ]
    if not forward:
        return None
    row = forward[-1]
    return {
        "source_type": row.source_type,
        "source_doc_id": row.source_doc_id,
        "source_doc_code": row.source_doc_code,
        "movement_type": row.movement_type,
        "direction": row.direction,
        "occurred_at": _iso(row.occurred_at),
    }


async def _load_rows(tenant_id: int, serial_no: str) -> list[Any]:
    return await MaterialSerialDocumentLedger.filter(
        tenant_id=tenant_id,
        serial_no=serial_no,
    ).order_by("occurred_at", "id")


async def _pointed_ids(tenant_id: int, serial_no: str) -> set[int]:
    raw = await MaterialSerialDocumentLedger.filter(
        tenant_id=tenant_id,
        serial_no=serial_no,
        reverses_id__isnull=False,
    ).values_list("reverses_id", flat=True)
    return {int(item) for item in raw if item is not None}


async def _forward_rows(
    tenant_id: int,
    serial_no: str,
    source_type: str,
    source_doc_id: Optional[int],
) -> list[Any]:
    query = MaterialSerialDocumentLedger.filter(
        tenant_id=tenant_id,
        serial_no=serial_no,
        source_type=source_type,
        reverses_id__isnull=True,
    )
    if source_doc_id is None:
        query = query.filter(source_doc_id__isnull=True)
    else:
        query = query.filter(source_doc_id=int(source_doc_id))
    return await query.order_by("occurred_at", "id")


async def _latest_unreversed_forward(
    tenant_id: int,
    serial_no: str,
    source_type: str,
    source_doc_id: Optional[int],
) -> Optional[Any]:
    rows = await _forward_rows(tenant_id, serial_no, source_type, source_doc_id)
    if not rows:
        return None
    pointed = await _pointed_ids(tenant_id, serial_no)
    unreversed = [row for row in rows if int(row.id) not in pointed]
    if not unreversed:
        return None
    return unreversed[-1]


async def record_serial_document_ledger(
    *,
    tenant_id: int,
    serial_no: str,
    material_id: int,
    direction: str,
    movement_type: Optional[str],
    source_type: Optional[str],
    source_doc_id: Optional[int],
    source_doc_code: Optional[str],
    idempotency_key: Optional[str],
    operator_id: Optional[int],
    operator_name: Optional[str],
    reconfirm_tolerant: bool = False,
) -> None:
    """写一行留痕。同一幂等键加同一序列号已有行则直接成功，不插第二行。

    撤回追加相反方向，``reverses_id`` 指向原行，不修改原行。
    再确认容忍时，已有未被冲销的正向行则不再追加。
    """
    key = str(idempotency_key or "").strip()
    if not key:
        raise ValidationError("序列号台账缺少库存幂等键")
    movement = str(movement_type or "").strip()
    if not movement:
        raise ValidationError("序列号台账缺少移动类型")
    source = str(source_type or "").strip()
    if not source:
        raise ValidationError("序列号台账缺少来源单据类型")
    sn = serial_no if isinstance(serial_no, str) else str(serial_no)
    if sn == "":
        return

    existing = await MaterialSerialDocumentLedger.filter(
        tenant_id=tenant_id,
        idempotency_key=key,
        serial_no=sn,
    ).first()
    if existing is not None:
        return

    doc_id = int(source_doc_id) if source_doc_id is not None else None
    reverses_id = None
    row_direction = direction
    if posting_is_reversal(source):
        original = await _latest_unreversed_forward(
            tenant_id,
            sn,
            forward_source_type(source),
            doc_id,
        )
        if original is not None:
            reverses_id = int(original.id)
            row_direction = DIRECTION_OUT if original.direction == DIRECTION_IN else DIRECTION_IN
    elif reconfirm_tolerant:
        if await _latest_unreversed_forward(tenant_id, sn, source, doc_id) is not None:
            return

    operator_name_text = (operator_name or "").strip() or None
    try:
        await MaterialSerialDocumentLedger.create(
            tenant_id=tenant_id,
            serial_no=sn,
            material_id=int(material_id),
            direction=row_direction,
            movement_type=movement,
            source_type=source,
            source_doc_id=doc_id,
            source_doc_code=(source_doc_code or "").strip() or None,
            idempotency_key=key,
            occurred_at=now_utc(),
            operator_id=int(operator_id) if operator_id is not None else None,
            operator_name=operator_name_text,
            reverses_id=reverses_id,
            created_by=int(operator_id) if operator_id is not None else None,
            created_by_name=operator_name_text,
        )
    except IntegrityError:
        again = await MaterialSerialDocumentLedger.filter(
            tenant_id=tenant_id,
            idempotency_key=key,
            serial_no=sn,
        ).first()
        if again is not None:
            return
        raise


async def serial_document_trace(tenant_id: int, serial_no: str) -> dict[str, Any]:
    sn = serial_no if isinstance(serial_no, str) else str(serial_no or "")
    if not sn:
        return {"serial_document_ledger": [], "current_document": None}
    rows = await _load_rows(tenant_id, sn)
    return {
        "serial_document_ledger": [ledger_row_for_trace(row) for row in rows],
        "current_document": current_document_from_rows(rows),
    }
