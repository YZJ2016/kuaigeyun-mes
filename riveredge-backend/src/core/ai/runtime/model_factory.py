"""模型工厂（KR-D5 / 设计 §6.1，2026-10-02 再决策）。

运行时只读应用连接器里该角色的选用连接（chat / embed / vision）。
``model_id`` 不再参与解析。出站一律 ``ChatOpenAI`` / ``OpenAIEmbeddings``，
只用 base_url + api_key + model。禁止厂商 SDK 分支。Key 只服务端解析；
日志不落 key/cipher/base_url。rerank 连接只保存，不在本工厂构造客户端。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from infra.exceptions.exceptions import ValidationError
from infra.infrastructure.http import get_http_client

_REQUEST_TIMEOUT = 120
_EMBED_REQUEST_TIMEOUT = 30
# 切块写入 pgvector vector(768)。兼容端点（如 text-embedding-v4）默认维数不是 768，
# 须显式 dimensions；其单次 input 上限为 10 条字符串，且拒绝 tiktoken 的 token id。
_EMBED_DIM = 768
_EMBED_BATCH_SIZE = 10

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


async def _resolve_catalog_source(
    tenant_id: int, model_id: Optional[int], model_type: str
) -> None:
    """目录解析已退出运行时。保留符号供既有发送路径补丁；生产恒为未命中。"""
    del tenant_id, model_id, model_type
    return None


async def _load_role_source(tenant_id: int, model_type: str) -> ModelSource:
    from core.utils.integration_settings import resolve_selected_llm_connection

    raw = await resolve_selected_llm_connection(tenant_id, model_type)
    return ModelSource(
        base_url=str(raw["base_url"]).rstrip("/"),
        api_key=str(raw["api_key"]),
        model_name=str(raw["model"]),
        model_type=model_type,
    )


async def resolve_model_source(
    tenant_id: int,
    model_id: Optional[int] = None,
    *,
    model_type: str = "chat",
) -> ModelSource:
    """按角色选用连接解析。``model_id`` 忽略。"""
    del model_id
    if not tenant_id:
        raise ValidationError("组织上下文缺失，无法解析 AI 模型")
    if model_type == "rerank":
        raise ValidationError("重排连接只作选用保存，检索打分仍使用对话连接")
    return await _load_role_source(tenant_id, model_type)


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
    """构造（并缓存）对话选用连接。``model_id`` 忽略。"""
    del model_id
    key = (tenant_id, None)
    if key not in _MODEL_CACHE:
        source = await resolve_model_source(tenant_id, model_type="chat")
        _MODEL_CACHE[key] = _new_chat_model(source)
    return _MODEL_CACHE[key]


async def build_vision_model(
    tenant_id: int, model_id: Optional[int] = None
) -> ChatOpenAI:
    """视觉选用连接。``model_id`` 忽略。"""
    del model_id
    key = (tenant_id, None)
    if key not in _VISION_CACHE:
        source = await resolve_model_source(tenant_id, model_type="vision")
        _VISION_CACHE[key] = _new_chat_model(source)
    return _VISION_CACHE[key]


async def build_embeddings(
    tenant_id: int, model_id: Optional[int] = None
) -> OpenAIEmbeddings:
    """构造（并缓存）嵌入选用连接。``model_id`` 忽略。

    出站发原始文本、每批最多 ``_EMBED_BATCH_SIZE`` 条，并请求 ``_EMBED_DIM`` 维。
    调用方仍按 vector(768) 失败关闭。
    """
    del model_id
    key = (tenant_id, None)
    if key not in _EMBED_CACHE:
        source = await resolve_model_source(tenant_id, model_type="embed")
        _EMBED_CACHE[key] = OpenAIEmbeddings(
            api_key=source.api_key,
            base_url=source.base_url,
            model=source.model_name,
            request_timeout=_EMBED_REQUEST_TIMEOUT,
            http_async_client=get_http_client(),
            check_embedding_ctx_length=False,
            dimensions=_EMBED_DIM,
            chunk_size=_EMBED_BATCH_SIZE,
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
