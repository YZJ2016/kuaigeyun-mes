"""体系文件/内审与条款多对多关联"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from apps.kuaizhizao.models.qms_audit_clause import QmsAuditClause
from apps.kuaizhizao.models.qms_document_clause import QmsDocumentClause
from apps.kuaizhizao.models.qms_iso_clause import QmsIsoClause
from apps.kuaizhizao.models.qms_review_standard import QmsReviewStandard
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError


async def _validate_clause_ids(
    tenant_id: int,
    clause_ids: Sequence[int],
    *,
    standard_id: Optional[int] = None,
) -> List[QmsIsoClause]:
    if not clause_ids:
        return []
    unique_ids = list(dict.fromkeys(int(i) for i in clause_ids))
    rows = await QmsIsoClause.filter(
        tenant_id=tenant_id, id__in=unique_ids, deleted_at__isnull=True
    ).all()
    if len(rows) != len(unique_ids):
        raise BusinessLogicError("存在无效条款")
    if standard_id is not None:
        for row in rows:
            if row.standard_id != standard_id:
                raise BusinessLogicError("条款须属于同一标准")
    return rows


async def replace_document_clauses(
    tenant_id: int,
    document_id: int,
    clause_ids: Optional[Sequence[int]],
    *,
    standard_id: Optional[int] = None,
) -> None:
    now = resolve_business_datetime()
    await QmsDocumentClause.filter(
        tenant_id=tenant_id, document_id=document_id, deleted_at__isnull=True
    ).update(deleted_at=now)
    if not clause_ids:
        return
    clauses = await _validate_clause_ids(tenant_id, clause_ids, standard_id=standard_id)
    primary_id = clauses[0].id
    for idx, clause in enumerate(clauses):
        await QmsDocumentClause.create(
            tenant_id=tenant_id,
            document_id=document_id,
            clause_id=clause.id,
            is_primary=clause.id == primary_id,
        )


async def replace_audit_clauses(
    tenant_id: int,
    audit_id: int,
    clause_ids: Optional[Sequence[int]],
    *,
    standard_id: Optional[int] = None,
) -> None:
    now = resolve_business_datetime()
    await QmsAuditClause.filter(
        tenant_id=tenant_id, audit_id=audit_id, deleted_at__isnull=True
    ).update(deleted_at=now)
    if not clause_ids:
        return
    clauses = await _validate_clause_ids(tenant_id, clause_ids, standard_id=standard_id)
    primary_id = clauses[0].id
    for clause in clauses:
        await QmsAuditClause.create(
            tenant_id=tenant_id,
            audit_id=audit_id,
            clause_id=clause.id,
            is_primary=clause.id == primary_id,
        )


async def replace_review_standards(
    tenant_id: int, review_id: int, standard_ids: Optional[Sequence[int]]
) -> None:
    now = resolve_business_datetime()
    await QmsReviewStandard.filter(
        tenant_id=tenant_id, review_id=review_id, deleted_at__isnull=True
    ).update(deleted_at=now)
    if not standard_ids:
        return
    unique = list(dict.fromkeys(int(i) for i in standard_ids))
    for sid in unique:
        await QmsReviewStandard.create(
            tenant_id=tenant_id,
            review_id=review_id,
            standard_id=sid,
        )


async def list_document_clause_ids(tenant_id: int, document_id: int) -> List[int]:
    rows = await QmsDocumentClause.filter(
        tenant_id=tenant_id, document_id=document_id, deleted_at__isnull=True
    ).order_by("-is_primary", "id")
    return [r.clause_id for r in rows]


async def list_audit_clause_ids(tenant_id: int, audit_id: int) -> List[int]:
    rows = await QmsAuditClause.filter(
        tenant_id=tenant_id, audit_id=audit_id, deleted_at__isnull=True
    ).order_by("-is_primary", "id")
    return [r.clause_id for r in rows]


async def list_review_standard_ids(tenant_id: int, review_id: int) -> List[int]:
    rows = await QmsReviewStandard.filter(
        tenant_id=tenant_id, review_id=review_id, deleted_at__isnull=True
    ).order_by("id")
    return [r.standard_id for r in rows]


async def document_ids_for_clauses(tenant_id: int, clause_ids: Iterable[int]) -> List[int]:
    ids = list(clause_ids)
    if not ids:
        return []
    rows = await QmsDocumentClause.filter(
        tenant_id=tenant_id, clause_id__in=ids, deleted_at__isnull=True
    ).all()
    return list({r.document_id for r in rows})


async def audit_ids_for_clauses(tenant_id: int, clause_ids: Iterable[int]) -> List[int]:
    ids = list(clause_ids)
    if not ids:
        return []
    rows = await QmsAuditClause.filter(
        tenant_id=tenant_id, clause_id__in=ids, deleted_at__isnull=True
    ).all()
    return list({r.audit_id for r in rows})


async def clause_labels_for_ids(
    tenant_id: int, clause_ids: Sequence[int]
) -> Dict[int, str]:
    if not clause_ids:
        return {}
    rows = await QmsIsoClause.filter(
        tenant_id=tenant_id, id__in=list(clause_ids), deleted_at__isnull=True
    ).all()
    return {r.id: f"{r.clause_code} {r.title}" for r in rows}


async def enrich_clause_fields(
    tenant_id: int,
    *,
    document_id: Optional[int] = None,
    audit_id: Optional[int] = None,
    review_id: Optional[int] = None,
) -> Tuple[List[int], List[str], Optional[int], List[int]]:
    clause_ids: List[int] = []
    standard_ids: List[int] = []
    primary_clause_id: Optional[int] = None
    if document_id is not None:
        links = await QmsDocumentClause.filter(
            tenant_id=tenant_id, document_id=document_id, deleted_at__isnull=True
        ).order_by("-is_primary", "id")
        clause_ids = [l.clause_id for l in links]
        primary = next((l for l in links if l.is_primary), links[0] if links else None)
        primary_clause_id = primary.clause_id if primary else None
    if audit_id is not None:
        links = await QmsAuditClause.filter(
            tenant_id=tenant_id, audit_id=audit_id, deleted_at__isnull=True
        ).order_by("-is_primary", "id")
        clause_ids = [l.clause_id for l in links]
        primary = next((l for l in links if l.is_primary), links[0] if links else None)
        primary_clause_id = primary.clause_id if primary else None
    if review_id is not None:
        standard_ids = await list_review_standard_ids(tenant_id, review_id)
    labels_map = await clause_labels_for_ids(tenant_id, clause_ids)
    clause_labels = [labels_map[i] for i in clause_ids if i in labels_map]
    return clause_ids, clause_labels, primary_clause_id, standard_ids
