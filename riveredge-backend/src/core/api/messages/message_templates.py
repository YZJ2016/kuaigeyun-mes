"""
消息模板管理 API 路由

提供消息模板的 CRUD 操作。
"""

from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query

from core.schemas.message_template import (
    MessageTemplateCreate,
    MessageTemplateUpdate,
    MessageTemplateResponse,
)
from core.schemas.resource_category import (
    ResourceCategoryCreate,
    ResourceCategoryUpdate,
    ResourceCategoryResponse,
    ResourceCategoryListResponse,
)
from core.services.messaging.message_template_service import MessageTemplateService
from core.services.resource.resource_category_service import ResourceCategoryService
from core.services.resource.collab_function_category_service import CollabFunctionCategoryService
from core.models.resource_category import RESOURCE_TYPE_MESSAGE_TEMPLATE
from core.api.deps.deps import get_current_tenant
from core.services.system.installed_feature_scope import get_installed_application_codes
from core.services.system.installed_feature_scope import message_template_codes_for_installed_apps
from infra.api.deps.deps import get_current_user as soil_get_current_user
from infra.models.user import User
from infra.exceptions.exceptions import NotFoundError, ValidationError

router = APIRouter(prefix="/message-templates", tags=["Core - Message Templates"])


@router.post("", response_model=MessageTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_message_template(
    data: MessageTemplateCreate,
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """
    创建消息模板
    
    创建新的消息模板并保存到数据库。
    
    Args:
        data: 消息模板创建数据
        tenant_id: 当前组织ID（依赖注入）
        
    Returns:
        MessageTemplateResponse: 创建的消息模板对象
        
    Raises:
        HTTPException: 当模板代码已存在时抛出
    """
    try:
        message_template = await MessageTemplateService.create_message_template(
            tenant_id=tenant_id,
            data=data
        )
        return MessageTemplateService.build_message_template_response(message_template)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )


@router.get("", response_model=List[MessageTemplateResponse])
async def list_message_templates(
    skip: int = Query(0, ge=0, description="跳过数量"),
    limit: int = Query(100, ge=1, le=1000, description="限制数量"),
    type: Optional[str] = Query(None, description="消息类型（可选）"),
    is_active: Optional[bool] = Query(None, description="是否启用（可选）"),
    keyword: Optional[str] = Query(None, description="模糊搜索（名称、代码、描述、主题）"),
    category_uuid: Optional[UUID] = Query(None, description="分类 UUID 筛选"),
    no_category: bool = Query(False, description="仅未分类"),
    tenant_id: int = Depends(get_current_tenant),
):
    """
    获取消息模板列表
    
    获取当前组织的消息模板列表，支持分页和筛选。
    
    Args:
        skip: 跳过数量（默认 0）
        limit: 限制数量（默认 100，最大 1000）
        type: 消息类型（可选）
        is_active: 是否启用（可选）
        tenant_id: 当前组织ID（依赖注入）
        
    Returns:
        List[MessageTemplateResponse]: 消息模板列表
    """
    if category_uuid and no_category:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="category_uuid 与 no_category 不能同时使用",
        )
    message_templates = await MessageTemplateService.list_message_templates(
        tenant_id=tenant_id,
        skip=skip,
        limit=limit,
        type=type,
        is_active=is_active,
        keyword=keyword,
        installed_app_codes=await get_installed_application_codes(tenant_id),
        category_uuid=category_uuid,
        no_category=no_category,
    )
    return [
        MessageTemplateService.build_message_template_response(mt) for mt in message_templates
    ]


@router.get("/categories", response_model=ResourceCategoryListResponse)
async def list_message_template_categories(
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """获取消息模板分类列表"""
    try:
        result = await ResourceCategoryService().list_categories(
            tenant_id, RESOURCE_TYPE_MESSAGE_TEMPLATE
        )
        return ResourceCategoryListResponse(**result)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取消息模板分类失败: {str(e)}",
        )


