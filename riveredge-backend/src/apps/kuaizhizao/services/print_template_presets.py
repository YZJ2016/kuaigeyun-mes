"""加载快制造打印模板预设到租户。

约定：库内 PrintTemplate.content 为版式唯一真源。
预设在「租户尚无该 code」时创建。

升级：exact code 匹配的预置若尚非可视化（无 designer_schema.blocks，
或仍为 asset_card_table），用当前可视化预置覆盖 content/config。
用户自建的 code_001 等后缀模板不覆盖。
"""

from __future__ import annotations

import copy

from loguru import logger

from apps.kuaizhizao.print.preset_templates import KUAIZHIZAO_PRESET_PRINT_TEMPLATES
from apps.kuaizhizao.print.red_voucher_presets import (
    is_kuaizhizao_red_voucher_print_template,
    is_purchase_receipt_red_voucher_template,
    patch_purchase_receipt_red_voucher_html,
    patch_purchase_receipt_red_voucher_schema,
    recompile_designer_schema,
)
from core.models.print_template import PrintTemplate
from core.schemas.print_template import PrintTemplateCreate
from core.services.print.print_template_service import PrintTemplateService
from core.services.print.print_template_visual import is_visual_designer_config


async def _upgrade_non_visual_builtin_preset(tenant_id: int, item: dict) -> bool:
    """将 exact-code 预置从纯 HTML / 旧资产卡模式升级为可视化预设。"""
    code = str(item.get("code") or "").strip().upper()
    if not code:
        return False
    tpl = await PrintTemplate.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        code=code,
    ).first()
    if not tpl or is_visual_designer_config(tpl.config):
        return False
    tpl.name = item["name"]
    tpl.description = item.get("description")
    tpl.content = item["content"]
    tpl.config = item.get("config")
    tpl.is_active = item.get("is_active", True)
    if item.get("is_default") is not None:
        tpl.is_default = bool(item.get("is_default"))
    await tpl.save()
    logger.info("已升级打印模板为可视化: tenant={} code={}", tenant_id, code)
    return True


def patch_detail_tables_plain_background(schema: dict) -> bool:
    """预置单据明细统一白底；保留边框与深色表头文字。"""
    changed = False

    def walk(blocks: object) -> None:
        nonlocal changed
        if not isinstance(blocks, list):
            return
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "detail_table":
                current = block.get("tableStyle")
                style = dict(current) if isinstance(current, dict) else {}
                next_style = {
                    **style,
                    "headerBgColor": "#ffffff",
                    "headerTextColor": "#1e293b",
                    "headerFontWeight": "700",
                    "zebraStripe": False,
                    "zebraBgColor": "#ffffff",
                }
                if next_style != style:
                    block["tableStyle"] = next_style
                    changed = True
            walk(block.get("blocks"))
            cols = block.get("cols")
            if isinstance(cols, list):
                for col in cols:
                    if isinstance(col, dict):
                        walk(col.get("blocks"))

    walk(schema.get("blocks"))
    return changed


async def upgrade_builtin_detail_table_backgrounds(tenant_id: int) -> int:
    """升级 exact-code 快制造预置模板；用户自建后缀模板不改。"""
    preset_codes = {
        str(item.get("code") or "").strip().upper()
        for item in KUAIZHIZAO_PRESET_PRINT_TEMPLATES
        if str(item.get("code") or "").strip()
    }
    templates = await PrintTemplate.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        code__in=list(preset_codes),
    ).all()
    upgraded = 0
    for tpl in templates:
        config_raw = tpl.config
        if not isinstance(config_raw, dict):
            continue
        schema = config_raw.get("designer_schema")
        if not isinstance(schema, dict):
            continue
        schema_copy = copy.deepcopy(schema)
        if not patch_detail_tables_plain_background(schema_copy):
            continue
        tpl.content = recompile_designer_schema(schema_copy)
        tpl.config = {**config_raw, "designer_schema": schema_copy}
        await tpl.save()
        upgraded += 1
        logger.info("打印明细已改白底 tenant={} code={}", tenant_id, tpl.code)
    return upgraded


async def upgrade_purchase_receipt_red_voucher_templates(tenant_id: int) -> int:
    """红框凭证：采购入库库位列/标题简称等 HTML 修补（幂等）。"""
    return await upgrade_kuaizhizao_red_voucher_print_templates(tenant_id)


async def upgrade_kuaizhizao_red_voucher_print_templates(tenant_id: int) -> int:
    """三份红框凭证（入库/其他出库/生产领料）：库位列与 v4 版式（标题简称在库内 HTML 直接维护）。"""
    upgraded = 0
    templates = await PrintTemplate.filter(tenant_id=tenant_id, deleted_at__isnull=True).all()
    for tpl in templates:
        config_raw = tpl.config
        if not isinstance(config_raw, dict):
            continue
        if not is_kuaizhizao_red_voucher_print_template(
            name=tpl.name,
            code=tpl.code,
            config=config_raw,
        ):
            continue
        schema = config_raw.get("designer_schema")
        if not isinstance(schema, dict):
            continue
        schema_copy = dict(schema)
        blocks = schema_copy.get("blocks")
        if isinstance(blocks, list):
            schema_copy["blocks"] = [dict(b) if isinstance(b, dict) else b for b in blocks]

        schema_changed = False
        content_html_changed = False
        from apps.kuaizhizao.print.red_voucher_presets import (
            patch_kuaizhizao_red_voucher_kingdee_bill_no_html,
        )

        kingdee_html, kingdee_html_changed = patch_kuaizhizao_red_voucher_kingdee_bill_no_html(
            str(tpl.content or "")
        )
        if kingdee_html_changed:
            tpl.content = kingdee_html
            content_html_changed = True
            for blk in schema_copy.get("blocks") or []:
                if (
                    isinstance(blk, dict)
                    and blk.get("type") == "text"
                    and isinstance(blk.get("content"), str)
                ):
                    blk["content"] = kingdee_html
                    schema_changed = True
                    break

        is_purchase_red = is_purchase_receipt_red_voucher_template(
            name=tpl.name,
            code=tpl.code,
            config=config_raw,
        )
        purchase_red_html_saved = False
        if is_purchase_red:
            purchase_schema_changed = patch_purchase_receipt_red_voucher_schema(schema_copy)
            if purchase_schema_changed:
                schema_changed = True
            next_content, purchase_html_changed = patch_purchase_receipt_red_voucher_html(
                str(tpl.content or "")
            )
            if purchase_html_changed:
                content_html_changed = True
                tpl.content = next_content
                purchase_red_html_saved = True
                for blk in schema_copy.get("blocks") or []:
                    if (
                        isinstance(blk, dict)
                        and blk.get("type") == "text"
                        and isinstance(blk.get("content"), str)
                    ):
                        blk["content"] = next_content
                        schema_changed = True
                        break

        if not (schema_changed or content_html_changed):
            continue

        if not purchase_red_html_saved:
            text_body: str | None = None
            for blk in schema_copy.get("blocks") or []:
                if (
                    isinstance(blk, dict)
                    and blk.get("type") == "text"
                    and isinstance(blk.get("content"), str)
                    and blk.get("content").strip()
                ):
                    text_body = str(blk["content"])
                    break
            if text_body is not None:
                tpl.content = text_body
            else:
                try:
                    tpl.content = recompile_designer_schema(schema_copy)
                except Exception as e:
                    logger.warning(
                        "编译红框打印模板失败 tenant={} code={}: {}",
                        tenant_id,
                        tpl.code,
                        e,
                    )
                    continue

        next_config = dict(config_raw)
        next_config["designer_schema"] = schema_copy
        tpl.config = next_config
        await tpl.save()
        upgraded += 1
        logger.info(
            "已升级红框打印模板 tenant={} code={}",
            tenant_id,
            tpl.code,
        )
    return upgraded


