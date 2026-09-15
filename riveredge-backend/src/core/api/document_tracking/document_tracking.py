"""
单据跟踪中心API模块

提供按单据维度的操作记录时间线及关联关系查询。

Author: Luigi Lu
Date: 2026-02-20
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from core.api.deps import get_current_user, get_current_tenant
from core.services.document_tracking_service import DocumentTrackingService
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User

router = APIRouter(prefix="/document-tracking", tags=["Core - Document Tracking"])


@router.get("/resolve-by-code", summary="按单据编号精确解析单据类型与 ID")
async def resolve_document_by_code(
    code: str = Query(..., min_length=1, max_length=64, description="单据编号（精确匹配）"),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> dict:
    """
    按编号在单据登记表中精确查找，返回 document_type + document_id。
    供 IM 等场景点开详情；禁止前端按前缀猜测类型。
    """
    _ = current_user
    try:
        service = DocumentTrackingService()
        items = await service.resolve_documents_by_code(tenant_id=tenant_id, code=code)
        return {"items": items, "total": len(items)}
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_type}/{document_id}", summary="Get document tracking timeline")
async def get_document_tracking(
    document_type: str,
    document_id: int,
    tenant_id: int = Depends(get_current_tenant),
) -> dict:
    """
    获取单据的操作记录时间线及上下游关联关系

    聚合：StateTransitionLog、ApprovalRecord、DocumentRelation
    """
    try:
        service = DocumentTrackingService()
        result = await service.get_document_tracking(
            tenant_id=tenant_id,
            document_type=document_type,
            document_id=document_id,
        )
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
