"""数据源登记路由。"""

from fastapi import APIRouter, Depends, status

from apps.kuaireport.schemas.data_source import DataSourceCreate, DataSourceOut, DataSourceUpdate
from apps.kuaireport.services import data_source_service
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user

router = APIRouter(prefix="/data-sources", tags=["App - 星报表 - 数据源"])


@router.get(
    "",
    response_model=list[DataSourceOut],
    dependencies=[Depends(require_permission_codes("kuaireport:data-source:display"))],
)
async def api_list_data_sources(tenant_id: int = Depends(get_current_tenant)):
    return await data_source_service.list_data_sources(tenant_id)


@router.post(
    "",
    response_model=DataSourceOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission_codes("kuaireport:data-source:create"))],
)
async def api_create_data_source(
    payload: DataSourceCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await data_source_service.create_data_source(
        tenant_id, payload, user_id=getattr(current_user, "id", None)
    )


@router.get(
    "/{source_id}",
    response_model=DataSourceOut,
    dependencies=[Depends(require_permission_codes("kuaireport:data-source:read"))],
)
async def api_get_data_source(source_id: int, tenant_id: int = Depends(get_current_tenant)):
    return await data_source_service.get_data_source(tenant_id, source_id)


@router.put(
    "/{source_id}",
    response_model=DataSourceOut,
    dependencies=[Depends(require_permission_codes("kuaireport:data-source:update"))],
)
async def api_update_data_source(
    source_id: int,
    payload: DataSourceUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user=Depends(get_current_user),
):
    return await data_source_service.update_data_source(
        tenant_id, source_id, payload, user_id=getattr(current_user, "id", None)
    )


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission_codes("kuaireport:data-source:delete"))],
)
async def api_delete_data_source(source_id: int, tenant_id: int = Depends(get_current_tenant)):
    await data_source_service.delete_data_source(tenant_id, source_id)