def patch_purchase_requisition_print_line_no(schema: dict) -> bool:
    """采购申请明细表缺行号时插到第一列。已有 line_no 则不改。"""
    changed = False

    def visit(block: dict) -> None:
        nonlocal changed
        if block.get("type") != "detail_table":
            return
        if str(block.get("collection") or "items") != "items":
            return
        columns = block.get("columns")
        if not isinstance(columns, list):
            return
        if any(isinstance(col, dict) and col.get("key") == "line_no" for col in columns):
            return
        block["columns"] = [{"key": "line_no", "label": "行号", "type": "text"}, *columns]
        changed = True

    def walk(blocks: object) -> None:
        if not isinstance(blocks, list):
            return
        for block in blocks:
            if not isinstance(block, dict):
                continue
            visit(block)
            walk(block.get("blocks"))
            cols = block.get("cols")
            if isinstance(cols, list):
                for col in cols:
                    if isinstance(col, dict):
                        walk(col.get("blocks"))

    walk(schema.get("blocks"))
    return changed


_OTHER_EXPENSE_DETAIL_COLUMN_KEYS = (
    "line_no",
    "category_name",
    "description",
    "amount",
    "payee_name",
)
_OTHER_EXPENSE_DETAIL_COLUMN_KEYS_LEGACY = (
    "line_no",
    "category_name",
    "amount",
    "payee_name",
    "description",
)


def patch_other_expense_print_detail_columns(schema: dict) -> bool:
    """其他费用支出明细：摘要列置于金额前（仅升级旧版预置列序）。"""
    changed = False

    def visit(block: dict) -> None:
        nonlocal changed
        if block.get("type") != "detail_table":
            return
        if str(block.get("collection") or "items") != "items":
            return
        columns = block.get("columns")
        if not isinstance(columns, list):
            return
        keys = [str(c.get("key") or "") for c in columns if isinstance(c, dict)]
        if keys == list(_OTHER_EXPENSE_DETAIL_COLUMN_KEYS):
            return
        if keys != list(_OTHER_EXPENSE_DETAIL_COLUMN_KEYS_LEGACY):
            return
        by_key = {str(c.get("key") or ""): c for c in columns if isinstance(c, dict)}
        block["columns"] = [dict(by_key[k]) for k in _OTHER_EXPENSE_DETAIL_COLUMN_KEYS]
        changed = True

    def walk(blocks: object) -> None:
        if not isinstance(blocks, list):
            return
        for block in blocks:
            if not isinstance(block, dict):
                continue
            visit(block)
            walk(block.get("blocks"))
            cols = block.get("cols")
            if isinstance(cols, list):
                for col in cols:
                    if isinstance(col, dict):
                        walk(col.get("blocks"))

    walk(schema.get("blocks"))
    return changed


def _schema_tree_field_keys(nodes: object) -> set[str]:
    keys: set[str] = set()

    def walk(blocks: object) -> None:
        if not isinstance(blocks, list):
            return
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "field":
                key = str(block.get("key") or "").strip()
                if key:
                    keys.add(key)
            walk(block.get("blocks"))
            cols = block.get("cols")
            if isinstance(cols, list):
                for col in cols:
                    if isinstance(col, dict):
                        walk(col.get("blocks"))

    walk(nodes)
    return keys


def patch_other_expense_print_basic_fields(schema: dict) -> bool:
    """其他费用支出基本信息：补往来收款户名、开户行、账号。"""
    required = {
        "counterparty_account_name",
        "counterparty_bank_name",
        "counterparty_bank_account",
    }
    all_keys = _schema_tree_field_keys(schema.get("blocks"))
    if required.issubset(all_keys):
        return False
    if "counterparty_name" not in all_keys:
        return False
    from apps.kuaizhizao.print.designer_presets import DOCUMENT_LAYOUTS, _info_columns

    layout = DOCUMENT_LAYOUTS.get("other_expense")
    if not layout:
        return False
    new_col = _info_columns(layout.info_items)
    blocks = schema.get("blocks")
    if not isinstance(blocks, list):
        return False
    for index, block in enumerate(blocks):
        if not isinstance(block, dict) or block.get("type") != "columns":
            continue
        col_keys = _schema_tree_field_keys(block.get("cols"))
        if "counterparty_name" in col_keys:
            blocks[index] = new_col
            return True
    return False


async def upgrade_other_expense_print_detail_columns(tenant_id: int) -> int:
    """已落地的其他费用支出打印模板：明细列序与基本信息字段升级。"""
    from apps.kuaizhizao.print.red_voucher_presets import recompile_designer_schema

    upgraded = 0
    templates = await PrintTemplate.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        config__contains={"document_type": "other_expense"},
    ).all()
    for tpl in templates:
        config_raw = tpl.config
        if not isinstance(config_raw, dict):
            continue
        schema = config_raw.get("designer_schema")
        if not isinstance(schema, dict):
            continue
        schema_copy = copy.deepcopy(schema)
        changed = patch_other_expense_print_detail_columns(schema_copy)
        changed = patch_other_expense_print_basic_fields(schema_copy) or changed
        if not changed:
            continue
        try:
            tpl.content = recompile_designer_schema(schema_copy)
        except Exception as e:
            logger.warning(
                "编译其他费用支出打印模板失败 tenant={} code={}: {}",
                tenant_id,
                tpl.code,
                e,
            )
            continue
        next_config = dict(config_raw)
        next_config["designer_schema"] = schema_copy
        tpl.config = next_config
        await tpl.save()
        upgraded += 1
        logger.info(
            "其他费用支出打印模板已升级 tenant={} code={}",
            tenant_id,
            tpl.code,
        )
    return upgraded


