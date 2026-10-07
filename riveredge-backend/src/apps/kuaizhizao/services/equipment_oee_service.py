"""
设备OEE统计服务模块

提供设备综合效率（OEE）统计功能，包括OEE计算、统计分析等。

OEE (Overall Equipment Effectiveness) = 时间稼动率 × 性能稼动率 × 良品率

其中：
- 时间稼动率 = 实际运行时间 / 计划运行时间
- 性能稼动率 = (实际产量 × 标准工时) / 实际运行时间
- 良品率 = 合格数量 / 总数量

Author: Luigi Lu
Date: 2026-01-16
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
from loguru import logger

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaizhizao.models.equipment_status_monitor import EquipmentStatusMonitor
from apps.kuaizhizao.services.oee_calculator import calculate_oee, reports_in_plan
from apps.kuaizhizao.models.reporting_record import ReportingRecord
from apps.kuaizhizao.models.work_order import WorkOrder
from apps.kuaizhizao.models.work_order_operation import WorkOrderOperation
from apps.kuaizhizao.services.work_order_service import WorkOrderService
from apps.kuaizhizao.services.equipment_service import EquipmentService
from core.utils.timezone_utils import resolve_business_datetime, to_api_isoformat
from infra.exceptions.exceptions import NotFoundError, ValidationError


class EquipmentOEEService:
    """
    设备OEE统计服务类

    提供设备OEE统计相关的业务逻辑。
    """

    def __init__(self):
        self.work_order_service = WorkOrderService()
        self.equipment_service = EquipmentService()

    async def calculate_equipment_oee(
        self,
        tenant_id: int,
        equipment_id: int,
        date_start: Optional[datetime] = None,
        date_end: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        计算设备OEE

        Args:
            tenant_id: 租户ID
            equipment_id: 设备ID
            date_start: 开始日期（可选，默认最近30天）
            date_end: 结束日期（可选，默认当前时间）

        Returns:
            Dict[str, Any]: OEE统计数据
        """
        # 验证设备是否存在
        equipment = await Equipment.filter(
            tenant_id=tenant_id,
            id=equipment_id,
            deleted_at__isnull=True
        ).first()
        
        if not equipment:
            raise NotFoundError(f"设备不存在: {equipment_id}")

        # 设置默认时间范围（最近30天）
        if not date_end:
            date_end = resolve_business_datetime()
        if not date_start:
            date_start = date_end - timedelta(days=30)

        # 从报工记录中获取数据（通过device_info字段匹配设备）
        # 注意：这里假设device_info中存储了equipment_id或equipment_code
        reporting_records = await ReportingRecord.filter(
            tenant_id=tenant_id,
            reported_at__gte=date_start,
            reported_at__lte=date_end,
            status="approved",
            deleted_at__isnull=True
        ).all()

        # 筛选该设备的报工记录（从device_info中提取设备信息）
        equipment_records = []
        for record in reporting_records:
            if record.device_info:
                device_id = record.device_info.get("equipment_id") or record.device_info.get("id")
                device_code = record.device_info.get("equipment_code") or record.device_info.get("code")
                
                if device_id == equipment_id or device_code == equipment.code:
                    equipment_records.append(record)

        monitors = await EquipmentStatusMonitor.filter(tenant_id=tenant_id, equipment_uuid=equipment.uuid, data_source="sensor", deleted_at__isnull=True, monitored_at__gte=date_start-timedelta(minutes=5), monitored_at__lte=date_end)
        equipment_records = reports_in_plan(equipment_records, (equipment.technical_parameters or {}).get("oee", {}), date_start, date_end)
        actual_quantity = sum(float(record.reported_quantity or 0) for record in equipment_records)
        qualified_quantity = None if any(record.qualified_quantity is None for record in equipment_records) else sum(float(record.qualified_quantity) for record in equipment_records)
        metrics = calculate_oee(monitors, date_start, date_end, (equipment.technical_parameters or {}).get("oee", {}), actual_quantity, qualified_quantity)
        actual_runtime = metrics["running_seconds"] / 3600
        planned_runtime = metrics["planned_seconds"] / 3600 if metrics["planned_seconds"] is not None else None
        def percent(key):
            value = metrics[key]
            return round(value * 100, 2) if value is not None else None

        return {
            "equipment": {
                "id": equipment.id,
                "uuid": equipment.uuid,
                "code": equipment.code,
                "name": equipment.name,
            },
            "period": {
                "start": to_api_isoformat(date_start),
                "end": to_api_isoformat(date_end),
            },
            "metrics": {
                "planned_runtime": round(planned_runtime, 2) if planned_runtime is not None else None,  # 计划运行时间（小时）
                "actual_runtime": round(actual_runtime, 2),  # 实际运行时间（小时）
                "actual_quantity": round(actual_quantity, 2),  # 实际产量
                "qualified_quantity": round(qualified_quantity, 2) if qualified_quantity is not None else None,  # 合格数量
                "unqualified_quantity": round(actual_quantity - qualified_quantity, 2) if qualified_quantity is not None else None,  # 不合格数量
            },
            "oee": {
                "availability_rate": percent("availability_rate"),  # 时间稼动率（%）
                "performance_rate": percent("performance_rate"),  # 性能稼动率（%）
                "quality_rate": percent("quality_rate"),  # 良品率（%）
                "oee_value": percent("oee"),  # OEE值（%）
            },
            "coverage_rate": metrics["coverage_rate"],
            "unavailable_reasons": metrics["reasons"],
            "record_count": len(equipment_records),  # 报工记录数
        }

    async def list_equipment_oee(
        self,
        tenant_id: int,
        date_start: Optional[datetime] = None,
        date_end: Optional[datetime] = None,
        equipment_ids: Optional[List[int]] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        获取设备OEE统计列表

        Args:
            tenant_id: 租户ID
            date_start: 开始日期（可选）
            date_end: 结束日期（可选）
            equipment_ids: 设备ID列表（可选，如果指定则只统计这些设备）
            skip: 跳过数量
            limit: 限制数量

        Returns:
            List[Dict[str, Any]]: OEE统计列表
        """
        # 设置默认时间范围（最近30天）
        if not date_end:
            date_end = resolve_business_datetime()
        if not date_start:
            date_start = date_end - timedelta(days=30)

        # 获取设备列表
        if equipment_ids:
            equipment_list = await Equipment.filter(
                tenant_id=tenant_id,
                id__in=equipment_ids,
                deleted_at__isnull=True
            ).all()
        else:
            equipment_list = await Equipment.filter(
                tenant_id=tenant_id,
                deleted_at__isnull=True,
                is_active=True
            ).offset(skip).limit(limit).all()

        # 计算每个设备的OEE
        oee_list = []
        for equipment in equipment_list:
            try:
                oee_data = await self.calculate_equipment_oee(
                    tenant_id=tenant_id,
                    equipment_id=equipment.id,
                    date_start=date_start,
                    date_end=date_end,
                )
                oee_list.append(oee_data)
            except Exception as e:
                logger.error(f"计算设备 {equipment.code} OEE失败: {e}")
                # 即使计算失败，也返回基础信息
                oee_list.append({
                    "equipment": {
                        "id": equipment.id,
                        "uuid": equipment.uuid,
                        "code": equipment.code,
                        "name": equipment.name,
                    },
                    "period": {
                        "start": to_api_isoformat(date_start),
                        "end": to_api_isoformat(date_end),
                    },
                    "metrics": {
                        "planned_runtime": None,
                        "actual_runtime": None,
                        "actual_quantity": None,
                        "qualified_quantity": None,
                        "unqualified_quantity": None,
                    },
                    "oee": {
                        "availability_rate": None,
                        "performance_rate": None,
                        "quality_rate": None,
                        "oee_value": None,
                    },
                    "record_count": 0,
                    "error": "OEE 计算失败",
                    "unavailable_reasons": ["OEE 计算失败"],
                })

        return oee_list

    async def get_equipment_oee_trend(
        self,
        tenant_id: int,
        equipment_id: int,
        date_start: Optional[datetime] = None,
        date_end: Optional[datetime] = None,
        period: str = "day",  # day/week/month
    ) -> Dict[str, Any]:
        """
        获取设备OEE趋势数据

        Args:
            tenant_id: 租户ID
            equipment_id: 设备ID
            date_start: 开始日期（可选）
            date_end: 结束日期（可选）
            period: 统计周期（day/week/month）

        Returns:
            Dict[str, Any]: OEE趋势数据
        """
        # 设置默认时间范围（最近30天）
        if not date_end:
            date_end = resolve_business_datetime()
        if not date_start:
            if period == "day":
                date_start = date_end - timedelta(days=30)
            elif period == "week":
                date_start = date_end - timedelta(weeks=12)
            elif period == "month":
                date_start = date_end - timedelta(days=365)

        # 根据周期生成时间点
        trend_data = []
        current_date = date_start

        while current_date <= date_end:
            period_end = current_date
            if period == "day":
                period_end = current_date + timedelta(days=1)
            elif period == "week":
                period_end = current_date + timedelta(weeks=1)
            elif period == "month":
                # 计算下一个月
                if current_date.month == 12:
                    period_end = current_date.replace(year=current_date.year + 1, month=1, day=1)
                else:
                    period_end = current_date.replace(month=current_date.month + 1, day=1)

            period_end = min(period_end, date_end)

            try:
                oee_data = await self.calculate_equipment_oee(
                    tenant_id=tenant_id,
                    equipment_id=equipment_id,
                    date_start=current_date,
                    date_end=period_end,
                )
                trend_data.append({
                    "period": to_api_isoformat(current_date),
                    "oee": oee_data["oee"],
                    "metrics": oee_data["metrics"],
                })
            except Exception as e:
                logger.error(f"计算设备 {equipment_id} 在 {current_date} 的OEE失败: {e}")
                trend_data.append({
                    "period": to_api_isoformat(current_date),
                    "oee": {
                        "availability_rate": None,
                        "performance_rate": None,
                        "quality_rate": None,
                        "oee_value": None,
                    },
                    "metrics": {
                        "planned_runtime": None,
                        "actual_runtime": None,
                        "actual_quantity": None,
                        "qualified_quantity": None,
                        "unqualified_quantity": None,
                    },
                })

            current_date = period_end

        return {
            "equipment_id": equipment_id,
            "period_type": period,
            "trend_data": trend_data,
        }
