"""KU-AI 产品路由（S1：会话/消息 CRUD；S2：模型目录 + Agent 档案/授权）。

挂载：应用安装启用后由 ApplicationRegistryService 挂到 /api/v1/apps/kuaiai。
权限码与 spec 134/135 契约 B/C 逐字一致（kuaiai:{domain}:{list|query|add|edit|remove}）。
这些 action 动词不在 STANDARD_ACTIONS 内，require_permission_codes 装配期即
validate 会拒绝，故统一用 require_access(required_permissions=...) 做显式权限码
校验（required_permissions 不经 validate_permission_code，RBAC 精确匹配生效；
check_abac 留默认 True 对齐兄弟应用，仅在存在匹配 ABAC 策略时叠加判定）。

对话发送仍走网关 POST /api/v1/core/ai/chat/completions（kuaiai:act:execute），
不在本路由暴露。
"""

from fastapi import APIRouter, Depends, Query, status

from apps.kuaiai.schemas.agent import (
    AgentGrantsOut,
    AgentGrantsUpdate,
    AgentProfileCreate,
    AgentProfileOption,
    AgentProfileOut,
    AgentProfileUpdate,
)
from apps.kuaiai.schemas.catalog import (
    LlmModelCreate,
    LlmModelOption,
    LlmModelOut,
    LlmModelUpdate,
    LlmProviderCreate,
    LlmProviderOut,
    LlmProviderUpdate,
)
from apps.kuaiai.schemas.chat import (
    ChatMessageOut,
    ChatSessionCreate,
    ChatSessionOut,
    ChatSessionUpdate,
)
from apps.kuaiai.schemas.knowledge import (
    ChunkOut,
    DocumentCreate,
    DocumentListOut,
    DocumentOut,
    KnowledgeBaseCreate,
    KnowledgeBaseOption,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
)
from apps.kuaiai.services import (
    agent_service,
    catalog_service,
    grant_service,
    knowledge_base_service,
    session_service,
)
from apps.kuaiai.services.knowledge_service import KnowledgeService
from core.api.deps.access import require_access
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user

router = APIRouter(prefix="", tags=["App - KU-AI"])


@router.get(
    "/sessions",
    response_model=list[ChatSessionOut],
    dependencies=[
        Depends(
            require_access(
                "kuaiai.session",
                "list",
                required_permissions=["kuaiai:session:list"],
            )
        )
    ],
)
async def api_list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    """当前用户在本租户的会话列表（仅本人会话）。"""
    items, _total = await session_service.list_sessions(
        tenant_id, current_user.id, page, page_size
    )
    return items


@router.post(
    "/sessions",
    response_model=ChatSessionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.session",
                "add",
                required_permissions=["kuaiai:session:add"],
            )
        )
    ],
)
async def api_create_session(
    payload: ChatSessionCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await session_service.create_session(tenant_id, current_user, payload)


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionOut,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.session",
                "query",
                required_permissions=["kuaiai:session:query"],
            )
        )
    ],
)
async def api_get_session(
    session_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await session_service.get_owned_session(tenant_id, session_id, current_user.id)


@router.patch(
    "/sessions/{session_id}",
    response_model=ChatSessionOut,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.session",
                "edit",
                required_permissions=["kuaiai:session:edit"],
            )
        )
    ],
)
async def api_update_session(
    session_id: int,
    payload: ChatSessionUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await session_service.update_session(tenant_id, current_user, session_id, payload)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.session",
                "remove",
                required_permissions=["kuaiai:session:remove"],
            )
        )
    ],
)
async def api_delete_session(
    session_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    await session_service.delete_session(tenant_id, current_user.id, session_id)


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[ChatMessageOut],
    dependencies=[
        Depends(
            require_access(
                "kuaiai.session",
                "query",
                required_permissions=["kuaiai:session:query"],
            )
        )
    ],
)
async def api_list_messages(
    session_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    session = await session_service.get_owned_session(tenant_id, session_id, current_user.id)
    return await session_service.list_messages(tenant_id, session)


# ============================================================ S2 模型目录


@router.get(
    "/llm-providers",
    response_model=list[LlmProviderOut],
    dependencies=[
        Depends(
            require_access(
                "kuaiai.model",
                "list",
                required_permissions=["kuaiai:model:list"],
            )
        )
    ],
)
async def api_list_llm_providers(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    tenant_id: int = Depends(get_current_tenant),
):
    """厂商目录列表（api_key 打码回显，不回明文）。"""
    items, _total = await catalog_service.list_providers(tenant_id, page, page_size)
    return [catalog_service.provider_out(p) for p in items]


@router.post(
    "/llm-providers",
    response_model=LlmProviderOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.model",
                "add",
                required_permissions=["kuaiai:model:add"],
            )
        )
    ],
)
async def api_create_llm_provider(
    payload: LlmProviderCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    provider = await catalog_service.create_provider(tenant_id, current_user, payload)
    return catalog_service.provider_out(provider)


@router.get(
    "/llm-providers/{provider_id}",
    response_model=LlmProviderOut,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.model",
                "query",
                required_permissions=["kuaiai:model:query"],
            )
        )
    ],
)
async def api_get_llm_provider(
    provider_id: int,
    tenant_id: int = Depends(get_current_tenant),
):
    provider = await catalog_service.get_provider(tenant_id, provider_id)
    return catalog_service.provider_out(provider)