async def upgrade_purchase_requisition_print_line_no(tenant_id: int) -> int:
    """已落地的采购申请打印模板补行号列，并重编译版式。"""
    from apps.kuaizhizao.print.red_voucher_presets import recompile_designer_schema

    upgraded = 0
    templates = await PrintTemplate.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        config__contains={"document_type": "purchase_requisition"},
    ).all()
    for tpl in templates:
        config_raw = tpl.config
        if not isinstance(config_raw, dict):
            continue
        schema = config_raw.get("designer_schema")
        if not isinstance(schema, dict):
            continue
        schema_copy = copy.deepcopy(schema)
        if not patch_purchase_requisition_print_line_no(schema_copy):
            continue
        try:
            tpl.content = recompile_designer_schema(schema_copy)
        except Exception as e:
            logger.warning(
                "编译采购申请打印模板失败 tenant={} code={}: {}",
                tenant_id,
                tpl.code,
                e,
            )
            continue
        next_config = dict(config_raw)
        next_config["designer_schema"] = schema_copy
        tpl.config = next_config
        await tpl.save()
        upgraded += 1
        logger.info("采购申请打印模板已补行号 tenant={} code={}", tenant_id, tpl.code)
    return upgraded


_PO_PRINT_TOTALS = "总数量：{{ total_quantity | number }}    总金额：{{ total_amount | money }}"
_PO_PRINT_TOTALS_WITH_INCLUSIVE = (
    _PO_PRINT_TOTALS + "    含税金额：{{ tax_inclusive_amount | money }}"
)
# 采购订单合计只展示数量与含税金额，不再露出未税总金额
_PO_PRINT_TOTALS_QTY_INCLUSIVE_ONLY = (
    "总数量：{{ total_quantity | number }}    含税金额：{{ tax_inclusive_amount | money }}"
)


def _set_style_font_size(block: dict, font_size: str) -> bool:
    style = block.get("style")
    if not isinstance(style, dict):
        block["style"] = {"fontSize": font_size}
        return True
    if str(style.get("fontSize") or "") == font_size:
        return False
    block["style"] = {**style, "fontSize": font_size}
    return True


_PAYMENT_PRINT_HEADER_FIELDS: tuple[tuple[str, str], ...] = (
    ("department_name", "申请部门"),
)

_PO_PRINT_HEADER_FIELDS: tuple[tuple[str, str], ...] = (
    ("department_name", "申请部门"),
    ("settlement_terms", "供应商结算方式"),
    ("payment_cycle", "付款周期"),
)


def _patch_print_basic_info_fields(
    schema: dict,
    fields: tuple[tuple[str, str], ...],
    *,
    field_id_prefix: str,
) -> bool:
    """在基本信息 columns 中补缺失字段。"""
    changed = False

    def find_info_columns_blocks(blocks: object) -> list | None:
        if not isinstance(blocks, list):
            return None
        saw_basic = False
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and str(block.get("content") or "").strip() == "基本信息":
                saw_basic = True
                continue
            if saw_basic and block.get("type") == "columns":
                return block.get("cols") if isinstance(block.get("cols"), list) else None
            nested = find_info_columns_blocks(block.get("blocks"))
            if nested is not None:
                return nested
            cols = block.get("cols")
            if isinstance(cols, list):
                for col in cols:
                    if isinstance(col, dict):
                        nested = find_info_columns_blocks(col.get("blocks"))
                        if nested is not None:
                            return nested
        return None

    cols = find_info_columns_blocks(schema.get("blocks"))
    if not isinstance(cols, list) or not cols:
        return False

    existing_keys: set[str] = set()
    for col in cols:
        if not isinstance(col, dict):
            continue
        for blk in col.get("blocks") or []:
            if isinstance(blk, dict) and blk.get("type") == "field":
                key = str(blk.get("key") or "").strip()
                if key:
                    existing_keys.add(key)

    missing = [(k, label) for k, label in fields if k not in existing_keys]
    if not missing:
        return False

    for index, (key, label) in enumerate(missing):
        target = cols[index % len(cols)]
        if not isinstance(target, dict):
            continue
        blocks = target.get("blocks")
        if not isinstance(blocks, list):
            blocks = []
            target["blocks"] = blocks
        blocks.append(
            {
                "id": f"{field_id_prefix}-{key}",
                "type": "field",
                "key": key,
                "label": label,
                "showLabel": True,
                "style": {"fontSize": "12px"},
            }
        )
        changed = True
    return changed


def patch_payment_application_print_department_field(schema: dict) -> bool:
    """付款申请基本信息补申请部门。"""
    return _patch_print_basic_info_fields(
        schema,
        _PAYMENT_PRINT_HEADER_FIELDS,
        field_id_prefix="pa-field",
    )


def patch_purchase_order_print_basic_info_fields(schema: dict) -> bool:
    """采购订单基本信息补申请部门、供应商结算方式、付款周期。"""
    return _patch_print_basic_info_fields(
        schema,
        _PO_PRINT_HEADER_FIELDS,
        field_id_prefix="po-field",
    )


