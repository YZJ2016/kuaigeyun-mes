"""KU-AI 运营层 Schemas（spec 181：hub 能力矩阵 + 智能体库）。

契约逐字对齐设计 §11.1/§11.2：状态闭集 ready|partial|not_ready；
响应模型不回 system_prompt / 授权名单 / 密钥 / tenant_id；
写请求 extra=forbid，禁止夹带未声明字段。
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool


# ============================================================ hub


class HubModelOut(BaseModel):
    configured: bool = False
    name: Optional[str] = None
    connection_uuid: Optional[str] = None


class HubMetricsOut(BaseModel):
    total_calls: Optional[int] = None
    pulse_count: Optional[int] = None
    corpus_count: Optional[int] = None
    avg_latency_ms: Optional[int] = None


class HubCapabilityOut(BaseModel):
    key: str
    name: str
    status: str = Field(description="ready|partial|not_ready")
    description: Optional[str] = None
    route: Optional[str] = None
    disabled_reason: Optional[str] = None


class HubOut(BaseModel):
    days: int
    model: HubModelOut
    metrics: HubMetricsOut
    capabilities: List[HubCapabilityOut]


# ============================================================ 智能体库


class LibraryProvisioningOut(BaseModel):
    complete: bool
    missing_template_keys: List[str] = Field(default_factory=list)
    retryable: bool = True


class LibraryItemOut(BaseModel):
    key: str
    template_key: str
    name: str
    description: Optional[str] = None
    image_key: Optional[str] = None
    enabled: bool = False
    status: str = Field(description="ready|partial|not_ready")
    capability_tags: List[str] = Field(default_factory=list)
    sample_prompt: Optional[str] = None
    agent_profile_id: Optional[int] = None
    scene_route: Optional[str] = None
    scene_available: bool = False
    disabled_reason: Optional[str] = None


class LibraryOut(BaseModel):
    provisioning: LibraryProvisioningOut
    items: List[LibraryItemOut]


# ============================================================ 信任中心（spec 184）
# 契约逐字对齐设计 §11.5：cards/permissions/hitl；
# status 闭集 ready|partial|not_ready；不回角色关系、密钥或内部路径。


class TrustCardOut(BaseModel):
    key: str
    title: str
    status: str = Field(description="ready|partial|not_ready")
    description: Optional[str] = None
    evidence: List[str] = Field(default_factory=list)


class TrustPermissionOut(BaseModel):
    """当前用户权限码持有状态（只反映当前用户，不接收 user_id）。"""

    code: str
    granted: bool = False


class TrustHitlOut(BaseModel):
    implemented: bool = False
    mode: str = "not_implemented"


class TrustOut(BaseModel):
    cards: List[TrustCardOut]
    permissions: List[TrustPermissionOut]
    hitl: TrustHitlOut


# ============================================================ 写请求


class SceneInstanceUpdate(BaseModel):
    """实例定制/改绑/开关：字段缺省=不动；显式 null 清覆盖（agent_profile_id 的
    null 表示解绑）。template_key/origin 不可改。"""

    model_config = ConfigDict(extra="forbid")

    agent_profile_id: Optional[int] = Field(default=None, ge=1)
    enabled: Optional[bool] = None
    name: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = None
    image_key: Optional[str] = None
    sample_prompt: Optional[str] = Field(default=None, max_length=500)
    capability_tags: Optional[List[str]] = None
    scene_route: Optional[str] = None


class SceneCloneOverrides(BaseModel):
    """克隆覆盖字段（与 PUT 相同但不含 agent_profile_id/enabled 语义由服务端固定）。"""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = None
    image_key: Optional[str] = None
    sample_prompt: Optional[str] = Field(default=None, max_length=500)
    capability_tags: Optional[List[str]] = None
    scene_route: Optional[str] = None


class SceneInstanceClone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_key: str = Field(..., min_length=1, max_length=80)
    source_agent_id: int = Field(..., ge=1)
    overrides: Optional[SceneCloneOverrides] = None


# ============================================================ 设置（spec 185）
# 契约逐字对齐设计 §11.6：option 无 key/cipher；写请求 extra=forbid。


class SettingsOptionOut(BaseModel):
    uuid: str
    name: str
    provider: str
    model: Optional[str] = None
    model_role: Optional[str] = None
    is_active: bool = True
    is_selected: bool = False


class SettingsOcrOut(BaseModel):
    configured: bool = False
    base_url_masked: str = ""
    model: Optional[str] = None


class SettingsCapabilitiesOut(BaseModel):
    tools_enabled: bool = True
    rag_enabled: bool = True
    rag_use_embedding: bool = True
    rag_backend: str = "native"
    rag_top_k: int = 5
    stream_enabled: bool = True
    custom_system_prompt: str = ""


class SettingsOut(BaseModel):
    chat_connection_uuid: Optional[str] = None
    vision_connection_uuid: Optional[str] = None
    chat_options: List[SettingsOptionOut] = Field(default_factory=list)
    vision_options: List[SettingsOptionOut] = Field(default_factory=list)
    ocr: SettingsOcrOut
    agent_switches: Dict[str, bool] = Field(default_factory=dict)
    capabilities: SettingsCapabilitiesOut
    version: str


class SettingsCapabilitiesIn(BaseModel):
    """能力配置整体替换：七字段全部必填（rag_backend 当前闭集 native）。"""

    model_config = ConfigDict(extra="forbid")

    tools_enabled: StrictBool
    rag_enabled: StrictBool
    rag_use_embedding: StrictBool
    rag_backend: str = Field(pattern="^native$")
    rag_top_k: int = Field(ge=1, le=20)
    stream_enabled: StrictBool
    custom_system_prompt: str


class SettingsUpdateIn(BaseModel):
    """PUT /operations/settings 请求体；version 为 GET 下发的不透明字符串。"""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=128)
    chat_connection_uuid: str = Field(min_length=1, max_length=64)
    vision_connection_uuid: Optional[str] = Field(default=None, max_length=64)
    agent_switches: Dict[str, StrictBool]
    capabilities: SettingsCapabilitiesIn
