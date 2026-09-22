"""单据数据修正（造数/演示）：工单时间链、采购单价、登录地点。

与「时间修正」同权限族；不改 updated_at；工作时段取自请求中的 WorkScheduleParams。
"""

from __future__ import annotations

import random
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from core.services.document_time_rewrite_service import WorkScheduleParams
from core.utils.timezone_utils import resolve_business_datetime, site_timezone_name


def _as_utc(dt: datetime) -> datetime:
    return resolve_business_datetime(dt)


def _to_site(dt: datetime | None, tz: ZoneInfo) -> datetime | None:
    if dt is None:
        return None
    return _as_utc(dt).astimezone(tz)


def _to_utc(site_dt: datetime) -> datetime:
    return site_dt.astimezone(timezone.utc)


def _window_last(start: datetime, end: datetime) -> datetime:
    """工作窗 [start, end) 的最后合法秒。"""
    last = end - timedelta(seconds=1)
    return last if last >= start else start


def _clamp_forward(when_site: datetime, schedule: WorkScheduleParams) -> datetime:
    """保证落在工作时段内；过晚则推到下一工作日上班时刻。"""
    if when_site.tzinfo is None:
        raise ValueError("when_site 必须是带时区的站点墙钟时刻")
    tz = ZoneInfo(str(when_site.tzinfo))
    cur = when_site.replace(microsecond=0)
    day = cur.date()
    for _ in range(400):
        window = schedule.window_on(day, tz)
        if window is None:
            day += timedelta(days=1)
            continue
        start, end = window
        last = _window_last(start, end)
        if cur.date() < day:
            return start
        if cur < start:
            return start
        if cur > last:
            day += timedelta(days=1)
            cur = datetime(day.year, day.month, day.day, tzinfo=tz)
            continue
        return cur
    raise ValueError("找不到可用工作时段，请检查工作日与上下班时间")


def _add_work_minutes(
    when_site: datetime,
    minutes: float,
    schedule: WorkScheduleParams,
) -> datetime:
    """在工作时段内累加分钟（可跨工作日）。"""
    remain = max(0.0, float(minutes))
    cur = _clamp_forward(when_site, schedule)
    tz = ZoneInfo(str(cur.tzinfo))
    for _ in range(800):
        if remain <= 0:
            return cur
        window = schedule.window_on(cur.date(), tz)
        if window is None:
            cur = _clamp_forward(
                datetime(cur.year, cur.month, cur.day, tzinfo=tz) + timedelta(days=1),
                schedule,
            )
            continue
        start, end = window
        last = _window_last(start, end)
        if cur < start:
            cur = start
        available_sec = (last - cur).total_seconds()
        need_sec = remain * 60.0
        if need_sec <= available_sec:
            return cur + timedelta(seconds=need_sec)
        remain -= available_sec / 60.0
        nxt = cur.date() + timedelta(days=1)
        cur = _clamp_forward(datetime(nxt.year, nxt.month, nxt.day, tzinfo=tz), schedule)
    raise ValueError("累加工作分钟失败")


def _random_clock_on(
    day: date,
    schedule: WorkScheduleParams,
    tz: ZoneInfo,
    rng: random.Random,
) -> datetime:
    d = day
    for _ in range(400):
        window = schedule.window_on(d, tz)
        if window is None:
            d += timedelta(days=1)
            continue
        start, end = window
        last = _window_last(start, end)
        span = max(0, int((last - start).total_seconds()))
        return start + timedelta(seconds=rng.randint(0, span))
    raise ValueError("找不到可用工作日")


def _offset_minutes_clamped(
    anchor: datetime,
    offset_min: int,
    schedule: WorkScheduleParams,
) -> datetime:
    return _clamp_forward(anchor + timedelta(minutes=offset_min), schedule)