def patch_purchase_order_print_header_and_type(schema: dict) -> bool:
    """采购订单：基本信息去掉采购员；统一标题/正文/明细/签核字号。"""
    from apps.kuaizhizao.print.designer_presets import (
        PRINT_BODY_FONT_SIZE,
        PRINT_FOOTER_FONT_SIZE,
        PRINT_TITLE_FONT_SIZE,
    )

    changed = False

    def visit(block: dict, *, in_sign_row: bool = False) -> None:
        nonlocal changed
        blk_type = str(block.get("type") or "")
        if blk_type == "field" and str(block.get("key") or "") == "purchaser_name":
            # 由调用方在 columns.blocks 列表里删除；此处仅标记
            return
        if blk_type == "text":
            content = str(block.get("content") or "").strip()
            if content == "采购订单" or (
                block.get("tag") == "h1" and "采购订单" in content and "{{" not in content
            ):
                if _set_style_font_size(block, PRINT_TITLE_FONT_SIZE):
                    changed = True
            elif content in ("基本信息", "明细", "备注"):
                if _set_style_font_size(block, PRINT_BODY_FONT_SIZE):
                    changed = True
            elif content.startswith("总数量："):
                if _set_style_font_size(block, PRINT_BODY_FONT_SIZE):
                    changed = True
            elif content.startswith("本单据由系统自动生成"):
                if _set_style_font_size(block, PRINT_FOOTER_FONT_SIZE):
                    changed = True
            elif in_sign_row or content.startswith(("采购员：", "审核人：", "供应商确认：")):
                if _set_style_font_size(block, PRINT_BODY_FONT_SIZE):
                    changed = True
        elif blk_type == "field":
            if _set_style_font_size(block, PRINT_BODY_FONT_SIZE):
                changed = True
        elif blk_type == "seal_overlay":
            if _set_style_font_size(block, PRINT_BODY_FONT_SIZE):
                changed = True
        elif blk_type == "detail_table":
            table_style = block.get("tableStyle")
            if not isinstance(table_style, dict):
                block["tableStyle"] = {"fontSize": PRINT_BODY_FONT_SIZE}
                changed = True
            elif str(table_style.get("fontSize") or "") != PRINT_BODY_FONT_SIZE:
                block["tableStyle"] = {**table_style, "fontSize": PRINT_BODY_FONT_SIZE}
                changed = True

    def walk(blocks: object, *, in_sign_row: bool = False) -> None:
        nonlocal changed
        if not isinstance(blocks, list):
            return
        i = 0
        while i < len(blocks):
            block = blocks[i]
            if not isinstance(block, dict):
                i += 1
                continue
            # 基本信息区：删掉采购员字段（签核行保留）
            if (
                not in_sign_row
                and block.get("type") == "field"
                and str(block.get("key") or "") == "purchaser_name"
            ):
                del blocks[i]
                changed = True
                continue
            sign_here = in_sign_row or (
                block.get("type") == "columns"
                and any(
                    isinstance(col, dict)
                    and any(
                        isinstance(b, dict)
                        and (
                            str(b.get("content") or "").startswith("采购员：")
                            or str(b.get("content") or "").startswith("审核人：")
                            or str(b.get("content") or "").startswith("供应商确认：")
                        )
                        for b in (col.get("blocks") or [])
                    )
                    for col in (block.get("cols") or [])
                )
            )
            visit(block, in_sign_row=sign_here)
            walk(block.get("blocks"), in_sign_row=sign_here)
            cols = block.get("cols")
            if isinstance(cols, list):
                for col in cols:
                    if isinstance(col, dict):
                        walk(col.get("blocks"), in_sign_row=sign_here)
            i += 1

    walk(schema.get("blocks"))
    return changed


def patch_purchase_order_print_tax_inclusive_amount(schema: dict) -> bool:
    """采购订单明细对齐：数量、含税单价、含税金额（替换旧「单价/金额」列）。"""
    changed = False

    def visit(block: dict) -> None:
        nonlocal changed
        if block.get("type") == "detail_table" and str(block.get("collection") or "items") == "items":
            columns = block.get("columns")
            if not isinstance(columns, list):
                return
            has_incl_unit = any(
                isinstance(col, dict) and col.get("key") == "tax_inclusive_unit_price"
                for col in columns
            )
            next_columns: list = []
            for col in columns:
                if not isinstance(col, dict):
                    next_columns.append(col)
                    continue
                key = str(col.get("key") or "")
                label = str(col.get("label") or "")
                if key == "ordered_quantity" and label == "采购数量":
                    col = {**col, "label": "数量"}
                    changed = True
                elif key == "unit_price" and label in ("单价", "含税单价"):
                    col = {
                        **col,
                        "key": "tax_inclusive_unit_price",
                        "label": "含税单价",
                    }
                    has_incl_unit = True
                    changed = True
                elif key == "total_amount" and label == "金额":
                    # 与含税金额并排易混，改为只保留含税金额
                    changed = True
                    continue
                next_columns.append(col)

            if not has_incl_unit:
                insert_at = next(
                    (
                        index + 1
                        for index, col in enumerate(next_columns)
                        if isinstance(col, dict) and col.get("key") == "ordered_quantity"
                    ),
                    len(next_columns),
                )
                next_columns.insert(
                    insert_at,
                    {
                        "key": "tax_inclusive_unit_price",
                        "label": "含税单价",
                        "type": "number",
                        "precision": 4,
                    },
                )
                changed = True
                has_incl_unit = True

            if not any(
                isinstance(col, dict) and col.get("key") == "tax_inclusive_amount"
                for col in next_columns
            ):
                insert_at = next(
                    (
                        index + 1
                        for index, col in enumerate(next_columns)
                        if isinstance(col, dict)
                        and col.get("key")
                        in ("tax_inclusive_unit_price", "total_amount", "unit_price")
                    ),
                    len(next_columns),
                )
                next_columns.insert(
                    insert_at,
                    {
                        "key": "tax_inclusive_amount",
                        "label": "含税金额",
                        "type": "number",
                        "precision": 2,
                    },
                )
                changed = True

            if not any(
                isinstance(col, dict) and col.get("key") == "tax_exclusive_amount"
                for col in next_columns
            ):
                insert_at = next(
                    (
                        index
                        for index, col in enumerate(next_columns)
                        if isinstance(col, dict)
                        and col.get("key") == "tax_inclusive_amount"
                    ),
                    len(next_columns),
                )
                next_columns.insert(
                    insert_at,
                    {
                        "key": "tax_exclusive_amount",
                        "label": "不含税金额",
                        "type": "number",
                        "precision": 2,
                    },
                )
                changed = True

            if next_columns != columns:
                block["columns"] = next_columns
                changed = True
        if block.get("type") == "text":
            content = str(block.get("content") or "")
            if content in (_PO_PRINT_TOTALS, _PO_PRINT_TOTALS_WITH_INCLUSIVE) or (
                content.startswith("总数量：")
                and "总金额：{{ total_amount" in content
                and "tax_inclusive_amount" in content
            ):
                if content != _PO_PRINT_TOTALS_QTY_INCLUSIVE_ONLY:
                    block["content"] = _PO_PRINT_TOTALS_QTY_INCLUSIVE_ONLY
                    changed = True

    def walk(blocks: object) -> None:
        if not isinstance(blocks, list):
            return
        for block in blocks:
            if not isinstance(block, dict):
                continue
            visit(block)
            walk(block.get("blocks"))
            cols = block.get("cols")
            if isinstance(cols, list):
                for col in cols:
                    if isinstance(col, dict):
                        walk(col.get("blocks"))

    walk(schema.get("blocks"))
    return changed


def patch_print_numeric_column_precision(schema: dict) -> bool:
    """明细单价列 precision=4，总价/税额/金额列 precision=2，并标为 number。"""
    from apps.kuaizhizao.print.designer_presets import annotate_print_numeric_column

    changed = False

    def visit(block: dict) -> None:
        nonlocal changed
        if block.get("type") != "detail_table":
            return
        columns = block.get("columns")
        if not isinstance(columns, list):
            return
        next_columns: list = []
        for col in columns:
            if not isinstance(col, dict):
                next_columns.append(col)
                continue
            annotated = annotate_print_numeric_column(col)
            if (
                annotated.get("type") != col.get("type")
                or annotated.get("precision") != col.get("precision")
            ):
                changed = True
            next_columns.append(annotated)
        block["columns"] = next_columns

    def walk(blocks: object) -> None:
        if not isinstance(blocks, list):
            return
        for block in blocks:
            if not isinstance(block, dict):
                continue
            visit(block)
            walk(block.get("blocks"))
            cols = block.get("cols")
            if isinstance(cols, list):
                for col in cols:
                    if isinstance(col, dict):
                        walk(col.get("blocks"))

    walk(schema.get("blocks"))
    return changed


