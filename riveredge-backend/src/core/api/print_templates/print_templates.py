"""
打印模板管理 API 路由

提供打印模板的 CRUD 操作和模板渲染功能。
"""

from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query

from core.schemas.print_template import (
    PrintTemplateCreate,
    PrintTemplateUpdate,
    PrintTemplateRenderRequest,
    PrintTemplateCompileRequest,
    PrintTemplateCompilePreviewRequest,
    PrintTemplateResponse,
    PrintTemplateRenderResponse,
    PrintTemplateCompileResponse,
    PrintTemplateCompilePreviewResponse,
)
from core.schemas.resource_category import (
    ResourceCategoryCreate,
    ResourceCategoryUpdate,
    ResourceCategoryResponse,
    ResourceCategoryListResponse,
)
from core.services.print.print_template_service import PrintTemplateService
from core.services.resource.resource_category_service import ResourceCategoryService
from core.services.resource.collab_function_category_service import CollabFunctionCategoryService
from core.models.resource_category import RESOURCE_TYPE_PRINT_TEMPLATE
from core.api.deps.deps import get_current_tenant
from core.services.system.installed_feature_scope import get_installed_application_codes
from infra.api.deps.deps import get_current_user as soil_get_current_user
from infra.models.user import User
from infra.exceptions.exceptions import NotFoundError, ValidationError

router = APIRouter(prefix="/print-templates", tags=["Core - Print Templates"])


@router.post("", response_model=PrintTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_print_template(
    data: PrintTemplateCreate,
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """
    创建打印模板
    
    创建新的打印模板。
    
    Args:
        data: 打印模板创建数据
        tenant_id: 当前组织ID（依赖注入）
        
    Returns:
        PrintTemplateResponse: 创建的打印模板对象
        
    Raises:
        HTTPException: 当模板代码已存在时抛出
    """
    try:
        print_template = await PrintTemplateService.create_print_template(
            tenant_id=tenant_id,
            data=data
        )
        return PrintTemplateService.build_print_template_response(print_template)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )


@router.get("", response_model=List[PrintTemplateResponse])
async def list_print_templates(
    skip: int = Query(0, ge=0, description="跳过数量"),
    limit: int = Query(100, ge=1, le=1000, description="限制数量"),
    type: Optional[str] = Query(None, description="模板类型（可选）"),
    is_active: Optional[bool] = Query(None, description="是否启用（可选）"),
    document_type: Optional[str] = Query(None, description="关联业务单据类型（可选，按 config.document_type 筛选）"),
    keyword: Optional[str] = Query(None, description="模糊搜索（名称、代码、描述）"),
    category_uuid: Optional[UUID] = Query(None, description="分类 UUID 筛选"),
    no_category: bool = Query(False, description="仅未分类"),
    tenant_id: int = Depends(get_current_tenant),
):
    """
    获取打印模板列表
    
    获取当前组织的打印模板列表，支持分页和筛选。
    
    Args:
        skip: 跳过数量（默认 0）
        limit: 限制数量（默认 100，最大 1000）
        type: 模板类型（可选）
        is_active: 是否启用（可选）
        tenant_id: 当前组织ID（依赖注入）
        
    Returns:
        List[PrintTemplateResponse]: 打印模板列表
    """
    if category_uuid and no_category:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="category_uuid 与 no_category 不能同时使用",
        )
    print_templates = await PrintTemplateService.list_print_templates(
        tenant_id=tenant_id,
        skip=skip,
        limit=limit,
        type=type,
        is_active=is_active,
        document_type=document_type,
        keyword=keyword,
        installed_app_codes=await get_installed_application_codes(tenant_id),
        category_uuid=category_uuid,
        no_category=no_category,
    )
    return [
        PrintTemplateService.build_print_template_response(pt) for pt in print_templates
    ]


@router.get("/categories", response_model=ResourceCategoryListResponse)
async def list_print_template_categories(
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """获取打印模板分类列表"""
    try:
        result = await ResourceCategoryService().list_categories(
            tenant_id, RESOURCE_TYPE_PRINT_TEMPLATE
        )
        return ResourceCategoryListResponse(**result)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取打印模板分类失败: {str(e)}",
        )