@router.put(
    "/llm-providers/{provider_id}",
    response_model=LlmProviderOut,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.model",
                "edit",
                required_permissions=["kuaiai:model:edit"],
            )
        )
    ],
)
async def api_update_llm_provider(
    provider_id: int,
    payload: LlmProviderUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    provider = await catalog_service.update_provider(
        tenant_id, current_user, provider_id, payload
    )
    return catalog_service.provider_out(provider)


@router.delete(
    "/llm-providers/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.model",
                "remove",
                required_permissions=["kuaiai:model:remove"],
            )
        )
    ],
)
async def api_delete_llm_provider(
    provider_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    await catalog_service.delete_provider(tenant_id, current_user, provider_id)


@router.get(
    "/llm-models/options",
    response_model=list[LlmModelOption],
    dependencies=[
        Depends(
            require_access(
                "kuaiai.model",
                "query",
                required_permissions=["kuaiai:model:query"],
            )
        )
    ],
)
async def api_llm_model_options(
    model_type: str | None = Query(None),
    tenant_id: int = Depends(get_current_tenant),
):
    """启用模型下拉项（可带 model_type 过滤；不下发 api_key/base_url）。"""
    return await catalog_service.model_options(tenant_id, model_type)


@router.get(
    "/llm-models",
    response_model=list[LlmModelOut],
    dependencies=[
        Depends(
            require_access(
                "kuaiai.model",
                "list",
                required_permissions=["kuaiai:model:list"],
            )
        )
    ],
)
async def api_list_llm_models(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    model_type: str | None = Query(None),
    provider_id: int | None = Query(None),
    tenant_id: int = Depends(get_current_tenant),
):
    items, _total = await catalog_service.list_models(
        tenant_id, page, page_size, model_type=model_type, provider_id=provider_id
    )
    return items


@router.post(
    "/llm-models",
    response_model=LlmModelOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.model",
                "add",
                required_permissions=["kuaiai:model:add"],
            )
        )
    ],
)
async def api_create_llm_model(
    payload: LlmModelCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await catalog_service.create_model(tenant_id, current_user, payload)


@router.get(
    "/llm-models/{model_id}",
    response_model=LlmModelOut,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.model",
                "query",
                required_permissions=["kuaiai:model:query"],
            )
        )
    ],
)
async def api_get_llm_model(
    model_id: int,
    tenant_id: int = Depends(get_current_tenant),
):
    return await catalog_service.get_model(tenant_id, model_id)