async def upgrade_print_numeric_column_precision(tenant_id: int) -> int:
    """存量可视化打印模板：单价 4 位、金额/税额 2 位。"""
    upgraded = 0
    templates = await PrintTemplate.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    ).all()
    for tpl in templates:
        if not is_visual_designer_config(tpl.config):
            continue
        config = copy.deepcopy(tpl.config) if isinstance(tpl.config, dict) else {}
        schema = config.get("designer_schema")
        if not isinstance(schema, dict):
            continue
        schema_copy = copy.deepcopy(schema)
        if not patch_print_numeric_column_precision(schema_copy):
            continue
        try:
            config["designer_schema"] = schema_copy
            compiled = recompile_designer_schema(schema_copy)
            tpl.config = config
            if compiled:
                tpl.content = compiled
            await tpl.save()
            upgraded += 1
        except Exception as e:
            logger.warning(
                "升级打印数值小数位失败 template={} tenant={}: {}",
                getattr(tpl, "code", None),
                tenant_id,
                e,
            )
    return upgraded


async def upgrade_purchase_order_print_tax_inclusive_amount(tenant_id: int) -> int:
    """已落地的采购订单打印模板对齐数量/含税单价/含税金额，并重编译版式。"""
    from apps.kuaizhizao.print.red_voucher_presets import recompile_designer_schema

    upgraded = 0
    templates = await PrintTemplate.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        config__contains={"document_type": "purchase_order"},
    ).all()
    for tpl in templates:
        config_raw = tpl.config
        if not isinstance(config_raw, dict):
            continue
        schema = config_raw.get("designer_schema")
        if not isinstance(schema, dict):
            continue
        schema_copy = copy.deepcopy(schema)
        columns_changed = patch_purchase_order_print_tax_inclusive_amount(schema_copy)
        layout_changed = patch_purchase_order_print_header_and_type(schema_copy)
        header_fields_changed = patch_purchase_order_print_basic_info_fields(schema_copy)
        layout_changed = layout_changed or header_fields_changed
        if not columns_changed and not layout_changed:
            continue
        try:
            tpl.content = recompile_designer_schema(schema_copy)
        except Exception as e:
            logger.warning(
                "编译采购订单打印模板失败 tenant={} code={}: {}",
                tenant_id,
                tpl.code,
                e,
            )
            continue
        next_config = dict(config_raw)
        next_config["designer_schema"] = schema_copy
        tpl.config = next_config
        await tpl.save()
        upgraded += 1
        logger.info(
            "采购订单打印模板已升级版式/明细 tenant={} code={}",
            tenant_id,
            tpl.code,
        )
    return upgraded


def _schema_supports_site_name_banner(schema: dict) -> bool:
    if str(schema.get("cardKind") or "").strip():
        return False
    if schema.get("repeatCollection"):
        return False
    return True


def _find_document_title_header_index(blocks: list) -> int | None:
    for index, block in enumerate(blocks[:4]):
        if not isinstance(block, dict) or block.get("type") != "columns":
            continue
        cols = block.get("cols")
        if not isinstance(cols, list) or not cols:
            continue
        first_col = cols[0]
        if not isinstance(first_col, dict):
            continue
        inner = first_col.get("blocks") or []
        for inner_blk in inner:
            if (
                isinstance(inner_blk, dict)
                and inner_blk.get("type") == "text"
                and str(inner_blk.get("tag") or "") == "h1"
            ):
                return index
    return None


def patch_document_header_site_name_layout(schema: dict) -> bool:
    """站点名与单据标题同列紧贴展示，字体样式与标题一致。"""
    from apps.kuaizhizao.print.designer_presets import (
        DOC_TITLE_TEXT_STYLE,
        site_name_in_header_field,
    )

    if not _schema_supports_site_name_banner(schema):
        return False
    blocks = schema.get("blocks")
    if not isinstance(blocks, list):
        return False
    hdr_idx = _find_document_title_header_index(blocks)
    if hdr_idx is None:
        return False

    changed = False
    if blocks and isinstance(blocks[0], dict):
        first = blocks[0]
        if first.get("type") == "field" and str(first.get("key") or "") == "site_name":
            blocks.pop(0)
            if hdr_idx > 0:
                hdr_idx -= 1
            changed = True

    header = blocks[hdr_idx]
    cols = header.get("cols")
    if not isinstance(cols, list) or not cols:
        return changed
    left_col = cols[0]
    if not isinstance(left_col, dict):
        return changed
    inner = left_col.get("blocks")
    if not isinstance(inner, list):
        inner = []
        left_col["blocks"] = inner

    text_align = (
        "center"
        if str(left_col.get("horizontalAlign") or header.get("horizontalAlign") or "") == "center"
        else "left"
    )
    site_field = site_name_in_header_field(text_align=text_align)

    new_inner: list[dict] = []
    site_kept = False
    for block in inner:
        if not isinstance(block, dict):
            new_inner.append(block)
            continue
        if block.get("type") == "field" and str(block.get("key") or "") == "site_name":
            if site_kept:
                changed = True
                continue
            site_kept = True
            normalized = {**block, **site_field}
            if normalized != block:
                changed = True
            new_inner.append(normalized)
            continue
        if block.get("type") == "text" and str(block.get("tag") or "") == "h1":
            title_style = dict(DOC_TITLE_TEXT_STYLE)
            if text_align == "center":
                title_style["textAlign"] = "center"
            if (block.get("style") or {}) != title_style:
                block = {**block, "style": title_style}
                changed = True
        new_inner.append(block)

    h1_index = next(
        (
            i
            for i, block in enumerate(new_inner)
            if isinstance(block, dict)
            and block.get("type") == "text"
            and str(block.get("tag") or "") == "h1"
        ),
        None,
    )
    if h1_index is None:
        left_col["blocks"] = new_inner
        return changed

    if not site_kept:
        new_inner.insert(h1_index, site_field)
        changed = True
    else:
        site_index = next(
            i
            for i, block in enumerate(new_inner)
            if isinstance(block, dict)
            and block.get("type") == "field"
            and str(block.get("key") or "") == "site_name"
        )
        if site_index > h1_index:
            site_blk = new_inner.pop(site_index)
            new_inner.insert(h1_index, site_blk)
            changed = True

    left_col["blocks"] = new_inner
    return changed


def patch_print_site_name_header(schema: dict) -> bool:
    """表头站点名布局补丁（并入标题区，不再单独占一行居中）。"""
    return patch_document_header_site_name_layout(schema)


