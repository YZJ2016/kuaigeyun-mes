"""
接口 Schema 模块

定义接口相关的 Pydantic Schema，用于数据验证和序列化。
"""

from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime
from uuid import UUID

ApiSyncDirection = Literal["pull", "push", "bidirectional"]
VALID_API_SYNC_DIRECTIONS = frozenset({"pull", "push", "bidirectional"})
ApiInterfaceType = Literal["standard", "custom"]


def normalize_api_sync_direction(value: Optional[str]) -> ApiSyncDirection:
    direction = (value or "pull").strip() or "pull"
    if direction not in VALID_API_SYNC_DIRECTIONS:
        raise ValueError("同步方向须为 pull、push 或 bidirectional")
    return direction  # type: ignore[return-value]


class APIBase(BaseModel):
    """接口基础 Schema"""
    name: str = Field(..., max_length=100, description="接口名称")
    code: str = Field(..., max_length=50, description="接口代码")
    description: Optional[str] = Field(None, description="接口描述")
    path: str = Field(..., max_length=500, description="接口路径")
    method: str = Field(..., max_length=10, description="请求方法")
    sync_direction: ApiSyncDirection = Field(
        default="pull",
        description="同步方向：pull 入站、push 出站、bidirectional 双向",
    )
    connection_uuid: Optional[UUID] = Field(None, description="关联应用连接器 UUID（可选）")
    category_uuid: Optional[UUID] = Field(None, description="所属分类 UUID（可选）")
    request_headers: Optional[Dict[str, Any]] = Field(None, description="请求头")
    request_params: Optional[Dict[str, Any]] = Field(None, description="请求参数")
    request_body: Optional[Dict[str, Any]] = Field(None, description="请求体")
    response_format: Optional[Dict[str, Any]] = Field(None, description="响应格式")
    response_example: Optional[Dict[str, Any]] = Field(None, description="响应示例")
    source_type_conversion_map: Optional[List[Dict[str, Any]]] = Field(
        None,
        description='来源类型编码转换映射（如金蝶 FErpClsID: {"1":"Buy"}），用于物料同步时自动转换编码',
    )
    outbound_field_mappings: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="出站字段映射：enabled/level/local_field/remote_field/default_value",
    )
    is_active: bool = Field(True, description="是否启用")
    is_system: bool = Field(False, description="是否系统接口")
    related_document_code: Optional[str] = Field(
        None,
        max_length=64,
        description="关联 MES 单据 source_type（可选）",
    )
    api_interface_type: ApiInterfaceType = Field(
        default="custom",
        description="接口类型：standard 标准API、custom 自定义API",
    )

    @field_validator("sync_direction", mode="before")
    @classmethod
    def _validate_sync_direction(cls, value: Optional[str]) -> ApiSyncDirection:
        return normalize_api_sync_direction(value)

    @field_validator("api_interface_type", mode="before")
    @classmethod
    def _validate_api_interface_type(cls, value: Optional[str]) -> ApiInterfaceType:
        from core.config.api_library_contract import normalize_api_interface_type

        return normalize_api_interface_type(value)


class APICreate(APIBase):
    """创建接口 Schema"""

    @field_validator("related_document_code", mode="before")
    @classmethod
    def _validate_related_document(cls, value: Optional[str]) -> Optional[str]:
        from core.config.api_library_contract import normalize_api_related_document_code

        if value is None or str(value).strip() == "":
            return None
        return normalize_api_related_document_code(value)


class APIUpdate(BaseModel):
    """更新接口 Schema"""
    name: Optional[str] = Field(None, max_length=100, description="接口名称")
    code: Optional[str] = Field(None, max_length=50, description="接口代码")
    description: Optional[str] = Field(None, description="接口描述")
    path: Optional[str] = Field(None, max_length=500, description="接口路径")
    method: Optional[str] = Field(None, max_length=10, description="请求方法")
    sync_direction: Optional[ApiSyncDirection] = Field(
        None,
        description="同步方向：pull 入站、push 出站、bidirectional 双向",
    )
    connection_uuid: Optional[UUID] = Field(None, description="关联应用连接器 UUID（可选，传 null 清除绑定）")
    category_uuid: Optional[UUID] = Field(None, description="所属分类 UUID（可选，传 null 清除分类）")
    request_headers: Optional[Dict[str, Any]] = Field(None, description="请求头")
    request_params: Optional[Dict[str, Any]] = Field(None, description="请求参数")
    request_body: Optional[Dict[str, Any]] = Field(None, description="请求体")
    response_format: Optional[Dict[str, Any]] = Field(None, description="响应格式")
    response_example: Optional[Dict[str, Any]] = Field(None, description="响应示例")
    source_type_conversion_map: Optional[List[Dict[str, Any]]] = Field(
        None,
        description='来源类型编码转换映射（如金蝶 FErpClsID: {"1":"Buy"}），用于物料同步时自动转换编码',
    )
    outbound_field_mappings: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="出站字段映射：enabled/level/local_field/remote_field/default_value",
    )
    is_active: Optional[bool] = Field(None, description="是否启用")
    related_document_code: Optional[str] = Field(
        None,
        max_length=64,
        description="关联 MES 单据 source_type（可选，传 null 清除）",
    )
    api_interface_type: Optional[ApiInterfaceType] = Field(
        None,
        description="接口类型：standard 标准API、custom 自定义API",
    )

    @field_validator("sync_direction", mode="before")
    @classmethod
    def _validate_sync_direction(cls, value: Optional[str]) -> Optional[ApiSyncDirection]:
        if value is None:
            return None
        return normalize_api_sync_direction(value)

    @field_validator("related_document_code", mode="before")
    @classmethod
    def _validate_related_document(cls, value: Optional[str]) -> Optional[str]:
        from core.config.api_library_contract import normalize_api_related_document_code

        if value is None or str(value).strip() == "":
            return None
        return normalize_api_related_document_code(value)

    @field_validator("api_interface_type", mode="before")
    @classmethod
    def _validate_api_interface_type(cls, value: Optional[str]) -> Optional[ApiInterfaceType]:
        if value is None or str(value).strip() == "":
            return None
        from core.config.api_library_contract import normalize_api_interface_type

        return normalize_api_interface_type(value)


