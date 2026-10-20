"""
采购询价：按受邀供应商生成固定版式询价单 PDF，写入本单 attachments。
"""

from __future__ import annotations

import html
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from apps.kuaizhizao.models import (
    PurchaseDemandParty,
    PurchaseInquiry,
    PurchaseInquiryItem,
    PurchaseInquiryVendor,
)
from apps.kuaizhizao.services.print_service import html_to_pdf_bytes
from apps.master_data.models import Supplier
from core.services.file.file_service import FileService
from infra.exceptions.exceptions import BusinessLogicError

VENDOR_SYSTEM_SOURCE = "purchase_inquiry_vendor"
VENDOR_SYSTEM_KIND = "system"
ATTACHMENT_CATEGORY = "purchase_inquiry_attachments"

_CURRENCY_LABELS = {
    "CNY": "人民币",
    "USD": "美元",
    "EUR": "欧元",
    "HKD": "港币",
    "JPY": "日元",
}


def is_vendor_system_attachment(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    source = str(entry.get("source") or "").strip()
    kind = str(entry.get("kind") or "").strip()
    return source == VENDOR_SYSTEM_SOURCE or (
        kind == VENDOR_SYSTEM_KIND and source in ("", VENDOR_SYSTEM_SOURCE)
    )


def keep_manual_attachments(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    kept: List[Dict[str, Any]] = []
    for entry in raw:
        if is_vendor_system_attachment(entry):
            continue
        if isinstance(entry, dict):
            kept.append(dict(entry))
    return kept


def _esc(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value).strip())


def _fmt_date(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return str(value.isoformat())[:10]
    text = str(value).strip()
    return text[:10] if text else ""


def _fmt_qty(value: Any) -> str:
    if value is None:
        return ""
    try:
        d = Decimal(str(value))
    except Exception:
        return _esc(value)
    text = format(d.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _fmt_tax_percent(value: Any) -> str:
    if value is None:
        return ""
    try:
        d = Decimal(str(value))
    except Exception:
        return _esc(value)
    pct = (d * Decimal("100")).quantize(Decimal("0.01"))
    return f"{pct}%"


def _currency_label(code: Optional[str]) -> str:
    raw = str(code or "").strip().upper()
    if not raw:
        return ""
    return _CURRENCY_LABELS.get(raw, raw)


def _safe_filename_part(name: str, *, max_len: int = 40) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", (name or "").strip())
    cleaned = cleaned.strip("._") or "供应商"
    return cleaned[:max_len]


def build_vendor_inquiry_html(
    *,
    inquiry: PurchaseInquiry,
    vendor: PurchaseInquiryVendor,
    items: Sequence[PurchaseInquiryItem],
    demand_party: Optional[PurchaseDemandParty] = None,
    supplier: Optional[Supplier] = None,
) -> str:
    party_name = (
        (demand_party.name if demand_party else None)
        or inquiry.demand_party_name
        or ""
    )
    party_contact = (demand_party.contact_name if demand_party else None) or inquiry.buyer_name or ""
    party_phone = (
        (demand_party.contact_phone if demand_party else None)
        or inquiry.buyer_phone
        or ""
    )
    party_address = (demand_party.address if demand_party else None) or ""

    supplier_name = vendor.supplier_name or (supplier.name if supplier else "") or ""
    supplier_contact = vendor.contact_name or (supplier.contact_person if supplier else "") or ""
    supplier_phone = vendor.contact_phone or (supplier.phone if supplier else "") or ""
    supplier_address = (supplier.address if supplier else None) or ""

    rows_html: List[str] = []
    total_qty = Decimal("0")
    for idx, item in enumerate(items, start=1):
        qty = item.quantity if item.quantity is not None else Decimal("0")
        total_qty += Decimal(str(qty))
        rows_html.append(
            f"""
            <tr>
              <td class="c">{idx}</td>
              <td>{_esc(item.material_code)}</td>
              <td>{_esc(item.material_name)}</td>
              <td>{_esc(item.material_spec)}</td>
              <td class="c">{_esc(item.unit)}</td>
              <td class="r">{_esc(_fmt_qty(qty))}</td>
              <td class="c">{_esc(_fmt_date(item.required_date))}</td>
              <td>{_esc(item.notes)}</td>
            </tr>
            """
        )
    if not rows_html:
        rows_html.append(
            """
            <tr>
              <td class="c" colspan="8">暂无询价明细</td>
            </tr>
            """
        )

    notes = inquiry.notes or ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>询价单 {_esc(inquiry.inquiry_code)}</title>
  <style>
    @page {{ size: A4; margin: 16mm 14mm; }}
    body {{
      font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
      font-size: 12px;
      color: #222;
      margin: 0;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;
      border-bottom: 2px solid #333;
      padding-bottom: 10px;
    }}
    .party-name {{
      font-size: 18px;
      font-weight: 700;
      margin: 0 0 6px 0;
    }}
    .meta {{ line-height: 1.6; color: #444; }}
    .doc-title {{
      text-align: center;
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 4px;
      margin: 10px 0 14px;
    }}
    .section {{
      margin-bottom: 12px;
    }}
    .section-title {{
      font-weight: 700;
      margin-bottom: 6px;
      border-left: none;
      padding: 0;
    }}
    table.grid {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }}
    table.grid th, table.grid td {{
      border: 1px solid #333;
      padding: 6px 6px;
      vertical-align: top;
      word-wrap: break-word;
    }}
    table.grid th {{
      background: #f5f5f5;
      font-weight: 600;
      text-align: center;
    }}
    .c {{ text-align: center; }}
    .r {{ text-align: right; }}
    .kv {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 8px;
    }}
    .kv td {{
      padding: 3px 4px;
      vertical-align: top;
    }}
    .kv .label {{ color: #666; width: 72px; white-space: nowrap; }}
    .terms td {{ padding: 4px 0; }}
    .footer-note {{
      margin-top: 10px;
      min-height: 48px;
      border: 1px solid #333;
      padding: 8px;
      white-space: pre-wrap;
    }}
  </style>
</head>
<body>
  <div class="header">
    <div>
      <p class="party-name">{_esc(party_name) or "需方"}</p>
      <div class="meta">
        <div>地址：{_esc(party_address)}</div>
        <div>联系人：{_esc(party_contact)}</div>
        <div>电话：{_esc(party_phone)}</div>
      </div>
    </div>
    <div class="meta" style="text-align:right;">
      <div>询价单号：{_esc(inquiry.inquiry_code)}</div>
      <div>询价日期：{_esc(_fmt_date(inquiry.inquiry_date))}</div>
    </div>
  </div>

  <div class="doc-title">询价单</div>

  <div class="section">
    <div class="section-title">供方</div>
    <table class="kv">
      <tr>
        <td class="label">名称</td><td>{_esc(supplier_name)}</td>
        <td class="label">联系人</td><td>{_esc(supplier_contact)}</td>
      </tr>
      <tr>
        <td class="label">地址</td><td>{_esc(supplier_address)}</td>
        <td class="label">电话</td><td>{_esc(supplier_phone)}</td>
      </tr>
    </table>
  </div>

  <div class="section">
    <div class="section-title">询价商品</div>
    <table class="grid">
      <thead>
        <tr>
          <th style="width:36px;">序号</th>
          <th style="width:110px;">物料编码</th>
          <th>物料名称</th>
          <th style="width:90px;">规格</th>
          <th style="width:48px;">单位</th>
          <th style="width:72px;">数量</th>
          <th style="width:88px;">期望交期</th>
          <th style="width:90px;">备注</th>
        </tr>
      </thead>
      <tbody>
        {"".join(rows_html)}
        <tr>
          <td colspan="5" class="r"><strong>合计</strong></td>
          <td class="r"><strong>{_esc(_fmt_qty(total_qty))}</strong></td>
          <td colspan="2"></td>
        </tr>
      </tbody>
    </table>
    <table class="kv" style="margin-top:8px;">
      <tr>
        <td class="label">税率</td><td>{_esc(_fmt_tax_percent(inquiry.tax_rate))}</td>
        <td class="label">币种</td><td>{_esc(_currency_label(inquiry.currency))}</td>
      </tr>
    </table>
  </div>

  <div class="section">
    <div class="section-title">商务条款</div>
    <table class="kv terms">
      <tr>
        <td class="label">付款条件</td><td>{_esc(inquiry.payment_terms)}</td>
        <td class="label">付款方式</td><td>{_esc(inquiry.payment_method)}</td>
      </tr>
      <tr>
        <td class="label">成交方式</td><td>{_esc(inquiry.trade_mode)}</td>
        <td class="label">报价截止</td><td>{_esc(_fmt_date(inquiry.quote_deadline))}</td>
      </tr>
      <tr>
        <td class="label">发票类型</td><td colspan="3">{_esc(inquiry.invoice_type)}</td>
      </tr>
    </table>
  </div>

  <div class="section">
    <div class="section-title">其他询价说明</div>
    <div class="footer-note">{_esc(notes) or " "}</div>
  </div>
</body>
</html>
"""


async def render_vendor_inquiry_pdf(
    *,
    tenant_id: int,
    inquiry: PurchaseInquiry,
    vendor: PurchaseInquiryVendor,
    items: Sequence[PurchaseInquiryItem],
    demand_party: Optional[PurchaseDemandParty] = None,
    supplier: Optional[Supplier] = None,
) -> bytes:
    html_content = build_vendor_inquiry_html(
        inquiry=inquiry,
        vendor=vendor,
        items=items,
        demand_party=demand_party,
        supplier=supplier,
    )
    pdf_bytes, _engine = await html_to_pdf_bytes(html_content, tenant_id=tenant_id)
    if not pdf_bytes:
        raise BusinessLogicError("询价单 PDF 生成失败：未得到文件内容")
    return pdf_bytes


async def generate_purchase_inquiry_vendor_attachments(
    *,
    tenant_id: int,
    inquiry: PurchaseInquiry,
    user_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    按当前受邀供应商生成系统附件条目（不写库）。
    失败直接抛错，由发布流程中止。
    """
    vendors = await PurchaseInquiryVendor.filter(
        tenant_id=tenant_id, inquiry_id=inquiry.id
    ).order_by("id")
    if not vendors:
        raise BusinessLogicError("请至少邀请一家供应商")

    items = await PurchaseInquiryItem.filter(
        tenant_id=tenant_id, inquiry_id=inquiry.id
    ).order_by("id")

    demand_party: Optional[PurchaseDemandParty] = None
    if inquiry.demand_party_id:
        demand_party = await PurchaseDemandParty.get_or_none(
            tenant_id=tenant_id,
            id=inquiry.demand_party_id,
            deleted_at__isnull=True,
        )

    supplier_ids = [int(v.supplier_id) for v in vendors if v.supplier_id]
    suppliers_by_id: Dict[int, Supplier] = {}
    if supplier_ids:
        rows = await Supplier.filter(
            tenant_id=tenant_id, id__in=supplier_ids, deleted_at__isnull=True
        )
        suppliers_by_id = {int(s.id): s for s in rows}

    # 先全部渲染，避免部分落盘后失败导致发布半成功
    rendered: List[tuple[PurchaseInquiryVendor, bytes, str]] = []
    for vendor in vendors:
        supplier = suppliers_by_id.get(int(vendor.supplier_id)) if vendor.supplier_id else None
        try:
            pdf_bytes = await render_vendor_inquiry_pdf(
                tenant_id=tenant_id,
                inquiry=inquiry,
                vendor=vendor,
                items=items,
                demand_party=demand_party,
                supplier=supplier,
            )
        except BusinessLogicError:
            raise
        except Exception as exc:
            raise BusinessLogicError(
                f"生成供应商「{vendor.supplier_name or vendor.supplier_id}」询价附件失败：{exc}"
            ) from exc
        safe_name = _safe_filename_part(str(vendor.supplier_name or vendor.supplier_id or "供应商"))
        filename = f"{inquiry.inquiry_code}-{safe_name}.pdf"
        rendered.append((vendor, pdf_bytes, filename))

    attachments: List[Dict[str, Any]] = []
    for vendor, pdf_bytes, filename in rendered:
        try:
            file_row = await FileService.save_uploaded_file(
                tenant_id=tenant_id,
                file_content=pdf_bytes,
                original_name=filename,
                category=ATTACHMENT_CATEGORY,
                description=f"采购询价系统附件 supplier_id={vendor.supplier_id}",
                user_id=user_id,
            )
        except Exception as exc:
            raise BusinessLogicError(
                f"保存供应商「{vendor.supplier_name or vendor.supplier_id}」询价附件失败：{exc}"
            ) from exc
        uid = str(file_row.uuid)
        attachments.append(
            {
                "uid": uid,
                "name": filename,
                "status": "done",
                "url": f"/api/v1/core/files/{uid}/download",
                "kind": VENDOR_SYSTEM_KIND,
                "source": VENDOR_SYSTEM_SOURCE,
                "supplier_id": int(vendor.supplier_id) if vendor.supplier_id else None,
            }
        )
    return attachments