@router.put(
    "/llm-models/{model_id}",
    response_model=LlmModelOut,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.model",
                "edit",
                required_permissions=["kuaiai:model:edit"],
            )
        )
    ],
)
async def api_update_llm_model(
    model_id: int,
    payload: LlmModelUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await catalog_service.update_model(
        tenant_id, current_user, model_id, payload
    )


@router.delete(
    "/llm-models/{model_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.model",
                "remove",
                required_permissions=["kuaiai:model:remove"],
            )
        )
    ],
)
async def api_delete_llm_model(
    model_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    await catalog_service.delete_model(tenant_id, current_user, model_id)


# ============================================================ S2 Agent 档案


@router.get(
    "/agents/options",
    response_model=list[AgentProfileOption],
    dependencies=[
        Depends(
            require_access(
                "kuaiai.agent",
                "query",
                required_permissions=["kuaiai:agent:query"],
            )
        )
    ],
)
async def api_agent_options(
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    """档案下拉：仅当前用户有使用权的启用档案（KR-D9）。"""
    return await agent_service.profile_options(tenant_id, current_user)


@router.get(
    "/agents",
    response_model=list[AgentProfileOut],
    dependencies=[
        Depends(
            require_access(
                "kuaiai.agent",
                "list",
                required_permissions=["kuaiai:agent:list"],
            )
        )
    ],
)
async def api_list_agents(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    tenant_id: int = Depends(get_current_tenant),
):
    """管理 list：本租户全部档案（不按使用权过滤）。"""
    items, _total = await agent_service.list_profiles(tenant_id, page, page_size)
    return items


@router.post(
    "/agents",
    response_model=AgentProfileOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.agent",
                "add",
                required_permissions=["kuaiai:agent:add"],
            )
        )
    ],
)
async def api_create_agent(
    payload: AgentProfileCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await agent_service.create_profile(tenant_id, current_user, payload)


@router.get(
    "/agents/{agent_id}",
    response_model=AgentProfileOut,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.agent",
                "query",
                required_permissions=["kuaiai:agent:query"],
            )
        )
    ],
)
async def api_get_agent(
    agent_id: int,
    tenant_id: int = Depends(get_current_tenant),
):
    return await agent_service.get_profile(tenant_id, agent_id)


@router.put(
    "/agents/{agent_id}",
    response_model=AgentProfileOut,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.agent",
                "edit",
                required_permissions=["kuaiai:agent:edit"],
            )
        )
    ],
)
async def api_update_agent(
    agent_id: int,
    payload: AgentProfileUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await agent_service.update_profile(
        tenant_id, current_user, agent_id, payload
    )


@router.delete(
    "/agents/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.agent",
                "remove",
                required_permissions=["kuaiai:agent:remove"],
            )
        )
    ],
)
async def api_delete_agent(
    agent_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    await agent_service.delete_profile(tenant_id, current_user, agent_id)


@router.get(
    "/agents/{agent_id}/grants",
    response_model=AgentGrantsOut,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.agent",
                "query",
                required_permissions=["kuaiai:agent:query"],
            )
        )
    ],
)
async def api_get_agent_grants(
    agent_id: int,
    tenant_id: int = Depends(get_current_tenant),
):
    profile = await agent_service.get_profile(tenant_id, agent_id)
    return await grant_service.list_grants(tenant_id, profile)


@router.put(
    "/agents/{agent_id}/grants",
    response_model=AgentGrantsOut,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.agent",
                "edit",
                required_permissions=["kuaiai:agent:edit"],
            )
        )
    ],
)
async def api_put_agent_grants(
    agent_id: int,
    payload: AgentGrantsUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    profile = await agent_service.get_profile(tenant_id, agent_id)
    return await grant_service.replace_grants(
        tenant_id, profile, payload.target_ids, current_user
    )


# ============================================================ S3 知识库


@router.get(
    "/knowledge-bases",
    dependencies=[
        Depends(
            require_access(
                "kuaiai.knowledge",
                "list",
                required_permissions=["kuaiai:knowledge:list"],
            )
        )
    ],
)
async def api_list_knowledge_bases(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    keyword: str | None = Query(None),
    tenant_id: int = Depends(get_current_tenant),
):
    """知识库分页列表 {items,total}；keyword 命中 name。"""
    result = await knowledge_base_service.list_bases(
        tenant_id, page=page, page_size=page_size, keyword=keyword
    )
    return {
        "items": [KnowledgeBaseOut.model_validate(b) for b in result["items"]],
        "total": result["total"],
    }


@router.post(
    "/knowledge-bases",
    response_model=KnowledgeBaseOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.knowledge",
                "add",
                required_permissions=["kuaiai:knowledge:add"],
            )
        )
    ],
)
async def api_create_knowledge_base(
    payload: KnowledgeBaseCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await knowledge_base_service.create_base(tenant_id, current_user, payload)


# /knowledge-bases/options 必须先于 /knowledge-bases/{kb_id} 注册
@router.get(
    "/knowledge-bases/options",
    response_model=list[KnowledgeBaseOption],
    dependencies=[
        Depends(
            require_access(
                "kuaiai.knowledge",
                "query",
                required_permissions=["kuaiai:knowledge:query"],
            )
        )
    ],
)
async def api_knowledge_base_options(
    tenant_id: int = Depends(get_current_tenant),
):
    """启用知识库下拉项。"""
    return await knowledge_base_service.base_options(tenant_id)


@router.get(
    "/knowledge-bases/{kb_id}",
    response_model=KnowledgeBaseOut,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.knowledge",
                "query",
                required_permissions=["kuaiai:knowledge:query"],
            )
        )
    ],
)
async def api_get_knowledge_base(
    kb_id: int,
    tenant_id: int = Depends(get_current_tenant),
):
    return await knowledge_base_service.get_base(tenant_id, kb_id)


