"""KU-AI 运营层路由（spec 181：hub 能力矩阵 + 智能体库）。

挂载：由 ``api/router.py`` include，随应用挂到 /api/v1/apps/kuaiai。
权限矩阵（require_all=True，任一缺失即 403）：

- GET  /operations/hub            : entry:read + hub:display
- GET  /operations/agent-library  : entry:read + library:display
- PUT  /operations/agent-library/instances/{key}
                                  : entry:read + library:display + library:manage
                                    （改绑另需 agent:read，服务层复核）
- POST /operations/agent-library/instances
                                  : entry:read + library:display + library:manage
                                    + agent:read + agent:create
- GET  /operations/pulse          : entry:read + pulse:display
                                    （detector 内再复核领域读权限）
- GET  /operations/settings       : entry:read + settings:display
- PUT  /operations/settings       : entry:read + settings:display
                                    + settings:update
- GET  /operations/trust          : entry:read + trust:display（spec 184）
- GET  /operations/corpus         : entry:read + corpus:display
- GET  /operations/corpus/knowledge-options
                                  : entry:read + corpus:display
- POST /operations/corpus/faqs    : + corpus:create（201 语料项）
- POST /operations/corpus/seed-faqs
                                  : + corpus:create（幂等 {created,skipped}）
- POST /operations/corpus/batch-index
                                  : + corpus:update（逐项结果）
- POST /operations/corpus/batch-delete
                                  : + corpus:delete（逐项结果）
- GET  /operations/corpus/export.jsonl
                                  : + corpus:export（JSONL 流式下载）

路由只编排；模板合并、开关、脱敏、克隆与租户隔离规则均在服务层。
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from apps.kuaiai.schemas.corpus import (
    CorpusBatchIn,
    CorpusBatchOut,
    CorpusFaqCreate,
    CorpusItemOut,
    CorpusKnowledgeOption,
    CorpusListOut,
    CorpusSeedFaqsIn,
    CorpusSeedFaqsOut,
)
from apps.kuaiai.schemas.operations import (
    HubOut,
    LibraryItemOut,
    LibraryOut,
    SceneInstanceClone,
    SceneInstanceUpdate,
    SettingsOut,
    SettingsUpdateIn,
    TrustOut,
)
from apps.kuaiai.schemas.pulse import PulseOut
from apps.kuaiai.services import (
    agent_scene_service,
    corpus_service,
    operations_service,
    settings_service,
)
from apps.kuaiai.services.pulse import registry as pulse_registry
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user

router = APIRouter(prefix="/operations", tags=["App - KU-AI Operations"])


@router.get(
    "/hub",
    response_model=HubOut,
    dependencies=[
        Depends(
            require_permission_codes(
                "kuaiai:entry:read",
                "kuaiai:hub:display",
                require_all=True,
            )
        )
    ],
)
async def api_get_hub(
    days: int = Query(7, ge=1, le=90),
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    """能力矩阵聚合：模型/四项指标/八能力状态（局部降级，不伪造）。"""
    return await operations_service.get_hub(tenant_id, days, current_user)


@router.get(
    "/agent-library",
    response_model=LibraryOut,
    dependencies=[
        Depends(
            require_permission_codes(
                "kuaiai:entry:read",
                "kuaiai:library:display",
                require_all=True,
            )
        )
    ],
)
async def api_get_agent_library(
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    """智能体库：六预置项 + 租户复制项 + provisioning 状态。"""
    return await agent_scene_service.list_agent_library(
        tenant_id, current_user
    )


@router.put(
    "/agent-library/instances/{instance_key}",
    response_model=LibraryItemOut,
    dependencies=[
        Depends(
            require_permission_codes(
                "kuaiai:entry:read",
                "kuaiai:library:display",
                "kuaiai:library:manage",
                require_all=True,
            )
        )
    ],
)
async def api_update_agent_library_instance(
    instance_key: str,
    payload: SceneInstanceUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    """实例定制/改绑/单项开关（改绑服务层另复核 agent:read）。"""
    return await agent_scene_service.update_instance(
        tenant_id,
        current_user,
        instance_key,
        payload.model_dump(exclude_unset=True),
    )


@router.post(
    "/agent-library/instances",
    response_model=LibraryItemOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_permission_codes(
                "kuaiai:entry:read",
                "kuaiai:library:display",
                "kuaiai:library:manage",
                "kuaiai:agent:read",
                "kuaiai:agent:create",
                require_all=True,
            )
        )
    ],
)
async def api_clone_agent_library_instance(
    payload: SceneInstanceClone,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    """按模板 + 本租户源档案克隆停用无授权档案并原子创建复制实例。"""
    overrides = (
        payload.overrides.model_dump(exclude_unset=True)
        if payload.overrides
        else None
    )
    return await agent_scene_service.clone_instance(
        tenant_id,
        current_user,
        payload.template_key,
        payload.source_agent_id,
        overrides,
    )


@router.get(
    "/pulse",
    response_model=PulseOut,
    dependencies=[
        Depends(
            require_permission_codes(
                "kuaiai:entry:read",
                "kuaiai:pulse:display",
                require_all=True,
            )
        )
    ],
)
async def api_get_pulse(
    domain: Optional[str] = Query(
        None,
        description="逗号分隔单参数：production|inventory|sales|quality|equipment，空=全部",
    ),
    severity: Optional[str] = Query(
        None, pattern="^(info|warning|error|critical)$"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=100),
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    """异常感知聚合：五领域 detector 编排 + 局部错误脱敏（spec 182）。"""
    try:
        domains = pulse_registry.parse_domains(domain)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    return await pulse_registry.run_pulse(
        tenant_id,
        current_user,
        domains=domains,
        severity=severity,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/settings",
    response_model=SettingsOut,
    dependencies=[
        Depends(
            require_permission_codes(
                "kuaiai:entry:read",
                "kuaiai:settings:display",
                require_all=True,
            )
        )
    ],
)
async def api_get_operations_settings(
    tenant_id: int = Depends(get_current_tenant),
):
    """模型与能力设置聚合：角色候选/OCR 脱敏/六开关/能力项/乐观版本。"""
    return await settings_service.get_settings(tenant_id)


@router.put(
    "/settings",
    response_model=SettingsOut,
    dependencies=[
        Depends(
            require_permission_codes(
                "kuaiai:entry:read",
                "kuaiai:settings:display",
                "kuaiai:settings:update",
                require_all=True,
            )
        )
    ],
)
async def api_update_operations_settings(
    payload: SettingsUpdateIn,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    """设置原子保存：锁内版本比对（409）+ 白名单深合并，返回新快照。"""
    return await settings_service.update_settings(
        tenant_id, current_user, payload
    )


@router.get(
    "/trust",
    response_model=TrustOut,
    dependencies=[
        Depends(
            require_permission_codes(
                "kuaiai:entry:read",
                "kuaiai:trust:display",
                require_all=True,
            )
        )
    ],
)
async def api_get_trust(
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    """信任中心聚合：RBAC/HITL/审计三卡 + 当前用户权限码视图（spec 184）。

    不接收 user_id；只回当前用户持有状态。审计明细仍走既有
    /core/ai/audit/logs（本端点不复制审计数据）。
    """
    return await operations_service.get_trust(tenant_id, current_user)


# ============================================================ 知识语料（spec 183）


@router.get(
    "/corpus",
    response_model=CorpusListOut,
    dependencies=[
        Depends(
            require_permission_codes(
                "kuaiai:entry:read",
                "kuaiai:corpus:display",
                require_all=True,
            )
        )
    ],
)
async def api_list_corpus(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    knowledge_id: Optional[int] = Query(None, ge=1),
    doc_type: Optional[str] = Query(
        None, alias="type", pattern="^(faq|text|file)$"
    ),
    doc_status: Optional[str] = Query(
        None, alias="status", pattern="^(pending|parsing|ready|failed)$"
    ),
    created_from: Optional[date] = Query(None),
    created_to: Optional[date] = Query(None),
    tenant_id: int = Depends(get_current_tenant),
):
    """跨知识库扁平语料分页：本租户、不回 raw_content/存储键。"""
    result = await corpus_service.list_corpus(
        tenant_id,
        page=page,
        page_size=page_size,
        keyword=keyword,
        knowledge_id=knowledge_id,
        doc_type=doc_type,
        doc_status=doc_status,
        created_from=created_from,
        created_to=created_to,
    )
    return {
        "items": result["items"],
        "total": result["total"],
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/corpus/knowledge-options",
    response_model=List[CorpusKnowledgeOption],
    dependencies=[
        Depends(
            require_permission_codes(
                "kuaiai:entry:read",
                "kuaiai:corpus:display",
                require_all=True,
            )
        )
    ],
)
async def api_corpus_knowledge_options(
    tenant_id: int = Depends(get_current_tenant),
):
    """语料页启用知识库下拉项（筛选/FAQ 归属必选；不要求知识库权限）。"""
    return await corpus_service.knowledge_options(tenant_id)


@router.post(
    "/corpus/faqs",
    response_model=CorpusItemOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_permission_codes(
                "kuaiai:entry:read",
                "kuaiai:corpus:display",
                "kuaiai:corpus:create",
                require_all=True,
            )
        )
    ],
)
async def api_create_corpus_faq(
    payload: CorpusFaqCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    """FAQ 语料创建：必选本租户启用知识库，落库 pending 走既有解析管线。"""
    return await corpus_service.create_faq(tenant_id, current_user, payload)


@router.post(
    "/corpus/seed-faqs",
    response_model=CorpusSeedFaqsOut,
    dependencies=[
        Depends(
            require_permission_codes(
                "kuaiai:entry:read",
                "kuaiai:corpus:display",
                "kuaiai:corpus:create",
                require_all=True,
            )
        )
    ],
)
async def api_seed_corpus_faqs(
    payload: CorpusSeedFaqsIn,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    """出厂 FAQ 幂等加载：同题（含人工 FAQ）跳过不覆盖，库行锁串行化。"""
    return await corpus_service.seed_faqs(
        tenant_id, current_user, payload.knowledge_id
    )


@router.post(
    "/corpus/batch-index",
    response_model=CorpusBatchOut,
    dependencies=[
        Depends(
            require_permission_codes(
                "kuaiai:entry:read",
                "kuaiai:corpus:display",
                "kuaiai:corpus:update",
                require_all=True,
            )
        )
    ],
)
async def api_batch_index_corpus(
    payload: CorpusBatchIn,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    """批量索引/重试：逐项调用同一 request_parse，逐项租户复核。"""
    return await corpus_service.batch_index(
        tenant_id, current_user, payload.ids
    )


@router.post(
    "/corpus/batch-delete",
    response_model=CorpusBatchOut,
    dependencies=[
        Depends(
            require_permission_codes(
                "kuaiai:entry:read",
                "kuaiai:corpus:display",
                "kuaiai:corpus:delete",
                require_all=True,
            )
        )
    ],
)
async def api_batch_delete_corpus(
    payload: CorpusBatchIn,
    tenant_id: int = Depends(get_current_tenant),
):
    """批量删除：逐项事务软删（chunks 同事务），逐项返回结果。"""
    return await corpus_service.batch_delete(tenant_id, payload.ids)


@router.get(
    "/corpus/export.jsonl",
    dependencies=[
        Depends(
            require_permission_codes(
                "kuaiai:entry:read",
                "kuaiai:corpus:display",
                "kuaiai:corpus:export",
                require_all=True,
            )
        )
    ],
)
async def api_export_corpus_jsonl(
    keyword: Optional[str] = Query(None),
    knowledge_id: Optional[int] = Query(None, ge=1),
    doc_type: Optional[str] = Query(
        None, alias="type", pattern="^(faq|text|file)$"
    ),
    doc_status: Optional[str] = Query(
        None, alias="status", pattern="^(pending|parsing|ready|failed)$"
    ),
    created_from: Optional[date] = Query(None),
    created_to: Optional[date] = Query(None),
    tenant_id: int = Depends(get_current_tenant),
):
    """训练 JSONL 流式导出：白名单字段、分批硬上限、UTF-8 一行一 JSON。"""
    stream = corpus_service.iter_export_jsonl(
        tenant_id,
        keyword=keyword,
        knowledge_id=knowledge_id,
        doc_type=doc_type,
        doc_status=doc_status,
        created_from=created_from,
        created_to=created_to,
    )
    return StreamingResponse(
        stream,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": 'attachment; filename="corpus-export.jsonl"'
        },
    )