async def upgrade_print_site_name_header(tenant_id: int) -> int:
    """已落地可视化打印模板：表头补站点名并重编译。"""
    from apps.kuaizhizao.print.red_voucher_presets import recompile_designer_schema

    upgraded = 0
    templates = await PrintTemplate.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    ).all()
    for tpl in templates:
        config_raw = tpl.config
        if not isinstance(config_raw, dict):
            continue
        if not is_visual_designer_config(config_raw):
            continue
        schema = config_raw.get("designer_schema")
        if not isinstance(schema, dict):
            continue
        schema_copy = copy.deepcopy(schema)
        if not patch_print_site_name_header(schema_copy):
            continue
        try:
            tpl.content = recompile_designer_schema(schema_copy)
        except Exception as e:
            logger.warning(
                "编译站点名表头打印模板失败 tenant={} code={}: {}",
                tenant_id,
                tpl.code,
                e,
            )
            continue
        next_config = dict(config_raw)
        next_config["designer_schema"] = schema_copy
        tpl.config = next_config
        await tpl.save()
        upgraded += 1
        logger.info(
            "打印模板已补表头站点名 tenant={} code={}",
            tenant_id,
            tpl.code,
        )
    return upgraded


def _payment_application_builtin_preset() -> dict | None:
    code = "PAYMENT_APPLICATION_PRINT"
    for item in KUAIZHIZAO_PRESET_PRINT_TEMPLATES:
        if str(item.get("code") or "").strip().upper() == code:
            return item
    return None


def patch_payment_application_print_line_items(schema: dict) -> bool:
    """付款申请可视化模板补申请明细表（幂等）。"""
    from apps.kuaizhizao.print.designer_presets import (
        _TABLE_COLUMNS,
        _detail_table,
        _section_title,
    )

    blocks = schema.get("blocks")
    if not isinstance(blocks, list):
        return False
    for block in blocks:
        if (
            isinstance(block, dict)
            and block.get("type") == "detail_table"
            and str(block.get("collection") or "") == "items"
        ):
            return False

    insert_at: int | None = None
    for i, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        if block.get("type") == "columns" and i > 0:
            insert_at = i + 1
            break
    if insert_at is None:
        insert_at = min(3, len(blocks))

    blocks.insert(insert_at, _section_title("申请明细"))
    blocks.insert(
        insert_at + 1,
        _detail_table("items", _TABLE_COLUMNS["payment_application"]),
    )
    return True


def patch_payment_application_print_po_detail(schema: dict) -> bool:
    """付款申请可视化模板补采购订单明细表与合计行（幂等）。"""
    from apps.kuaizhizao.print.designer_presets import (
        PRINT_BODY_FONT_SIZE,
        _TABLE_COLUMNS,
        _detail_table,
        _section_title,
        _text,
    )

    blocks = schema.get("blocks")
    if not isinstance(blocks, list):
        return False
    for block in blocks:
        if (
            isinstance(block, dict)
            and block.get("type") == "detail_table"
            and str(block.get("collection") or "") == "purchase_order_items"
        ):
            return False

    items_table_index: int | None = None
    for i, block in enumerate(blocks):
        if (
            isinstance(block, dict)
            and block.get("type") == "detail_table"
            and str(block.get("collection") or "") == "items"
        ):
            items_table_index = i
            break
    if items_table_index is None:
        return False

    changed = False
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            if str(block.get("content") or "").strip() == "明细":
                block["content"] = "申请明细"
                changed = True

    insert_at = items_table_index + 1
    has_total = False
    while insert_at < len(blocks):
        nxt = blocks[insert_at]
        if isinstance(nxt, dict) and nxt.get("type") == "text":
            content = str(nxt.get("content") or "")
            if "total_request_amount" in content:
                has_total = True
                insert_at += 1
                continue
        break

    to_insert: list[dict] = []
    if not has_total:
        to_insert.append(
            _text(
                "合计申请金额：{{ total_request_amount | money }}",
                style={
                    "textAlign": "right",
                    "fontSize": PRINT_BODY_FONT_SIZE,
                    "fontWeight": "600",
                },
            )
        )
        changed = True
    to_insert.extend(
        [
            _section_title("采购订单明细"),
            _detail_table(
                "purchase_order_items",
                _TABLE_COLUMNS["payment_application_po_lines"],
            ),
        ]
    )
    for offset, blk in enumerate(to_insert):
        blocks.insert(insert_at + offset, blk)
    return True if to_insert else changed


def _payment_application_template_needs_visual_preset(
    config_raw: dict,
    content: str,
) -> bool:
    """是否仍为朴素黑白/非可视化付款申请模板。"""
    if str(config_raw.get("theme") or "").strip() == "plain_bw":
        return True
    if not is_visual_designer_config(config_raw):
        return True
    body = (content or "").strip()
    if not body:
        return True
    if "朴素黑白" in body:
        return True
    if "#0f4c81" not in body and "headerBgColor" not in body:
        if "border-bottom: 1px solid #000" in body or ".section-title" in body:
            return True
    return False


async def _apply_payment_application_builtin_preset(tpl, preset: dict) -> None:
    tpl.name = preset["name"]
    tpl.description = preset.get("description")
    tpl.content = preset["content"]
    tpl.config = preset.get("config")
    tpl.is_active = preset.get("is_active", True)
    if preset.get("is_default") is not None:
        tpl.is_default = bool(preset.get("is_default"))
    await tpl.save()


async def upgrade_payment_application_print_template(tenant_id: int) -> int:
    """付款申请：朴素黑白/HTML 预置升级为与其它单据一致的可视化版式。"""
    from apps.kuaizhizao.print.red_voucher_presets import recompile_designer_schema

    preset = _payment_application_builtin_preset()
    if not preset:
        return 0
    templates = await PrintTemplate.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        config__contains={"document_type": "payment_application"},
    ).all()
    if not templates:
        tpl = await PrintTemplate.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            code="PAYMENT_APPLICATION_PRINT",
        ).first()
        templates = [tpl] if tpl else []

    upgraded = 0
    for tpl in templates:
        if not tpl:
            continue
        config_raw = tpl.config if isinstance(tpl.config, dict) else {}
        if _payment_application_template_needs_visual_preset(config_raw, str(tpl.content or "")):
            await _apply_payment_application_builtin_preset(tpl, preset)
            upgraded += 1
            logger.info(
                "付款申请打印模板已升级为可视化 tenant={} code={}",
                tenant_id,
                tpl.code,
            )
            continue

        schema = config_raw.get("designer_schema")
        if not isinstance(schema, dict):
            continue
        schema_copy = copy.deepcopy(schema)
        layout_changed = patch_document_header_site_name_layout(schema_copy)
        line_changed = patch_payment_application_print_line_items(schema_copy)
        po_changed = patch_payment_application_print_po_detail(schema_copy)
        dept_changed = patch_payment_application_print_department_field(schema_copy)
        if not layout_changed and not line_changed and not po_changed and not dept_changed:
            continue
        try:
            tpl.content = recompile_designer_schema(schema_copy)
        except Exception as e:
            logger.warning(
                "编译付款申请打印模板失败 tenant={} code={}: {}",
                tenant_id,
                tpl.code,
                e,
            )
            continue
        next_config = dict(config_raw)
        next_config.pop("theme", None)
        next_config["designer_schema"] = schema_copy
        tpl.config = next_config
        await tpl.save()
        upgraded += 1
        logger.info("付款申请打印模板已更新 tenant={} code={}", tenant_id, tpl.code)
    return upgraded


