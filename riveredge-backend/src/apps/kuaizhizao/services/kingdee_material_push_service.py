"""业务适配：物料主数据 → 金蝶物料（BD_MATERIAL）。"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger

from apps.kuaizhizao.models.document_relation import DocumentRelation
from apps.master_data.models.material import Material
from core.services.integration.document_push_mapping import apply_field_map, set_path
from core.services.integration.document_push_pipeline import (
    DocumentPushPipeline,
    DocumentPushPrepared,
    DocumentPushRequest,
)
from core.utils.timezone_utils import to_api_isoformat
from infra.exceptions.exceptions import BusinessLogicError
from infra.services.business_config_service import BusinessConfigService

DEFAULT_FORM_ID = "BD_MATERIAL"
TARGET_TYPE = "kingdee_bd_material"
TARGET_PROFILE = "kingdee_bd_material"
SOURCE_TYPE = "material"
PUSH_DISABLED_MESSAGE = "金蝶物料推送未启用"


def material_push_skip_reason(
    material: Material,
    *,
    already_pushed: bool = False,
) -> Optional[str]:
    if getattr(material, "external_sync_at", None) is not None:
        return "金蝶拉取导入的物料不可回推"
    if already_pushed:
        return "已推送过金蝶物料"
    if not bool(getattr(material, "is_active", True)):
        return "物料已停用，不可推送"
    code = str(getattr(material, "main_code", None) or getattr(material, "code", None) or "").strip()
    if not code:
        return "缺少物料编码"
    name = str(getattr(material, "name", None) or "").strip()
    if not name:
        return "缺少物料名称"
    return None


def build_kingdee_bd_material_model(
    *,
    material: Material,
    group_number: Optional[str] = None,
    unit_number: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    config = cfg or {}
    template = config.get("model_template")
    if isinstance(template, dict) and template:
        model = copy.deepcopy(template)
    else:
        model = {"FMATERIALID": 0}

    code = str(getattr(material, "main_code", None) or getattr(material, "code", None) or "").strip()
    name = str(getattr(material, "name", None) or "").strip()
    model["FNumber"] = code
    model["FName"] = name
    spec = str(getattr(material, "specification", None) or "").strip()
    if spec:
        model["FSpecification"] = spec
    if group_number:
        model["FMaterialGroup"] = {"FNumber": group_number}
    if unit_number:
        model["FBaseUnitId"] = {"FNumber": unit_number}

    default_field_map = {
        "create_org_number": "FCreateOrgId.FNumber",
        "use_org_number": "FUseOrgId.FNumber",
    }

    def local_value(key: str) -> Any:
        if key in ("create_org_number", "use_org_number"):
            return config.get(key) or config.get("org_number")
        return getattr(material, key, None)

    apply_field_map(model, default_field_map, local_value)
    fixed_values = config.get("fixed_values")
    if isinstance(fixed_values, dict):
        for target_path, value in fixed_values.items():
            set_path(model, str(target_path), value)
    return model


class KingdeeMaterialPushService:
    TARGET_PROFILE = TARGET_PROFILE

    async def push_material(
        self,
        *,
        tenant_id: int,
        material_id: int,
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

        material = await Material.get_or_none(
            tenant_id=tenant_id,
            id=material_id,
            deleted_at__isnull=True,
        )
        if not material:
            return None

        already_pushed = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type=SOURCE_TYPE,
            source_id=material_id,
            target_type=TARGET_TYPE,
        ).exists()
        skip_reason = material_push_skip_reason(material, already_pushed=already_pushed)
        if skip_reason:
            return {"success": True, "skipped": True, "message": skip_reason}

        try:
            return await self._push_now(
                tenant_id=tenant_id,
                material=material,
                acting_user_id=acting_user_id,
                config=config,
                dry_run=dry_run,
            )
        except Exception as exc:
            logger.warning(
                "物料推送金蝶失败 tenant_id={} material_id={} err={}",
                tenant_id,
                material_id,
                exc,
            )
            if bool(config.get("fail_on_error", False)):
                raise BusinessLogicError(f"推送金蝶物料失败：{exc}")
            return {"success": False, "message": str(exc)}

    async def get_push_config(self, tenant_id: int) -> Dict[str, Any]:
        biz_config = await BusinessConfigService().get_business_config(tenant_id)
        master = (biz_config.get("parameters", {}) or {}).get("master_data", {}) or {}
        raw = master.get("kingdee_material_push") or {}
        return dict(raw) if isinstance(raw, dict) else {}

    async def _push_now(
        self,
        *,
        tenant_id: int,
        material: Material,
        acting_user_id: int,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        form_id = str(config.get("form_id") or DEFAULT_FORM_ID).strip() or DEFAULT_FORM_ID
        group_number = None
        group_id = int(getattr(material, "group_id", None) or 0)
        if group_id > 0:
            try:
                from apps.master_data.models.material import MaterialGroup

                group = await MaterialGroup.get_or_none(
                    tenant_id=tenant_id, id=group_id, deleted_at__isnull=True
                )
                if group:
                    group_number = str(getattr(group, "code", None) or "").strip() or None
            except Exception as exc:
                logger.warning("resolve material group failed material_id={} err={}", material.id, exc)

        unit_number = str(config.get("unit_number") or "").strip() or None
        if not unit_number:
            try:
                from apps.master_data.models.unit import MaterialUnit

                unit_id = int(getattr(material, "unit_id", None) or 0)
                if unit_id > 0:
                    unit = await MaterialUnit.get_or_none(
                        tenant_id=tenant_id, id=unit_id, deleted_at__isnull=True
                    )
                    if unit:
                        unit_number = str(unit.code or "").strip() or None
            except Exception:
                pass

        source_code = str(
            getattr(material, "main_code", None) or getattr(material, "code", None) or material.id
        ).strip()
        model = build_kingdee_bd_material_model(
            material=material,
            group_number=group_number,
            unit_number=unit_number,
            cfg=config,
        )
        request = DocumentPushRequest(
            source_type=SOURCE_TYPE,
            source_id=int(material.id),
            target_profile=TARGET_PROFILE,
            source_code=source_code,
            source_name=str(getattr(material, "name", None) or source_code),
            connection_code=str(config.get("connection_code") or "").strip() or None,
            save_api_uuid=str(config.get("save_api_uuid") or "").strip() or None,
            dry_run=dry_run,
        )
        prepared = DocumentPushPrepared(
            form_id=form_id,
            model=model,
            target_type=TARGET_TYPE,
            target_name="金蝶物料",
            relation_desc="物料推送金蝶BD_MATERIAL",
            connector_type="kingdee_galaxy",
            config=config,
        )

        async def _persist(result: Dict[str, Any]) -> None:
            await DocumentRelation.create(
                tenant_id=tenant_id,
                source_type=str(result.get("source_type") or SOURCE_TYPE),
                source_id=int(result.get("source_id") or material.id),
                source_code=result.get("source_code") or source_code,
                source_name=result.get("source_name") or source_code,
                target_type=str(result.get("target_type") or TARGET_TYPE),
                target_id=int(result.get("bill_id") or 0),
                target_code=(result.get("bill_no") or None),
                target_name=str(result.get("target_name") or "金蝶物料"),
                relation_type="source",
                relation_mode="push",
                relation_desc=str(result.get("relation_desc") or "物料推送金蝶BD_MATERIAL"),
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
