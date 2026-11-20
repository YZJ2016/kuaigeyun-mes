"""
单据关联关系API模块

提供单据关联关系查询的API接口。

Author: Luigi Lu
Date: 2025-01-14
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any

from core.api.deps import get_current_user, get_current_tenant
from core.api.deps.access import require_permission_codes
from infra.models.user import User
from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService
from apps.kuaizhizao.services.document_attachment_center_service import DocumentAttachmentCenterService
from apps.kuaizhizao.schemas.document_relation import (
    DocumentAttachmentCenterResponse,
    DocumentRelationListResponse,
    DocumentTraceResponse,
)
from apps.kuaizhizao.schemas.document_line_material_attachments import (
    DocumentLineMaterialAttachmentSourcesResponse,
)
from apps.kuaizhizao.services.document_line_material_attachment_source_service import (
    DocumentLineMaterialAttachmentSourceService,
)
from infra.exceptions.exceptions import NotFoundError, ValidationError

router = APIRouter(prefix="/document-relations", tags=["App - Kuaige Zhizao - Document Relations"])

_DOCUMENT_LINE_MATERIAL_ATTACHMENT_READ = require_permission_codes(
    "kuaizhizao:purchase-requisition:read",
    "kuaizhizao:purchase-order:read",
    "kuaizhizao:inbound:read",
    "kuaizhizao:quotation:read",
    "kuaizhizao:sales-order:read",
    "kuaizhizao:outbound:read",
    "master-data:material:read",
    "master-data:material:display",
    "master-data:process:drawing:read",
    require_all=False,
)


@router.get(
    "/material-line-attachment-sources",
    response_model=DocumentLineMaterialAttachmentSourcesResponse,
    summary="List material images and engineering drawings for document line picker",
    dependencies=[Depends(_DOCUMENT_LINE_MATERIAL_ATTACHMENT_READ)],
)
async def list_material_line_attachment_sources(
    material_id: int = Query(..., ge=1, description="物料 ID"),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> DocumentLineMaterialAttachmentSourcesResponse:
    service = DocumentLineMaterialAttachmentSourceService()
    try:
        return await service.list_sources_for_material(
            tenant_id,
            material_id,
            current_user=current_user,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{document_type}/{document_id}", response_model=DocumentRelationListResponse, summary="List document relations")
async def get_document_relations(
    document_type: str,
    document_id: int,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant)
) -> DocumentRelationListResponse:
    """
    获取单据的关联关系（上游和下游单据）
    
    Args:
        document_type: 单据类型（如：demand、work_order等）
        document_id: 单据ID
        
    Returns:
        DocumentRelationListResponse: 包含上游和下游单据的响应
    """
    try:
        service = DocumentRelationNewService()
        result = await service.get_relations(
            tenant_id=tenant_id,
            document_type=document_type,
            document_id=document_id
        )
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取单据关联关系失败: {str(e)}")


@router.get(
    "/{document_type}/{document_id}/attachment-center",
    response_model=DocumentAttachmentCenterResponse,
    summary="Aggregate attachments across document chain",
)
async def get_document_attachment_center(
    document_type: str,
    document_id: int,
    max_depth: int = Query(10, ge=1, le=20, description="最大追溯深度（默认10层）"),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> DocumentAttachmentCenterResponse:
    """
    聚合本单与全链路关联单据的 attachments JSON。
    """
    try:
        service = DocumentAttachmentCenterService()
        return await service.get_attachment_center(
            tenant_id=tenant_id,
            document_type=document_type,
            document_id=document_id,
            max_depth=max_depth,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取附件中心失败: {str(e)}")


@router.get("/{document_type}/{document_id}/trace", response_model=DocumentTraceResponse, summary="Trace document relation chain")
async def trace_document_chain(
    document_type: str,
    document_id: int,
    direction: str = Query("both", description="追溯方向（upstream: 向上追溯, downstream: 向下追溯, both: 双向追溯）"),
    max_depth: int = Query(10, ge=1, le=20, description="最大追溯深度（防止无限递归，默认10层）"),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant)
) -> DocumentTraceResponse:
    """
    追溯单据关联链（完整追溯）
    
    支持向上追溯（查找所有上游单据）和向下追溯（查找所有下游单据），
    自动避免循环引用。
    
    Args:
        document_type: 单据类型（如：demand、work_order等）
        document_id: 单据ID
        direction: 追溯方向（upstream: 向上追溯, downstream: 向下追溯, both: 双向追溯）
        max_depth: 最大追溯深度（防止无限递归，默认10层）
        
    Returns:
        DocumentTraceResponse: 完整的追溯链
    """
    try:
        service = DocumentRelationNewService()
        result = await service.trace_document_chain(
            tenant_id=tenant_id,
            document_type=document_type,
            document_id=document_id,
            direction=direction,
            max_depth=max_depth
        )
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"追溯单据关联链失败: {str(e)}")