# 物料名关键词 → 基准单价（通用估价，非客户定制）
_PRICE_RULES: tuple[tuple[str, Decimal], ...] = (
    (r"西门子.*(?:PLC|控制器|S7)|(?:PLC|控制器|S7).*西门子", Decimal("3280")),
    (r"PLC", Decimal("2100")),
    (r"HMI|人机界面", Decimal("1280")),
    (r"变频器", Decimal("2680")),
    (r"软启动", Decimal("980")),
    (r"电源冗余", Decimal("360")),
    (r"开关电源", Decimal("165")),
    (r"物联网", Decimal("420")),
    (r"交换机", Decimal("320")),
    (r"光纤", Decimal("185")),
    (r"温控", Decimal("128")),
    (r"风扇", Decimal("48")),
    (r"照明", Decimal("36")),
    (r"插座", Decimal("12")),
    (r"端子", Decimal("1.60")),
    (r"热继电器", Decimal("42")),
    (r"继电器", Decimal("22")),
    (r"微型断路器", Decimal("18")),
    (r"塑壳|回路断路器|断路器", Decimal("145")),
    (r"接触器", Decimal("78")),
    (r"主线缆", Decimal("36")),
    (r"控制线缆", Decimal("6.50")),
    (r"电缆|电线", Decimal("6.80")),
    (r"壳体", Decimal("1280")),
    (r"脉冲控制", Decimal("860")),
    (r"PH", Decimal("280")),
    (r"传感器", Decimal("95")),
    (r"316L", Decimal("18500")),  # 吨级，千克另除
    (r"Q235|钢板|槽钢|角铁|花纹板|焊管|扁铁|碳钢|钢材", Decimal("4250")),
    (r"不锈钢", Decimal("260")),
    (r"法兰DN500", Decimal("680")),
    (r"法兰DN200", Decimal("185")),
    (r"法兰DN", Decimal("48")),
    (r"法兰三角", Decimal("62")),
    (r"法兰", Decimal("86")),
    (r"盲板DN500", Decimal("420")),
    (r"盲板", Decimal("95")),
    (r"弯头", Decimal("14")),
    (r"喷嘴", Decimal("165")),
    (r"熟焦", Decimal("1680")),
    (r"生焦", Decimal("1450")),
    (r"白泥", Decimal("420")),
    (r"长石", Decimal("320")),
    (r"莱阳土", Decimal("240")),
    (r"保温板|防火保温|微塑板", Decimal("68")),
    (r"砌块", Decimal("220")),
    (r"砂浆", Decimal("420")),
    (r"减水剂", Decimal("6.80")),
    (r"水泥", Decimal("24")),
    (r"北铝|山铝|中州|HMF|HWF|HID|湿氢|ATH|改性剂", Decimal("2450")),
    (r"三相异步|电动机", Decimal("980")),
    (r"减速机", Decimal("680")),
    (r"油缸", Decimal("680")),
    (r"工业遥控器", Decimal("380")),
    (r"联轴器", Decimal("85")),
    (r"轴承", Decimal("85")),
    (r"主材", Decimal("1860")),
    (r"牛腿", Decimal("420")),
    (r"地脚板", Decimal("186")),
    (r"顶板", Decimal("128")),
    (r"筋板", Decimal("48")),
    (r"柱脚筋", Decimal("36")),
    (r"顶托|墙檩托|角托|檩托", Decimal("85")),
    (r"系杆板", Decimal("38")),
    (r"封头", Decimal("95")),
    (r"隅撑", Decimal("42")),
    (r"抗风柱|女儿墙", Decimal("78")),
    (r"提升机护板", Decimal("185")),
    (r"内衬板", Decimal("96")),
    (r"菱形网", Decimal("78")),
    (r"钢格板", Decimal("165")),
    (r"镀锌", Decimal("420")),
    (r"黑铁", Decimal("280")),
    (r"畚斗带", Decimal("18")),
    (r"畚斗", Decimal("12")),
    (r"链条", Decimal("28")),
    (r"链轮", Decimal("78")),
    (r"螺栓|螺母|螺钉|垫圈|开口销", Decimal("1.60")),
    (r"纸袋|吨包|内衬|HF-", Decimal("2.20")),
    (r"托盘", Decimal("28")),
    (r"槽钢", Decimal("138")),
    (r"角钢", Decimal("42")),
    (r"方管", Decimal("52")),
    (r"冷轧", Decimal("186")),
)

_KG_TON_NAME = re.compile(r"泥|土|长石|焦|北铝|山铝|中州|湿氢")
_KG_UNIT = re.compile(r"千克|公斤|^kg$|^KG$", re.I)
_TON_UNIT = re.compile(r"吨")
_SHEET_UNIT = re.compile(r"张")


