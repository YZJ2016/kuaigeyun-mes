"""其他费用支出服务"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from apps.common.base_service import AppBaseService
from apps.kuaicaiwu.models.other_voucher import OtherExpense, OtherExpenseLine
from apps.kuaicaiwu.schemas.other_voucher import (
    OtherExpenseCreate,
    OtherExpenseResponse,
    OtherExpenseUpdate,
    OtherVoucherLineInput,
    OtherVoucherLineResponse,
)
from apps.kuaicaiwu.services.document_action_policy.other_expense import (
    assert_other_expense_capability,
    derive_other_expense_capabilities,
    is_other_expense_confirmed_status,
)
from apps.kuaicaiwu.services.finance_misc_category_service import FinanceMiscCategoryService
from apps.kuaicaiwu.services.other_expense_audit_service import (
    OtherExpenseAuditService,
    assert_other_expense_review_editable,
)
from apps.kuaicaiwu.services.finance_voucher_codes import allocate_other_expense_code
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import NotFoundError, ValidationError


class OtherExpenseService(AppBaseService[OtherExpense]):
    def __init__(self) -> None:
        super().__init__(OtherExpense)
        self._categories = FinanceMiscCategoryService()

    async def _sum_and_validate_lines(
        self,
        tenant_id: int,
        lines: List[OtherVoucherLineInput],
        *,
        payment_method: str,
    ) -> tuple[Decimal, List[dict]]:
        total = Decimal("0")
        normalized: List[dict] = []
        require_payee = str(payment_method or "").strip() == "员工垫付"
        for idx, item in enumerate(lines, start=1):
            amt = Decimal(str(item.amount))
            if amt <= 0:
                raise ValidationError(f"第 {idx} 行金额须大于 0")
            code = str(item.category_code).strip()
            cat = await self._categories.get_active_by_code(tenant_id, "expense", code)
            gl = item.gl_account_code
            if not gl and cat.default_gl_account_code:
                gl = cat.default_gl_account_code
            payee_id = int(item.payee_id) if item.payee_id else None
            payee_name = (str(item.payee_name).strip() if item.payee_name else "") or None
            if require_payee:
                if not payee_id or not payee_name:
                    raise ValidationError(f"第 {idx} 行须选择领款人（员工垫付）")
            else:
                payee_id = None
                payee_name = None
            normalized.append(
                {
                    "line_no": idx,
                    "category_code": cat.code,
                    "category_name": cat.name,
                    "amount": amt,
                    "description": item.description,
                    "gl_account_code": gl,
                    "payee_id": payee_id,
                    "payee_name": payee_name,
                }
            )
            total += amt
        return total, normalized

    _PR_LINK_ELIGIBLE_STATUSES = frozenset(
        {"已入库", "已完成", "部分入库", "COMPLETED", "completed"}
    )

    async def normalize_related_purchase_receipts(
        self,
        tenant_id: int,
        *,
        counterparty_kind: str,
        counterparty_id: Optional[int],
        related: Optional[List[Any]],
    ) -> Optional[List[dict]]:
        """往来为供应商时可关联采购入库；须属于该供应商且已入库类状态。"""
        kind = str(counterparty_kind or "").strip().lower()
        if kind != "supplier":
            return None
        if not related:
            return []
        if not counterparty_id:
            raise ValidationError("关联采购入库前须先选择供应商")
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
        from apps.kuaicaiwu.schemas.other_voucher import RelatedPurchaseReceiptRef

        refs: List[RelatedPurchaseReceiptRef] = []
        for item in related:
            if isinstance(item, RelatedPurchaseReceiptRef):
                refs.append(item)
            elif isinstance(item, dict):
                refs.append(RelatedPurchaseReceiptRef.model_validate(item))
            else:
                refs.append(RelatedPurchaseReceiptRef.model_validate(item))
        ids = [int(r.id) for r in refs if int(r.id) > 0]
        if not ids:
            return []
        rows = await PurchaseReceipt.filter(
            tenant_id=tenant_id,
            id__in=ids,
            deleted_at__isnull=True,
        )
        by_id = {int(r.id): r for r in rows}
        out: List[dict] = []
        for rid in ids:
            receipt = by_id.get(rid)
            if not receipt:
                raise ValidationError(f"采购入库单不存在: {rid}")
            if int(receipt.supplier_id or 0) != int(counterparty_id):
                raise ValidationError(
                    f"采购入库单 {receipt.receipt_code} 不属于当前供应商"
                )
            status = str(receipt.status or "").strip()
            if status not in self._PR_LINK_ELIGIBLE_STATUSES:
                raise ValidationError(
                    f"采购入库单 {receipt.receipt_code} 状态不可关联（须已入库类）"
                )
            out.append(
                {
                    "id": rid,
                    "code": str(receipt.receipt_code or rid),
                }
            )
        return out

    async def list_purchase_receipt_link_candidates(
        self,
        tenant_id: int,
        *,
        supplier_id: int,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        if supplier_id <= 0:
            raise ValidationError("须指定供应商")
        query = PurchaseReceipt.filter(
            tenant_id=tenant_id,
            supplier_id=supplier_id,
            status__in=list(self._PR_LINK_ELIGIBLE_STATUSES),
            deleted_at__isnull=True,
        )
        kw = str(keyword or "").strip()
        if kw:
            from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem
            from apps.kuaizhizao.services.warehouse_list_core import (
                PURCHASE_RECEIPT_KEYWORD_FIELDS,
            )
            from apps.kuaizhizao.utils.list_item_material_keyword import (
                apply_query_header_or_line_material_keyword,
            )

            query = await apply_query_header_or_line_material_keyword(
                query,
                tenant_id=tenant_id,
                kw=kw,
                keyword_fields=PURCHASE_RECEIPT_KEYWORD_FIELDS,
                item_model=PurchaseReceiptItem,
                item_header_fk_field="receipt_id",
            )
        total = await query.count()
        receipts = await query.offset(skip).limit(limit).order_by("-created_at")
        receipts_list = list(receipts)
        from apps.kuaicaiwu.services.finance_tax import (
            money_to_json_float,
            quantize_money,
        )
        from apps.kuaicaiwu.services.purchase_settlement import (
            batch_purchase_receipt_settlement_excl,
        )

        excl_map = await batch_purchase_receipt_settlement_excl(tenant_id, receipts_list)
        receipt_ids = [int(r.id) for r in receipts_list]
        from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem
        from apps.kuaizhizao.services.document_action_policy.enricher import (
            batch_document_item_counts,
            batch_document_item_material_previews,
        )

        item_previews = await batch_document_item_material_previews(
            tenant_id, PurchaseReceiptItem, "receipt_id", receipt_ids
        )
        item_counts = await batch_document_item_counts(
            tenant_id, PurchaseReceiptItem, "receipt_id", receipt_ids
        )
        data = []
        for r in receipts_list:
            rid = int(r.id)
            excl = excl_map.get(rid)
            if excl is None:
                excl = quantize_money(r.total_amount or 0)
            data.append(
                {
                    "id": rid,
                    "code": str(r.receipt_code or r.id),
                    "receipt_code": str(r.receipt_code or r.id),
                    "supplier_id": int(r.supplier_id or 0) or None,
                    "supplier_name": r.supplier_name,
                    "source_status": r.status,
                    "source_date": str(
                        getattr(r, "receipt_time", None)
                        or getattr(r, "created_at", None)
                        or ""
                    ),
                    "amount": money_to_json_float(excl),
                    "items": item_previews.get(rid, []),
                    "item_count": int(item_counts.get(rid, 0)),
                    "purchase_order_code": (
                        str(getattr(r, "purchase_order_code", None) or "").strip() or None
                    ),
                    "total_quantity": float(getattr(r, "total_quantity", 0) or 0),
                }
            )
        return {"data": data, "total": total, "success": True}

    async def _resolve_expense_counterparty_payee(
        self, head: OtherExpense
    ) -> dict[str, Optional[str]]:
        """头表未写入收款账户时，从来源支出申请继承（与附件继承口径一致）。"""
        keys = (
            "counterparty_account_name",
            "counterparty_bank_name",
            "counterparty_bank_account",
        )
        out: dict[str, Optional[str]] = {
            k: (str(getattr(head, k, None) or "").strip() or None) for k in keys
        }
        missing = [k for k in keys if not out[k]]
        if not missing:
            return out
        if (
            str(head.source_type or "").strip() == "other_expense_application"
            and head.source_id
        ):
            from apps.kuaicaiwu.models.other_expense_application import (
                OtherExpenseApplication,
            )

            app = await OtherExpenseApplication.get_or_none(
                tenant_id=head.tenant_id,
                id=int(head.source_id),
                deleted_at__isnull=True,
            )
            if app:
                for key in missing:
                    inherited = str(getattr(app, key, None) or "").strip() or None
                    if inherited:
                        out[key] = inherited
        return out

    async def _resolve_expense_department_fields(
        self, head: OtherExpense
    ) -> dict[str, Any]:
        """头表未写部门时，从来源支出申请继承（与附件、收款账户一致）。"""
        dept_id = head.department_id
        dept_name = str(head.department_name or "").strip() or None
        if dept_id and dept_name:
            return {"department_id": dept_id, "department_name": dept_name}
        if (
            str(head.source_type or "").strip() == "other_expense_application"
            and head.source_id
        ):
            from apps.kuaicaiwu.models.other_expense_application import (
                OtherExpenseApplication,
            )

            app = await OtherExpenseApplication.get_or_none(
                tenant_id=head.tenant_id,
                id=int(head.source_id),
                deleted_at__isnull=True,
            )
            if app:
                return {
                    "department_id": app.department_id,
                    "department_name": app.department_name,
                }
        return {"department_id": dept_id, "department_name": dept_name}

    async def _resolve_expense_attachments(
        self, head: OtherExpense
    ) -> Optional[List[Any]]:
        raw = head.attachments
        if isinstance(raw, list) and raw:
            return raw
        if (
            str(head.source_type or "").strip() == "other_expense_application"
            and head.source_id
        ):
            from apps.kuaicaiwu.models.other_expense_application import (
                OtherExpenseApplication,
            )

            app = await OtherExpenseApplication.get_or_none(
                tenant_id=head.tenant_id,
                id=int(head.source_id),
                deleted_at__isnull=True,
            )
            if app and isinstance(app.attachments, list) and app.attachments:
                return app.attachments
        return raw if isinstance(raw, list) else None

    async def _to_response(self, head: OtherExpense) -> OtherExpenseResponse:
        lines = await OtherExpenseLine.filter(
            tenant_id=head.tenant_id, other_expense_id=head.id
        ).order_by("line_no")
        from apps.kuaicaiwu.services.misc_voucher_finance_bridge import MiscVoucherFinanceBridge

        finance_links = await MiscVoucherFinanceBridge().finance_links_for_expense(
            head.tenant_id, int(head.id)
        )
        caps = derive_other_expense_capabilities(
            head,
            has_payable=bool(finance_links.get("payable_id")),
            has_payment=bool(finance_links.get("payment_id")),
        )
        base = OtherExpenseResponse.model_validate(head, from_attributes=True)
        attachments = await self._resolve_expense_attachments(head)
        payee = await self._resolve_expense_counterparty_payee(head)
        department_fields = await self._resolve_expense_department_fields(head)
        return base.model_copy(
            update={
                "lines": [OtherVoucherLineResponse.model_validate(r) for r in lines],
                "capabilities": {k: v.model_dump() for k, v in caps.items()},
                "attachments": attachments,
                **department_fields,
                **{k: v for k, v in payee.items() if v},
                **finance_links,
            }
        )

    async def _finalize_application_pull(
        self,
        tenant_id: int,
        *,
        application_id: int,
        application_code: str,
        expense_id: int,
        expense_code: str,
        line_pushes: List[tuple[int, Decimal]],
        created_by: int,
    ) -> None:
        from apps.kuaizhizao.schemas.document_relation import DocumentRelationCreate
        from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService
        from apps.kuaicaiwu.services.other_expense_application_service import (
            OtherExpenseApplicationService,
        )

        rel_svc = DocumentRelationNewService()
        await rel_svc.create_relation(
            tenant_id=tenant_id,
            relation_data=DocumentRelationCreate(
                source_type="other_expense_application",
                source_id=application_id,
                source_code=application_code,
                target_type="other_expense",
                target_id=expense_id,
                target_code=expense_code,
                relation_type="source",
                relation_mode="push",
                relation_desc="其他费用支出申请下推支出单",
            ),
            created_by=created_by,
        )
        await OtherExpenseApplicationService().record_line_pushed(
            tenant_id, application_id, line_pushes
        )

    async def create_expense_from_application(
        self,
        tenant_id: int,
        data: OtherExpenseCreate,
        created_by: int,
        *,
        line_pushes: List[tuple[int, Decimal]],
    ) -> OtherExpenseResponse:
        if str(data.source_type or "") != "other_expense_application" or not data.source_id:
            raise ValidationError("缺少申请来源")
        app_id = int(data.source_id)
        from apps.kuaicaiwu.models.other_expense_application import OtherExpenseApplication

        app = await OtherExpenseApplication.get_or_none(
            tenant_id=tenant_id, id=app_id, deleted_at__isnull=True
        )
        if not app:
            raise NotFoundError(f"其他费用支出申请不存在: {app_id}")
        resp = await self._create_expense_record(tenant_id, data, created_by)
        await self._finalize_application_pull(
            tenant_id,
            application_id=app_id,
            application_code=str(app.application_code),
            expense_id=int(resp.id),
            expense_code=str(resp.expense_code),
            line_pushes=line_pushes,
            created_by=created_by,
        )
        return await self.get_by_id(tenant_id, int(resp.id))

    async def _create_expense_record(
        self, tenant_id: int, data: OtherExpenseCreate, created_by: int
    ) -> OtherExpenseResponse:
        from apps.kuaicaiwu.constants.payment_method import assert_supplier_payee_account

        if str(data.counterparty_kind or "").strip() in ("supplier", "employee"):
            assert_supplier_payee_account(
                payment_method=data.payment_method,
                account_name=data.counterparty_account_name,
                bank_name=data.counterparty_bank_name,
                bank_account=data.counterparty_bank_account,
            )
        total, line_rows = await self._sum_and_validate_lines(
            tenant_id, data.lines, payment_method=str(data.payment_method or "")
        )
        user = await self.get_user_info(created_by)
        code = (data.expense_code or await allocate_other_expense_code(tenant_id)).strip().upper()
        from apps.kuaizhizao.services.document_recognition import (
            ensure_payable_recognition_on_create,
            payable_recognition_for_misc_expense_counterparty,
        )

        supplier_id = (
            int(data.counterparty_id)
            if (data.counterparty_kind or "").lower() == "supplier" and data.counterparty_id
            else None
        )
        payable_resolved = await ensure_payable_recognition_on_create(
            tenant_id,
            supplier_id,
            getattr(data, "payable_recognition", None),
        )
        payable_recognition = payable_recognition_for_misc_expense_counterparty(
            str(data.counterparty_kind or "none"),
            payable_resolved,
        )
        related_receipts = await self.normalize_related_purchase_receipts(
            tenant_id,
            counterparty_kind=str(data.counterparty_kind or "none"),
            counterparty_id=data.counterparty_id,
            related=data.related_purchase_receipts,
        )
        source_type = (str(data.source_type).strip() if data.source_type else None) or None
        source_id = int(data.source_id) if data.source_id else None
        source_code = (str(data.source_code).strip() if data.source_code else None) or None
        async with in_transaction():
            head = await OtherExpense.create(
                tenant_id=tenant_id,
                expense_code=code,
                business_date=data.business_date,
                counterparty_kind=data.counterparty_kind or "none",
                counterparty_id=data.counterparty_id,
                counterparty_name=data.counterparty_name,
                counterparty_account_name=data.counterparty_account_name,
                counterparty_bank_name=data.counterparty_bank_name,
                counterparty_bank_account=data.counterparty_bank_account,
                total_amount=total,
                payment_method=data.payment_method,
                bank_account_id=data.bank_account_id,
                bank_account=data.bank_account,
                department_id=data.department_id,
                department_name=data.department_name,
                project_id=data.project_id,
                project_name=data.project_name,
                notes=data.notes,
                attachments=data.attachments,
                related_purchase_receipts=related_receipts,
                payable_recognition=payable_recognition,
                source_type=source_type,
                source_id=source_id,
                source_code=source_code,
                status="Draft",
                review_status="草稿",
                created_by=created_by,
                created_by_name=user["name"],
                updated_by=created_by,
                updated_by_name=user["name"],
            )
            for row in line_rows:
                await OtherExpenseLine.create(
                    tenant_id=tenant_id, other_expense_id=head.id, **row
                )
            head_id = head.id
        # 下推自申请单不走手动建单自动提交
        if not source_type:
            from apps.kuaizhizao.services.manual_create_auto_lifecycle import (
                apply_manual_create_auto_submit,
            )

            await apply_manual_create_auto_submit(
                tenant_id=tenant_id,
                node_key="other_expense",
                entity_id=head_id,
                operator_id=created_by,
            )
        return await self.get_by_id(tenant_id, head_id)

    async def create_expense(
        self, tenant_id: int, data: OtherExpenseCreate, created_by: int
    ) -> OtherExpenseResponse:
        source_type = str(data.source_type or "").strip()
        if source_type == "other_expense_application":
            if not data.source_id:
                raise ValidationError("缺少申请来源ID")
            total, _ = await self._sum_and_validate_lines(
                tenant_id, data.lines, payment_method=str(data.payment_method or "")
            )
            from apps.kuaicaiwu.services.other_expense_application_pull_service import (
                OtherExpenseApplicationPullService,
            )
            from apps.kuaicaiwu.services.other_expense_application_service import (
                OtherExpenseApplicationService,
            )

            preview = await OtherExpenseApplicationPullService().assert_pull_create_allowed(
                tenant_id,
                application_id=int(data.source_id),
                total_amount=total,
            )
            app_svc = OtherExpenseApplicationService()
            from apps.kuaicaiwu.models.other_expense_application import (
                OtherExpenseApplicationLine,
            )

            lines = await OtherExpenseApplicationLine.filter(
                tenant_id=tenant_id, application_id=int(data.source_id)
            ).order_by("line_no")
            allocations = await app_svc.allocate_push_amount_to_lines(list(lines), total)
            line_pushes = [(int(ln.id), amt) for ln, amt in allocations]
            if not data.source_code and preview.get("source_code"):
                data = data.model_copy(update={"source_code": preview.get("source_code")})
            return await self.create_expense_from_application(
                tenant_id, data, created_by, line_pushes=line_pushes
            )
        return await self._create_expense_record(tenant_id, data, created_by)

    async def get_by_id(
        self,
        tenant_id: int,
        expense_id: int,
        *,
        viewer_id: Optional[int] = None,
    ) -> OtherExpenseResponse:
        head = await OtherExpense.get_or_none(
            tenant_id=tenant_id, id=expense_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用支出单不存在: {expense_id}")
        item = await self._to_response(head)
        from core.services.approval.audit_record_enricher import enrich_items

        enriched = await enrich_items(
            tenant_id, "other_expense", [item], viewer_id=viewer_id
        )
        return enriched[0]

    async def list_expenses(
        self,
        tenant_id: int,
        *,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        review_status: Optional[str] = None,
        keyword: Optional[str] = None,
        viewer_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        q = OtherExpense.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if status:
            q = q.filter(status=status)
        if review_status:
            q = q.filter(review_status=review_status)
        kw = (keyword or "").strip()
        if kw:
            from apps.kuaizhizao.utils.list_item_material_keyword import (
                apply_query_header_or_line_icontains_keyword,
            )

            q = await apply_query_header_or_line_icontains_keyword(
                q,
                tenant_id=tenant_id,
                kw=kw,
                keyword_fields=(
                    "expense_code",
                    "counterparty_name",
                    "notes",
                    "department_name",
                    "source_code",
                    "bank_account",
                ),
                item_model=OtherExpenseLine,
                item_header_fk_field="other_expense_id",
                line_fields=(
                    "category_code",
                    "category_name",
                    "description",
                    "payee_name",
                ),
            )
        total = await q.count()
        rows = await q.offset(skip).limit(limit).order_by("-created_at")
        items = [await self._to_response(r) for r in rows]
        from core.services.approval.audit_record_enricher import enrich_items

        items = await enrich_items(
            tenant_id, "other_expense", items, viewer_id=viewer_id
        )
        return {"items": items, "total": total}

    async def update_expense(
        self,
        tenant_id: int,
        expense_id: int,
        data: OtherExpenseUpdate,
        updated_by: int,
    ) -> OtherExpenseResponse:
        head = await OtherExpense.get_or_none(
            tenant_id=tenant_id, id=expense_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用支出单不存在: {expense_id}")
        assert_other_expense_capability(head, "update")
        assert_other_expense_review_editable(head)
        dump = data.model_dump(exclude_unset=True)
        from apps.kuaicaiwu.constants.payment_method import assert_supplier_payee_account

        if str(dump.get("counterparty_kind", head.counterparty_kind) or "").strip() in ("supplier", "employee"):
            assert_supplier_payee_account(
                payment_method=dump.get("payment_method", head.payment_method),
                account_name=dump.get("counterparty_account_name", head.counterparty_account_name),
                bank_name=dump.get("counterparty_bank_name", head.counterparty_bank_name),
                bank_account=dump.get("counterparty_bank_account", head.counterparty_bank_account),
            )
        # 明细须用 schema 实例校验；model_dump 后的 dict 无 .amount
        lines_provided = "lines" in dump
        dump.pop("lines", None)
        related_provided = "related_purchase_receipts" in dump
        related_raw = dump.pop("related_purchase_receipts", None)
        user = await self.get_user_info(updated_by)
        kind_for_related = str(
            dump.get("counterparty_kind", head.counterparty_kind) or head.counterparty_kind or "none"
        )
        cp_id_for_related = dump.get("counterparty_id", head.counterparty_id)
        if related_provided or "counterparty_kind" in dump or "counterparty_id" in dump:
            dump["related_purchase_receipts"] = await self.normalize_related_purchase_receipts(
                tenant_id,
                counterparty_kind=kind_for_related,
                counterparty_id=int(cp_id_for_related) if cp_id_for_related else None,
                related=related_raw if related_provided else head.related_purchase_receipts,
            )
        if str(kind_for_related).strip().lower() != "supplier":
            from apps.kuaizhizao.services.document_recognition import (
                payable_recognition_for_misc_expense_counterparty,
            )

            dump["payable_recognition"] = payable_recognition_for_misc_expense_counterparty(
                kind_for_related,
                str(head.payable_recognition or "manual"),
            )
        async with in_transaction():
            if lines_provided:
                if not data.lines:
                    raise ValidationError("至少一行明细")
                method = str(
                    dump.get("payment_method", head.payment_method) or head.payment_method or ""
                )
                total, line_rows = await self._sum_and_validate_lines(
                    tenant_id, data.lines, payment_method=method
                )
                await OtherExpenseLine.filter(
                    tenant_id=tenant_id, other_expense_id=expense_id
                ).delete()
                for row in line_rows:
                    await OtherExpenseLine.create(
                        tenant_id=tenant_id, other_expense_id=expense_id, **row
                    )
                dump["total_amount"] = total
            dump["updated_by"] = updated_by
            dump["updated_by_name"] = user["name"]
            await head.update_from_dict(dump).save()
        return await self.get_by_id(tenant_id, expense_id)

    async def delete_expense(self, tenant_id: int, expense_id: int) -> None:
        head = await OtherExpense.get_or_none(
            tenant_id=tenant_id, id=expense_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用支出单不存在: {expense_id}")
        assert_other_expense_capability(head, "delete")
        assert_other_expense_review_editable(head)
        from apps.kuaicaiwu.services.other_expense_application_service import (
            OtherExpenseApplicationService,
        )

        await OtherExpenseApplicationService().release_expense_occupancy(tenant_id, head)
        head.deleted_at = resolve_business_datetime()
        await head.save()

    async def submit_expense(
        self,
        tenant_id: int,
        expense_id: int,
        user_id: int,
        *,
        selected_approver_user_ids: Optional[List[int]] = None,
        selected_approver_by_node: Optional[Dict[str, List[int]]] = None,
    ) -> OtherExpenseResponse:
        """内部一次性送审。页面提交请走 uni-audit commit。"""
        await OtherExpenseAuditService().submit_expense(
            tenant_id,
            expense_id,
            user_id,
            selected_approver_user_ids=selected_approver_user_ids,
            selected_approver_by_node=selected_approver_by_node,
        )
        return await self.get_by_id(tenant_id, expense_id)

    async def _on_expense_approved(
        self, tenant_id: int, head: OtherExpense, operator_id: int
    ) -> None:
        from apps.kuaicaiwu.services.misc_voucher_finance_bridge import MiscVoucherFinanceBridge

        await MiscVoucherFinanceBridge().ensure_payable_on_expense_approved(
            tenant_id, head, operator_id
        )

    async def approve_expense(
        self,
        tenant_id: int,
        expense_id: int,
        *,
        approved: bool,
        operator_id: int,
        review_remarks: Optional[str] = None,
    ) -> OtherExpenseResponse:
        await OtherExpenseAuditService().approve_expense(
            tenant_id,
            expense_id,
            operator_id,
            approved=approved,
            review_remarks=review_remarks,
        )
        return await self.get_by_id(tenant_id, expense_id)

    async def withdraw_expense_submit(
        self, tenant_id: int, expense_id: int, user_id: int
    ) -> OtherExpenseResponse:
        await OtherExpenseAuditService().withdraw_expense(tenant_id, expense_id, user_id)
        return await self.get_by_id(tenant_id, expense_id)

    async def revoke_expense_approval(
        self, tenant_id: int, expense_id: int, user_id: int
    ) -> OtherExpenseResponse:
        await OtherExpenseAuditService().revoke_expense(tenant_id, expense_id, user_id)
        return await self.get_by_id(tenant_id, expense_id)

    async def cancel_expense(
        self, tenant_id: int, expense_id: int, operator_id: int
    ) -> OtherExpenseResponse:
        head = await OtherExpense.get_or_none(
            tenant_id=tenant_id, id=expense_id, deleted_at__isnull=True
        )
        if not head:
            raise NotFoundError(f"其他费用支出单不存在: {expense_id}")
        assert_other_expense_capability(head, "cancel")
        if is_other_expense_confirmed_status(str(head.status or "")):
            from apps.kuaicaiwu.services.misc_voucher_posting_service import (
                MiscVoucherPostingService,
            )

            await MiscVoucherPostingService().unpost_other_expense(
                tenant_id, expense_id, operator_id=operator_id
            )
        user = await self.get_user_info(operator_id)
        head.status = "Cancelled"
        head.updated_by = operator_id
        head.updated_by_name = user["name"]
        await head.save()
        return await self.get_by_id(tenant_id, expense_id)