@router.put(
    "/knowledge-bases/{kb_id}",
    response_model=KnowledgeBaseOut,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.knowledge",
                "edit",
                required_permissions=["kuaiai:knowledge:edit"],
            )
        )
    ],
)
async def api_update_knowledge_base(
    kb_id: int,
    payload: KnowledgeBaseUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await knowledge_base_service.update_base(
        tenant_id, current_user, kb_id, payload
    )


@router.delete(
    "/knowledge-bases/{kb_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.knowledge",
                "remove",
                required_permissions=["kuaiai:knowledge:remove"],
            )
        )
    ],
)
async def api_delete_knowledge_base(
    kb_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    await knowledge_base_service.delete_base(tenant_id, current_user, kb_id)


@router.get(
    "/knowledge-bases/{kb_id}/documents",
    dependencies=[
        Depends(
            require_access(
                "kuaiai.knowledge",
                "list",
                required_permissions=["kuaiai:knowledge:list"],
            )
        )
    ],
)
async def api_list_kb_documents(
    kb_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    tenant_id: int = Depends(get_current_tenant),
):
    """库下文档分页 {items,total}；先复核库归属（跨租户 404）。

    列表摘去 raw_content 全文（DocumentListOut），detail 端点才回全文。
    """
    base = await knowledge_base_service.get_base(tenant_id, kb_id)
    result = await KnowledgeService.list_documents(
        tenant_id, base.id, page=page, page_size=page_size
    )
    return {
        "items": [DocumentListOut.model_validate(d) for d in result["items"]],
        "total": result["total"],
    }


@router.post(
    "/knowledge-bases/{kb_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.knowledge",
                "add",
                required_permissions=["kuaiai:knowledge:add"],
            )
        )
    ],
)
async def api_create_kb_document(
    kb_id: int,
    payload: DocumentCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    base = await knowledge_base_service.get_base(tenant_id, kb_id)
    return await KnowledgeService.create_document(
        tenant_id, current_user, base.id, payload
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentOut,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.knowledge",
                "query",
                required_permissions=["kuaiai:knowledge:query"],
            )
        )
    ],
)
async def api_get_document(
    document_id: int,
    tenant_id: int = Depends(get_current_tenant),
):
    return await KnowledgeService.get_document(tenant_id, document_id)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(
            require_access(
                "kuaiai.knowledge",
                "remove",
                required_permissions=["kuaiai:knowledge:remove"],
            )
        )
    ],
)
async def api_delete_document(
    document_id: int,
    tenant_id: int = Depends(get_current_tenant),
):
    await KnowledgeService.delete_document(tenant_id, document_id)


@router.post(
    "/documents/{document_id}/parse",
    dependencies=[
        Depends(
            require_access(
                "kuaiai.knowledge",
                "edit",
                required_permissions=["kuaiai:knowledge:edit"],
            )
        )
    ],
)
async def api_parse_document(
    document_id: int,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    """投递解析异步任务（taskiq），返回 job 状态对象。"""
    return await KnowledgeService.request_parse(
        tenant_id, current_user.id, document_id
    )


@router.get(
    "/documents/{document_id}/chunks",
    dependencies=[
        Depends(
            require_access(
                "kuaiai.knowledge",
                "query",
                required_permissions=["kuaiai:knowledge:query"],
            )
        )
    ],
)
async def api_list_document_chunks(
    document_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    tenant_id: int = Depends(get_current_tenant),
):
    """切块只读浏览 {items,total}；不回 embedding 向量。"""
    result = await KnowledgeService.list_chunks(
        tenant_id, document_id, page=page, page_size=page_size
    )
    return {
        "items": [ChunkOut.model_validate(c) for c in result["items"]],
        "total": result["total"],
    }
