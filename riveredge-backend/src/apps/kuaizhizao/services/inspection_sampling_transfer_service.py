"""
GB/T 2828.1 跨批严格度转移 + 检验模板 resolved_sampling
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from apps.kuaizhizao.models.inspection_sampling_transfer import InspectionSamplingTransferState
from apps.kuaizhizao.services.gb2828_sampling import STRICTNESS_VALUES
from apps.kuaizhizao.services.inspection_step_spec import (
    normalize_sampling_spec,
    resolve_effective_sampling_spec,
)


def _verdict_token(lot_accepted: bool) -> str:
    return "accept" if lot_accepted else "reject"


def _compute_next_strictness(
    current: str,
    lot_accepted: bool,
    consecutive_accept: int,
    consecutive_reject: int,
    recent: List[str],
) -> tuple[str, int, int, List[str]]:
    """简化转移规则（一次抽样表配套）。"""
    token = _verdict_token(lot_accepted)
    recent = list(recent or [])
    recent.append(token)
    recent = recent[-5:]
    if lot_accepted:
        consecutive_accept += 1
        consecutive_reject = 0
    else:
        consecutive_reject += 1
        consecutive_accept = 0

    strict = current if current in STRICTNESS_VALUES else "normal"
    reject_in_last5 = sum(1 for v in recent if v == "reject")

    if strict == "normal":
        if reject_in_last5 >= 2:
            strict = "tightened"
            consecutive_accept = 0
            consecutive_reject = 0
            recent = []
        elif consecutive_accept >= 10:
            strict = "reduced"
            consecutive_accept = 0
            consecutive_reject = 0
            recent = []
    elif strict == "tightened":
        if consecutive_accept >= 5:
            strict = "normal"
            consecutive_accept = 0
            consecutive_reject = 0
            recent = []
        elif consecutive_reject >= 5:
            strict = "normal"
            consecutive_accept = 0
            consecutive_reject = 0
            recent = []
    elif strict == "reduced":
        if consecutive_reject >= 2:
            strict = "normal"
            consecutive_accept = 0
            consecutive_reject = 0
            recent = []

    return strict, consecutive_accept, consecutive_reject, recent


async def get_transfer_strictness(
    tenant_id: int,
    material_id: int,
    plan_id: int,
    step_key: str,
    *,
    configured_strictness: str,
    transfer_enabled: bool,
) -> str:
    if not transfer_enabled:
        return configured_strictness
    row = await InspectionSamplingTransferState.get_or_none(
        tenant_id=tenant_id,
        material_id=material_id,
        plan_id=plan_id,
        step_key=step_key,
    )
    if row and row.strictness in STRICTNESS_VALUES:
        return str(row.strictness)
    return configured_strictness


async def update_transfer_after_lot_close(
    tenant_id: int,
    material_id: int,
    plan_id: int,
    step_key: str,
    *,
    lot_accepted: bool,
    configured_strictness: str,
    transfer_enabled: bool,
) -> None:
    if not transfer_enabled:
        return
    row = await InspectionSamplingTransferState.get_or_none(
        tenant_id=tenant_id,
        material_id=material_id,
        plan_id=plan_id,
        step_key=step_key,
    )
    if not row:
        row = await InspectionSamplingTransferState.create(
            tenant_id=tenant_id,
            material_id=material_id,
            plan_id=plan_id,
            step_key=step_key,
            strictness=configured_strictness if configured_strictness in STRICTNESS_VALUES else "normal",
            recent_lot_verdicts=[],
            consecutive_accept=0,
            consecutive_reject=0,
        )
    current = str(row.strictness or configured_strictness or "normal")
    strict, ca, cr, recent = _compute_next_strictness(
        current,
        lot_accepted,
        int(row.consecutive_accept or 0),
        int(row.consecutive_reject or 0),
        list(row.recent_lot_verdicts or []),
    )
    row.strictness = strict
    row.consecutive_accept = ca
    row.consecutive_reject = cr
    row.recent_lot_verdicts = recent
    await row.save()


async def enrich_template_payload_resolved_sampling(
    tenant_id: int,
    material_id: Optional[int],
    template_payload: Any,
    lot_quantity: Any,
) -> Any:
    if not isinstance(template_payload, dict):
        return template_payload
    items = template_payload.get("items")
    if not isinstance(items, list):
        return template_payload
    plan_id = template_payload.get("plan_id")
    if not plan_id:
        return template_payload
    try:
        lot = float(lot_quantity)
    except (TypeError, ValueError):
        return template_payload
    if lot <= 0:
        return template_payload

    new_items: List[Dict[str, Any]] = []
    changed = False
    for raw in items:
        if not isinstance(raw, dict):
            new_items.append(raw)
            continue
        item = dict(raw)
        if item.get("sampling_type") != "sampling":
            new_items.append(item)
            continue
        spec = item.get("value_spec") if isinstance(item.get("value_spec"), dict) else {}
        sampling = normalize_sampling_spec(spec.get("sampling"))
        if sampling.get("mode") != "gb2828_single":
            new_items.append(item)
            continue
        strictness = str(sampling.get("strictness") or "normal")
        if sampling.get("transfer_enabled") and material_id:
            strictness = await get_transfer_strictness(
                tenant_id,
                int(material_id),
                int(plan_id),
                str(item.get("step_key") or ""),
                configured_strictness=strictness,
                transfer_enabled=True,
            )
        resolved = resolve_effective_sampling_spec(
            sampling,
            lot,
            strictness_override=strictness,
        )
        item["resolved_sampling"] = {
            "mode": "gb2828_single",
            "sample_size": resolved.get("sample_size"),
            "accept_num": resolved.get("accept_num"),
            "reject_num": resolved.get("reject_num"),
            "strictness": strictness,
            "level": sampling.get("level"),
            "aql": sampling.get("aql"),
            "transfer_enabled": bool(sampling.get("transfer_enabled")),
            "gb2828": resolved.get("resolved_gb2828"),
            "label": resolved.get("resolved_label"),
        }
        changed = True
        new_items.append(item)

    if not changed:
        return template_payload
    out = dict(template_payload)
    out["items"] = new_items
    return out


async def apply_sampling_transfers_for_template(
    tenant_id: int,
    material_id: Optional[int],
    template_payload: Any,
    *,
    lot_accepted: bool,
) -> None:
    if not material_id or not isinstance(template_payload, dict):
        return
    plan_id = template_payload.get("plan_id")
    if not plan_id:
        return
    items = template_payload.get("items")
    if not isinstance(items, list):
        return
    for raw in items:
        if not isinstance(raw, dict) or raw.get("sampling_type") != "sampling":
            continue
        spec = raw.get("value_spec") if isinstance(raw.get("value_spec"), dict) else {}
        sampling = normalize_sampling_spec(spec.get("sampling"))
        if sampling.get("mode") != "gb2828_single" or not sampling.get("transfer_enabled"):
            continue
        step_key = str(raw.get("step_key") or "")
        if not step_key:
            continue
        await update_transfer_after_lot_close(
            tenant_id,
            int(material_id),
            int(plan_id),
            step_key,
            lot_accepted=lot_accepted,
            configured_strictness=str(sampling.get("strictness") or "normal"),
            transfer_enabled=True,
        )
