"""
登录日志 Schema 模块

定义登录日志相关的 Pydantic Schema，用于数据验证和序列化。
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from uuid import UUID

from core.schemas.base import BaseSchema


class LoginLogBase(BaseModel):
    """登录日志基础 Schema"""
    tenant_id: Optional[int] = Field(None, description="组织ID（登录失败时可能为空）")
    user_id: Optional[int] = Field(None, description="登录用户ID（登录失败时可能为空）")
    username: Optional[str] = Field(None, description="登录账号")
    login_ip: str = Field(..., description="登录IP地址")
    login_location: Optional[str] = Field(None, description="登录地点")
    login_latitude: Optional[float] = Field(None, description="登录 IP 纬度")
    login_longitude: Optional[float] = Field(None, description="登录 IP 经度")
    login_device: Optional[str] = Field(None, description="登录设备")
    login_browser: Optional[str] = Field(None, description="登录浏览器")
    login_status: str = Field(..., description="登录状态（success、failed）")
    failure_reason: Optional[str] = Field(None, description="失败原因")


class LoginLogCreate(LoginLogBase):
    """创建登录日志 Schema"""
    pass


class LoginLogResponse(LoginLogBase, BaseSchema):
    """登录日志响应 Schema（API JSON 走 BaseSchema 站点墙钟）"""
    uuid: UUID = Field(..., description="登录日志UUID")
    tenant_id: Optional[int] = Field(None, description="组织ID")
    created_at: datetime = Field(..., description="创建时间")
    
    model_config = ConfigDict(from_attributes=True)


class LoginLogListResponse(BaseModel):
    """登录日志列表响应 Schema"""
    items: list[LoginLogResponse] = Field(..., description="登录日志列表")
    total: int = Field(..., description="总数量")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")


class LoginLogStatsResponse(BaseModel):
    """登录日志统计响应 Schema"""
    total: int = Field(..., description="总登录数")
    success_count: int = Field(..., description="成功登录数")
    failed_count: int = Field(..., description="失败登录数")
    by_status: dict = Field(default_factory=dict, description="按登录状态统计")
    by_user: dict = Field(default_factory=dict, description="按用户统计（前10名）")
    
    today_total: int = Field(0, description="今日登录数")
    yesterday_total: int = Field(0, description="昨日登录数")
    trend_data: list[dict] = Field(default_factory=list, description="最近7天趋势数据")


class LoginLogMapPoint(BaseModel):
    """登录日志地图散点（按地点聚合，同地点多 IP 合并）"""
    login_ip: str = Field(..., description="代表 IP（该地点登录次数最高的 IP）")
    latitude: float = Field(..., description="纬度")
    longitude: float = Field(..., description="经度")
    login_location: Optional[str] = Field(None, description="登录地点文案")
    login_count: int = Field(..., description="该地点在筛选范围内的登录次数")
    success_count: int = Field(0, description="成功次数")
    failed_count: int = Field(0, description="失败次数")
    last_login_at: datetime = Field(..., description="该地点最近一次登录时间")
    usernames: list[str] = Field(default_factory=list, description="涉及用户名（去重，最多 5 个）")
    ip_count: int = Field(1, description="该地点涉及的去重 IP 数")


class LoginLogMapPointsResponse(BaseModel):
    """登录日志地图视图响应"""
    items: list[LoginLogMapPoint] = Field(default_factory=list, description="可定位散点")
    unresolved_ips: list[str] = Field(default_factory=list, description="无法解析坐标的 IP")
    scanned_logs: int = Field(0, description="参与聚合的日志条数")
    unique_ips: int = Field(0, description="去重 IP 数")