class APIResponse(APIBase):
    """接口响应 Schema"""
    uuid: UUID = Field(..., description="接口UUID")
    tenant_id: int = Field(..., description="组织ID")
    connection_name: Optional[str] = Field(None, description="关联应用连接器名称")
    connection_type: Optional[str] = Field(None, description="关联应用连接器类型")
    category_uuid: Optional[UUID] = Field(None, description="所属分类 UUID")
    category_name: Optional[str] = Field(None, description="所属分类名称")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    
    model_config = ConfigDict(from_attributes=True)


class APIRelatedDocumentOption(BaseModel):
    code: str = Field(..., description="关联单据 source_type 编码")
    label: str = Field(..., description="展示名称")


class APIRelatedDocumentOptionsResponse(BaseModel):
    items: List[APIRelatedDocumentOption] = Field(default_factory=list)


class APIRelatedDocumentGroupCount(BaseModel):
    category_uuid: Optional[UUID] = Field(None, description="分类 UUID；空表示未分类")
    related_document_code: Optional[str] = Field(
        None,
        description="关联单据编码；空表示未填写",
    )
    count: int = Field(..., ge=0, description="接口数量")


class APIRelatedDocumentGroupCountsResponse(BaseModel):
    items: List[APIRelatedDocumentGroupCount] = Field(default_factory=list)


class APITestRequest(BaseModel):
    """接口测试请求 Schema"""
    headers: Optional[Dict[str, Any]] = Field(None, description="请求头（覆盖接口定义）")
    params: Optional[Dict[str, Any]] = Field(None, description="请求参数（覆盖接口定义）")
    body: Optional[Dict[str, Any]] = Field(None, description="请求体（覆盖接口定义）")


class APITestResponse(BaseModel):
    """接口测试响应 Schema"""
    status_code: int = Field(..., description="响应状态码")
    headers: Dict[str, Any] = Field(..., description="响应头")
    body: Any = Field(..., description="响应体")
    elapsed_time: float = Field(..., description="请求耗时（秒）")


class APIProbeRequest(BaseModel):
    """草稿接口探测（编辑弹窗预览，无需已保存接口）"""

    connection_uuid: UUID = Field(..., description="应用连接器 UUID")
    path: str = Field(..., max_length=500, description="接口路径")
    method: str = Field(default="POST", max_length=10, description="请求方法")
    request_headers: Optional[Dict[str, Any]] = Field(None, description="请求头")
    request_params: Optional[Dict[str, Any]] = Field(None, description="请求参数")
    request_body: Optional[Dict[str, Any]] = Field(None, description="请求体")


class KingdeeExecuteBillQueryFieldOption(BaseModel):
    key: str = Field(..., description="字段编码")
    label: str = Field(..., description="字段名称")


class KingdeeExecuteBillQueryFormCatalogItem(BaseModel):
    form_id: str = Field(..., description="FormId")
    name: str = Field(..., description="业务对象名称")
    default_field_keys: List[str] = Field(default_factory=list, description="默认字段")
    fields: List[KingdeeExecuteBillQueryFieldOption] = Field(default_factory=list, description="可选字段")


class KingdeeExecuteBillQueryCatalogResponse(BaseModel):
    items: List[KingdeeExecuteBillQueryFormCatalogItem] = Field(default_factory=list)


class OutboundSourceFieldOption(BaseModel):
    field: str = Field(..., description="本地字段名")
    label: str = Field(..., description="字段中文名")


class OutboundSourceTableItem(BaseModel):
    profile_code: Optional[str] = Field(None, description="业务档案编码")
    profile_name: Optional[str] = Field(None, description="业务档案名称")
    table: str = Field(..., description="本地表名")
    label: str = Field(..., description="表显示名")
    level: Literal["header", "entry"] = Field("header", description="建议映射层级")
    fields: List[OutboundSourceFieldOption] = Field(default_factory=list, description="表字段")


