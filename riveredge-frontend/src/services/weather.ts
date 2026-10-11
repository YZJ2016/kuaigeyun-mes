/**
 * 天气服务
 *
 * 提供天气相关的API调用
 * 使用免费的天气API服务
 *
 * @author Luigi Lu
 * @date 2026-01-21
 */

import i18n from '../config/i18n';
import { resolveChinaAdminRegionLabels, resolveWeatherCityLabel } from '../constants/chinaAdminRegions';
import { useConfigStore } from '../stores/configStore';

/**
 * 天气数据接口
 */
export interface WeatherData {
  /** 城市名称 */
  city: string;
  /** 当前温度（摄氏度） */
  temperature: number;
  /** 天气描述（如：晴、多云、雨等） */
  description: string;
  /** 天气代码（用于匹配图标） */
  iconCode: string;
  /** 湿度（百分比） */
  humidity?: number;
  /** 风速（km/h） */
  windSpeed?: number;
  /** 体感温度 */
  feelsLike?: number;
  /** 定位纬度（用于按语言反查地名） */
  lat?: number;
  /** 定位经度 */
  lon?: number;
}

export type WeatherLang = 'zh' | 'en';

/** 解析当前界面语言对应的天气文案语言 */
export function resolveWeatherLanguage(language?: string): WeatherLang {
  const raw = language ?? i18n.language ?? 'zh-CN';
  return String(raw).toLowerCase().startsWith('en') ? 'en' : 'zh';
}

/**
 * IP定位数据接口
 */
export interface LocationData {
  /** 城市名称 */
  city: string;
  /** 省份/州 */
  region?: string;
  /** 国家 */
  country?: string;
  /** 经纬度 */
  lat?: number;
  lon?: number;
}

/**
 * 获取IP定位信息
 * 通过后端代理调用 ip-api.com，避免 HTTPS 页面的 Mixed Content 问题
 */
export async function getLocationByIP(): Promise<LocationData | null> {
  try {
    const { apiRequest } = await import('./api');
    const data = await apiRequest<{ city?: string; region?: string; country?: string; lat?: number; lon?: number }>(
      '/core/ip-location'
    );
    if (data && (data.city || data.region || data.country)) {
      return {
        city: data.city || '',
        region: data.region || '',
        country: data.country || '',
        lat: data.lat,
        lon: data.lon,
      };
    }
    return null;
  } catch (error) {
    if (typeof window !== 'undefined') {
      window.console.error('获取IP定位失败:', error);
    }
    return null;
  }
}

/**
 * 通过 Open-Meteo 地理编号 API 将城市名解析为经纬度
 */
type GeoHit = { lat: number; lon: number; label?: string; admin1?: string };

const ADMIN_SUFFIX =
  /(?:维吾尔自治区|壮族自治区|回族自治区|特别行政区|自治区|自治州|地区|盟|省|市|区|县|旗)$/u;

function adminStem(name: string): string {
  return name.replace(ADMIN_SUFFIX, '').trim();
}

function isPlaceholderAdminLabel(name: string): boolean {
  return name === '市辖区' || name === '县' || name === '省直辖县级行政区划';
}

async function searchGeo(name: string, language: WeatherLang): Promise<GeoHit[]> {
  try {
    const url = `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(name)}&count=8&language=${language}`;
    const res = await window.fetch(url, { signal: (window.AbortSignal as any).timeout(5000) });
    if (!res.ok) return [];
    const data = await res.json();
    const results = data.results;
    if (!Array.isArray(results)) return [];
    const hits: GeoHit[] = [];
    for (const r of results) {
      const lat = parseFloat(r.latitude);
      const lon = parseFloat(r.longitude);
      if (Number.isNaN(lat) || Number.isNaN(lon)) continue;
      hits.push({
        lat,
        lon,
        label: typeof r.name === 'string' ? r.name : undefined,
        admin1: typeof r.admin1 === 'string' ? r.admin1 : undefined,
      });
    }
    return hits;
  } catch {
    return [];
  }
}

function admin1Matches(admin1: string | undefined, provinceKey: string): boolean {
  if (!provinceKey) return true;
  if (!admin1) return false;
  const stem = adminStem(admin1);
  return stem === provinceKey || stem.includes(provinceKey) || provinceKey.includes(stem);
}

