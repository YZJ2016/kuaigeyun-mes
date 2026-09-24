"""模型工厂（KR-D5 / 设计 §6.1）。

解析顺序（钉死）：
1. 目录行优先——``apps.kuaiai.models.catalog`` 的 ``KuaiaiLlmModel`` /
   ``KuaiaiLlmProvider``（tenant_id + status 过滤；目录模块属并行开发，
   暂不存在时 try/ImportError 直接走兜底）；
2. 无目录行 → ``AiRuntimeConfig`` / ``IntegrationConfig`` 单活连接兜底。

出站一律 ``ChatOpenAI`` / ``OpenAIEmbeddings``，只用 base_url + api_key +
model_name；禁止厂商分支、禁止 DeepSeek SDK、禁止 ``LLM_PROVIDER_SPECS``
闭集校验。Key 只服务端解析；日志不落 key/cipher/base_url。

目录行字段约定（并行侧需对齐）：模型行 ``provider_id`` / ``model_name`` /
``model_type``(chat|embed|vision) / ``status``；厂商行 ``base_url`` /
``api_key``。``status`` 判定按「非停用即启用」，停用值见
``_DISABLED_STATUS_VALUES``（兼容 '1'/'disabled'/'停用' 等写法）；
provider 的 ``api_key`` 优先走 ``decrypt_api_key()`` / ``get_config()``
（IntegrationConfig 同款解析），否则取列原值。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from infra.exceptions.exceptions import ValidationError
from infra.infrastructure.http import get_http_client

_REQUEST_TIMEOUT = 120
_EMBED_REQUEST_TIMEOUT = 30

# 目录行停用值集合：非集合内的 status（含 None/'0'/'enabled'/'normal'）视为启用。
_DISABLED_STATUS_VALUES = {"1", "disabled", "off", "stopped", "停用"}
# IntegrationConfig 打码占位，密文槽被回填掩码时视为未配置
_MASKED_KEY = "********"

_MODEL_CACHE: Dict[Tuple[int, Optional[int]], ChatOpenAI] = {}
_EMBED_CACHE: Dict[Tuple[int, Optional[int]], OpenAIEmbeddings] = {}
_VISION_CACHE: Dict[Tuple[int, Optional[int]], ChatOpenAI] = {}


@dataclass(frozen=True)
class ModelSource:
    """一次出站所需的最小凭证视图（不落库、不出日志）。"""

    base_url: str
    api_key: str
    model_name: str
    model_type: str = "chat"


def _catalog_models() -> Optional[Tuple[Any, Any]]:
    """惰性加载模型目录 ORM；模块暂不存在（并行开发中）返回 None 走兜底。"""
    try:
        from apps.kuaiai.models.catalog import KuaiaiLlmModel, KuaiaiLlmProvider
    except ImportError:
        return None
    return KuaiaiLlmModel, KuaiaiLlmProvider


def _attr(row: Any, *names: str) -> Any:
    """鸭子读取：容忍并行目录模型的近义列名。"""
    for name in names:
        value = getattr(row, name, None)
        if value not in (None, ""):
            return value
    return None


def _row_enabled(row: Any) -> bool:
    """目录行启用判定：非停用即启用。"""
    status = getattr(row, "status", None)
    if status is None:
        is_active = getattr(row, "is_active", None)
        return True if is_active is None else bool(is_active)
    return str(status).strip().lower() not in _DISABLED_STATUS_VALUES


def _provider_config(provider: Any) -> Dict[str, Any]:
    """IntegrationConfig 同款 config 视图（get_config() 优先，否则 .config 列）。"""
    get_config = getattr(provider, "get_config", None)
    if callable(get_config):
        cfg = get_config()
        if isinstance(cfg, dict):
            return cfg
    cfg = getattr(provider, "config", None)
    return cfg if isinstance(cfg, dict) else {}


def _provider_api_key(provider: Any) -> str:
    """provider api_key 服务端解析：decrypt_api_key() > config['api_key'] > api_key 列。"""
    decrypt = getattr(provider, "decrypt_api_key", None)
    if callable(decrypt):
        try:
            value = decrypt()
        except Exception:
            value = None
        if isinstance(value, str) and value.strip() and value.strip() != _MASKED_KEY:
            return value.strip()
    for value in (
        _provider_config(provider).get("api_key"),
        getattr(provider, "api_key", None),
    ):
        if isinstance(value, str) and value.strip() and value.strip() != _MASKED_KEY:
            return value.strip()
    return ""


def _provider_base_url(provider: Any) -> str:
    value = _attr(provider, "base_url", "api_host", "api_base")
    if value is None:
        value = _provider_config(provider).get("base_url")
    return str(value or "").strip().rstrip("/")


async def _resolve_catalog_source(
    tenant_id: int, model_id: Optional[int], model_type: str
) -> Optional[ModelSource]:
    catalog = _catalog_models()
    if catalog is None:
        return None
    KuaiaiLlmModel, KuaiaiLlmProvider = catalog

    if model_id is not None:
        row = await KuaiaiLlmModel.filter(
            tenant_id=tenant_id, id=model_id, deleted_at__isnull=True
        ).first()
        if row is None:
            # 指定目录行不存在/跨租户：失败关闭，不静默落到别的模型
            raise ValidationError("所选模型不存在，请检查模型目录配置")
        row_type = str(_attr(row, "model_type", "type") or "chat")
        if row_type != model_type:
            # 显式 id 与调用场景类型不符（如拿 chat 行当 vision）：失败关闭，
            # 不回落兜底——静默换型会掩盖目录配置错误
            raise ValidationError("所选模型类型与调用场景不匹配")
        if not _row_enabled(row):
            raise ValidationError("所选模型已停用")
    else:
        rows = await KuaiaiLlmModel.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        ).order_by("id").all()
        candidates = [
            r
            for r in rows
            if _row_enabled(r)
            and str(_attr(r, "model_type", "type") or "chat") == model_type
        ]
        row = next(
            (r for r in candidates if getattr(r, "is_default", False) is True),
            candidates[0] if candidates else None,
        )
        if row is None:
            return None

    provider_id = _attr(row, "provider_id", "llm_provider_id")
    provider = None
    if provider_id is not None:
        provider = await KuaiaiLlmProvider.filter(
            tenant_id=tenant_id, id=provider_id, deleted_at__isnull=True
        ).first()
    if provider is None or not _row_enabled(provider):
        raise ValidationError("模型目录中的厂商配置不可用")

    base_url = _provider_base_url(provider)
    api_key = _provider_api_key(provider)
    model_name = str(_attr(row, "model_name", "name") or "").strip()
    if not base_url or not api_key or not model_name:
        raise ValidationError("模型目录行缺少 base_url / api_key / model_name")
    return ModelSource(
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        model_type=str(_attr(row, "model_type", "type") or model_type),
    )


async def _resolve_fallback_source(tenant_id: int, model_type: str) -> ModelSource:
    """IntegrationConfig 单活连接兜底（OpenAI 兼容 base_url+key，非厂商 SDK）。"""
    from core.ai.runtime_config import AiRuntimeConfig

    config = await AiRuntimeConfig.load(tenant_id)
    if model_type == "vision":
        if config.ocr_base_url and config.ocr_model:
            return ModelSource(
                base_url=str(config.ocr_base_url).strip().rstrip("/"),
                api_key=(config.ocr_api_key or config.chat_api_key or "").strip(),
                model_name=str(config.ocr_model).strip(),
                model_type="vision",
            )
        from core.utils.deepseek_vision_client import OCR_NOT_CONFIGURED_MSG

        raise ValidationError(OCR_NOT_CONFIGURED_MSG)
    if model_type == "embed":
        raise ValidationError("未配置 embedding 模型，请先在模型目录中添加 embed 模型")
    return ModelSource(
        base_url=config.chat_base_url.rstrip("/"),
        api_key=config.chat_api_key,
        model_name=config.chat_model,
        model_type="chat",
    )


async def resolve_model_source(
    tenant_id: int,
    model_id: Optional[int] = None,
    *,
    model_type: str = "chat",
) -> ModelSource:
    """目录行优先解析 base_url + api_key + model_name；无行走兜底连接。"""
    if not tenant_id:
        raise ValidationError("组织上下文缺失，无法解析 AI 模型")
    source = await _resolve_catalog_source(tenant_id, model_id, model_type)
    if source is not None:
        return source
    return await _resolve_fallback_source(tenant_id, model_type)


def _new_chat_model(source: ModelSource) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=source.api_key,
        base_url=source.base_url,
        model=source.model_name,
        streaming=True,
        # 自定义 base_url / http_async_client 时 langchain-openai 默认关闭
        # stream_usage，astream chunk 无 usage_metadata → token 回填恒 NULL；
        # 显式开启让上游在末帧返回 usage。
        stream_usage=True,
        request_timeout=_REQUEST_TIMEOUT,
        http_async_client=get_http_client(),
    )


async def build_chat_model(
    tenant_id: int, model_id: Optional[int] = None
) -> ChatOpenAI:
    """构造（并缓存）对话模型；缓存键 (tenant_id, model_id)。

    请求级 model/temperature/response_format 覆盖由调用方 ``.bind(...)``，
    不另建缓存键。
    """
    key = (tenant_id, model_id)
    if key not in _MODEL_CACHE:
        source = await resolve_model_source(tenant_id, model_id)
        _MODEL_CACHE[key] = _new_chat_model(source)
    return _MODEL_CACHE[key]


async def build_vision_model(
    tenant_id: int, model_id: Optional[int] = None
) -> ChatOpenAI:
    """视觉模型：目录 ``model_type=vision`` 行优先，否则 IntegrationConfig OCR 组兜底。"""
    key = (tenant_id, model_id)
    if key not in _VISION_CACHE:
        source = await resolve_model_source(
            tenant_id, model_id, model_type="vision"
        )
        _VISION_CACHE[key] = _new_chat_model(source)
    return _VISION_CACHE[key]


async def build_embeddings(
    tenant_id: int, model_id: Optional[int] = None
) -> OpenAIEmbeddings:
    """构造（并缓存）embedding 模型；缓存键 (tenant_id, model_id)。

    维度仍受 KR-G7：写入 vector(768) 失败关闭，由调用方把关。
    """
    key = (tenant_id, model_id)
    if key not in _EMBED_CACHE:
        source = await resolve_model_source(
            tenant_id, model_id, model_type="embed"
        )
        _EMBED_CACHE[key] = OpenAIEmbeddings(
            api_key=source.api_key,
            base_url=source.base_url,
            model=source.model_name,
            request_timeout=_EMBED_REQUEST_TIMEOUT,
            http_async_client=get_http_client(),
        )
    return _EMBED_CACHE[key]


def evict_model_cache(tenant_id: int, model_id: Optional[int] = None) -> None:
    """目录/连接写路径 evict。

    ``model_id=None`` 清该租户全部缓存；指定 id 时同时清默认槽
    （默认解析可能正指向被编辑行）。
    """
    caches = (_MODEL_CACHE, _EMBED_CACHE, _VISION_CACHE)
    if model_id is None:
        for cache in caches:
            for key in [k for k in cache if k[0] == tenant_id]:
                cache.pop(key, None)
        return
    for cache in caches:
        cache.pop((tenant_id, model_id), None)
        cache.pop((tenant_id, None), None)