@router.post("/categories", response_model=ResourceCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_print_template_category(
    data: ResourceCategoryCreate,
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """创建打印模板分类"""
    try:
        category = await ResourceCategoryService().create_category(
            tenant_id, RESOURCE_TYPE_PRINT_TEMPLATE, data
        )
        return ResourceCategoryService()._build_response(category, 0)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建打印模板分类失败: {str(e)}",
        )


@router.get("/categories/{category_uuid}", response_model=ResourceCategoryResponse)
async def get_print_template_category(
    category_uuid: UUID,
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """获取打印模板分类详情"""
    try:
        category = await ResourceCategoryService().get_category_by_uuid(
            tenant_id, RESOURCE_TYPE_PRINT_TEMPLATE, category_uuid
        )
        count = await ResourceCategoryService()._count_items(
            tenant_id, RESOURCE_TYPE_PRINT_TEMPLATE, category.id
        )
        return ResourceCategoryService()._build_response(category, count)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取打印模板分类失败: {str(e)}",
        )


@router.put("/categories/{category_uuid}", response_model=ResourceCategoryResponse)
async def update_print_template_category(
    category_uuid: UUID,
    data: ResourceCategoryUpdate,
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """更新打印模板分类"""
    try:
        category = await ResourceCategoryService().update_category(
            tenant_id, RESOURCE_TYPE_PRINT_TEMPLATE, category_uuid, data
        )
        count = await ResourceCategoryService()._count_items(
            tenant_id, RESOURCE_TYPE_PRINT_TEMPLATE, category.id
        )
        return ResourceCategoryService()._build_response(category, count)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新打印模板分类失败: {str(e)}",
        )


@router.post("/categories/load-function-presets")
async def load_print_template_function_categories(
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """按功能域预置打印模板分类，并回填未分类模板。"""
    try:
        return await CollabFunctionCategoryService().load_function_presets(
            tenant_id,
            RESOURCE_TYPE_PRINT_TEMPLATE,
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"预置打印模板分类失败: {str(e)}",
        )


@router.delete("/categories/{category_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_print_template_category(
    category_uuid: UUID,
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """删除打印模板分类（分类下模板变为未分类）"""
    try:
        await ResourceCategoryService().delete_category(
            tenant_id, RESOURCE_TYPE_PRINT_TEMPLATE, category_uuid
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除打印模板分类失败: {str(e)}",
        )


@router.get("/next-code")
async def get_next_print_template_code(
    base_code: str = Query(..., min_length=1, description="模板代码基名（如 QUOTATION_PRINT）"),
    tenant_id: int = Depends(get_current_tenant),
):
    """
    获取下一个模板代码预览（不占号）。
    """
    code = await PrintTemplateService.preview_next_template_code(
        tenant_id=tenant_id,
        raw_code=base_code,
    )
    return {"code": code}


@router.get("/{uuid}", response_model=PrintTemplateResponse)
async def get_print_template(
    uuid: str,
    tenant_id: int = Depends(get_current_tenant),
):
    """
    获取打印模板详情
    
    根据UUID获取打印模板详情。
    
    Args:
        uuid: 打印模板UUID
        tenant_id: 当前组织ID（依赖注入）
        
    Returns:
        PrintTemplateResponse: 打印模板对象
        
    Raises:
        HTTPException: 当打印模板不存在时抛出
    """
    try:
        print_template = await PrintTemplateService.get_print_template_by_uuid(
            tenant_id=tenant_id,
            uuid=uuid
        )
        return PrintTemplateService.build_print_template_response(print_template)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.put("/{uuid}", response_model=PrintTemplateResponse)
async def update_print_template(
    uuid: str,
    data: PrintTemplateUpdate,
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """
    更新打印模板
    
    更新打印模板信息。
    
    Args:
        uuid: 打印模板UUID
        data: 打印模板更新数据
        tenant_id: 当前组织ID（依赖注入）
        
    Returns:
        PrintTemplateResponse: 更新后的打印模板对象
        
    Raises:
        HTTPException: 当打印模板不存在时抛出
    """
    try:
        print_template = await PrintTemplateService.update_print_template(
            tenant_id=tenant_id,
            uuid=uuid,
            data=data
        )
        return PrintTemplateService.build_print_template_response(print_template)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_print_template(
    uuid: str,
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """
    删除打印模板
    
    软删除打印模板。
    
    Args:
        uuid: 打印模板UUID
        tenant_id: 当前组织ID（依赖注入）
        
    Raises:
        HTTPException: 当打印模板不存在时抛出
    """
    try:
        await PrintTemplateService.delete_print_template(
            tenant_id=tenant_id,
            uuid=uuid
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/load-preset")
async def load_preset_print_templates(
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """
    加载打印模板预设

    为当前组织加载系统打印模板预设；预设项会按已安装应用自动过滤。
    """
    count = await PrintTemplateService.load_all_preset_print_templates(tenant_id)
    return {"created": count, "message": f"成功加载 {count} 个打印模板预设"}


@router.post("/{uuid}/render", response_model=PrintTemplateRenderResponse)
async def render_print_template(
    uuid: str,
    data: PrintTemplateRenderRequest,
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """
    渲染打印模板
    
    渲染打印模板（同步或异步）。
    
    Args:
        uuid: 打印模板UUID
        data: 渲染请求数据
        current_user: 当前用户（依赖注入）
        tenant_id: 当前组织ID（依赖注入）
        
    Returns:
        PrintTemplateRenderResponse: 渲染结果
        
    Raises:
        HTTPException: 当打印模板不存在或渲染失败时抛出
    """
    try:
        result = await PrintTemplateService.render_print_template(
            tenant_id=tenant_id,
            uuid=uuid,
            data=data
        )
        return PrintTemplateRenderResponse(**result)
    except (NotFoundError, ValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )


@router.post("/compile", response_model=PrintTemplateCompileResponse)
async def compile_print_template(
    data: PrintTemplateCompileRequest,
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """
    编译可视化模板 schema 为可执行 Jinja 模板。
    """
    try:
        result = PrintTemplateService.compile_designer_schema(data)
        return PrintTemplateCompileResponse(**result)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )


@router.post("/compile-preview", response_model=PrintTemplateCompilePreviewResponse)
async def compile_preview_print_template(
    data: PrintTemplateCompilePreviewRequest,
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """
    编译可视化模板并使用样本数据返回预览 HTML。
    """
    try:
        preview_data = dict(data.preview_data or {})
        preview_data.setdefault("page_num", 1)
        preview_data.setdefault("total_pages", 1)
        if not preview_data.get("company_logo"):
            from apps.kuaizhizao.services.print_service import _resolve_company_logo_for_print

            preview_data["company_logo"] = await _resolve_company_logo_for_print(tenant_id)
        if not preview_data.get("logo"):
            preview_data["logo"] = preview_data.get("company_logo") or ""
        if not preview_data.get("company_seal"):
            from apps.kuaizhizao.services.print_service import _resolve_company_seal_for_print

            preview_data["company_seal"] = await _resolve_company_seal_for_print(tenant_id)

        enriched = data.model_copy(update={"preview_data": preview_data})
        result = PrintTemplateService.compile_and_preview_designer_schema(enriched)
        return PrintTemplateCompilePreviewResponse(**result)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )

