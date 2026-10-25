from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from core.api.deps.access import AuthContext, get_auth_context, require_permission_codes
from core.api.deps.deps import get_current_tenant
from core.services.logging.operation_log_service import OperationLogService
from infra.models.user import User
from infra.api.deps.deps import get_current_user
from apps.master_data.services.reset_data_service import ResetDataService

router = APIRouter(prefix="/management", tags=["App - Master Data - App Management"])

RESET_PERMISSION = "master-data:app-management:reset-data"
_TOKEN_TTL_SECONDS = 300

_ALLOWED_INPUT = ResetDataService.allowed_module_codes() | {
    ResetDataService.LEGACY_BUSINESS,
    ResetDataService.LEGACY_MASTER,
}


class ResetDataPrepareRequest(BaseModel):
    scopes: List[str] = Field(
        ...,
        min_length=1,
        description="重置模块 code 列表（见 /reset-data/modules）；也可传 business/master 展开整组",
    )

    @field_validator("scopes")
    @classmethod
    def _scopes_valid(cls, value: List[str]) -> List[str]:
        if not value:
            raise ValueError("请至少选择一个要重置的模块")
        seen: set[str] = set()
        out: List[str] = []
        for item in value:
            code = str(item or "").strip().lower()
            if not code:
                continue
            if code not in _ALLOWED_INPUT:
                raise ValueError(f"未知重置模块: {code}")
            if code not in seen:
                seen.add(code)
                out.append(code)
        if not out:
            raise ValueError("请至少选择一个要重置的模块")
        return out


class ResetDataRequest(BaseModel):
    confirmation_token: str = Field(..., min_length=16, description="二次确认 token（先调用 prepare）")
    scopes: List[str] = Field(
        ...,
        min_length=1,
        description="须与 prepare 时 scopes 一致",
    )

    @field_validator("scopes")
    @classmethod
    def _scopes_valid(cls, value: List[str]) -> List[str]:
        return ResetDataPrepareRequest._scopes_valid(value)


class ResetDataPrepareResponse(BaseModel):
    confirmation_token: str
    expires_in: int = _TOKEN_TTL_SECONDS
    scopes: List[str]
    message: str = "请在有效期内携带 confirmation_token 与相同 scopes 再次确认重置"


class ResetDataModuleItem(BaseModel):
    code: str
    group: str


def _assert_admin_gate(auth: AuthContext, *, action: str) -> None:
    if auth.is_tenant_admin or auth.is_infra_admin:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "FORBIDDEN",
            "message": f"仅组织管理员或平台管理员可{action}",
            "details": {"reason": "require_tenant_admin"},
        },
    )


def _assert_reset_gate(auth: AuthContext) -> None:
    _assert_admin_gate(auth, action="重置主数据")


@router.get(
    "/reset-data/modules",
    response_model=List[ResetDataModuleItem],
    summary="List reset-data modules",
    dependencies=[Depends(require_permission_codes(RESET_PERMISSION))],
)
async def list_reset_data_modules(
    auth: AuthContext = Depends(get_auth_context),
):
    _assert_reset_gate(auth)
    return [ResetDataModuleItem(**m) for m in ResetDataService.list_module_catalog()]


@router.post(
    "/reset-data/prepare",
    response_model=ResetDataPrepareResponse,
    summary="Prepare reset-data confirmation token",
    dependencies=[Depends(require_permission_codes(RESET_PERMISSION))],
)
async def prepare_reset_app_data(
    body: ResetDataPrepareRequest,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    auth: AuthContext = Depends(get_auth_context),
):
    _assert_reset_gate(auth)
    try:
        normalized = ResetDataService.normalize_scopes(body.scopes)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    token = ResetDataService.issue_confirmation_token(
        tenant_id=tenant_id,
        operator_id=current_user.id,
        scopes=normalized,
        ttl_seconds=_TOKEN_TTL_SECONDS,
    )
    return ResetDataPrepareResponse(
        confirmation_token=token,
        expires_in=_TOKEN_TTL_SECONDS,
        scopes=normalized,
    )


@router.post(
    "/reset-data",
    summary="Reset app data (Master Data)",
    dependencies=[Depends(require_permission_codes(RESET_PERMISSION))],
)
async def reset_app_data(
    body: ResetDataRequest,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    auth: AuthContext = Depends(get_auth_context),
):
    """
    按所选模块重置主数据。

    安全机制与快制造一致：权限码 + 管理员门禁 + 二次确认 token + 自动备份。
    """
    _assert_reset_gate(auth)
    try:
        normalized = ResetDataService.verify_confirmation_token(
            tenant_id=tenant_id,
            operator_id=current_user.id,
            token=body.confirmation_token,
            scopes=body.scopes,
            ttl_seconds=_TOKEN_TTL_SECONDS,
        )
        result = await ResetDataService.reset_master_data(
            tenant_id, current_user.id, normalized
        )
        try:
            await OperationLogService.create_operation_log(
                tenant_id=tenant_id,
                user_id=current_user.id,
                operation_type="reset_data",
                operation_module="master-data.app-management",
                operation_object_type="tenant_app_data",
                operation_object_id=tenant_id,
                operation_content=(
                    f"物理删除主数据 scopes={'+'.join(normalized)} "
                    f"success={result.get('success')} message={result.get('message')}"
                ),
                request_method="POST",
                request_path="/management/reset-data",
            )
        except Exception as log_exc:
            logger.error(f"重置主数据操作日志写入失败（删除已执行）: {log_exc}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception(f"重置主数据失败: {e}")
        return {"success": False, "message": str(e)}
