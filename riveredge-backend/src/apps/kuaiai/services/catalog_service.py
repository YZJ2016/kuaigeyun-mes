"""KU-AI 模型目录服务（KR-D5）：llm_providers / llm_models CRUD + options。

- 归属校验统一入口 get_provider / get_model：tenant_id 强过滤，
  跨租户/软删/不存在一律 404（KR-I1/I2）。
- api_key 复用 IntegrationConfig 口径：列存服务端解析值，出参打码
  （**** + api_key_configured）；写路径传打码占位/空串视为保留原值。
  本仓 IntegrationConfig 无独立 at-rest cipher，不新建第二套。
- 写路径（add/edit/remove/status 变更）统一 evict_model_cache(tenant_id)；
  core.ai.runtime.model_factory 由并行单元提供，lazy import + 兜底。
- provider_type 仅模板标签，不做闭集校验（KR-D5）。
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional, Tuple

from apps.kuaiai.constants import (
    CATALOG_STATUSES,
    MODEL_TYPES,
    STATUS_ENABLED,
)
from apps.kuaiai.models.agent import KuaiaiAgentProfile
from apps.kuaiai.models.catalog import KuaiaiLlmModel, KuaiaiLlmProvider
from apps.kuaiai.schemas.catalog import (
    LlmModelCreate,
    LlmModelUpdate,
    LlmProviderCreate,
    LlmProviderUpdate,
)
from core.utils.timezone_utils import now_utc
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError
from infra.models.user import User

# IntegrationConfig 打码占位：_mask_config_password 输出 "****"，
# site_settings 侧使用 INTEGRATION_API_KEY_MASK("********")，两者都视为「保留原值」
_MASKED_API_KEY_TOKENS = {"****", "********"}


def masked_api_key_fields(api_key: Optional[str]) -> Dict[str, Any]:
    """api_key 出参打码（复用 IntegrationConfig 打码函数口径）。

    返回 {"api_key": "****"|None, "api_key_configured": bool}，
    与 _mask_config_password 对 config["api_key"] 的处理逐字一致。
    """
    from core.services.integration.integration_config_service import (
        _mask_config_password,
    )

    masked = _mask_config_password({"api_key": api_key})
    return {
        "api_key": masked.get("api_key"),
        "api_key_configured": bool(masked.get("api_key_configured")),
    }


def _is_masked_or_blank(value: Optional[str]) -> bool:
    """写路径：打码占位或空白均表示「保留原 api_key」（IntegrationConfig 惯例）。"""
    if value is None:
        return True
    stripped = value.strip()
    return not stripped or stripped in _MASKED_API_KEY_TOKENS


async def _evict_model_cache(tenant_id: int, model_id: Optional[int] = None) -> None:
    """写路径 evict 模型缓存：core/ai/runtime/model_factory 由并行单元提供。

    文件未落地时 ImportError 兜底跳过（两批代码会合后生效）。
    """
    try:
        from core.ai.runtime.model_factory import evict_model_cache
    except ImportError:
        return
    result = evict_model_cache(tenant_id, model_id)
    if inspect.isawaitable(result):
        await result


def _audit_create(user: Optional[User]) -> Dict[str, Any]:
    if user is None or getattr(user, "id", None) is None:
        return {}
    name = getattr(user, "full_name", None) or getattr(user, "username", None)
    return {
        "created_by": user.id,
        "created_by_name": name,
        "updated_by": user.id,
        "updated_by_name": name,
    }


def _audit_update(user: Optional[User]) -> Dict[str, Any]:
    if user is None or getattr(user, "id", None) is None:
        return {}
    return {
        "updated_by": user.id,
        "updated_by_name": getattr(user, "full_name", None)
        or getattr(user, "username", None),
    }


def _require_status(value: Optional[str]) -> str:
    stripped = (value or "").strip()
    if stripped not in CATALOG_STATUSES:
        raise BusinessLogicError("status 仅允许 启用|停用")
    return stripped


def _require_model_type(value: Optional[str]) -> str:
    stripped = (value or "").strip()
    if stripped not in MODEL_TYPES:
        raise BusinessLogicError("model_type 仅允许 chat|embed|vision")
    return stripped


def provider_out(provider: KuaiaiLlmProvider) -> Dict[str, Any]:
    """厂商行响应 dict：api_key 打码回显，不含明文/cipher/tenant_id。"""
    return {
        "id": provider.id,
        "uuid": str(provider.uuid),
        "code": provider.code,
        "name": provider.name,
        "base_url": provider.base_url,
        "provider_type": provider.provider_type,
        "status": provider.status,
        "created_at": provider.created_at,
        "updated_at": provider.updated_at,
        **masked_api_key_fields(provider.api_key),
    }


# ---------------------------------------------------------------- providers


async def list_providers(
    tenant_id: int, page: int = 1, page_size: int = 20
) -> Tuple[List[KuaiaiLlmProvider], int]:
    q = KuaiaiLlmProvider.filter(tenant_id=tenant_id, deleted_at__isnull=True)
    total = await q.count()
    items = await (
        q.order_by("id").offset((page - 1) * page_size).limit(page_size)
    )
    return items, total


async def get_provider(tenant_id: int, provider_id: int) -> KuaiaiLlmProvider:
    provider = await KuaiaiLlmProvider.get_or_none(
        tenant_id=tenant_id, id=provider_id, deleted_at__isnull=True
    )
    if provider is None:
        raise NotFoundError("LLM 厂商", str(provider_id))
    return provider


async def create_provider(
    tenant_id: int, user: User, payload: LlmProviderCreate
) -> KuaiaiLlmProvider:
    code = payload.code.strip()
    dup = await KuaiaiLlmProvider.get_or_none(
        tenant_id=tenant_id, code=code, deleted_at__isnull=True
    )
    if dup is not None:
        raise BusinessLogicError(f"厂商代码 {code} 已存在")
    api_key = None if _is_masked_or_blank(payload.api_key) else payload.api_key.strip()
    provider = await KuaiaiLlmProvider.create(
        tenant_id=tenant_id,
        code=code,
        name=payload.name.strip(),
        base_url=payload.base_url.strip().rstrip("/"),
        api_key=api_key,
        provider_type=(payload.provider_type or "").strip() or None,
        status=(
            _require_status(payload.status)
            if payload.status is not None
            else STATUS_ENABLED
        ),
        **_audit_create(user),
    )
    await _evict_model_cache(tenant_id)
    return provider


async def update_provider(
    tenant_id: int, user: User, provider_id: int, payload: LlmProviderUpdate
) -> KuaiaiLlmProvider:
    provider = await get_provider(tenant_id, provider_id)
    data = payload.model_dump(exclude_unset=True)
    # 非空列显式传 null 视为非法（避免写入 NULL）
    for non_nullable in ("name", "base_url"):
        if non_nullable in data and data[non_nullable] is None:
            raise BusinessLogicError(f"{non_nullable} 不允许为空")
    if "name" in data:
        data["name"] = data["name"].strip()
    if "base_url" in data:
        data["base_url"] = data["base_url"].strip().rstrip("/")
    if "provider_type" in data:
        pt = data["provider_type"]
        data["provider_type"] = pt.strip() if isinstance(pt, str) and pt.strip() else None
    if "status" in data:
        data["status"] = _require_status(data["status"])
    if "api_key" in data:
        # IntegrationConfig 惯例：打码占位/空串/None → 保留原值，不写库
        new_key = data.pop("api_key")
        if not _is_masked_or_blank(new_key):
            data["api_key"] = new_key.strip()
    data.update(_audit_update(user))
    await provider.update_from_dict(data).save()
    await _evict_model_cache(tenant_id)
    return provider


async def delete_provider(tenant_id: int, user: User, provider_id: int) -> None:
    provider = await get_provider(tenant_id, provider_id)
    provider.deleted_at = now_utc()
    provider.update_from_dict(_audit_update(user))
    await provider.save()
    await _evict_model_cache(tenant_id)


# ------------------------------------------------------------------- models


async def list_models(
    tenant_id: int,
    page: int = 1,
    page_size: int = 20,
    *,
    model_type: Optional[str] = None,
    provider_id: Optional[int] = None,
) -> Tuple[List[KuaiaiLlmModel], int]:
    q = KuaiaiLlmModel.filter(tenant_id=tenant_id, deleted_at__isnull=True)
    if model_type:
        q = q.filter(model_type=_require_model_type(model_type))
    if provider_id is not None:
        q = q.filter(provider_id=provider_id)
    total = await q.count()
    items = await (
        q.order_by("id").offset((page - 1) * page_size).limit(page_size)
    )
    return items, total


async def get_model(tenant_id: int, model_id: int) -> KuaiaiLlmModel:
    model = await KuaiaiLlmModel.get_or_none(
        tenant_id=tenant_id, id=model_id, deleted_at__isnull=True
    )
    if model is None:
        raise NotFoundError("LLM 模型", str(model_id))
    return model


async def create_model(
    tenant_id: int, user: User, payload: LlmModelCreate
) -> KuaiaiLlmModel:
    model_type = _require_model_type(payload.model_type)
    provider = await get_provider(tenant_id, payload.provider_id)
    model = await KuaiaiLlmModel.create(
        tenant_id=tenant_id,
        provider_id=provider.id,
        model_name=payload.model_name.strip(),
        model_type=model_type,
        status=(
            _require_status(payload.status)
            if payload.status is not None
            else STATUS_ENABLED
        ),
        **_audit_create(user),
    )
    await _evict_model_cache(tenant_id)
    return model


async def update_model(
    tenant_id: int, user: User, model_id: int, payload: LlmModelUpdate
) -> KuaiaiLlmModel:
    model = await get_model(tenant_id, model_id)
    data = payload.model_dump(exclude_unset=True)
    # 非空列显式传 null 视为非法（避免写入 NULL）
    for non_nullable in ("provider_id", "model_name", "model_type"):
        if non_nullable in data and data[non_nullable] is None:
            raise BusinessLogicError(f"{non_nullable} 不允许为空")
    if "provider_id" in data:
        provider = await get_provider(tenant_id, data["provider_id"])
        data["provider_id"] = provider.id
    if "model_name" in data:
        data["model_name"] = data["model_name"].strip()
    if "model_type" in data:
        new_type = _require_model_type(data["model_type"])
        if new_type != model.model_type:
            # m4：已被 Agent 档案 default_model_id 引用的模型行禁止事后改型——
            # 档案装配按 default_model_id 直连该行，改型会静默改变其语义
            # （如 chat→embed 后档案解析到非对话模型）。未引用则允许改型。
            referenced = await KuaiaiAgentProfile.filter(
                tenant_id=tenant_id,
                default_model_id=model.id,
                deleted_at__isnull=True,
            ).exists()
            if referenced:
                raise BusinessLogicError(
                    "该模型已被 Agent 档案引用为默认模型，不允许变更 model_type"
                )
        data["model_type"] = new_type
    if "status" in data:
        data["status"] = _require_status(data["status"])
    data.update(_audit_update(user))
    await model.update_from_dict(data).save()
    await _evict_model_cache(tenant_id)
    return model


async def delete_model(tenant_id: int, user: User, model_id: int) -> None:
    model = await get_model(tenant_id, model_id)
    model.deleted_at = now_utc()
    model.update_from_dict(_audit_update(user))
    await model.save()
    await _evict_model_cache(tenant_id)


async def model_options(
    tenant_id: int, model_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """启用模型下拉项：不含 api_key/base_url 等连接信息（KR-I5）。"""
    q = KuaiaiLlmModel.filter(
        tenant_id=tenant_id, status=STATUS_ENABLED, deleted_at__isnull=True
    )
    if model_type:
        q = q.filter(model_type=_require_model_type(model_type))
    rows = await q.order_by("id").all()
    provider_ids = {r.provider_id for r in rows}
    providers = (
        await KuaiaiLlmProvider.filter(
            tenant_id=tenant_id, id__in=list(provider_ids), deleted_at__isnull=True
        ).all()
        if provider_ids
        else []
    )
    provider_names = {p.id: p.name for p in providers}
    return [
        {
            "id": r.id,
            "provider_id": r.provider_id,
            "provider_name": provider_names.get(r.provider_id),
            "model_name": r.model_name,
            "model_type": r.model_type,
        }
        for r in rows
    ]