/**
 * 手工行政区：Open-Meteo 没有「玄武区」这类区县，且去掉「区」后会命中外省同名点。
 * 区县用上一级市名查询，再用省名对上 admin1。
 */
async function geocodeChinaAdminLabels(
  labels: string[],
  language: WeatherLang,
): Promise<GeoHit | null> {
  const usable = labels.map((x) => String(x).trim()).filter((x) => x && !isPlaceholderAdminLabel(x));
  if (!usable.length) return null;
  const provinceKey = adminStem(usable[0]);
  const names: string[] = [];
  const push = (raw: string | undefined) => {
    if (!raw) return;
    const stem = adminStem(raw);
    if (stem && !names.includes(stem)) names.push(stem);
    if (raw !== stem && !names.includes(raw)) names.push(raw);
  };
  const last = usable[usable.length - 1];
  const isDistrict = /(区|县|旗)$/.test(last);
  if (isDistrict && usable.length >= 2) {
    push(usable[usable.length - 2]);
  }
  for (let i = usable.length - 1; i >= 0; i -= 1) push(usable[i]);
  for (const name of names) {
    const hits = await searchGeo(name, language);
    const matched = hits.find((hit) => admin1Matches(hit.admin1, provinceKey));
    if (matched) return matched;
  }
  return null;
}

async function geocodeCity(cityName: string, language: WeatherLang = 'zh'): Promise<GeoHit | null> {
  const hits = await searchGeo(cityName, language);
  return hits[0] ?? null;
}

/** 逆地理：按当前语言返回城市/地区名（经后端代理，Open-Meteo 无 reverse 端点） */
export async function reverseGeocodeLabel(
  lat: number,
  lon: number,
  language: WeatherLang = resolveWeatherLanguage()
): Promise<string | null> {
  try {
    const { apiRequest } = await import('./api');
    const data = await apiRequest<{ name?: string }>(
      `/core/ip-location/reverse?latitude=${encodeURIComponent(String(lat))}&longitude=${encodeURIComponent(String(lon))}&language=${encodeURIComponent(language)}`
    );
    const name = data?.name?.trim();
    return name || null;
  } catch {
    return null;
  }
}

/**
 * 通过 Open-Meteo 获取天气（经纬度）
 */
