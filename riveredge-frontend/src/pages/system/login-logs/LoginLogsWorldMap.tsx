import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Empty, Spin, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import * as echarts from 'echarts/core';
import { EffectScatterChart, MapChart } from 'echarts/charts';
import { GeoComponent, TooltipComponent, VisualMapComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsOption } from 'echarts';
import worldGeoJson from '../../../assets/geo/world.json';
import {
  getLoginLogMapPoints,
  LoginLogMapPoint,
  LoginLogMapPointsResponse,
} from '../../../services/loginLog';
import { formatDateTimeBySiteSetting } from '../../../utils/format';

echarts.use([
  MapChart,
  EffectScatterChart,
  GeoComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

const WORLD_MAP_NAME = 'login_logs_world';

let worldMapRegistered = false;

function ensureWorldMapRegistered(): void {
  if (worldMapRegistered) return;
  echarts.registerMap(WORLD_MAP_NAME, worldGeoJson as never);
  worldMapRegistered = true;
}

export interface LoginLogMapQuery {
  login_status?: string;
  username?: string;
  login_ip?: string;
  start_time?: string;
  end_time?: string;
}

export interface LoginLogsWorldMapProps {
  query: LoginLogMapQuery;
  refreshToken: number;
}

const MAP_SHELL_STYLE: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  flex: 1,
  minHeight: 0,
  height: '100%',
};

function resolveMapGeoView(points: LoginLogMapPoint[]): { center: [number, number]; zoom: number } {
  if (!points.length) {
    return { center: [105, 35], zoom: 4.5 };
  }

  const sorted = [...points].sort((a, b) => b.login_count - a.login_count);
  const totalWeight = sorted.reduce(
    (sum, point) => sum + (point.login_count > 0 ? point.login_count : 1),
    0,
  );
  const focusWeight = Math.max(1, totalWeight * 0.85);
  const focusPoints: LoginLogMapPoint[] = [];
  let accumulated = 0;
  for (const point of sorted) {
    focusPoints.push(point);
    accumulated += point.login_count > 0 ? point.login_count : 1;
    if (accumulated >= focusWeight) break;
  }

  let lngSum = 0;
  let latSum = 0;
  let weightSum = 0;
  let minLng = Infinity;
  let maxLng = -Infinity;
  let minLat = Infinity;
  let maxLat = -Infinity;

  for (const point of focusPoints) {
    const weight = point.login_count > 0 ? point.login_count : 1;
    lngSum += point.longitude * weight;
    latSum += point.latitude * weight;
    weightSum += weight;
    minLng = Math.min(minLng, point.longitude);
    maxLng = Math.max(maxLng, point.longitude);
    minLat = Math.min(minLat, point.latitude);
    maxLat = Math.max(maxLat, point.latitude);
  }

  const center: [number, number] = [lngSum / weightSum, latSum / weightSum];
  const lngSpan = Math.max(maxLng - minLng, 3);
  const latSpan = Math.max(maxLat - minLat, 2.5);
  const span = Math.max(lngSpan, latSpan / 0.75);
  const zoom = Math.min(10, Math.max(2.8, 32 / span));

  return { center, zoom };
}

export const LoginLogsWorldMap: React.FC<LoginLogsWorldMapProps> = ({
  query,
  refreshToken,
}) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const [loading, setLoading] = useState(true);
  const [payload, setPayload] = useState<LoginLogMapPointsResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getLoginLogMapPoints(query)
      .then((res) => {
        if (!cancelled) setPayload(res);
      })
      .catch(() => {
        if (!cancelled) setPayload({ items: [], unresolved_ips: [], scanned_logs: 0, unique_ips: 0 });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query, refreshToken]);

  const option = useMemo((): EChartsOption => {
    ensureWorldMapRegistered();
    const points = payload?.items ?? [];
    const maxCount = Math.max(1, ...points.map((p) => p.login_count));
    const geoView = resolveMapGeoView(points);
    return {
      backgroundColor: '#f4f7fb',
      tooltip: {
        trigger: 'item',
        formatter: (params) => {
          const raw = params as { data?: LoginLogMapPoint & { value?: [number, number, number] } };
          const row = raw.data;
          if (!row) return '';
          const title = row.login_location || row.login_ip;
          if (!title) return '';
          const users =
            row.usernames?.length > 0
              ? row.usernames.join('、')
              : t('pages.system.loginLogs.mapNoUsername');
          const lines = [
            `<div style="font-weight:600;margin-bottom:4px">${title}</div>`,
            `${t('pages.system.loginLogs.loginLocation')}：${row.login_location || '-'}`,
            `${t('pages.system.loginLogs.mapLoginCount')}：${row.login_count}`,
            `${t('pages.system.loginLogs.mapSuccessFailed')}：${row.success_count}/${row.failed_count}`,
          ];
          if ((row.ip_count ?? 1) > 1) {
            lines.push(
              `${t('pages.system.loginLogs.mapIpCount')}：${row.ip_count}`,
            );
          }
          if (row.login_ip) {
            lines.push(`${t('pages.system.loginLogs.loginIp')}：${row.login_ip}`);
          }
          lines.push(
            `${t('pages.system.loginLogs.mapUsers')}：${users}`,
            `${t('pages.system.loginLogs.mapLastLogin')}：${formatDateTimeBySiteSetting(row.last_login_at)}`,
          );
          return lines.join('<br/>');
        },
      },
      visualMap: {
        min: 1,
        max: maxCount,
        calculable: true,
        orient: 'horizontal',
        left: 16,
        bottom: 12,
        text: [t('pages.system.loginLogs.mapHeatHigh'), t('pages.system.loginLogs.mapHeatLow')],
        inRange: {
          color: ['#91caff', '#1677ff', '#003eb3'],
        },
        textStyle: { color: token.colorTextSecondary },
      },
      geo: {
        map: WORLD_MAP_NAME,
        roam: true,
        zoom: geoView.zoom,
        center: geoView.center,
        aspectScale: 0.75,
        layoutCenter: ['50%', '50%'],
        layoutSize: '100%',
        label: { show: false },
        itemStyle: {
          areaColor: '#dce4ef',
          borderColor: '#8c9bb0',
          borderWidth: 0.8,
        },
        emphasis: {
          itemStyle: {
            areaColor: '#c5d3e3',
          },
        },
      },
      series: [
        {
          name: t('pages.system.loginLogs.mapSeriesName'),
          type: 'effectScatter',
          coordinateSystem: 'geo',
          geoIndex: 0,
          data: points.map((p) => ({
            ...p,
            name: p.login_location || p.login_ip,
            value: [p.longitude, p.latitude, p.login_count],
          })),
          symbolSize: (val) => {
            const count = Array.isArray(val) ? Number(val[2] || 1) : 1;
            return Math.min(40, 10 + Math.sqrt(count) * 5);
          },
          showEffectOn: 'render',
          rippleEffect: {
            brushType: 'stroke',
            scale: 2.4,
          },
          itemStyle: {
            color: token.colorPrimary,
            shadowBlur: 8,
            shadowColor: 'rgba(22, 119, 255, 0.35)',
          },
          zlevel: 2,
        },
      ],
    };
  }, [payload?.items, t, token]);

  useLayoutEffect(() => {
    if (!containerRef.current || !payload?.items.length) return;
    ensureWorldMapRegistered();
    const el = containerRef.current;
    if (!chartRef.current) {
      chartRef.current = echarts.init(el);
    }
    chartRef.current.setOption(option, true);
    chartRef.current.resize();

    const ro = new ResizeObserver(() => {
      chartRef.current?.resize();
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, [option, payload?.items.length]);

  useEffect(() => {
    return () => {
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  if (loading) {
    return (
      <div style={{ ...MAP_SHELL_STYLE, alignItems: 'center', justifyContent: 'center' }}>
        <Spin description={t('pages.system.loginLogs.mapLoading')} />
      </div>
    );
  }

  if (!payload?.items.length) {
    return (
      <div style={{ ...MAP_SHELL_STYLE, alignItems: 'center', justifyContent: 'center' }}>
        <Empty description={t('pages.system.loginLogs.mapEmpty')} />
      </div>
    );
  }

  return (
    <div style={MAP_SHELL_STYLE}>
      <div
        ref={containerRef}
        style={{
          flex: 1,
          minHeight: 0,
          width: '100%',
          backgroundColor: '#f4f7fb',
          border: `1px solid ${token.colorBorderSecondary}`,
          borderRadius: token.borderRadius,
        }}
      />
    </div>
  );
};
