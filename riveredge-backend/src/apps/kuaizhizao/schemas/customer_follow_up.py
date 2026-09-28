"""
客户跟进记录 Schema
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import Field

from core.schemas.base import BaseSchema


class CustomerFollowUpBase(BaseSchema):
    """客户跟进基础"""

    customer_id: int = Field(..., description="客户ID")
    customer_name: str = Field(..., max_length=200, description="客户名称")
    activity_type_code: str = Field(..., max_length=50, description="跟进方式字典值")
    content: str = Field(..., description="跟进内容")
    occurred_at: datetime = Field(..., description="跟进发生时间")
    next_follow_up_at: Optional[datetime] = Field(None, description="计划下次跟进时间")
    quotation_id: Optional[int] = Field(None, description="关联报价单ID")
    quotation_code: Optional[str] = Field(None, max_length=50, description="关联报价单编码")
    sales_order_id: Optional[int] = Field(None, description="关联销售订单ID")
    sales_order_code: Optional[str] = Field(None, max_length=50, description="关联销售订单编码")
    opportunity_id: Optional[int] = Field(None, description="关联销售商机ID")
    stage_code_before: Optional[str] = Field(None, max_length=50, description="跟进时商机阶段（变更前）")
    stage_code_after: Optional[str] = Field(None, max_length=50, description="跟进后商机阶段（变更后）")
    attachment_uuids: Optional[List[str]] = Field(None, description="跟进附件 UUID 列表")


class CustomerFollowUpCreate(BaseSchema):
    """创建客户跟进（客户名称与关联单据由服务校验后填充）"""

    customer_id: int = Field(..., description="客户ID")
    activity_type_code: str = Field(..., max_length=50, description="跟进方式字典值")
    content: str = Field(..., description="跟进内容")
    occurred_at: datetime = Field(..., description="跟进发生时间")
    next_follow_up_at: Optional[datetime] = Field(None, description="计划下次跟进时间")
    quotation_id: Optional[int] = Field(None, description="关联报价单ID")
    sales_order_id: Optional[int] = Field(None, description="关联销售订单ID")
    opportunity_id: Optional[int] = Field(None, description="关联销售商机ID")
    stage_code_after: Optional[str] = Field(None, max_length=50, description="跟进后目标阶段（变更时提交）")
    attachment_uuids: Optional[List[str]] = Field(None, description="跟进附件 UUID 列表")


class CustomerFollowUpUpdate(BaseSchema):
    """更新客户跟进"""

    customer_name: Optional[str] = Field(None, max_length=200, description="客户名称")
    activity_type_code: Optional[str] = Field(None, max_length=50, description="跟进方式字典值")
    content: Optional[str] = Field(None, description="跟进内容")
    occurred_at: Optional[datetime] = Field(None, description="跟进发生时间")
    next_follow_up_at: Optional[datetime] = Field(None, description="计划下次跟进时间")
    quotation_id: Optional[int] = Field(None, description="关联报价单ID")
    sales_order_id: Optional[int] = Field(None, description="关联销售订单ID")
    opportunity_id: Optional[int] = Field(None, description="关联销售商机ID")
    stage_code_after: Optional[str] = Field(None, max_length=50, description="跟进后目标阶段（变更时提交）")
    attachment_uuids: Optional[List[str]] = Field(None, description="跟进附件 UUID 列表")


class CustomerFollowUpResponse(CustomerFollowUpBase):
    """客户跟进响应"""

    id: int = Field(..., description="跟进记录ID")
    uuid: str = Field(..., max_length=36, description="业务UUID")
    tenant_id: int = Field(..., description="租户ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    created_by: Optional[int] = Field(None, description="创建人ID")
    updated_by: Optional[int] = Field(None, description="更新人ID")
    created_by_name: Optional[str] = Field(None, description="跟进人员显示名")
    updated_by_name: Optional[str] = Field(None, description="更新人显示名")
    follow_up_count: int = Field(0, description="该客户已跟进次数（未删除记录合计）")


class CustomerFollowUpListResponse(CustomerFollowUpResponse):
    """列表项"""

    pass

class CustomerFollowUpListEnvelope(BaseSchema):
    """分页列表"""

    items: List[CustomerFollowUpListResponse] = Field(default_factory=list, description="当前页数据")
    total: int = Field(0, description="总条数")


class CustomerFollowUpDashboardSnapshot(BaseSchema):
    """销售中心待跟进 KPI（按客户最新一条跟进计划统计）+ CRM 经营快照"""

    pending_customers: int = Field(0, description="待跟进客户数（计划跟进日已到或逾期）")
    overdue_customers: int = Field(0, description="已逾期客户数（计划跟进时刻已过）")
    items: List[CustomerFollowUpListResponse] = Field(
        default_factory=list,
        description="待跟进预览（按下次跟进时间升序）",
    )
    inactive_customers: int = Field(0, description="未联系客户数（按客户池规则未联系提醒天数）")
    inactive_alert_days: int = Field(7, description="未联系提醒天数（来自客户池规则）")
    follow_status_pending: int = Field(0, description="跟进状态=未跟进客户数")
    follow_status_followed: int = Field(0, description="跟进状态=已跟进客户数")
    follow_up_records_total: int = Field(0, description="跟进记录总条数（数据范围内）")
    level_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="客户定级分布（字典码→数量；空码为 _unset）",
    )