async function getWeatherByCoords(
  lat: number,
  lon: number,
  cityLabel?: string,
  language: WeatherLang = resolveWeatherLanguage()
): Promise<WeatherData | null> {
  try {
    const meteoUrl = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&timezone=auto`;
    const res = await window.fetch(meteoUrl, { signal: (window.AbortSignal as any).timeout(6000) });
    if (!res.ok) return null;
    const data = await res.json();
    const current = data.current;
    if (!current) return null;
    const weatherCode = current.weather_code || 0;
    let city = cityLabel;
    if (!city) {
      city = (await reverseGeocodeLabel(lat, lon, language)) ?? `${lat},${lon}`;
    }
    return {
      city,
      lat,
      lon,
      temperature: Math.round(current.temperature_2m ?? 0),
      description: getWeatherDescription(weatherCode, language),
      iconCode: weatherCode.toString(),
      humidity: Math.round(current.relative_humidity_2m ?? 0),
      windSpeed: Math.round((current.wind_speed_10m ?? 0) * 3.6),
      feelsLike: Math.round(current.temperature_2m ?? 0),
    };
  } catch {
    return null;
  }
}

/**
 * 获取天气信息。只走 Open-Meteo。
 * 经纬度不再把 "lat,lon" 当城市名再查一遍，也不再串 wttr.in。
 * 三段超时（约 6s + 5s + 4s）会在工作台已经画完后约 15 秒才返回，并带动日历天空背景重绘。
 *
 * @param city 城市名称或经纬度（格式：lat,lon）
 */
export async function getWeather(city: string, language: WeatherLang = resolveWeatherLanguage()): Promise<WeatherData | null> {
  try {
    if (city.includes(',')) {
      const parts = city.split(',');
      const lat = parseFloat(parts[0]);
      const lon = parseFloat(parts[1]);
      if (!isNaN(lat) && !isNaN(lon)) {
        return getWeatherByCoords(lat, lon, undefined, language);
      }
    }

    const coords = await geocodeCity(city, language);
    if (!coords) return null;
    return getWeatherByCoords(
      coords.lat,
      coords.lon,
      coords.label ?? city,
      language
    );
  } catch (error) {
    if (typeof window !== 'undefined') {
      window.console.error('获取天气信息失败:', error);
    }
    return null;
  }
}

/**
 * 根据 Open-Meteo WMO 天气代码获取本地化描述
 */
export function getWeatherDescription(code: number, language: WeatherLang = resolveWeatherLanguage()): string {
  const zhMap: Record<number, string> = {
    0: '晴',
    1: '基本晴',
    2: '部分多云',
    3: '阴',
    45: '雾',
    48: '沉积霜雾',
    51: '小雨',
    53: '中雨',
    55: '大雨',
    56: '冻小雨',
    57: '冻大雨',
    61: '小雨',
    63: '中雨',
    65: '大雨',
    66: '冻雨',
    67: '冻大雨',
    71: '小雪',
    73: '中雪',
    75: '大雪',
    77: '雪粒',
    80: '小阵雨',
    81: '中阵雨',
    82: '大阵雨',
    85: '小阵雪',
    86: '大阵雪',
    95: '雷暴',
    96: '雷暴伴冰雹',
    99: '雷暴伴大冰雹',
  };
  const enMap: Record<number, string> = {
    0: 'Clear',
    1: 'Mainly clear',
    2: 'Partly cloudy',
    3: 'Overcast',
    45: 'Fog',
    48: 'Depositing rime fog',
    51: 'Light drizzle',
    53: 'Moderate drizzle',
    55: 'Dense drizzle',
    56: 'Light freezing drizzle',
    57: 'Dense freezing drizzle',
    61: 'Slight rain',
    63: 'Moderate rain',
    65: 'Heavy rain',
    66: 'Light freezing rain',
    67: 'Heavy freezing rain',
    71: 'Slight snow',
    73: 'Moderate snow',
    75: 'Heavy snow',
    77: 'Snow grains',
    80: 'Slight rain showers',
    81: 'Moderate rain showers',
    82: 'Violent rain showers',
    85: 'Slight snow showers',
    86: 'Heavy snow showers',
    95: 'Thunderstorm',
    96: 'Thunderstorm with hail',
    99: 'Thunderstorm with heavy hail',
  };
  const map = language === 'en' ? enMap : zhMap;
  return map[code] ?? (language === 'en' ? 'Unknown' : '未知');
}

/** 按当前语言刷新描述（城市名需配合 reverseGeocodeLabel） */
export function localizeWeatherData(
  data: WeatherData,
  language?: string
): WeatherData {
  const lang = resolveWeatherLanguage(language);
  const code = parseInt(data.iconCode, 10);
  const normalizedCode = Number.isFinite(code) ? code : 0;
  return {
    ...data,
    description: getWeatherDescription(normalizedCode, lang),
  };
}

const WEATHER_CACHE_KEY = 'RIVEREDGE_WEATHER_CACHE_V3';
const WEATHER_CACHE_DURATION = 60 * 60 * 1000; // 缓存1小时

interface WeatherCachePayload {
  data: WeatherData;
  timestamp: number;
  /** 定位来源指纹：变更站点用户位置后须失效 */
  locationKey: string;
}

export type SiteWeatherLocationMode = 'ip' | 'manual';

export function getSiteWeatherLocationMode(): SiteWeatherLocationMode {
  const mode = useConfigStore.getState().getConfig<string>('user_location.mode', 'ip');
  return mode === 'manual' ? 'manual' : 'ip';
}

function readManualRegionLabels(): string[] {
  const stored = useConfigStore.getState().getConfig<string[]>('user_location.region_labels', []);
  if (Array.isArray(stored) && stored.length > 0) {
    return stored.map((item) => String(item));
  }
  const codes = useConfigStore.getState().getConfig<string[]>('user_location.region_codes', []);
  return resolveChinaAdminRegionLabels(Array.isArray(codes) ? codes.map((item) => String(item)) : []);
}

export function getSiteWeatherManualCity(): string | null {
  return resolveWeatherCityLabel(readManualRegionLabels());
}

export function getSiteWeatherLocationKey(): string {
  const mode = getSiteWeatherLocationMode();
  if (mode === 'manual') {
    const city = getSiteWeatherManualCity() || '';
    const codes = useConfigStore.getState().getConfig<string[]>('user_location.region_codes', []);
    return `manual:${Array.isArray(codes) ? codes.join('/') : ''}:${city}`;
  }
  return 'ip';
}

function readWeatherCache(): WeatherCachePayload | null {
  try {
    if (typeof window === 'undefined') return null;
    const cached = window.localStorage.getItem(WEATHER_CACHE_KEY);
    if (!cached) return null;
    const parsed = JSON.parse(cached) as WeatherCachePayload;
    if (!parsed?.data || typeof parsed.timestamp !== 'number') {
      window.localStorage.removeItem(WEATHER_CACHE_KEY);
      return null;
    }
    if (parsed.locationKey !== getSiteWeatherLocationKey()) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

/**
 * 获取本地缓存的天气数据
 */
export function getCachedWeather(language?: string): WeatherData | null {
  const raw = readWeatherCache()?.data ?? null;
  if (!raw) return null;
  return localizeWeatherData(raw, language);
}

/**
 * 本地天气缓存是否超过有效期
 */
export function isWeatherCacheExpired(maxAge = WEATHER_CACHE_DURATION): boolean {
  const cached = readWeatherCache();
  if (!cached) return true;
  return Date.now() - cached.timestamp > maxAge;
}

/**
 * 按站点「用户位置」获取天气：IP 定位或手工行政区。
 * 增加本地缓存逻辑，减少拉取频率。
 *
 * @param force 是否强制拉取最新数据（跳过缓存）
 */
export async function getWeatherByIP(force = false, language?: string): Promise<WeatherData | null> {
  return getSiteWeather(force, language);
}

/**
 * 工作台天气入口：读取站点用户位置配置。
 */
export async function getSiteWeather(force = false, language?: string): Promise<WeatherData | null> {
  const lang = resolveWeatherLanguage(language);
  const locationKey = getSiteWeatherLocationKey();
  try {
    if (!force) {
      const cached = readWeatherCache();
      if (cached && Date.now() - cached.timestamp < WEATHER_CACHE_DURATION) {
        return localizeWeatherData(cached.data, lang);
      }
    }

    let weather: WeatherData | null = null;
    if (getSiteWeatherLocationMode() === 'manual') {
      const labels = readManualRegionLabels();
      const city = resolveWeatherCityLabel(labels);
      if (!city) return null;
      const coords = await geocodeChinaAdminLabels(labels, lang);
      if (!coords) return null;
      weather = await getWeatherByCoords(coords.lat, coords.lon, city, lang);
      if (weather) {
        weather.city = city;
        weather.description = getWeatherDescription(parseInt(weather.iconCode, 10) || 0, lang);
      }
    } else {
      const location = await getLocationByIP();
      if (!location || (!location.city && (location.lat == null || location.lon == null))) {
        return null;
      }
      const locationParam =
        location.lat != null && location.lon != null
          ? `${location.lat},${location.lon}`
          : location.city;

      weather = await getWeather(locationParam, lang);
      if (weather) {
        if (location.lat != null && location.lon != null) {
          weather.lat = location.lat;
          weather.lon = location.lon;
        }
        if (!weather.city || weather.city.includes(',')) {
          weather.city = location.city || location.region || weather.city;
        }
        weather.description = getWeatherDescription(parseInt(weather.iconCode, 10) || 0, lang);
      }
    }

    if (weather && typeof window !== 'undefined') {
      window.localStorage.setItem(
        WEATHER_CACHE_KEY,
        JSON.stringify({
          data: weather,
          timestamp: Date.now(),
          locationKey,
        } satisfies WeatherCachePayload)
      );
    }
    return weather;
  } catch (error) {
    if (typeof window !== 'undefined') {
      window.console.error('获取站点天气失败:', error);
    }
    return null;
  }
}
