/**
 * 天气组件
 *
 * 显示当前天气信息，包括温度、天气状况、写实图标
 * 按站点「用户位置」：IP 定位或手工行政区
 *
 * @author Luigi Lu
 * @date 2026-01-21
 */

import React, { useState, useEffect, useLayoutEffect, useCallback, useRef, useMemo } from 'react';
import { Space, Typography, Spin, Tooltip } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {
  getWeatherByIP,
  type WeatherData,
  getCachedWeather,
  isWeatherCacheExpired,
  localizeWeatherData,
  reverseGeocodeLabel,
  resolveWeatherLanguage,
  getSiteWeatherLocationKey,
} from '../../services/weather';
import { useConfigStore } from '../../stores/configStore';
import { getWeatherIcon } from './weatherIcons';

const { Text } = Typography;
const WEATHER_REFRESH_ONCE_PER_PAGE_KEY = 'RIVEREDGE_WEATHER_REFRESH_ONCE_PER_PAGE';
/** Zustand selector 缺省值须稳定引用，禁止 inline []（每次 render 新数组 → 无限重渲染 React #185） */
const EMPTY_REGION_CODES: string[] = [];

function weatherVisualKey(data: WeatherData | null): string {
  if (!data) return '';
  return [
    data.iconCode,
    data.temperature,
    data.city,
    data.description,
    data.lat ?? '',
    data.lon ?? '',
  ].join('|');
}

interface WeatherWidgetProps {
  /** 是否显示刷新按钮 */
  showRefresh?: boolean;
  /** 自定义样式 */
  style?: React.CSSProperties;
  /** 天气数据变化时回调（用于外层卡片背景随天气变化） */
  onWeatherChange?: (data: WeatherData | null) => void;
  /** 紧凑布局（窄列、工作台首行） */
  compact?: boolean;
  /** 侧栏日历等极窄场景：更小图标与字号，与周围文字对齐 */
  mini?: boolean;
  /** 浅色卡上用深色字；深色背景卡用 light（默认） */
  tone?: 'light' | 'dark';
}

/**
 * 天气组件
 */