def estimate_unit_price(material_name: str, unit: str) -> Decimal:
    """按物料名+单位估基准单价。"""
    name = (material_name or "").strip()
    uu = (unit or "").strip()
    # 带单位条件的规则优先（与手工 SQL 一致）
    if re.search(r"316L", name) and _TON_UNIT.search(uu):
        price = Decimal("18500")
    elif re.search(r"Q235|钢板|槽钢|角铁|花纹板|焊管|扁铁|碳钢|钢材", name) and _TON_UNIT.search(
        uu
    ):
        price = Decimal("4250")
    elif re.search(r"不锈钢", name) and _KG_UNIT.search(uu):
        price = Decimal("22")
    elif re.search(r"镀锌", name) and _SHEET_UNIT.search(uu):
        price = Decimal("420")
    elif re.search(r"黑铁", name) and _SHEET_UNIT.search(uu):
        price = Decimal("280")
    else:
        price = Decimal("86")
        for pattern, base in _PRICE_RULES:
            if re.search(pattern, name):
                price = base
                break

    if _KG_UNIT.search(uu) and _KG_TON_NAME.search(name):
        price = (price / Decimal("1000")).quantize(Decimal("0.0001"))
    return price


class DocumentDataPolishService:
    """演示数据修正：工单时间 / 采购单价 / 登录地点。"""

    @staticmethod
    async def rewrite_login_locations(
        *,
        tenant_id: int,
        location: str,
    ) -> dict[str, Any]:
        from core.models.login_log import LoginLog

        text = (location or "").strip()
        if not text:
            raise ValueError("登录地点不能为空")
        if len(text) > 200:
            raise ValueError("登录地点最多 200 字")

        qs = LoginLog.filter(tenant_id=tenant_id)
        total = await qs.count()
        updated = await qs.exclude(login_location=text).update(login_location=text)
        return {
            "updated": int(updated),
            "total": int(total),
            "location": text,
        }

    @staticmethod
    async def polish_work_order_times(
        *,
        tenant_id: int,
        work_order_ids: list[int],
        schedule: WorkScheduleParams,
        include_header: bool = True,
        include_operations: bool = True,
        include_reporting: bool = True,
        seed: int | None = None,
    ) -> dict[str, Any]:
        from apps.kuaizhizao.models.reporting_record import ReportingRecord
        from apps.kuaizhizao.models.work_order import WorkOrder
        from apps.kuaizhizao.models.work_order_operation import WorkOrderOperation

        schedule.validate()
        ids = [int(i) for i in work_order_ids]
        if not ids:
            raise ValueError("未选择工单")
        if not (include_header or include_operations or include_reporting):
            raise ValueError("至少勾选一项：头表 / 工序 / 报工")

        tz = ZoneInfo(site_timezone_name())
        rng = random.Random(seed if seed is not None else (tenant_id * 100003 + len(ids)))

        header_n = 0
        op_n = 0
        rr_n = 0
        failed = 0
        errors: list[str] = []

        for wo_id in ids:
            try:
                wo = await WorkOrder.get_or_none(tenant_id=tenant_id, id=wo_id)
                if not wo:
                    raise ValueError(f"工单不存在: {wo_id}")

                planned_start_site = _to_site(wo.planned_start_date, tz)
                if planned_start_site is None:
                    raise ValueError(f"工单 {getattr(wo, 'code', wo_id)} 无计划开始时间")

                new_ps = planned_start_site
                new_pe = _to_site(wo.planned_end_date, tz)
                new_as = _to_site(wo.actual_start_date, tz)
                new_ae = _to_site(wo.actual_end_date, tz)

                if include_header:
                    new_ps = _clamp_forward(planned_start_site, schedule)
                    pe_day = new_ps.date() + timedelta(days=rng.randint(2, 4))
                    new_pe = _random_clock_on(pe_day, schedule, tz, rng)
                    if new_pe <= new_ps:
                        new_pe = _add_work_minutes(new_ps, rng.randint(240, 480), schedule)

                    if new_ae is not None and new_as is None:
                        new_as = _offset_minutes_clamped(
                            new_ps, rng.randint(-28, 28), schedule
                        )
                    elif new_as is not None:
                        new_as = _offset_minutes_clamped(
                            new_ps, rng.randint(-28, 28), schedule
                        )
                    if new_ae is not None:
                        new_ae = _offset_minutes_clamped(
                            new_pe, rng.randint(-28, 28), schedule
                        )
                        if new_as is not None and new_ae <= new_as:
                            new_ae = _add_work_minutes(new_as, rng.randint(60, 240), schedule)

                    payload: dict[str, Any] = {
                        "planned_start_date": _to_utc(new_ps),
                        "planned_end_date": _to_utc(new_pe),
                    }
                    if new_as is not None:
                        payload["actual_start_date"] = _to_utc(new_as)
                    if new_ae is not None:
                        payload["actual_end_date"] = _to_utc(new_ae)
                    await WorkOrder.filter(tenant_id=tenant_id, id=wo_id).update(**payload)
                    header_n += 1

                ops = (
                    await WorkOrderOperation.filter(tenant_id=tenant_id, work_order_id=wo_id)
                    .order_by("sequence")
                    .all()
                )
                op_actual_map: dict[int, tuple[datetime | None, datetime | None]] = {}
                op_plan_map: dict[int, tuple[datetime, datetime]] = {}

                if include_operations and ops:
                    cursor = new_ps if include_header else _clamp_forward(planned_start_site, schedule)
                    used_starts: set[datetime] = set()
                    for op in ops:
                        dur = float(rng.randint(34, 80))
                        if rng.random() < 0.12:
                            dur += float(rng.randint(20, 55))
                        gap = float(rng.randint(3, 37))
                        ps = cursor
                        for _ in range(20):
                            if ps not in used_starts:
                                break
                            ps = _add_work_minutes(ps, float(rng.randint(1, 5)), schedule)
                        used_starts.add(ps)
                        pe = _add_work_minutes(ps, dur, schedule)
                        op_plan_map[int(op.id)] = (ps, pe)

                        had_actual = op.actual_start_date is not None or op.actual_end_date is not None
                        as_s: datetime | None = None
                        ae_s: datetime | None = None
                        if had_actual:
                            as_s = _offset_minutes_clamped(ps, rng.randint(-12, 18), schedule)
                            for _ in range(20):
                                if as_s not in used_starts:
                                    break
                                as_s = _add_work_minutes(as_s, float(rng.randint(1, 4)), schedule)
                            used_starts.add(as_s)
                            ae_s = _add_work_minutes(as_s, dur + float(rng.randint(-6, 12)), schedule)
                            if ae_s <= as_s:
                                ae_s = _add_work_minutes(as_s, max(20.0, dur), schedule)
                        op_actual_map[int(op.id)] = (as_s, ae_s)

                        op_payload: dict[str, Any] = {
                            "planned_start_date": _to_utc(ps),
                            "planned_end_date": _to_utc(pe),
                        }
                        if as_s is not None:
                            op_payload["actual_start_date"] = _to_utc(as_s)
                        if ae_s is not None:
                            op_payload["actual_end_date"] = _to_utc(ae_s)
                        await WorkOrderOperation.filter(
                            tenant_id=tenant_id, id=int(op.id)
                        ).update(**op_payload)
                        op_n += 1
                        cursor = _add_work_minutes(pe, gap, schedule)

                    # 末道尽量贴近工单结束
                    if include_header and new_pe is not None and ops:
                        last = ops[-1]
                        last_ps, last_pe = op_plan_map[int(last.id)]
                        if last_pe < new_pe - timedelta(hours=4):
                            tip = _add_work_minutes(new_pe, -float(rng.randint(40, 120)), schedule)
                            if tip > last_ps:
                                await WorkOrderOperation.filter(
                                    tenant_id=tenant_id, id=int(last.id)
                                ).update(planned_end_date=_to_utc(tip))
                                op_plan_map[int(last.id)] = (last_ps, tip)
                                as_s, ae_s = op_actual_map.get(int(last.id), (None, None))
                                if ae_s is not None and as_s is not None:
                                    tip_a = _add_work_minutes(
                                        tip, float(rng.randint(-15, 20)), schedule
                                    )
                                    if tip_a > as_s:
                                        await WorkOrderOperation.filter(
                                            tenant_id=tenant_id, id=int(last.id)
                                        ).update(actual_end_date=_to_utc(tip_a))
                                        op_actual_map[int(last.id)] = (as_s, tip_a)

                if include_reporting:
                    if not ops:
                        ops = (
                            await WorkOrderOperation.filter(
                                tenant_id=tenant_id, work_order_id=wo_id
                            )
                            .order_by("sequence")
                            .all()
                        )
                    if not op_plan_map and ops:
                        for op in ops:
                            ps = _to_site(op.planned_start_date, tz)
                            pe = _to_site(op.planned_end_date, tz)
                            if ps and pe:
                                op_plan_map[int(op.id)] = (ps, pe)
                            as_s = _to_site(op.actual_start_date, tz)
                            ae_s = _to_site(op.actual_end_date, tz)
                            op_actual_map[int(op.id)] = (as_s, ae_s)

                    # operation_id 在报工里可能是主数据工序 ID；优先按 operation 行匹配
                    records = await ReportingRecord.filter(
                        tenant_id=tenant_id, work_order_id=wo_id
                    ).all()
                    reported_used: set[datetime] = set()
                    ops_by_name = {(o.operation_name or "").strip(): o for o in ops}

                    for rr in records:
                        op = None
                        name = (rr.operation_name or "").strip()
                        if name and name in ops_by_name:
                            op = ops_by_name[name]
                        if op is None:
                            # 按 sequence 近似：报工条数与工序同序时靠 id 顺序不可靠，退回名称
                            for o in ops:
                                if int(o.operation_id or 0) == int(rr.operation_id or -1):
                                    op = o
                                    break
                        if op is None and ops:
                            # 无法匹配则按条序轮转
                            op = ops[int(rr.id) % len(ops)]

                        oid = int(op.id)
                        as_s, ae_s = op_actual_map.get(oid, (None, None))
                        ps, pe = op_plan_map.get(oid, (None, None))  # type: ignore[assignment]
                        start = as_s or ps
                        end = ae_s or pe
                        if start is None or end is None:
                            continue
                        reported = _add_work_minutes(end, float(rng.randint(6, 28)), schedule)
                        for _ in range(30):
                            if reported not in reported_used:
                                break
                            reported = _add_work_minutes(
                                reported, float(rng.randint(1, 5)), schedule
                            )
                        reported_used.add(reported)
                        approved = None
                        if rr.approved_at is not None or (rr.status or "") == "approved":
                            approved = _add_work_minutes(
                                reported, float(rng.randint(5, 28)), schedule
                            )
                        rr_payload: dict[str, Any] = {
                            "work_start_time": _to_utc(start),
                            "work_end_time": _to_utc(end),
                            "reported_at": _to_utc(reported),
                        }
                        if approved is not None:
                            rr_payload["approved_at"] = _to_utc(approved)
                        await ReportingRecord.filter(tenant_id=tenant_id, id=int(rr.id)).update(
                            **rr_payload
                        )
                        rr_n += 1
            except Exception as exc:  # noqa: BLE001 — 汇总到结果，不中断整批
                failed += 1
                errors.append(f"WO#{wo_id}: {exc}")

        return {
            "work_orders": len(ids),
            "header_updated": header_n,
            "operations_updated": op_n,
            "reporting_updated": rr_n,
            "failed": failed,
            "errors": errors[:50],
            "timezone": site_timezone_name(),
        }

    @staticmethod
    async def polish_purchase_prices(
        *,
        tenant_id: int,
        purchase_order_ids: list[int],
        seed: int | None = None,
    ) -> dict[str, Any]:
        """修正采购单价并同步入库 + 应付（PO + 入库 + 应付）。"""
        from apps.kuaicaiwu.models.payable import Payable
        from apps.kuaizhizao.models.purchase_order import PurchaseOrder, PurchaseOrderItem
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
        from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem

        ids = [int(i) for i in purchase_order_ids]
        if not ids:
            raise ValueError("未选择采购订单")

        rng = random.Random(seed if seed is not None else (tenant_id * 100019 + len(ids)))

        items = await PurchaseOrderItem.filter(
            tenant_id=tenant_id, order_id__in=ids, deleted_at=None
        ).all()
        item_price: dict[int, Decimal] = {}
        lines_updated = 0
        for item in items:
            base = estimate_unit_price(str(item.material_name or ""), str(item.unit or ""))
            factor = Decimal(str(round(0.90 + rng.random() * 0.20, 6)))
            up = (base * factor).quantize(Decimal("0.0001"))
            qty = Decimal(str(item.ordered_quantity or 0))
            total = (qty * up).quantize(Decimal("0.01"))
            await PurchaseOrderItem.filter(tenant_id=tenant_id, id=int(item.id)).update(
                unit_price=up,
                total_price=total,
            )
            item_price[int(item.id)] = up
            lines_updated += 1

        orders_updated = 0
        for po_id in ids:
            po = await PurchaseOrder.get_or_none(tenant_id=tenant_id, id=po_id, deleted_at=None)
            if not po:
                continue
            po_items = await PurchaseOrderItem.filter(
                tenant_id=tenant_id, order_id=po_id, deleted_at=None
            ).all()
            amt = sum((Decimal(str(i.total_price or 0)) for i in po_items), Decimal("0")).quantize(
                Decimal("0.01")
            )
            rate = Decimal(str(po.tax_rate or 0))
            if rate == 0:
                net, tax = amt, Decimal("0")
            else:
                tax = (amt * rate / (Decimal("100") + rate)).quantize(Decimal("0.01"))
                net = (amt - tax).quantize(Decimal("0.01"))
            await PurchaseOrder.filter(tenant_id=tenant_id, id=po_id).update(
                total_amount=amt,
                net_amount=net,
                tax_amount=tax,
            )
            orders_updated += 1

        receipts = await PurchaseReceipt.filter(
            tenant_id=tenant_id, purchase_order_id__in=ids, deleted_at=None
        ).all()
        old_receipt_amt = {int(r.id): Decimal(str(r.total_amount or 0)) for r in receipts}
        receipt_codes = {int(r.id): str(r.receipt_code or "") for r in receipts}

        receipt_items_updated = 0
        for ri in await PurchaseReceiptItem.filter(
            tenant_id=tenant_id,
            receipt_id__in=list(old_receipt_amt.keys()) or [-1],
            deleted_at=None,
        ).all():
            up = item_price.get(int(ri.purchase_order_item_id or 0))
            if up is None:
                continue
            qty = Decimal(str(ri.receipt_quantity or 0))
            await PurchaseReceiptItem.filter(tenant_id=tenant_id, id=int(ri.id)).update(
                unit_price=up,
                total_amount=(qty * up).quantize(Decimal("0.01")),
            )
            receipt_items_updated += 1

        receipts_updated = 0
        new_receipt_amt: dict[int, Decimal] = {}
        for rid in old_receipt_amt:
            rows = await PurchaseReceiptItem.filter(
                tenant_id=tenant_id, receipt_id=rid, deleted_at=None
            ).all()
            amt = sum((Decimal(str(r.total_amount or 0)) for r in rows), Decimal("0")).quantize(
                Decimal("0.01")
            )
            await PurchaseReceipt.filter(tenant_id=tenant_id, id=rid).update(total_amount=amt)
            new_receipt_amt[rid] = amt
            receipts_updated += 1

        payables_updated = 0
        po_codes = {
            int(p.id): str(p.order_code or "")
            for p in await PurchaseOrder.filter(tenant_id=tenant_id, id__in=ids).all()
        }
        payables = await Payable.filter(tenant_id=tenant_id, deleted_at=None).all()
        for py in payables:
            matched_amt: Decimal | None = None
            st = str(py.source_type or "").strip().lower()
            sid = int(py.source_id or 0)
            scode = str(py.source_code or "").strip()

            for rid, code in receipt_codes.items():
                if sid == rid or (code and scode == code):
                    matched_amt = new_receipt_amt.get(rid)
                    break
                old = old_receipt_amt.get(rid)
                if (
                    matched_amt is None
                    and old
                    and old > 0
                    and Decimal(str(py.total_amount or 0)) == old
                    and sum(1 for a in old_receipt_amt.values() if a == old) == 1
                ):
                    matched_amt = new_receipt_amt.get(rid)
                    break

            if matched_amt is None:
                for po_id, code in po_codes.items():
                    if ("purchase_order" in st or st in {"采购订单", "po"}) and (
                        sid == po_id or (code and scode == code)
                    ):
                        po = await PurchaseOrder.get_or_none(tenant_id=tenant_id, id=po_id)
                        if po:
                            matched_amt = Decimal(str(po.total_amount or 0))
                        break

            if matched_amt is None:
                continue

            paid = Decimal(str(py.paid_amount or 0))
            total = Decimal(str(py.total_amount or 0))
            remaining = Decimal(str(py.remaining_amount or 0))
            if remaining == 0 and paid == total:
                new_paid, new_rem = matched_amt, Decimal("0")
            else:
                new_paid = min(paid, matched_amt)
                new_rem = max(matched_amt - new_paid, Decimal("0"))
            await Payable.filter(tenant_id=tenant_id, id=int(py.id)).update(
                total_amount=matched_amt,
                paid_amount=new_paid,
                remaining_amount=new_rem,
            )
            payables_updated += 1

        return {
            "purchase_orders": orders_updated,
            "order_lines": lines_updated,
            "receipts": receipts_updated,
            "receipt_lines": receipt_items_updated,
            "payables": payables_updated,
        }