def patch_print_sign_field_bindings(schema: dict) -> bool:
    """签核栏静态下划线改为绑定采购人/审核人等字段。

    覆盖 seal_overlay 与纯 text（部分存量模板签核行是 text 而非签章叠放）。
    """
    import re

    from apps.kuaizhizao.print.designer_presets import (
        SIGN_LABEL_FIELD_KEYS,
        sign_label_content,
    )

    blank_re = re.compile(
        r"^("
        + "|".join(re.escape(label) for label in SIGN_LABEL_FIELD_KEYS)
        + r")：_{3,}\s*$"
    )
    changed = False

    def visit(block: dict) -> None:
        nonlocal changed
        blk_type = str(block.get("type") or "")
        if blk_type not in ("seal_overlay", "text"):
            return
        content = str(block.get("content") or "").strip()
        if not content or "{{" in content:
            return
        match = blank_re.match(content)
        if not match:
            return
        label = match.group(1)
        next_content = sign_label_content(label)
        if next_content == content:
            return
        block["content"] = next_content
        changed = True

    def walk(blocks: object) -> None:
        if not isinstance(blocks, list):
            return
        for block in blocks:
            if not isinstance(block, dict):
                continue
            visit(block)
            walk(block.get("blocks"))
            cols = block.get("cols")
            if isinstance(cols, list):
                for col in cols:
                    if isinstance(col, dict):
                        walk(col.get("blocks"))

    walk(schema.get("blocks"))
    return changed


async def upgrade_print_sign_field_bindings(tenant_id: int) -> int:
    """已落地可视化打印模板：签核栏绑定采购人/审核人等姓名字段并重编译。"""
    from apps.kuaizhizao.print.red_voucher_presets import recompile_designer_schema

    upgraded = 0
    templates = await PrintTemplate.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    ).all()
    for tpl in templates:
        config_raw = tpl.config
        if not isinstance(config_raw, dict):
            continue
        if not is_visual_designer_config(config_raw):
            continue
        schema = config_raw.get("designer_schema")
        if not isinstance(schema, dict):
            continue
        schema_copy = copy.deepcopy(schema)
        if not patch_print_sign_field_bindings(schema_copy):
            continue
        try:
            tpl.content = recompile_designer_schema(schema_copy)
        except Exception as e:
            logger.warning(
                "编译签核栏打印模板失败 tenant={} code={}: {}",
                tenant_id,
                tpl.code,
                e,
            )
            continue
        next_config = dict(config_raw)
        next_config["designer_schema"] = schema_copy
        tpl.config = next_config
        await tpl.save()
        upgraded += 1
        logger.info("打印模板签核栏已绑定姓名字段 tenant={} code={}", tenant_id, tpl.code)
    return upgraded


def patch_quotation_print_valid_until(schema: dict) -> bool:
    """报价单基本信息补报价有效期。已有 valid_until 时只把旧标题「有效期至」改成「报价有效期」。"""
    changed = False
    found = False

    def walk(blocks: object, *, insert: bool) -> bool:
        nonlocal changed, found
        if not isinstance(blocks, list):
            return False
        for index, block in enumerate(list(blocks)):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "field" and block.get("key") == "valid_until":
                found = True
                if block.get("label") == "有效期至":
                    block["label"] = "报价有效期"
                    changed = True
            if insert and not found and block.get("type") == "field" and block.get("key") == "quotation_date":
                blocks.insert(
                    index + 1,
                    {
                        "id": "fld-quotation-valid-until",
                        "type": "field",
                        "key": "valid_until",
                        "label": "报价有效期",
                        "showLabel": True,
                    },
                )
                found = True
                changed = True
                return True
            if walk(block.get("blocks"), insert=insert):
                return True
            cols = block.get("cols")
            if isinstance(cols, list):
                for col in cols:
                    if isinstance(col, dict) and walk(col.get("blocks"), insert=insert):
                        return True
        return False

    walk(schema.get("blocks"), insert=False)
    if not found:
        walk(schema.get("blocks"), insert=True)
    return changed


async def upgrade_quotation_print_valid_until(tenant_id: int) -> int:
    """已落地的报价单打印模板补报价有效期，并重编译版式。"""
    from apps.kuaizhizao.print.red_voucher_presets import recompile_designer_schema

    upgraded = 0
    templates = await PrintTemplate.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        config__contains={"document_type": "quotation"},
    ).all()
    for tpl in templates:
        config_raw = tpl.config
        if not isinstance(config_raw, dict):
            continue
        schema = config_raw.get("designer_schema")
        if not isinstance(schema, dict):
            continue
        schema_copy = copy.deepcopy(schema)
        if not patch_quotation_print_valid_until(schema_copy):
            continue
        try:
            tpl.content = recompile_designer_schema(schema_copy)
        except Exception as e:
            logger.warning(
                "编译报价单打印模板失败 tenant={} code={}: {}",
                tenant_id,
                tpl.code,
                e,
            )
            continue
        next_config = dict(config_raw)
        next_config["designer_schema"] = schema_copy
        tpl.config = next_config
        await tpl.save()
        upgraded += 1
        logger.info("报价单打印模板已补报价有效期 tenant={} code={}", tenant_id, tpl.code)
    return upgraded


_KINGDEE_PRINT_HEADER_FIELDS: tuple[tuple[str, str], ...] = (
    ("kingdee_bill_no", "金蝶单号"),
)


def patch_kingdee_bill_no_print_schema(schema: dict) -> bool:
    """可视化基本信息补金蝶单号。"""
    return _patch_print_basic_info_fields(
        schema,
        _KINGDEE_PRINT_HEADER_FIELDS,
        field_id_prefix="kd-bill",
    )


def _schema_has_field_key(schema: dict, key: str) -> bool:
    found = False

    def walk(blocks: object) -> None:
        nonlocal found
        if found or not isinstance(blocks, list):
            return
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "field" and str(block.get("key") or "") == key:
                found = True
                return
            walk(block.get("blocks"))
            cols = block.get("cols")
            if isinstance(cols, list):
                for col in cols:
                    if isinstance(col, dict):
                        walk(col.get("blocks"))

    walk(schema.get("blocks"))
    return found