export const WeatherWidget: React.FC<WeatherWidgetProps> = ({
  showRefresh = true,
  style,
  onWeatherChange,
  compact = false,
  mini = false,
  tone = 'dark',
}) => {
  const { t, i18n } = useTranslation();
  const configInitialized = useConfigStore((s) => s.initialized);
  const locationMode = useConfigStore((s) => s.getConfig<string>('user_location.mode', 'ip'));
  const locationCodes = useConfigStore((s) =>
    s.getConfig<string[]>('user_location.region_codes', EMPTY_REGION_CODES),
  );
  const locationKey = useMemo(
    () => getSiteWeatherLocationKey(),
    [locationMode, Array.isArray(locationCodes) ? locationCodes.join('/') : '']
  );
  // 1. 优先从本地缓存读取，实现"秒开"
  const cachedWeather = getCachedWeather(i18n.language);
  const [weather, setWeather] = useState<WeatherData | null>(cachedWeather);
  const [loading, setLoading] = useState(!cachedWeather);
  const [error, setError] = useState<string | null>(null);
  const [localizedCity, setLocalizedCity] = useState<string | null>(null);
  const weatherRef = useRef<WeatherData | null>(cachedWeather);
  /** 位置配置未就绪时发出的请求作废，避免约 15 秒后覆盖已画好的天气并重绘天空背景 */
  const requestGenRef = useRef(0);
  /** 同一位置只自动请求一次。翻译函数换引用不能把进行中的 IP 定位和 Open-Meteo 作废重开 */
  const startedKeyRef = useRef<string | null>(null);

  useEffect(() => {
    weatherRef.current = weather;
  }, [weather]);

  useLayoutEffect(() => {
    onWeatherChange?.(weather);
  }, [weather, onWeatherChange]);

  /**
   * 加载天气数据
   * @param force 是否强制刷新
   */
  const loadWeather = useCallback(async (force = false) => {
    const gen = ++requestGenRef.current;
    const hasCurrentWeather = !!weatherRef.current;
    // 已有天气时后台刷新，不要换成 Spin，否则 请求结束会把日历顶栏再画一遍
    if (!hasCurrentWeather) {
      setLoading(true);
    }
    setError(null);
    try {
      const data = await getWeatherByIP(force, i18n.language);
      if (gen !== requestGenRef.current) return;
      if (data) {
        setWeather((prev) => (weatherVisualKey(prev) === weatherVisualKey(data) ? prev : data));
      } else if (!hasCurrentWeather) {
        setWeather(null);
        setError(t('components.weather.loadFailed'));
      }
    } catch (err: unknown) {
      if (gen !== requestGenRef.current) return;
      if (typeof window !== 'undefined') {
        window.console.error('加载天气失败:', err);
      }
      if (!hasCurrentWeather) {
        setWeather(null);
        setError(err instanceof Error ? err.message : t('components.weather.loadFailed'));
      }
    } finally {
      if (gen === requestGenRef.current) {
        setLoading(false);
      }
    }
  }, [t, i18n.language]);

  const loadWeatherRef = useRef(loadWeather);
  loadWeatherRef.current = loadWeather;

  const displayWeather = useMemo(
    () => (weather ? localizeWeatherData(weather, i18n.language) : null),
    [weather, i18n.language]
  );

  useEffect(() => {
    if (!weather?.lat || !weather?.lon) {
      setLocalizedCity(null);
      return;
    }
    let cancelled = false;
    const lang = resolveWeatherLanguage(i18n.language);
    reverseGeocodeLabel(weather.lat, weather.lon, lang).then((name) => {
      if (!cancelled) setLocalizedCity(name);
    });
    return () => {
      cancelled = true;
    };
  }, [weather?.lat, weather?.lon, i18n.language]);

  useEffect(() => {
    // 工作台要等站点配置才挂上，这里再等一次只是避免配置未到时打错位置。
    // 同一位置只发一次，且不跳过缓存。天气还没返回时不能因为 t 换引用就重开 IP 定位。
    if (!configInitialized) return;
    const runKey = `${locationKey}|${i18n.language}`;
    const pageKey = `${WEATHER_REFRESH_ONCE_PER_PAGE_KEY}:${locationKey}`;
    const cached = getCachedWeather(i18n.language);
    if (cached && !isWeatherCacheExpired()) {
      requestGenRef.current += 1;
      startedKeyRef.current = runKey;
      setWeather((prev) => (weatherVisualKey(prev) === weatherVisualKey(cached) ? prev : cached));
      setLoading(false);
      window.sessionStorage.setItem(pageKey, '1');
      return;
    }
    if (startedKeyRef.current === runKey) return;
    startedKeyRef.current = runKey;
    window.sessionStorage.setItem(pageKey, '1');
    void loadWeatherRef.current(false);
  }, [configInitialized, locationKey, i18n.language]);

  const iconBox = mini ? 48 : 56;
  const tempSize = mini ? 16 : compact ? 24 : 20;
  const metaSize = mini ? 11 : compact ? 12 : 13;

  const tc =
    tone === 'light'
      ? {
          primary: '#18181b',
          meta: 'rgba(24, 24, 27, 0.78)',
          muted: 'rgba(24, 24, 27, 0.52)',
        }
      : {
          primary: '#ffffff',
          meta: 'rgba(255, 255, 255, 0.85)',
          muted: 'rgba(255, 255, 255, 0.65)',
        };

  if (loading) {
    return (
      <Space style={style} size={compact ? 'small' : 'middle'}>
        <Spin size="small" />
        <Text style={{ color: tc.meta, fontSize: compact ? 12 : 14 }}>
          {t('components.weather.loading')}
        </Text>
      </Space>
    );
  }

  if (error || !displayWeather) {
    return (
      <Space style={style} size={compact ? 'small' : 'middle'}>
        <Text style={{ color: tc.muted, fontSize: compact ? 12 : 14 }}>
          {t('components.weather.unavailable')}
        </Text>
        {showRefresh && (
          <ReloadOutlined
            style={{
              color: tc.meta,
              cursor: 'pointer',
              fontSize: 14,
            }}
            onClick={() => loadWeather(true)}
          />
        )}
      </Space>
    );
  }

  // 获取天气图标
  const weatherIcon = getWeatherIcon(
    displayWeather.iconCode,
    displayWeather.description,
    iconBox,
  );
  const cityLabel = localizedCity ?? displayWeather.city;

  return (
    <Space 
      size={compact ? 'small' : 'middle'}
      style={style}
    >
      {/* 天气图标 */}
      <div style={{ fontSize: iconBox, lineHeight: 1, flexShrink: 0 }}>
        {weatherIcon}
      </div>
      
      {/* 天气信息 */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: mini || compact ? 2 : 4,
          minWidth: 0,
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1, lineHeight: 1.1 }}>
          <Text
            style={{
              color: tc.primary,
              fontSize: tempSize,
              fontWeight: 600,
              lineHeight: 1.1,
              whiteSpace: 'nowrap',
              margin: 0,
            }}
          >
            {displayWeather.temperature}°C
          </Text>
          {displayWeather.feelsLike !== undefined &&
            displayWeather.feelsLike !== displayWeather.temperature && (
              <Text
                style={{
                  color: tc.muted,
                  fontSize: mini ? 10 : compact ? 11 : 12,
                  lineHeight: 1.1,
                  margin: 0,
                  whiteSpace: 'nowrap',
                }}
              >
                {t('components.weather.feelsLike', { value: displayWeather.feelsLike })}
              </Text>
            )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1, lineHeight: 1.1 }}>
          <Text
            ellipsis
            style={{
              color: tc.meta,
              fontSize: metaSize,
              lineHeight: 1.1,
              margin: 0,
            }}
          >
            {cityLabel}
          </Text>
          <Text
            ellipsis
            style={{
              color: tc.muted,
              fontSize: metaSize,
              lineHeight: 1.1,
              margin: 0,
            }}
          >
            {displayWeather.description}
          </Text>
        </div>
      </div>

      {/* 刷新按钮 */}
      {showRefresh && (
        <Tooltip title={t('components.weather.refresh')}>
          <ReloadOutlined
            style={{
              color: tc.muted,
              cursor: 'pointer',
              fontSize: compact ? 13 : 14,
            }}
            onClick={() => loadWeather(true)}
          />
        </Tooltip>
      )}
    </Space>
  );
};

export default WeatherWidget;
