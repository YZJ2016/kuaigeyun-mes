"""
登录日志管理服务模块

提供登录日志的创建、查询和统计功能。
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from tortoise.expressions import Q

logger = logging.getLogger(__name__)
from tortoise.functions import Count

from core.models.login_log import LoginLog
from core.schemas.login_log import (
    LoginLogCreate,
    LoginLogResponse,
    LoginLogListResponse,
    LoginLogStatsResponse,
    LoginLogMapPoint,
    LoginLogMapPointsResponse,
)
from infra.exceptions.exceptions import NotFoundError
from core.utils.timezone_utils import now_utc, site_day_bounds_utc, to_naive_utc, to_site_date


class LoginLogService:
    """
    登录日志管理服务类
    
    提供登录日志的创建、查询和统计功能。
    """

    _MAP_LOG_SCAN_BATCH = 5000
    _BACKFILL_IP_LOOKUP_CONCURRENCY = 4

    @staticmethod
    def _build_login_log_query(
        tenant_id: Optional[int],
        *,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        login_status: Optional[str] = None,
        login_ip: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Q:
        query = Q()
        if tenant_id is not None:
            query &= Q(tenant_id=tenant_id)
        if user_id:
            query &= Q(user_id=user_id)
        if username:
            query &= Q(username__icontains=username)
        if login_status:
            query &= Q(login_status=login_status)
        if login_ip:
            query &= Q(login_ip__icontains=login_ip)
        if start_time:
            query &= Q(created_at__gte=start_time)
        if end_time:
            query &= Q(created_at__lte=end_time)
        return query
    
    @staticmethod
    async def create_login_log(data: LoginLogCreate) -> LoginLogResponse:
        """
        创建登录日志
        
        Args:
            data: 登录日志创建数据
            
        Returns:
            LoginLogResponse: 创建的登录日志对象
        """
        login_log = await LoginLog.create(**data.model_dump())
        return LoginLogResponse.model_validate(login_log)
    
    @staticmethod
    async def get_login_logs(
        tenant_id: Optional[int],
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        login_status: Optional[str] = None,
        login_ip: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> LoginLogListResponse:
        """
        获取登录日志列表
        
        Args:
            tenant_id: 组织ID（可为空，用于查询所有组织的日志）
            page: 页码
            page_size: 每页数量
            user_id: 用户ID过滤（可选）
            username: 用户名过滤（可选）
            login_status: 登录状态过滤（可选）
            login_ip: 登录IP过滤（可选）
            start_time: 开始时间过滤（可选）
            end_time: 结束时间过滤（可选）
            
        Returns:
            LoginLogListResponse: 登录日志列表
        """
        query = LoginLogService._build_login_log_query(
            tenant_id,
            user_id=user_id,
            username=username,
            login_status=login_status,
            login_ip=login_ip,
            start_time=start_time,
            end_time=end_time,
        )

        logger.debug(f"get_login_logs: tenant_id={tenant_id}, page={page}, filters: user_id={user_id}, username={username}")
        
        total = await LoginLog.filter(query).count()
        if total == 0 and tenant_id is not None and logger.isEnabledFor(logging.DEBUG):
            # 无数据时记录调试信息，便于排查 tenant_id 不匹配
            any_count = await LoginLog.filter().count()
            logger.debug(f"get_login_logs: 当前租户 tenant_id={tenant_id} 无记录 (total=0), 全表记录数={any_count}")
        
        offset = (page - 1) * page_size
        logs = await LoginLog.filter(query).order_by("-created_at").offset(offset).limit(page_size)
        
        items = [LoginLogResponse.model_validate(log) for log in logs]
        
        return LoginLogListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    
    @staticmethod
    async def get_login_log_by_uuid(
        tenant_id: Optional[int],
        uuid: str
    ) -> LoginLogResponse:
        """
        根据UUID获取登录日志详情
        
        Args:
            tenant_id: 组织ID（可为空）
            uuid: 登录日志UUID
            
        Returns:
            LoginLogResponse: 登录日志详情
            
        Raises:
            NotFoundError: 当登录日志不存在时抛出
        """
        query = Q(uuid=uuid)
        if tenant_id is not None:
            query &= Q(tenant_id=tenant_id)
        
        log = await LoginLog.get_or_none(query)
        if not log:
            raise NotFoundError("登录日志", uuid)
        
        return LoginLogResponse.model_validate(log)
    
    @staticmethod
    async def get_login_log_stats(
        tenant_id: Optional[int],
    ) -> LoginLogStatsResponse:
        """
        获取登录日志统计
        
        Args:
            tenant_id: 组织ID（可为空）
            
        Returns:
            LoginLogStatsResponse: 登录日志统计数据
        """
        query = Q()
        if tenant_id is not None:
            query &= Q(tenant_id=tenant_id)
        
        total = await LoginLog.filter(query).count()
        success_count = await LoginLog.filter(query & Q(login_status="success")).count()
        failed_count = await LoginLog.filter(query & Q(login_status="failed")).count()
        
        # 按登录状态统计
        by_status_raw = await LoginLog.filter(query).group_by("login_status").annotate(count=Count("id")).values("login_status", "count")
        by_status = {item["login_status"]: item["count"] for item in by_status_raw}
        
        # 按用户统计（前10名）
        by_user_raw = await LoginLog.filter(query & Q(user_id__isnull=False)).group_by("user_id", "username").annotate(count=Count("id")).order_by("-count").limit(10).values("user_id", "username", "count")
        by_user = {f"{item['username']}({item['user_id']})": item["count"] for item in by_user_raw}
        
        # 最近 7 天趋势：站点日历日边界 → UTC（唯一真源 site_day_bounds_utc）
        import asyncio

        today = to_site_date(now_utc())
        trend_data = []
        tasks = []

        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            start_utc, end_utc = site_day_bounds_utc(d)
            day_query = query & Q(
                created_at__gte=to_naive_utc(start_utc),
                created_at__lt=to_naive_utc(end_utc),
            )
            tasks.append((d.isoformat(), LoginLog.filter(day_query).count()))

        day_strs, day_counts_awaitables = zip(*tasks)
        day_counts = await asyncio.gather(*day_counts_awaitables)

        for date_str, count in zip(day_strs, day_counts):
            trend_data.append({"date": date_str, "value": count})
            
        today_total_val = trend_data[-1]["value"] if trend_data else 0
        yesterday_total_val = trend_data[-2]["value"] if len(trend_data) > 1 else 0
        
        return LoginLogStatsResponse(
            total=total,
            success_count=success_count,
            failed_count=failed_count,
            by_status=by_status,
            by_user=by_user,
            today_total=today_total_val,
            yesterday_total=yesterday_total_val,
            trend_data=trend_data,
        )

    @staticmethod
    def _map_coordinate_cluster_key(latitude: float, longitude: float) -> str:
        """地图聚类真源：经纬度网格（约 1km），禁止按 login_location 字符串聚类。"""
        return f"{round(longitude, 2)}:{round(latitude, 2)}"

    @staticmethod
    def _aggregate_map_points_by_location(items: list[LoginLogMapPoint]) -> list[LoginLogMapPoint]:
        """同坐标网格的多 IP 合并为一点，展示文案取该网格内登录次数最多的地点。"""
        clusters: Dict[str, Dict[str, Any]] = {}

        for point in items:
            key = LoginLogService._map_coordinate_cluster_key(
                point.latitude,
                point.longitude,
            )
            bucket = clusters.get(key)
            if bucket is None:
                clusters[key] = {
                    "login_ip": point.login_ip,
                    "login_location": point.login_location,
                    "login_count": point.login_count,
                    "success_count": point.success_count,
                    "failed_count": point.failed_count,
                    "lat_weighted_sum": point.latitude * point.login_count,
                    "lon_weighted_sum": point.longitude * point.login_count,
                    "weight": point.login_count,
                    "last_login_at": point.last_login_at,
                    "usernames": list(point.usernames),
                    "ip_count": 1,
                    "top_ip_count": point.login_count,
                }
                continue

            bucket["login_count"] += point.login_count
            bucket["success_count"] += point.success_count
            bucket["failed_count"] += point.failed_count
            bucket["lat_weighted_sum"] += point.latitude * point.login_count
            bucket["lon_weighted_sum"] += point.longitude * point.login_count
            bucket["weight"] += point.login_count
            bucket["ip_count"] += 1
            if point.last_login_at > bucket["last_login_at"]:
                bucket["last_login_at"] = point.last_login_at
            if point.login_count > bucket["top_ip_count"]:
                bucket["top_ip_count"] = point.login_count
                bucket["login_ip"] = point.login_ip
                if point.login_location:
                    bucket["login_location"] = point.login_location
            for username in point.usernames:
                if username not in bucket["usernames"] and len(bucket["usernames"]) < 5:
                    bucket["usernames"].append(username)

        merged: list[LoginLogMapPoint] = []
        for bucket in clusters.values():
            weight = bucket["weight"] or 1
            display_location = bucket.get("login_location")
            if not display_location:
                lat = bucket["lat_weighted_sum"] / weight
                lon = bucket["lon_weighted_sum"] / weight
                display_location = LoginLogService._map_coordinate_cluster_key(lat, lon)
            merged.append(
                LoginLogMapPoint(
                    login_ip=bucket["login_ip"],
                    latitude=bucket["lat_weighted_sum"] / weight,
                    longitude=bucket["lon_weighted_sum"] / weight,
                    login_location=display_location,
                    login_count=int(bucket["login_count"]),
                    success_count=int(bucket["success_count"]),
                    failed_count=int(bucket["failed_count"]),
                    last_login_at=bucket["last_login_at"],
                    usernames=list(bucket["usernames"]),
                    ip_count=int(bucket["ip_count"]),
                )
            )

        merged.sort(key=lambda p: p.login_count, reverse=True)
        return merged

    @staticmethod
    async def get_login_log_map_points(
        tenant_id: Optional[int],
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        login_status: Optional[str] = None,
        login_ip: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> LoginLogMapPointsResponse:
        """按 IP 聚合登录日志；经纬度直读库内 login_latitude/login_longitude。"""
        query = LoginLogService._build_login_log_query(
            tenant_id,
            user_id=user_id,
            username=username,
            login_status=login_status,
            login_ip=login_ip,
            start_time=start_time,
            end_time=end_time,
        )

        rows: list[dict[str, Any]] = []
        last_id = 0
        while True:
            batch_query = query & Q(id__gt=last_id)
            batch = await (
                LoginLog.filter(batch_query)
                .order_by("id")
                .limit(LoginLogService._MAP_LOG_SCAN_BATCH)
                .values(
                    "id",
                    "login_ip",
                    "login_location",
                    "login_latitude",
                    "login_longitude",
                    "username",
                    "login_status",
                    "created_at",
                )
            )
            if not batch:
                break
            rows.extend(batch)
            last_id = int(batch[-1]["id"])
            if len(batch) < LoginLogService._MAP_LOG_SCAN_BATCH:
                break

        by_ip: Dict[str, Dict[str, Any]] = {}
        unresolved_ips: list[str] = []

        for row in rows:
            ip = str(row.get("login_ip") or "").strip()
            if not ip:
                continue
            bucket = by_ip.setdefault(
                ip,
                {
                    "login_count": 0,
                    "success_count": 0,
                    "failed_count": 0,
                    "last_login_at": row.get("created_at"),
                    "login_location": None,
                    "latitude": None,
                    "longitude": None,
                    "usernames": [],
                    "has_coords": False,
                },
            )
            bucket["login_count"] += 1
            status = str(row.get("login_status") or "")
            if status == "success":
                bucket["success_count"] += 1
            elif status == "failed":
                bucket["failed_count"] += 1
            created_at = row.get("created_at")
            if created_at and (
                bucket["last_login_at"] is None or created_at > bucket["last_login_at"]
            ):
                bucket["last_login_at"] = created_at
            location = str(row.get("login_location") or "").strip()
            if location and not bucket["login_location"]:
                bucket["login_location"] = location
            lat = row.get("login_latitude")
            lon = row.get("login_longitude")
            if lat is not None and lon is not None and not bucket["has_coords"]:
                bucket["latitude"] = float(lat)
                bucket["longitude"] = float(lon)
                bucket["has_coords"] = True
            uname = str(row.get("username") or "").strip()
            if uname and uname not in bucket["usernames"] and len(bucket["usernames"]) < 5:
                bucket["usernames"].append(uname)

        items: list[LoginLogMapPoint] = []
        for ip, agg in by_ip.items():
            if not agg.get("has_coords"):
                unresolved_ips.append(ip)
                continue
            last_at = agg.get("last_login_at")
            if last_at is None:
                last_at = to_naive_utc(now_utc())
            items.append(
                LoginLogMapPoint(
                    login_ip=ip,
                    latitude=float(agg["latitude"]),
                    longitude=float(agg["longitude"]),
                    login_location=agg.get("login_location"),
                    login_count=int(agg["login_count"]),
                    success_count=int(agg["success_count"]),
                    failed_count=int(agg["failed_count"]),
                    last_login_at=last_at,
                    usernames=list(agg["usernames"]),
                )
            )

        items = LoginLogService._aggregate_map_points_by_location(items)

        return LoginLogMapPointsResponse(
            items=items,
            unresolved_ips=unresolved_ips,
            scanned_logs=len(rows),
            unique_ips=len(by_ip),
        )

    @staticmethod
    async def backfill_login_log_ip_coordinates(
        *,
        tenant_id: Optional[int] = None,
        batch_size: int = 200,
        lookup_concurrency: Optional[int] = None,
        refresh_all: bool = False,
    ) -> dict[str, int]:
        """为历史登录日志按 IP 回填经纬度与 login_location（每个 IP 仅解析一次）。"""
        from core.utils.ip_parser import (
            _format_location_from_detail,
            _lookup_geo_from_login_logs,
            get_ip_location_detail,
            is_private_ip,
            normalize_login_location_label,
        )

        if refresh_all:
            query = Q()
            if tenant_id is not None:
                query &= Q(tenant_id=tenant_id)
        else:
            query = Q(login_latitude__isnull=True)
            if tenant_id is not None:
                query &= Q(tenant_id=tenant_id)

        ips = await (
            LoginLog.filter(query)
            .distinct()
            .values_list("login_ip", flat=True)
        )
        unique_ips = [str(ip).strip() for ip in ips if ip and str(ip).strip()]
        updated_rows = 0
        resolved_ips = 0
        skipped_ips = 0
        reused_ips = 0

        concurrency = lookup_concurrency or LoginLogService._BACKFILL_IP_LOOKUP_CONCURRENCY
        sem = asyncio.Semaphore(concurrency)

        async def _resolve_ip(ip: str) -> None:
            nonlocal updated_rows, resolved_ips, skipped_ips, reused_ips
            if is_private_ip(ip):
                skipped_ips += 1
                return

            lat: Optional[float] = None
            lon: Optional[float] = None
            location: Optional[str] = None

            if refresh_all:
                async with sem:
                    detail = await get_ip_location_detail(ip, timeout=2.5)
                if detail:
                    lat_raw = detail.get("lat")
                    lon_raw = detail.get("lon")
                    if lat_raw is not None and lon_raw is not None:
                        lat = float(lat_raw)
                        lon = float(lon_raw)
                    label = _format_location_from_detail(detail)
                    if label:
                        location = normalize_login_location_label(label)
            else:
                lat, lon = await _lookup_geo_from_login_logs(ip, tenant_id=tenant_id)
                if lat is not None and lon is not None:
                    reused_ips += 1
                else:
                    async with sem:
                        detail = await get_ip_location_detail(ip, timeout=2.5)
                    if detail:
                        lat_raw = detail.get("lat")
                        lon_raw = detail.get("lon")
                        if lat_raw is not None and lon_raw is not None:
                            lat = float(lat_raw)
                            lon = float(lon_raw)
                        label = _format_location_from_detail(detail)
                        if label:
                            location = normalize_login_location_label(label)

            if lat is None or lon is None:
                skipped_ips += 1
                return

            ip_query = Q(login_ip=ip)
            if not refresh_all:
                ip_query &= Q(login_latitude__isnull=True)
            if tenant_id is not None:
                ip_query &= Q(tenant_id=tenant_id)
            update_fields: dict[str, Any] = {
                "login_latitude": float(lat),
                "login_longitude": float(lon),
            }
            if location:
                update_fields["login_location"] = location
            count = await LoginLog.filter(ip_query).update(**update_fields)
            if count:
                updated_rows += int(count)
                resolved_ips += 1

        for offset in range(0, len(unique_ips), batch_size):
            batch = unique_ips[offset : offset + batch_size]
            await asyncio.gather(*[_resolve_ip(ip) for ip in batch])
            if offset + batch_size < len(unique_ips):
                await asyncio.sleep(0.35)

        return {
            "candidate_ips": len(unique_ips),
            "resolved_ips": resolved_ips,
            "reused_ips": reused_ips,
            "skipped_ips": skipped_ips,
            "updated_rows": updated_rows,
        }