def _schema_has_columns(schema: dict) -> bool:
    found = False

    def walk(blocks: object) -> None:
        nonlocal found
        if found or not isinstance(blocks, list):
            return
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "columns":
                found = True
                return
            walk(block.get("blocks"))

    walk(schema.get("blocks"))
    return found


async def upgrade_kingdee_bill_no_print_fields(tenant_id: int) -> int:
    """外推单据打印模板补金蝶单号：可视化基本信息重编译，整页 HTML 插在明细表前。"""
    from apps.kuaizhizao.print.red_voucher_presets import patch_print_kingdee_bill_no_html
    from apps.kuaizhizao.services.kingdee_push_bill_resolver import (
        KINGDEE_PRINT_SOURCE_TYPES,
    )

    upgraded = 0
    templates = await PrintTemplate.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    ).all()
    for tpl in templates:
        config_raw = tpl.config
        if not isinstance(config_raw, dict):
            continue
        doc_type = str(config_raw.get("document_type") or "").strip()
        if doc_type not in KINGDEE_PRINT_SOURCE_TYPES:
            continue
        content = str(tpl.content or "")
        schema = config_raw.get("designer_schema")
        schema_copy = copy.deepcopy(schema) if isinstance(schema, dict) else None
        columns_changed = False
        if schema_copy is not None:
            columns_changed = patch_kingdee_bill_no_print_schema(schema_copy)
        needs_recompile = columns_changed or (
            schema_copy is not None
            and _schema_has_columns(schema_copy)
            and _schema_has_field_key(schema_copy, "kingdee_bill_no")
            and "kingdee_bill_no" not in content
            and "金蝶单号" not in content
        )
        if needs_recompile and schema_copy is not None:
            try:
                compiled = recompile_designer_schema(schema_copy)
            except Exception as e:
                logger.warning(
                    "编译金蝶单号打印模板失败 tenant={} code={}: {}",
                    tenant_id,
                    tpl.code,
                    e,
                )
                continue
            if not compiled:
                continue
            tpl.content = compiled
            next_config = dict(config_raw)
            next_config["designer_schema"] = schema_copy
            tpl.config = next_config
            await tpl.save()
            upgraded += 1
            logger.info("打印模板已补金蝶单号 tenant={} code={}", tenant_id, tpl.code)
            continue

        next_content, content_changed = patch_print_kingdee_bill_no_html(content)
        schema_changed = False
        if schema_copy is not None:
            blocks = schema_copy.get("blocks")
            if isinstance(blocks, list):
                for blk in blocks:
                    if (
                        isinstance(blk, dict)
                        and blk.get("type") == "text"
                        and isinstance(blk.get("content"), str)
                    ):
                        patched, changed = patch_print_kingdee_bill_no_html(blk["content"])
                        if changed:
                            blk["content"] = patched
                            schema_changed = True
        if not content_changed and not schema_changed:
            continue
        if content_changed:
            tpl.content = next_content
        if schema_changed and schema_copy is not None:
            next_config = dict(config_raw)
            next_config["designer_schema"] = schema_copy
            tpl.config = next_config
        await tpl.save()
        upgraded += 1
        logger.info("打印 HTML 已补金蝶单号 tenant={} code={}", tenant_id, tpl.code)
    return upgraded


async def load_kuaizhizao_print_template_presets(tenant_id: int) -> int:
    """按 code 去重：创建缺失模板；非可视化预置可升级一次。"""
    created = 0
    for item in KUAIZHIZAO_PRESET_PRINT_TEMPLATES:
        base_code = str(item["code"]).strip().upper()
        if await PrintTemplateService.preset_code_family_exists(tenant_id, base_code):
            try:
                if await _upgrade_non_visual_builtin_preset(tenant_id, item):
                    created += 1
            except Exception as e:
                logger.warning("升级快制造打印模板 {} 失败: {}", item["code"], e)
            continue
        try:
            data = PrintTemplateCreate(
                name=item["name"],
                code=item["code"],
                type=item["type"],
                description=item.get("description"),
                content=item["content"],
                config=item.get("config"),
                is_active=item.get("is_active", True),
                is_default=item.get("is_default", False),
            )
            await PrintTemplateService.create_print_template(tenant_id, data)
            created += 1
        except Exception as e:
            logger.warning("创建快制造打印模板 {} 失败: {}", item["code"], e)
    try:
        created += await upgrade_kingdee_bill_no_print_fields(tenant_id)
    except Exception as e:
        logger.warning("升级打印金蝶单号失败 tenant={}: {}", tenant_id, e)
    try:
        created += await upgrade_purchase_receipt_red_voucher_templates(tenant_id)
    except Exception as e:
        logger.warning("升级采购入库红框打印模板失败 tenant={}: {}", tenant_id, e)
    try:
        created += await upgrade_builtin_detail_table_backgrounds(tenant_id)
    except Exception as e:
        logger.warning("升级预置打印明细白底失败 tenant={}: {}", tenant_id, e)
    try:
        created += await upgrade_purchase_requisition_print_line_no(tenant_id)
    except Exception as e:
        logger.warning("升级采购申请打印行号失败 tenant={}: {}", tenant_id, e)
    try:
        created += await upgrade_other_expense_print_detail_columns(tenant_id)
    except Exception as e:
        logger.warning("升级其他费用支出打印明细列序失败 tenant={}: {}", tenant_id, e)
    try:
        created += await upgrade_payment_application_print_template(tenant_id)
    except Exception as e:
        logger.warning("升级付款申请打印模板失败 tenant={}: {}", tenant_id, e)
    try:
        created += await upgrade_purchase_order_print_tax_inclusive_amount(tenant_id)
    except Exception as e:
        logger.warning("升级采购订单打印含税金额失败 tenant={}: {}", tenant_id, e)
    try:
        created += await upgrade_print_site_name_header(tenant_id)
    except Exception as e:
        logger.warning("升级打印表头站点名失败 tenant={}: {}", tenant_id, e)
    try:
        created += await upgrade_print_sign_field_bindings(tenant_id)
    except Exception as e:
        logger.warning("升级打印签核栏姓名绑定失败 tenant={}: {}", tenant_id, e)
    try:
        created += await upgrade_quotation_print_valid_until(tenant_id)
    except Exception as e:
        logger.warning("升级报价单打印有效期失败 tenant={}: {}", tenant_id, e)
    try:
        created += await upgrade_print_numeric_column_precision(tenant_id)
    except Exception as e:
        logger.warning("升级打印单价金额小数位失败 tenant={}: {}", tenant_id, e)
    return created
