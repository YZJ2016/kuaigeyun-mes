"""往来对账单物料行：展开、持久化、读取。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from apps.kuaicaiwu.config.finance_settlement_contract import (
    PARTNER_STATEMENT_EXPANDABLE_DOC_TYPES,
    PARTNER_STATEMENT_LINE_KIND_FINANCE,
    PARTNER_STATEMENT_LINE_KIND_MATERIAL,
)
from apps.kuaicaiwu.models.partner_statement import PartnerStatement
from apps.kuaicaiwu.models.partner_statement_line import PartnerStatementLine

if TYPE_CHECKING:
    from apps.kuaicaiwu.services.partner_statement_service import PartnerStatementService

_MONEY = Decimal("0.01")
_QTY = Decimal("0.0001")


def _q_money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(_MONEY, rounding=ROUND_HALF_UP)


def _normalize_source_doc_type(doc_type: Any) -> str:
    mapping = {
        "销售出库": "sales_delivery",
        "采购入库": "purchase_receipt",
        "委外收货": "outsource_material_receipt",
        "工序委外收货": "outsource_order_receipt",
    }
    raw = str(doc_type or "").strip()
    return mapping.get(raw, raw.replace("-", "_").lower())


class PartnerStatementLineService:
    async def expand_preview_lines_to_material_lines(
        self,
        tenant_id: int,
        preview_lines: List[Dict[str, Any]],
        statement_svc: "PartnerStatementService",
    ) -> List[Dict[str, Any]]:
        """将预览单据行展开为物料行；财务类单据保持单行。"""
        out: List[Dict[str, Any]] = []
        for ln in preview_lines:
            kind = str(ln.get("line_kind") or "").strip()
            if kind in (
                PARTNER_STATEMENT_LINE_KIND_MATERIAL,
                PARTNER_STATEMENT_LINE_KIND_FINANCE,
            ):
                row = dict(ln)
                if kind == PARTNER_STATEMENT_LINE_KIND_MATERIAL:
                    if not row.get("source_doc_type"):
                        row["source_doc_type"] = _normalize_source_doc_type(
                            ln.get("doc_type") or ln.get("doc_type_label")
                        )
                    if row.get("source_doc_id") is None:
                        row["source_doc_id"] = int(ln.get("doc_id") or 0)
                out.append(row)
                continue

            doc_type = str(ln.get("doc_type") or "").strip()
            if doc_type not in PARTNER_STATEMENT_EXPANDABLE_DOC_TYPES:
                row = dict(ln)
                row["line_kind"] = PARTNER_STATEMENT_LINE_KIND_FINANCE
                row["source_doc_type"] = _normalize_source_doc_type(doc_type)
                row["source_doc_id"] = int(ln.get("doc_id") or 0)
                row["source_line_id"] = 0
                out.append(row)
                continue

            doc_id = ln.get("doc_id")
            if doc_id is None:
                continue
            try:
                detail = await statement_svc.get_statement_line_detail(
                    tenant_id, doc_type, int(doc_id)
                )
            except Exception:
                row = dict(ln)
                row["line_kind"] = PARTNER_STATEMENT_LINE_KIND_MATERIAL
                row["source_line_id"] = 0
                out.append(row)
                continue

            items = list(detail.get("items") or [])
            if not items:
                row = dict(ln)
                row["line_kind"] = PARTNER_STATEMENT_LINE_KIND_MATERIAL
                row["source_line_id"] = 0
                out.append(row)
                continue

            stmt_total = _q_money(ln.get("statement_amount") or ln.get("doc_amount") or 0)
            doc_total = _q_money(ln.get("doc_amount") or stmt_total)
            prior_total = _q_money(ln.get("prior_stated_amount") or 0)
            weights = [_q_money(it.get("amount") or 0) for it in items]
            weight_sum = sum(weights, Decimal("0"))
            use_equal_weights = weight_sum <= 0
            if use_equal_weights:
                weight_sum = Decimal(len(items))

            allocated_stmt = Decimal("0")
            allocated_doc = Decimal("0")
            allocated_prior = Decimal("0")
            norm_type = _normalize_source_doc_type(doc_type)
            orig_debit = _q_money(ln.get("debit", 0))
            orig_credit = _q_money(ln.get("credit", 0))
            has_debit_side = orig_debit > 0 or (orig_debit == 0 and orig_credit == 0)

            for idx, it in enumerate(items):
                w = Decimal("1") if use_equal_weights else (weights[idx] if weights[idx] > 0 else Decimal("0"))
                if idx == len(items) - 1:
                    part_stmt = _q_money(stmt_total - allocated_stmt)
                    part_doc = _q_money(doc_total - allocated_doc)
                    part_prior = _q_money(prior_total - allocated_prior)
                else:
                    ratio = w / weight_sum
                    part_stmt = _q_money(stmt_total * ratio)
                    part_doc = _q_money(doc_total * ratio)
                    part_prior = _q_money(prior_total * ratio)
                    allocated_stmt += part_stmt
                    allocated_doc += part_doc
                    allocated_prior += part_prior

                remaining = _q_money(part_doc - part_prior)
                row = {
                    **{k: v for k, v in ln.items() if k not in ("statement_amount", "doc_amount", "prior_stated_amount", "remaining_amount")},
                    "line_kind": PARTNER_STATEMENT_LINE_KIND_MATERIAL,
                    "source_doc_type": norm_type,
                    "source_doc_id": int(doc_id),
                    "source_line_id": int(it.get("source_line_id") or it.get("id") or idx + 1),
                    "material_code": it.get("material_code"),
                    "material_name": it.get("material_name"),
                    "material_spec": it.get("material_spec"),
                    "unit": it.get("unit"),
                    "quantity": it.get("quantity"),
                    "doc_amount": float(part_doc),
                    "prior_stated_amount": float(part_prior),
                    "statement_amount": float(part_stmt),
                    "remaining_amount": float(remaining),
                    "debit": float(part_stmt) if (has_debit_side and part_stmt > 0) else 0.0,
                    "credit": float(part_stmt) if (not has_debit_side and part_stmt > 0) else 0.0,
                    "doc_type_label": doc_type,
                }
                row["invoiceable_amount"] = float(part_stmt)
                out.append(row)
        return out

    async def replace_statement_lines(
        self,
        tenant_id: int,
        statement: PartnerStatement,
        lines: List[Dict[str, Any]],
        *,
        amount_basis: str,
        is_read_only: bool = False,
    ) -> None:
        await PartnerStatementLine.filter(
            tenant_id=tenant_id,
            statement_id=statement.id,
        ).delete()

        sort_index = 0
        seen_src_keys: set[tuple[str, int, int]] = set()
        for ln in lines:
            sort_index += 1
            doc_date_raw = ln.get("date") or ln.get("sort_date")
            doc_date: Optional[date] = None
            if doc_date_raw:
                if isinstance(doc_date_raw, date):
                    doc_date = doc_date_raw
                else:
                    doc_date = date.fromisoformat(str(doc_date_raw)[:10])

            stmt_amt = _q_money(ln.get("statement_amount") or 0)
            inv_occ = _q_money(ln.get("invoice_occupied_amount") or 0)
            raw_invoiceable = ln.get("invoiceable_amount")
            invoiceable = (
                _q_money(raw_invoiceable)
                if raw_invoiceable is not None
                else max(stmt_amt - inv_occ, Decimal("0"))
            )
            src_doc_type = str(
                ln.get("source_doc_type") or _normalize_source_doc_type(ln.get("doc_type"))
            )
            src_doc_id = int(ln.get("source_doc_id") or ln.get("doc_id") or 0)
            src_line_id = int(ln.get("source_line_id") or 0)
            src_key = (src_doc_type, src_doc_id, src_line_id)
            while src_key in seen_src_keys:
                src_line_id = -(sort_index) if src_line_id == 0 else src_line_id + 1000000
                src_key = (src_doc_type, src_doc_id, src_line_id)
            seen_src_keys.add(src_key)

            await PartnerStatementLine.create(
                tenant_id=tenant_id,
                statement_id=statement.id,
                line_kind=str(ln.get("line_kind") or PARTNER_STATEMENT_LINE_KIND_MATERIAL),
                source_doc_type=src_doc_type,
                source_doc_id=src_doc_id,
                source_line_id=src_line_id,
                doc_code=str(ln.get("doc_code") or ""),
                doc_date=doc_date,
                material_id=ln.get("material_id"),
                material_code=ln.get("material_code"),
                material_name=ln.get("material_name"),
                material_spec=ln.get("material_spec"),
                unit=ln.get("unit"),
                quantity=ln.get("quantity"),
                amount_basis=amount_basis,
                doc_amount=_q_money(ln.get("doc_amount")),
                prior_stated_amount=_q_money(ln.get("prior_stated_amount")),
                statement_amount=stmt_amt,
                remaining_amount=_q_money(ln.get("remaining_amount")),
                invoice_occupied_amount=inv_occ,
                invoiceable_amount=invoiceable,
                debit=_q_money(ln.get("debit")),
                credit=_q_money(ln.get("credit")),
                doc_type_label=str(ln.get("doc_type") or ln.get("doc_type_label") or ""),
                is_read_only=is_read_only,
                sort_index=sort_index,
                line_snapshot=ln,
            )

    async def list_line_dicts(self, tenant_id: int, statement_id: int) -> List[Dict[str, Any]]:
        rows = await PartnerStatementLine.filter(
            tenant_id=tenant_id,
            statement_id=statement_id,
            deleted_at__isnull=True,
        ).order_by("sort_index", "id").all()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "id": r.id,
                "line_kind": r.line_kind,
                "source_doc_type": r.source_doc_type,
                "source_doc_id": r.source_doc_id,
                "source_line_id": r.source_line_id,
                "doc_code": r.doc_code,
                "doc_date": r.doc_date.isoformat() if r.doc_date else None,
                "material_code": r.material_code,
                "material_name": r.material_name,
                "material_spec": r.material_spec,
                "unit": r.unit,
                "quantity": float(r.quantity) if r.quantity is not None else None,
                "doc_amount": float(r.doc_amount),
                "prior_stated_amount": float(r.prior_stated_amount),
                "statement_amount": float(r.statement_amount),
                "remaining_amount": float(r.remaining_amount),
                "invoice_occupied_amount": float(r.invoice_occupied_amount),
                "invoiceable_amount": float(r.invoiceable_amount),
                "debit": float(r.debit),
                "credit": float(r.credit),
                "doc_type": r.doc_type_label,
                "is_read_only": r.is_read_only,
            })
        return out