@router.post("/categories", response_model=ResourceCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_message_template_category(
    data: ResourceCategoryCreate,
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """创建消息模板分类"""
    try:
        category = await ResourceCategoryService().create_category(
            tenant_id, RESOURCE_TYPE_MESSAGE_TEMPLATE, data
        )
        return ResourceCategoryService()._build_response(category, 0)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建消息模板分类失败: {str(e)}",
        )


@router.get("/categories/{category_uuid}", response_model=ResourceCategoryResponse)
async def get_message_template_category(
    category_uuid: UUID,
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """获取消息模板分类详情"""
    try:
        category = await ResourceCategoryService().get_category_by_uuid(
            tenant_id, RESOURCE_TYPE_MESSAGE_TEMPLATE, category_uuid
        )
        count = await ResourceCategoryService()._count_items(
            tenant_id, RESOURCE_TYPE_MESSAGE_TEMPLATE, category.id
        )
        return ResourceCategoryService()._build_response(category, count)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取消息模板分类失败: {str(e)}",
        )


@router.put("/categories/{category_uuid}", response_model=ResourceCategoryResponse)
async def update_message_template_category(
    category_uuid: UUID,
    data: ResourceCategoryUpdate,
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """更新消息模板分类"""
    try:
        category = await ResourceCategoryService().update_category(
            tenant_id, RESOURCE_TYPE_MESSAGE_TEMPLATE, category_uuid, data
        )
        count = await ResourceCategoryService()._count_items(
            tenant_id, RESOURCE_TYPE_MESSAGE_TEMPLATE, category.id
        )
        return ResourceCategoryService()._build_response(category, count)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新消息模板分类失败: {str(e)}",
        )


@router.post("/categories/load-function-presets")
async def load_message_template_function_categories(
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """按功能域预置消息模板分类，并回填未分类模板。"""
    try:
        return await CollabFunctionCategoryService().load_function_presets(
            tenant_id,
            RESOURCE_TYPE_MESSAGE_TEMPLATE,
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"预置消息模板分类失败: {str(e)}",
        )


@router.delete("/categories/{category_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message_template_category(
    category_uuid: UUID,
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """删除消息模板分类（分类下模板变为未分类）"""
    try:
        await ResourceCategoryService().delete_category(
            tenant_id, RESOURCE_TYPE_MESSAGE_TEMPLATE, category_uuid
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除消息模板分类失败: {str(e)}",
        )


@router.get("/{uuid}", response_model=MessageTemplateResponse)
async def get_message_template(
    uuid: str,
    tenant_id: int = Depends(get_current_tenant),
):
    """
    获取消息模板详情
    
    根据UUID获取消息模板的详细信息。
    
    Args:
        uuid: 消息模板UUID
        tenant_id: 当前组织ID（依赖注入）
        
    Returns:
        MessageTemplateResponse: 消息模板对象
        
    Raises:
        HTTPException: 当消息模板不存在时抛出
    """
    try:
        message_template = await MessageTemplateService.get_message_template_by_uuid(
            tenant_id=tenant_id,
            uuid=uuid
        )
        return MessageTemplateService.build_message_template_response(message_template)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.put("/{uuid}", response_model=MessageTemplateResponse)
async def update_message_template(
    uuid: str,
    data: MessageTemplateUpdate,
    tenant_id: int = Depends(get_current_tenant),
):
    """
    更新消息模板
    
    更新消息模板信息。
    
    Args:
        uuid: 消息模板UUID
        data: 消息模板更新数据
        tenant_id: 当前组织ID（依赖注入）
        
    Returns:
        MessageTemplateResponse: 更新后的消息模板对象
        
    Raises:
        HTTPException: 当消息模板不存在时抛出
    """
    try:
        message_template = await MessageTemplateService.update_message_template(
            tenant_id=tenant_id,
            uuid=uuid,
            data=data
        )
        return MessageTemplateService.build_message_template_response(message_template)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message_template(
    uuid: str,
    tenant_id: int = Depends(get_current_tenant),
):
    """
    删除消息模板（软删除）
    
    删除消息模板。
    
    Args:
        uuid: 消息模板UUID
        tenant_id: 当前组织ID（依赖注入）
        
    Raises:
        HTTPException: 当消息模板不存在时抛出
    """
    try:
        await MessageTemplateService.delete_message_template(
            tenant_id=tenant_id,
            uuid=uuid
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/load-preset")
async def load_preset_message_templates(
    current_user: User = Depends(soil_get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    """
    加载消息模板预设

    为当前组织加载中国中小制造业极简消息模板预设（审批通知、验证码、欢迎邮件等）。
    """
    installed_app_codes = await get_installed_application_codes(tenant_id)
    visible_codes = message_template_codes_for_installed_apps(installed_app_codes)
    count = await MessageTemplateService.load_preset_sme(
        tenant_id,
        only_codes=visible_codes,
    )
    if "haoligo" in installed_app_codes:
        from apps.haoligo.services.haoligo_message_template_registry import (
            load_haoligo_message_template_presets,
        )

        count += await load_haoligo_message_template_presets(tenant_id)
    return {"created": count, "message": f"成功加载 {count} 个消息模板预设"}


