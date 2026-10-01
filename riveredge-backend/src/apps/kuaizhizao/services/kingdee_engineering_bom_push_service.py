"""业务适配：工程 BOM → 金蝶工程 BOM（ENG_BOM）。

source_id = 版本组内最小 BOM 行 id（与 list_bom_groups 的 id 对齐）。
"""

from __future__ import annotations

import copy
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger

from apps.kuaizhizao.models.document_relation import DocumentRelation
from apps.master_data.models.material import BOM, Material
from core.services.integration.document_push_mapping import apply_field_map, set_path
from core.services.integration.document_push_pipeline import (
    DocumentPushPipeline,
    DocumentPushPrepared,
    DocumentPushRequest,
)
from core.utils.timezone_utils import to_api_isoformat
from infra.exceptions.exceptions import BusinessLogicError
from infra.services.business_config_service import BusinessConfigService

DEFAULT_FORM_ID = "ENG_BOM"
TARGET_TYPE = "kingdee_eng_bom"
TARGET_PROFILE = "kingdee_eng_bom"
SOURCE_TYPE = "engineering_bom"
PUSH_DISABLED_MESSAGE = "金蝶工程BOM推送未启用"


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def engineering_bom_push_skip_reason(
    lines: List[BOM],
    *,
    parent_code: Optional[str] = None,
    already_pushed: bool = False,
) -> Optional[str]:
    if already_pushed:
        return "已推送过金蝶工程BOM"
    if not lines:
        return "BOM无明细行"
    if any(getattr(line, "external_sync_at", None) is not None for line in lines):
        return "金蝶拉取导入的BOM不可回推"
    status = str(getattr(lines[0], "approval_status", None) or "").strip().lower()
    if status and status not in {"approved", "audited"}:
        return f"BOM审核状态 {status} 不可推送"
    if not str(parent_code or "").strip():
        return "缺少父件物料编码"
    return None


def build_kingdee_eng_bom_model(
    *,
    parent_code: str,
    lines: List[BOM],
    component_codes: Dict[int, str],
    bom_code: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    config = cfg or {}
    template = config.get("model_template")
    if isinstance(template, dict) and template:
        model = copy.deepcopy(template)
    else:
        model = {"FID": 0, "FTreeEntity": []}

    model["FMATERIALID"] = {"FNumber": parent_code}
    if bom_code:
        model["FNumber"] = bom_code
    version = str(getattr(lines[0], "version", None) or "1.0").strip() or "1.0"
    model["FBomVersion"] = version

    entities: List[Dict[str, Any]] = []
    for line in lines:
        child = component_codes.get(int(line.component_id))
        if not child:
            continue
        entities.append(
            {
                "FMATERIALIDCHILD": {"FNumber": child},
                "FNUMERATOR": _to_float(line.quantity),
                "FDENOMINATOR": _to_float(getattr(line, "base_quantity", None) or 1) or 1.0,
            }
        )
    model["FTreeEntity"] = entities

    default_field_map = {
        "create_org_number": "FCreateOrgId.FNumber",
        "use_org_number": "FUseOrgId.FNumber",
    }

    def local_value(key: str) -> Any:
        if key in ("create_org_number", "use_org_number"):
            return config.get(key) or config.get("org_number")
        return None

    apply_field_map(model, default_field_map, local_value)
    fixed_values = config.get("fixed_values")
    if isinstance(fixed_values, dict):
        for target_path, value in fixed_values.items():
            set_path(model, str(target_path), value)
    return model


class KingdeeEngineeringBomPushService:
    TARGET_PROFILE = TARGET_PROFILE

    async def push_engineering_bom(
        self,
        *,
        tenant_id: int,
        bom_line_id: int,
        acting_user_id: int,
        connection_code: Optional[str] = None,
        save_api_uuid: Optional[str] = None,
        dry_run: bool = False,
    ) -> Optional[Dict[str, Any]]:
        config = await self.get_push_config(tenant_id)
        code = str(connection_code or "").strip()
        api_uuid = str(save_api_uuid or "").strip()
        if code or api_uuid:
            config = {
                **config,
                **({"connection_code": code} if code else {}),
                **({"save_api_uuid": api_uuid} if api_uuid else {}),
                "enabled": True,
            }
        if not bool(config.get("enabled", False)):
            return None

        seed = await BOM.get_or_none(
            tenant_id=tenant_id,
            id=bom_line_id,
            deleted_at__isnull=True,
        )
        if not seed:
            return None

        lines = await BOM.filter(
            tenant_id=tenant_id,
            material_id=seed.material_id,
            version=seed.version,
            deleted_at__isnull=True,
            is_obsolete=False,
        ).all()
        parent = await Material.get_or_none(
            tenant_id=tenant_id,
            id=int(seed.material_id),
            deleted_at__isnull=True,
        )
        parent_code = (
            str(getattr(parent, "main_code", None) or getattr(parent, "code", None) or "").strip()
            if parent
            else ""
        )
        already_pushed = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type=SOURCE_TYPE,
            source_id=int(seed.id),
            target_type=TARGET_TYPE,
        ).exists()
        skip_reason = engineering_bom_push_skip_reason(
            lines,
            parent_code=parent_code,
            already_pushed=already_pushed,
        )
        if skip_reason:
            return {"success": True, "skipped": True, "message": skip_reason}

        try:
            return await self._push_now(
                tenant_id=tenant_id,
                seed=seed,
                lines=lines,
                parent_code=parent_code,
                acting_user_id=acting_user_id,
                config=config,
                dry_run=dry_run,
            )
        except Exception as exc:
            logger.warning(
                "工程BOM推送金蝶失败 tenant_id={} bom_id={} err={}",
                tenant_id,
                bom_line_id,
                exc,
            )
            if bool(config.get("fail_on_error", False)):
                raise BusinessLogicError(f"推送金蝶工程BOM失败：{exc}")
            return {"success": False, "message": str(exc)}

    async def get_push_config(self, tenant_id: int) -> Dict[str, Any]:
        biz_config = await BusinessConfigService().get_business_config(tenant_id)
        master = (biz_config.get("parameters", {}) or {}).get("master_data", {}) or {}
        raw = master.get("kingdee_engineering_bom_push") or {}
        return dict(raw) if isinstance(raw, dict) else {}

    async def _push_now(
        self,
        *,
        tenant_id: int,
        seed: BOM,
        lines: List[BOM],
        parent_code: str,
        acting_user_id: int,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        form_id = str(config.get("form_id") or DEFAULT_FORM_ID).strip() or DEFAULT_FORM_ID
        component_ids = [int(line.component_id) for line in lines]
        materials = await Material.filter(
            tenant_id=tenant_id,
            id__in=component_ids,
            deleted_at__isnull=True,
        ).all()
        component_codes = {
            int(m.id): str(getattr(m, "main_code", None) or getattr(m, "code", None) or "").strip()
            for m in materials
            if str(getattr(m, "main_code", None) or getattr(m, "code", None) or "").strip()
        }
        bom_code = str(getattr(seed, "bom_code", None) or "").strip() or None
        model = build_kingdee_eng_bom_model(
            parent_code=parent_code,
            lines=lines,
            component_codes=component_codes,
            bom_code=bom_code,
            cfg=config,
        )
        source_code = bom_code or f"{parent_code}|{seed.version}"
        request = DocumentPushRequest(
            source_type=SOURCE_TYPE,
            source_id=int(seed.id),
            target_profile=TARGET_PROFILE,
            source_code=source_code,
            source_name=source_code,
            connection_code=str(config.get("connection_code") or "").strip() or None,
            save_api_uuid=str(config.get("save_api_uuid") or "").strip() or None,
            dry_run=dry_run,
        )
        prepared = DocumentPushPrepared(
            form_id=form_id,
            model=model,
            target_type=TARGET_TYPE,
            target_name="金蝶工程BOM",
            relation_desc="工程BOM推送金蝶ENG_BOM",
            connector_type="kingdee_galaxy",
            config=config,
        )

        async def _persist(result: Dict[str, Any]) -> None:
            await DocumentRelation.create(
                tenant_id=tenant_id,
                source_type=str(result.get("source_type") or SOURCE_TYPE),
                source_id=int(result.get("source_id") or seed.id),
                source_code=result.get("source_code") or source_code,
                source_name=result.get("source_name") or source_code,
                target_type=str(result.get("target_type") or TARGET_TYPE),
                target_id=int(result.get("bill_id") or 0),
                target_code=(result.get("bill_no") or None),
                target_name=str(result.get("target_name") or "金蝶工程BOM"),
                relation_type="source",
                relation_mode="push",
                relation_desc=str(result.get("relation_desc") or "工程BOM推送金蝶ENG_BOM"),
                notes=to_api_isoformat(datetime.utcnow()),
                created_by=acting_user_id,
            )

        return await DocumentPushPipeline().push(
            tenant_id=tenant_id,
            acting_user_id=acting_user_id,
            request=request,
            prepared=prepared,
            persist_relation=None if dry_run else _persist,
        )