class OutboundSourceProfileItem(BaseModel):
    code: str
    name: str
    match_paths: List[str] = Field(default_factory=list)


class OutboundSourceCatalogResponse(BaseModel):
    profiles: List[OutboundSourceProfileItem] = Field(default_factory=list)
    tables: List[OutboundSourceTableItem] = Field(default_factory=list)
    recommended_profile: Optional[str] = Field(
        None, description="按接口路径推荐的本地单据/实体 code"
    )


class ApiLibraryItemPreview(BaseModel):
    """接口库条目预览"""

    item_key: str = Field(..., description="接口条目唯一键（包内）")
    name: str = Field(..., description="接口名称")
    description: str = Field(..., description="接口说明")


class ApiLibraryPackResponse(BaseModel):
    """接口库包预览"""

    pack_id: str = Field(..., description="接口包 ID")
    name: str = Field(..., description="接口包名称")
    description: str = Field(..., description="接口包说明")
    connector_type: str = Field(..., description="所需应用连接器类型")
    category_name: str = Field(..., description="加载后归入的分类名称")
    api_count: int = Field(..., description="接口数量")
    items: List[ApiLibraryItemPreview] = Field(default_factory=list, description="接口条目")
    source: Optional[str] = Field(default="system", description="来源：system / official")


class ApiLibraryListResponse(BaseModel):
    """接口库目录"""

    items: List[ApiLibraryPackResponse] = Field(default_factory=list, description="接口包列表")
    official_host: Optional[str] = Field(
        default=None, description="官方接口库域名（仅官方库目录返回）"
    )
    official_base_url: Optional[str] = Field(
        default=None, description="官方接口库 base URL（仅官方库目录返回）"
    )


class InstallApiLibraryPackRequest(BaseModel):
    """安装接口库包请求"""

    connection_uuid: UUID = Field(..., description="绑定的应用连接器 UUID")
    item_keys: List[str] = Field(..., min_length=1, description="要加载的接口条目键")


class InstallApiLibraryPackResponse(BaseModel):
    """安装接口库包结果"""

    pack_id: str = Field(..., description="接口包 ID")
    connection_uuid: str = Field(..., description="连接器 UUID")
    connection_code: str = Field(..., description="连接器代码")
    connection_type: str = Field(..., description="连接器类型")
    category_uuid: str = Field(..., description="分类 UUID")
    created_count: int = Field(..., description="新建接口数")
    skipped_count: int = Field(..., description="已存在跳过数")
    categorized_count: int = Field(..., description="已存在接口补充分类数")
    created_codes: List[str] = Field(default_factory=list, description="新建接口 code")
    skipped_codes: List[str] = Field(default_factory=list, description="跳过接口 code")
    categorized_codes: List[str] = Field(default_factory=list, description="补充分类接口 code")


class SubmitOfficialApiLibraryRequest(BaseModel):
    """向官方接口库提交本组织接口"""

    name: str = Field(..., min_length=1, max_length=100, description="接口包名称")
    description: str = Field(default="", max_length=2000, description="接口包说明")
    connector_type: str = Field(..., min_length=1, max_length=50, description="所需连接器类型")
    category_name: str = Field(..., min_length=1, max_length=50, description="分类名称")
    category_code: Optional[str] = Field(default=None, max_length=50, description="分类代码")
    category_description: Optional[str] = Field(default=None, max_length=200, description="分类说明")
    api_uuids: List[UUID] = Field(..., min_length=1, description="本组织接口 UUID 列表")
    submitter_hint: Optional[str] = Field(default=None, max_length=200, description="提交方提示")


class SubmitOfficialApiLibraryResponse(BaseModel):
    """提交官方接口库结果"""

    pack_id: str = Field(..., description="官方接口包 ID")
    name: str = Field(..., description="接口包名称")
    api_count: int = Field(..., description="提交接口数")
    status: str = Field(..., description="状态")


class APIBulkUpsertFailedItem(BaseModel):
    """批量导入失败项（index 与请求 items 下标对齐，从 0 起）"""

    index: int = Field(..., description="请求 items 下标（从 0 起）")
    code: Optional[str] = Field(None, description="接口代码（若有）")
    reason: str = Field(..., description="失败原因")


class APIBulkUpsertRequest(BaseModel):
    """批量按 code upsert 接口（导入分片；单次最多 200）"""

    items: List[APICreate] = Field(
        ...,
        min_length=1,
        max_length=200,
        description="待导入接口列表（单次最多 200）",
    )


class APIBulkUpsertResponse(BaseModel):
    """批量 upsert 结果"""

    created_count: int = Field(..., description="新建数量")
    updated_count: int = Field(..., description="更新数量")
    failed_count: int = Field(..., description="失败数量")
    requested_count: int = Field(..., description="请求条目数")
    failed_items: List[APIBulkUpsertFailedItem] = Field(
        default_factory=list,
        description="失败明细",
    )

