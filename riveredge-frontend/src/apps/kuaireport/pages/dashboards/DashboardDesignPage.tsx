import React, { useEffect, useRef, useState } from 'react';
import {
  App,
  Button,
  ColorPicker,
  Input,
  InputNumber,
  Select,
  Space,
  Tooltip,
  Upload,
} from 'antd';
import type { InputRef } from 'antd';
import {
  ArrowLeftOutlined,
  BarChartOutlined,
  BorderOuterOutlined,
  ClockCircleOutlined,
  ColumnHeightOutlined,
  ColumnWidthOutlined,
  DesktopOutlined,
  DoubleLeftOutlined,
  DoubleRightOutlined,
  EditOutlined,
  EyeOutlined,
  FontSizeOutlined,
  FullscreenOutlined,
  GlobalOutlined,
  PictureOutlined,
  PlaySquareOutlined,
  RedoOutlined,
  SaveOutlined,
  SoundOutlined,
  TableOutlined,
  UndoOutlined,
  UploadOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import './dashboardDesigner.css';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { DashboardWidgets, FlowBoard, flowParentId, type DashboardWidget, type FlowDropTarget } from './DashboardWidgets';
import {
  CANVAS_HEIGHT,
  CANVAS_WIDTH,
  DATA_WIDGET_TYPES,
  DEFAULT_THEME,
  DashboardStage,
  contentBox,
  isCanvasLayout,
  isFlowLayout,
  parseTheme,
  useThemeImageUrl,
  type PageTheme,
} from './dashboardStage';
import {
  createDashboard,
  getDashboardPreview,
  listDataSources,
  updateDashboard,
  type DataSourceOption,
} from './api';
import { getFileDownloadUrlWithToken, uploadFile } from '../../../../services/file';

type PaletteItem = {
  type: string;
  label: string;
  group: '容器' | '装饰' | '数据';
  w: number;
  h: number;
  contentTitle?: string;
  options?: Record<string, unknown>;
};

type CanvasWidget = {
  id: string;
  type: string;
  label: string;
  data_source_id?: number;
  refresh_seconds: number;
  title: string;
  options: Record<string, unknown>;
  layout: { x: number; y: number; w: number; h: number };
};

const ZOOM_FIT = 'fit';
const ZOOM_STOPS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2];

function stepZoom(zoom: typeof ZOOM_FIT | number, scale: number, direction: -1 | 1): number | null {
  if (zoom === ZOOM_FIT) {
    if (direction < 0) {
      for (let index = ZOOM_STOPS.length - 1; index >= 0; index -= 1) {
        if (ZOOM_STOPS[index] < scale - 0.001) return ZOOM_STOPS[index];
      }
      return null;
    }
    return ZOOM_STOPS.find((stop) => stop > scale + 0.001) ?? null;
  }
  const index = ZOOM_STOPS.indexOf(zoom);
  if (index < 0) return null;
  const next = index + direction;
  if (next < 0 || next >= ZOOM_STOPS.length) return null;
  return ZOOM_STOPS[next];
}

const PALETTE: PaletteItem[] = [
  { group: '容器', type: 'columns', label: '分栏容器', contentTitle: '', w: 640, h: 200, options: { columns: 2, columnRatios: '1:1', gap: 12, fillHeight: 'off', minHeight: 200 } },
  { group: '容器', type: 'columns', label: '分行容器', contentTitle: '', w: 960, h: 480, options: { rows: 3, rowRatios: '1:4:2', gap: 12, fillHeight: 'on', minHeight: 200 } },
  { group: '容器', type: 'border', label: '边框面板', contentTitle: '面板', w: 480, h: 280, options: { variant: 'bevel', animate: 'off', flipHorizontal: 'off', fillHeight: 'off', minHeight: 200 } },
  { group: '容器', type: 'carousel', label: '轮播容器', contentTitle: '', w: 480, h: 240, options: { interval: 5000, minHeight: 240 } },
  { group: '装饰', type: 'image', label: '公司LOGO', contentTitle: '', w: 220, h: 56, options: { role: 'logo', source: 'site', text: '', textSize: 18, textAlign: 'right', width: 140, height: 48, align: 'left', fillEnabled: 'off', fillPadding: 6, fillRadius: 4 } },
  { group: '装饰', type: 'title', label: '看板标题', contentTitle: '生产看板', w: 720, h: 56, options: { variant: 'bevel', subtitle: '', animate: 'on' } },
  { group: '装饰', type: 'clock', label: '时间', contentTitle: '', w: 220, h: 56 },
  { group: '装饰', type: 'text', label: '文本', contentTitle: '', w: 280, h: 48, options: { text: '文本内容', color: '#ffffff' } },
  { group: '装饰', type: 'fullscreen', label: '全屏按钮', contentTitle: '', w: 168, h: 56, options: { label: '全屏', variant: 'bevel' } },
  { group: '装饰', type: 'marquee', label: '跑马灯', contentTitle: '', w: 640, h: 40, options: { text: '欢迎使用生产看板', color: '#ffffff' } },
  { group: '装饰', type: 'image', label: '图片', contentTitle: '', w: 320, h: 200, options: { fit: 'cover', radius: 0, opacity: 1, height: 200, fillEnabled: 'off', fillPadding: 8 } },
  { group: '装饰', type: 'video', label: '视频', contentTitle: '', w: 480, h: 240, options: { height: 240 } },
  { group: '装饰', type: 'web', label: '网页嵌入', contentTitle: '', w: 480, h: 320, options: { height: 320 } },
  { group: '数据', type: 'chart', label: '图表', contentTitle: '', w: 480, h: 280, options: { chart_type: 'line', palette: 'theme', fillHeight: 'off', height: 280, valueSource: 'manual', category_field: 'type', value_field: 'value', x_field: 'x', y_field: 'y' } },
  { group: '数据', type: 'metric', label: '指标卡', contentTitle: '指标卡', w: 240, h: 140, options: { indicatorType: 'number', valueSource: 'manual', value: 8888, unit: '', variant: 'bevel', color: '#00d4ff' } },
  { group: '数据', type: 'table', label: '表格', contentTitle: '', w: 640, h: 240, options: { height: 240, fillHeight: 'off', themeMode: 'dark', displayMode: 'table', columnKeys: '', scrollMode: 'none', valueSource: 'manual' } },
  { group: '数据', type: 'card_list', label: '卡片列表', contentTitle: '', w: 680, h: 320, options: { height: 320, orientation: 'vertical', scrollAxis: 'x', fillHeight: 'off', cardWidth: 196, scrollMode: 'auto', scrollInterval: 3000, valueSource: 'manual' } },
  { group: '数据', type: 'resource_list', label: '进度列表', contentTitle: '', w: 960, h: 220, options: { fillHeight: 'on', scrollMode: 'page', scrollInterval: 5000, valueSource: 'manual' } },
];

const GROUPS = ['容器', '装饰', '数据'] as const;

const ACCENT_PRESETS = ['#00d4ff', '#3b9eff', '#7c5cff', '#00e5a8', '#ff6b4a'];

function paletteIcon(item: PaletteItem) {
  if (item.label === '分行容器') return <ColumnHeightOutlined />;
  if (item.type === 'columns') return <ColumnWidthOutlined />;
  if (item.type === 'border') return <BorderOuterOutlined />;
  if (item.type === 'carousel') return <DesktopOutlined />;
  if (item.label === '公司LOGO' || item.type === 'image') return <PictureOutlined />;
  if (item.type === 'title' || item.type === 'text') return <FontSizeOutlined />;
  if (item.type === 'clock') return <ClockCircleOutlined />;
  if (item.type === 'fullscreen') return <FullscreenOutlined />;
  if (item.type === 'marquee') return <SoundOutlined />;
  if (item.type === 'video') return <PlaySquareOutlined />;
  if (item.type === 'web') return <GlobalOutlined />;
  if (item.type === 'chart') return <BarChartOutlined />;
  if (item.type === 'metric') return <AppstoreOutlined />;
  if (item.type === 'table') return <TableOutlined />;
  if (item.type === 'card_list') return <AppstoreOutlined />;
  return <UnorderedListOutlined />;
}

function newId(): string {
  return `w_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`;
}

function makeWidget(item: PaletteItem, x: number, y: number, box: { width: number; height: number }): CanvasWidget {
  const w = Math.min(item.w, box.width);
  const h = Math.min(item.h, box.height);
  return {
    id: newId(),
    type: item.type,
    label: item.label,
    refresh_seconds: 30,
    title: item.contentTitle !== undefined ? item.contentTitle : item.label,
    options: { ...(item.options || {}), palette_label: item.label },
    layout: {
      x: Math.max(0, Math.min(Math.round(x), Math.max(0, box.width - w))),
      y: Math.max(0, Math.min(Math.round(y), Math.max(0, box.height - h))),
      w,
      h,
    },
  };
}

function gridToPixel(layout: DashboardWidget['layout'], index: number): CanvasWidget['layout'] {
  const col = layout?.x ?? (index % 3) * 4;
  const row = layout?.y ?? Math.floor(index / 3) * 6;
  const span = layout?.w ?? 4;
  const height = layout?.h ?? 6;
  return {
    x: Math.round((col / 12) * CANVAS_WIDTH),
    y: Math.round(row * 24),
    w: Math.max(120, Math.round((span / 12) * CANVAS_WIDTH)),
    h: Math.max(48, Math.round(height * 24)),
  };
}

function fromSaved(widget: DashboardWidget, index: number, canvasMode: boolean): CanvasWidget {
  const options = { ...(widget.options || {}) };
  const pixel =
    canvasMode && widget.layout
      ? {
          x: Number(widget.layout.x) || 0,
          y: Number(widget.layout.y) || 0,
          w: Number(widget.layout.w) || 320,
          h: Number(widget.layout.h) || 180,
        }
      : gridToPixel(widget.layout, index);
  const label = typeof options.palette_label === 'string' ? options.palette_label : widget.title || widget.type;
  return {
    id: widget.id || `w${index + 1}`,
    type: widget.type,
    label,
    data_source_id: widget.data_source_id && widget.data_source_id > 0 ? widget.data_source_id : undefined,
    refresh_seconds: widget.refresh_seconds || 30,
    title: widget.title || label,
    options,
    layout: pixel,
  };
}

function slotOf(widget: { options?: Record<string, unknown> }): string | null {
  const value = widget.options?.slot;
  return typeof value === 'string' && value ? value : null;
}

function linkedParent(widget: CanvasWidget, list: CanvasWidget[]): string | null {
  const parent = flowParentId(widget);
  return parent && list.some((item) => item.id === parent) ? parent : null;
}

function sameFlowList(widget: CanvasWidget, target: FlowDropTarget, list: CanvasWidget[]): boolean {
  return linkedParent(widget, list) === target.parentId && (target.parentId ? slotOf(widget) === target.slot : true);
}

function isInside(list: CanvasWidget[], ancestorId: string, id: string | null): boolean {
  let current = id;
  const seen = new Set<string>();
  while (current && !seen.has(current)) {
    if (current === ancestorId) return true;
    seen.add(current);
    const widget = list.find((item) => item.id === current);
    current = widget ? flowParentId(widget) || null : null;
  }
  return false;
}

function assignParent(widget: CanvasWidget, target: FlowDropTarget, width: number): CanvasWidget {
  const options = { ...(widget.options || {}) };
  if (target.parentId) options.parent_id = target.parentId;
  else delete options.parent_id;
  if (target.slot) options.slot = target.slot;
  else delete options.slot;
  return { ...widget, options, layout: { ...widget.layout, x: 0, y: 0, w: width } };
}

function insertFlow(list: CanvasWidget[], widget: CanvasWidget, target: FlowDropTarget, width: number): CanvasWidget[] | null {
  if (target.parentId && (target.parentId === widget.id || isInside(list, widget.id, target.parentId))) return null;
  const from = list.filter((item) => sameFlowList(item, target, list)).findIndex((item) => item.id === widget.id);
  let index = target.index;
  if (from >= 0 && from < index) index -= 1;
  const placed = assignParent(widget, target, width);
  const rest = list.filter((item) => item.id !== widget.id);
  const family = [...rest, placed];
  const siblings = rest.filter((item) => sameFlowList(item, target, family));
  const at = Math.max(0, Math.min(index, siblings.length));
  const siblingIds = new Set(siblings.map((item) => item.id));
  const nextIds = siblings.map((item) => item.id);
  nextIds.splice(at, 0, placed.id);
  const byId = new Map(rest.map((item) => [item.id, item]));
  byId.set(placed.id, placed);
  const result: CanvasWidget[] = [];
  let inserted = false;
  for (const item of rest) {
    if (!siblingIds.has(item.id)) {
      result.push(item);
      continue;
    }
    if (!inserted) {
      nextIds.forEach((id) => {
        const next = byId.get(id);
        if (next) result.push(next);
      });
      inserted = true;
    }
  }
  if (!inserted) {
    nextIds.forEach((id) => {
      const next = byId.get(id);
      if (next) result.push(next);
    });
  }
  return result;
}

function cloneTree(list: CanvasWidget[], id: string): { widgets: CanvasWidget[]; id: string } | null {
  const root = list.find((widget) => widget.id === id);
  if (!root) return null;
  const idMap = new Map<string, string>();
  const walk = (current: string) => {
    idMap.set(current, newId());
    list.forEach((widget) => {
      if (flowParentId(widget) === current) walk(widget.id);
    });
  };
  walk(id);
  const clones = list
    .filter((widget) => idMap.has(widget.id))
    .map((widget) => {
      const parent = flowParentId(widget);
      const options = { ...(widget.options || {}) };
      if (parent && idMap.has(parent)) options.parent_id = idMap.get(parent);
      return { ...widget, id: idMap.get(widget.id) || newId(), options, layout: { ...widget.layout } };
    });
  const copyId = idMap.get(id) || '';
  const widgets: CanvasWidget[] = [];
  list.forEach((widget) => {
    if (widget.id === id) {
      const copy = clones.find((item) => item.id === copyId);
      if (copy) widgets.push(copy);
      clones.filter((item) => item.id !== copyId).forEach((item) => widgets.push(item));
      widgets.push(widget);
      return;
    }
    if (!idMap.has(widget.id)) widgets.push(widget);
  });
  return { widgets, id: copyId };
}

function removeTree(list: CanvasWidget[], id: string): CanvasWidget[] {
  const drop = new Set<string>();
  const walk = (current: string) => {
    drop.add(current);
    list.forEach((widget) => {
      if (flowParentId(widget) === current) walk(widget.id);
    });
  };
  walk(id);
  return list.filter((widget) => !drop.has(widget.id));
}

function cleanOptions(options: Record<string, unknown>): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(options || {})) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value) && value.length === 0) continue;
    out[key] = value;
  }
  return Object.keys(out).length ? out : undefined;
}

type DragState = {
  id: string;
  mode: 'move' | 'resize';
  startX: number;
  startY: number;
  origin: CanvasWidget['layout'];
  snapshot: CanvasWidget[];
  changed: boolean;
};

/**
 * 大屏设计器。组件从左侧拖到 1920×1080 画布，页面样式写入 theme_config，
 * 坐标写入 widgets_config.layout。装饰组件不绑定数据源；数据组件保存前必须选定数据源。
 */
export default function DashboardDesignPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [name, setName] = useState('新建看板');
  const [code, setCode] = useState('');
  const [savedId, setSavedId] = useState<number | null>(null);
  const [rotateSeconds, setRotateSeconds] = useState(60);
  const [widgets, setWidgets] = useState<CanvasWidget[]>([]);
  const [flowMode, setFlowMode] = useState(true);
  const [hover, setHover] = useState<FlowDropTarget | null>(null);
  const [theme, setTheme] = useState<PageTheme>(DEFAULT_THEME);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [zoom, setZoom] = useState<typeof ZOOM_FIT | number>(ZOOM_FIT);
  const [scale, setScale] = useState(0.45);
  const [componentsOpen, setComponentsOpen] = useState(true);
  const [propertiesOpen, setPropertiesOpen] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dataSources, setDataSources] = useState<DataSourceOption[]>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [paletteDragging, setPaletteDragging] = useState(false);
  const historyRef = useRef<CanvasWidget[][]>([]);
  const futureRef = useRef<CanvasWidget[][]>([]);
  const widgetsRef = useRef(widgets);
  const scaleRef = useRef(scale);
  const themeRef = useRef(theme);
  const dragRef = useRef<DragState | null>(null);
  const paletteDragged = useRef(false);
  const viewportRef = useRef<HTMLDivElement>(null);
  const nameRef = useRef<InputRef>(null);
  const imageUrl = useThemeImageUrl(theme);
  widgetsRef.current = widgets;
  scaleRef.current = scale;
  themeRef.current = theme;

  const selected = widgets.find((widget) => widget.id === selectedId) || null;

  const refreshHistoryFlags = () => {
    setCanUndo(historyRef.current.length > 0);
    setCanRedo(futureRef.current.length > 0);
  };

  const commit = (next: CanvasWidget[]) => {
    historyRef.current.push(widgetsRef.current);
    if (historyRef.current.length > 40) historyRef.current.shift();
    futureRef.current = [];
    setWidgets(next);
    refreshHistoryFlags();
  };

  const undo = () => {
    const prev = historyRef.current.pop();
    if (!prev) return;
    futureRef.current.push(widgetsRef.current);
    setWidgets(prev);
    refreshHistoryFlags();
  };

  const redo = () => {
    const next = futureRef.current.pop();
    if (!next) return;
    historyRef.current.push(widgetsRef.current);
    setWidgets(next);
    refreshHistoryFlags();
  };

  useEffect(() => {
    listDataSources()
      .then((list) => setDataSources(Array.isArray(list) ? list : []))
      .catch((err: Error) => message.error(err.message || '数据源列表加载失败'));
  }, [message]);

  useEffect(() => {
    const raw = searchParams.get('id');
    const id = raw ? Number(raw) : NaN;
    if (!Number.isInteger(id) || id <= 0) return;
    let cancelled = false;
    getDashboardPreview(id)
      .then((body) => {
        if (cancelled) return;
        const canvasMode = isCanvasLayout(body.layout_config);
        const loaded = body.widgets_config || [];
        const flow = isFlowLayout(body.layout_config) || loaded.some((widget) => Boolean(flowParentId(widget)));
        setFlowMode(flow || loaded.length === 0);
        setSavedId(id);
        setCode(body.code || '');
        setName(body.name || '新建看板');
        setRotateSeconds(body.tv_config?.rotate_seconds ?? 60);
        setTheme(parseTheme(body.theme_config));
        setWidgets((body.widgets_config || []).map((widget, index) => fromSaved(widget, index, canvasMode)));
        historyRef.current = [];
        futureRef.current = [];
        refreshHistoryFlags();
      })
      .catch((err: Error) => {
        if (!cancelled) message.error(err.message || '大屏加载失败');
      });
    return () => {
      cancelled = true;
    };
  }, [message, searchParams]);

  useEffect(() => {
    const host = viewportRef.current;
    if (!host) return undefined;
    const measure = () => {
      if (zoom !== ZOOM_FIT) {
        setScale(zoom);
        return;
      }
      const rect = host.getBoundingClientRect();
      const next = Math.min((rect.width - 48) / CANVAS_WIDTH, (rect.height - 48) / CANVAS_HEIGHT);
      setScale(next > 0.05 ? next : 0.05);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(host);
    return () => observer.disconnect();
  }, [zoom, componentsOpen, propertiesOpen]);

  useEffect(() => {
    const host = viewportRef.current;
    if (!host) return undefined;
    const frame = requestAnimationFrame(() => {
      const overflowX = host.scrollWidth - host.clientWidth;
      host.scrollLeft = overflowX > 0 ? Math.round(overflowX / 2) : 0;
      const overflowY = host.scrollHeight - host.clientHeight;
      host.scrollTop = overflowY > 0 ? Math.round(overflowY / 2) : 0;
    });
    return () => cancelAnimationFrame(frame);
  }, [scale, componentsOpen, propertiesOpen]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);
      if (typing) return;
      if ((event.key === 'Delete' || event.key === 'Backspace') && selectedId) {
        event.preventDefault();
        commit(removeTree(widgetsRef.current, selectedId));
        setSelectedId(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedId]);

  const patchSelected = (patch: Partial<CanvasWidget>) => {
    if (!selectedId) return;
    commit(
      widgetsRef.current.map((widget) => (widget.id === selectedId ? { ...widget, ...patch } : widget)),
    );
  };

  const acceptDrop = (target: FlowDropTarget, raw: string) => {
    const box = contentBox(themeRef.current);
    let parsed: { kind?: string; index?: number; id?: string } = {};
    try {
      parsed = JSON.parse(raw) as { kind?: string; index?: number; id?: string };
    } catch {
      parsed = {};
    }
    if (parsed.kind === 'palette' && typeof parsed.index === 'number') {
      const item = PALETTE[parsed.index];
      if (!item) return;
      const widget = makeWidget(item, 0, 0, box);
      widget.layout = { x: 0, y: 0, w: box.width, h: item.h };
      const next = insertFlow(widgetsRef.current, widget, target, box.width);
      if (!next) return;
      commit(next);
      setSelectedId(widget.id);
      return;
    }
    if (parsed.kind === 'widget' && parsed.id) {
      const widget = widgetsRef.current.find((item) => item.id === parsed.id);
      if (!widget) return;
      const next = insertFlow(widgetsRef.current, widget, target, box.width);
      if (!next) return;
      commit(next);
      setSelectedId(widget.id);
    }
  };

  const addPaletteItem = (item: PaletteItem) => {
    const box = contentBox(themeRef.current);
    if (flowMode) {
      const widget = makeWidget(item, 0, 0, box);
      widget.layout = { x: 0, y: 0, w: box.width, h: item.h };
      const roots = widgetsRef.current.filter((widgetItem) => !linkedParent(widgetItem, widgetsRef.current));
      const next = insertFlow(widgetsRef.current, widget, { parentId: null, slot: null, index: roots.length }, box.width);
      if (!next) return;
      commit(next);
      setSelectedId(widget.id);
      return;
    }
    const offset = 24 + (widgetsRef.current.length % 8) * 28;
    const widget = makeWidget(item, offset, offset, box);
    commit([...widgetsRef.current, widget]);
    setSelectedId(widget.id);
  };

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const raw = event.dataTransfer.getData('text/plain');
    let index = -1;
    try {
      const parsed = JSON.parse(raw) as { kind?: string; index?: number };
      if (parsed.kind === 'palette' && typeof parsed.index === 'number') index = parsed.index;
    } catch {
      index = -1;
    }
    setPaletteDragging(false);
    const item = PALETTE[index];
    if (!item) return;
    if (flowMode) {
      const roots = widgetsRef.current.filter((widgetItem) => !linkedParent(widgetItem, widgetsRef.current));
      acceptDrop({ parentId: null, slot: null, index: roots.length }, raw);
      setHover(null);
      return;
    }
    const host = event.currentTarget.getBoundingClientRect();
    const box = contentBox(themeRef.current);
    const x = (event.clientX - host.left) / scaleRef.current - themeRef.current.padding.left - item.w / 2;
    const y = (event.clientY - host.top) / scaleRef.current - themeRef.current.padding.top - item.h / 2;
    const widget = makeWidget(item, x, y, box);
    commit([...widgetsRef.current, widget]);
    setSelectedId(widget.id);
  };

  const endDrag = () => {
    const drag = dragRef.current;
    dragRef.current = null;
    if (drag?.changed) {
      historyRef.current.push(drag.snapshot);
      if (historyRef.current.length > 40) historyRef.current.shift();
      futureRef.current = [];
      refreshHistoryFlags();
    }
  };

  const onWidgetPointerDown = (event: React.PointerEvent, widget: CanvasWidget, mode: 'move' | 'resize') => {
    if (event.button !== 0) return;
    event.stopPropagation();
    event.preventDefault();
    setSelectedId(widget.id);
    dragRef.current = {
      id: widget.id,
      mode,
      startX: event.clientX,
      startY: event.clientY,
      origin: { ...widget.layout },
      snapshot: widgetsRef.current,
      changed: false,
    };
    const move = (ev: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const box = contentBox(themeRef.current);
      const dx = (ev.clientX - drag.startX) / scaleRef.current;
      const dy = (ev.clientY - drag.startY) / scaleRef.current;
      if (Math.abs(dx) + Math.abs(dy) > 1) drag.changed = true;
      setWidgets((list) =>
        list.map((item) => {
          if (item.id !== drag.id) return item;
          if (drag.mode === 'resize') {
            return {
              ...item,
              layout: {
                ...item.layout,
                w: Math.max(80, Math.round(drag.origin.w + dx)),
                h: Math.max(36, Math.round(drag.origin.h + dy)),
              },
            };
          }
          return {
            ...item,
            layout: {
              ...item.layout,
              x: Math.max(0, Math.min(Math.round(drag.origin.x + dx), Math.max(0, box.width - item.layout.w))),
              y: Math.max(0, Math.min(Math.round(drag.origin.y + dy), Math.max(0, box.height - item.layout.h))),
            },
          };
        }),
      );
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      endDrag();
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  const onSave = async () => {
    const boardName = name.trim();
    if (!boardName) {
      message.error('请填写看板名称');
      return;
    }
    const missing = widgets.find(
      (widget) =>
        DATA_WIDGET_TYPES.has(widget.type) &&
        widget.options?.valueSource !== 'manual' &&
        !widget.data_source_id,
    );
    if (missing) {
      setSelectedId(missing.id);
      message.error(`${missing.title || missing.label} 未选择数据源`);
      return;
    }
    setSaving(true);
    try {
      const widgetsConfig: DashboardWidget[] = widgets.map((widget) => {
        const item: DashboardWidget = {
          id: widget.id,
          type: widget.type,
          refresh_seconds: Math.max(1, Math.trunc(widget.refresh_seconds || 30)),
          title: widget.title,
          layout: {
            x: Math.round(widget.layout.x),
            y: Math.round(widget.layout.y),
            w: Math.round(widget.layout.w),
            h: Math.round(widget.layout.h),
          },
        };
        if (DATA_WIDGET_TYPES.has(widget.type) && widget.data_source_id) {
          item.data_source_id = widget.data_source_id;
        }
        const options = cleanOptions(widget.options);
        if (options) item.options = options;
        return item;
      });
      const payload = {
        name: boardName,
        layout_config: {
          mode: 'canvas',
          ...(flowMode ? { compose: 'flow' } : {}),
          width: CANVAS_WIDTH,
          height: CANVAS_HEIGHT,
          fit: zoom === ZOOM_FIT ? 'adaptive' : zoom,
        },
        widgets_config: widgetsConfig,
        theme_config: theme,
        tv_config: { rotate_seconds: rotateSeconds || 60 },
      };
      const nextCode = code || `DB_${Date.now()}`;
      const saved = savedId
        ? await updateDashboard(savedId, payload)
        : await createDashboard({ ...payload, code: nextCode });
      setSavedId(saved.id);
      if (!code) setCode(nextCode);
      if (!searchParams.get('id')) {
        navigate(`/apps/kuaireport/dashboards/design?id=${saved.id}`, { replace: true });
      }
      message.success('设计已保存');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const box = contentBox(theme);
  const zoomOutStop = stepZoom(zoom, scale, -1);
  const zoomInStop = stepZoom(zoom, scale, 1);
  const zoomValue = zoom === ZOOM_FIT ? ZOOM_FIT : String(zoom);

  return (
    <div style={{ height: 'calc(100vh - 88px)', minHeight: 560, display: 'flex', flexDirection: 'column', background: '#0b1220', color: '#e6f4ff' }}>
      <header className="dashboard-designer-toolbar">
        <div className="dashboard-designer-toolbar__left">
          <Tooltip title="返回列表">
            <Button type="text" icon={<ArrowLeftOutlined />} className="dashboard-designer-toolbar__icon-btn" onClick={() => navigate('/apps/kuaireport/dashboards')} />
          </Tooltip>
          <div className="dashboard-designer-toolbar__name-wrap">
            <Input
              ref={nameRef}
              variant="borderless"
              value={name}
              placeholder="看板名称"
              className="dashboard-designer-toolbar__name"
              onChange={(event) => setName(event.target.value)}
            />
            <Tooltip title="点击可编辑标题">
              <button
                type="button"
                className="dashboard-designer-toolbar__name-edit"
                aria-label="点击可编辑标题"
                onClick={() => {
                  nameRef.current?.focus();
                  nameRef.current?.input?.select();
                }}
              >
                <EditOutlined />
              </button>
            </Tooltip>
          </div>
        </div>
        <div className="dashboard-designer-toolbar__center">
          <div className="dashboard-canvas-zoom">
            <Tooltip title="缩小">
              <Button
                type="text"
                size="small"
                icon={<ZoomOutOutlined />}
                disabled={zoomOutStop == null}
                className="dashboard-designer-toolbar__icon-btn"
                onClick={() => {
                  if (zoomOutStop != null) setZoom(zoomOutStop);
                }}
              />
            </Tooltip>
            <Select
              size="small"
              value={zoomValue}
              className="dashboard-canvas-zoom__select"
              classNames={{ popup: { root: 'dashboard-canvas-zoom__select-dropdown' } }}
              options={[
                { value: ZOOM_FIT, label: '自适应' },
                ...ZOOM_STOPS.map((stop) => ({ value: String(stop), label: `${Math.round(stop * 100)}%` })),
              ]}
              onChange={(value) => setZoom(value === ZOOM_FIT ? ZOOM_FIT : Number(value))}
            />
            <Tooltip title="放大">
              <Button
                type="text"
                size="small"
                icon={<ZoomInOutlined />}
                disabled={zoomInStop == null}
                className="dashboard-designer-toolbar__icon-btn"
                onClick={() => {
                  if (zoomInStop != null) setZoom(zoomInStop);
                }}
              />
            </Tooltip>
            <Tooltip title="按视口自适应画板">
              <Button
                type="text"
                size="small"
                icon={<ColumnWidthOutlined />}
                className={`dashboard-canvas-zoom__fit-btn${zoom === ZOOM_FIT ? ' is-active' : ''}`}
                onClick={() => setZoom(ZOOM_FIT)}
              >
                自适应
              </Button>
            </Tooltip>
            <span className="dashboard-canvas-zoom__size">
              {CANVAS_WIDTH}×{CANVAS_HEIGHT}
            </span>
          </div>
        </div>
        <div className="dashboard-designer-toolbar__right">
          <Space size={8}>
            {componentsOpen ? (
              <Tooltip title="收起组件面板">
                <Button
                  type="text"
                  icon={<DoubleLeftOutlined />}
                  className="dashboard-designer-toolbar__icon-btn"
                  aria-label="收起组件面板"
                  onClick={() => setComponentsOpen(false)}
                />
              </Tooltip>
            ) : (
              <Tooltip title="展开组件面板">
                <Button
                  type="text"
                  icon={<DoubleRightOutlined />}
                  className="dashboard-designer-toolbar__icon-btn"
                  onClick={() => setComponentsOpen(true)}
                >
                  组件
                </Button>
              </Tooltip>
            )}
            {propertiesOpen ? (
              <Tooltip title="收起属性面板">
                <Button
                  type="text"
                  icon={<DoubleRightOutlined />}
                  className="dashboard-designer-toolbar__icon-btn"
                  aria-label="收起属性面板"
                  onClick={() => setPropertiesOpen(false)}
                />
              </Tooltip>
            ) : (
              <Tooltip title="展开属性面板">
                <Button
                  type="text"
                  icon={<DoubleLeftOutlined />}
                  className="dashboard-designer-toolbar__icon-btn"
                  onClick={() => setPropertiesOpen(true)}
                >
                  属性
                </Button>
              </Tooltip>
            )}
            <Tooltip title="撤销">
              <Button type="text" icon={<UndoOutlined />} disabled={!canUndo} className="dashboard-designer-toolbar__icon-btn" onClick={undo} />
            </Tooltip>
            <Tooltip title="重做">
              <Button type="text" icon={<RedoOutlined />} disabled={!canRedo} className="dashboard-designer-toolbar__icon-btn" onClick={redo} />
            </Tooltip>
            <Button
              icon={<EyeOutlined />}
              disabled={!savedId}
              className="dashboard-designer-toolbar__ghost-btn"
              onClick={() => {
                if (savedId) navigate(`/apps/kuaireport/dashboards/${savedId}/preview`);
              }}
            >
              预览
            </Button>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => void onSave()}>
              保存设计
            </Button>
          </Space>
        </div>
      </header>
      <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
        {componentsOpen ? (
        <aside style={{ width: 248, overflow: 'auto', borderRight: '1px solid rgba(255,255,255,0.08)', padding: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 12 }}>组件</div>
          {GROUPS.map((group) => (
            <section key={group} style={{ marginBottom: 16 }}>
              <div style={{ opacity: 0.7, marginBottom: 8 }}>{group}</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                {PALETTE.map((item, index) =>
                  item.group === group ? (
                    <button
                      key={`${item.label}-${index}`}
                      type="button"
                      draggable
                      onDragStart={(event) => {
                        paletteDragged.current = true;
                        setPaletteDragging(true);
                        event.dataTransfer.setData('text/plain', JSON.stringify({ kind: 'palette', index }));
                        event.dataTransfer.effectAllowed = 'copy';
                      }}
                      onDragEnd={() => {
                        setPaletteDragging(false);
                        setHover(null);
                      }}
                      onClick={() => {
                        if (paletteDragged.current) {
                          paletteDragged.current = false;
                          return;
                        }
                        addPaletteItem(item);
                      }}
                      style={{
                        background: '#13284a',
                        color: '#9fd4ff',
                        border: '1px solid rgba(0,180,255,0.25)',
                        borderRadius: 8,
                        minHeight: 72,
                        cursor: 'grab',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: 6,
                        fontSize: 12,
                      }}
                    >
                      <span style={{ fontSize: 18 }}>{paletteIcon(item)}</span>
                      {item.label}
                    </button>
                  ) : null,
                )}
              </div>
            </section>
          ))}
        </aside>
        ) : null}
        <div ref={viewportRef} className="dashboard-canvas-viewport">
          <DashboardStage
            theme={theme}
            imageUrl={imageUrl}
            scale={scale}
            onDragOver={(event) => event.preventDefault()}
            onDrop={onDrop}
            onPointerDown={() => setSelectedId(null)}
          >
            <div style={{ position: 'relative', width: box.width, height: box.height }}>
              {flowMode ? (
                <FlowBoard
                  widgets={widgets}
                  accent={theme.background}
                  interactive={false}
                  selectedId={selectedId}
                  hover={hover}
                  canvasScale={scale}
                  onSelect={setSelectedId}
                  onDuplicate={(id) => {
                    const copied = cloneTree(widgetsRef.current, id);
                    if (!copied) return;
                    commit(copied.widgets);
                    setSelectedId(copied.id);
                  }}
                  onDelete={(id) => {
                    commit(removeTree(widgetsRef.current, id));
                    setSelectedId((current) => (current === id ? null : current));
                  }}
                  onDragOverTarget={setHover}
                  onDropTarget={(target, event) => {
                    acceptDrop(target, event.dataTransfer.getData('text/plain'));
                    setPaletteDragging(false);
                    setHover(null);
                  }}
                />
              ) : null}
              {flowMode
                ? null
                : widgets.map((widget) => (
                <div
                  key={widget.id}
                  onPointerDown={(event) => onWidgetPointerDown(event, widget, 'move')}
                  style={{
                    position: 'absolute',
                    left: widget.layout.x,
                    top: widget.layout.y,
                    width: widget.layout.w,
                    height: widget.layout.h,
                    boxShadow: widget.id === selectedId ? '0 0 0 2px #1677ff' : undefined,
                    zIndex: widget.id === selectedId ? 2 : 1,
                    cursor: 'move',
                    pointerEvents: paletteDragging ? 'none' : 'auto',
                  }}
                >
                  <DashboardWidgets
                    widgets={[{ ...widget, layout: { x: 0, y: 0, w: widget.layout.w, h: widget.layout.h } }]}
                    canvas={{ width: widget.layout.w, height: widget.layout.h }}
                    interactive={false}
                    accent={theme.background}
                  />
                  {widget.id === selectedId ? (
                    <div
                      onPointerDown={(event) => onWidgetPointerDown(event, widget, 'resize')}
                      style={{
                        position: 'absolute',
                        right: 0,
                        bottom: 0,
                        width: 14,
                        height: 14,
                        background: '#1677ff',
                        cursor: 'nwse-resize',
                      }}
                    />
                  ) : null}
                </div>
              ))}
            </div>
          </DashboardStage>
        </div>
        {propertiesOpen ? (
        <aside className="kb-inspector">
          {selected ? (
            <WidgetInspector widget={selected} dataSources={dataSources} onChange={patchSelected} />
          ) : (
            <PageInspector theme={theme} onChange={(patch) => setTheme((current) => ({ ...current, ...patch }))} />
          )}
        </aside>
        ) : null}
      </div>
    </div>
  );
}

const APPEARANCE = [
  { value: 'bevel', label: '切角' },
  { value: 'bracket', label: '角标' },
  { value: 'rail', label: '导轨' },
  { value: 'module', label: '模块' },
  { value: 'blade', label: '斜切' },
];

const ON_OFF = [
  { value: 'on', label: '开' },
  { value: 'off', label: '关' },
];

const GRADIENTS: { value: PageTheme['gradient']; label: string }[] = [
  { value: 'cyanRadial', label: '左上光晕' },
  { value: 'blueWash', label: '顶部渐隐' },
  { value: 'deepVoid', label: '顶心光晕' },
  { value: 'horizonBand', label: '底部光带' },
  { value: 'cornerBeam', label: '对角斜光' },
];

const TEXTURES: { value: PageTheme['texture']; label: string }[] = [
  { value: 'none', label: '无' },
  { value: 'grid', label: '网格' },
  { value: 'fineGrid', label: '细网格' },
  { value: 'scanlines', label: '扫描线' },
  { value: 'noise', label: '噪点' },
  { value: 'dots', label: '点阵' },
];

const CHART_TYPES = [
  { value: 'line', label: '折线图' },
  { value: 'column', label: '柱状图' },
  { value: 'pie', label: '饼图' },
  { value: 'area', label: '面积图' },
  { value: 'radar', label: '雷达图' },
  { value: 'scatter', label: '散点图' },
  { value: 'gauge', label: '仪表盘' },
  { value: 'liquid', label: '水波图' },
  { value: 'dualAxes', label: '双轴图' },
  { value: 'funnel', label: '漏斗图' },
];

const CHART_PALETTES = [
  { value: 'theme', label: '跟随主题' },
  { value: 'steel', label: '钢蓝' },
  { value: 'signal', label: '信号灯' },
  { value: 'amber', label: '暖橙' },
  { value: 'mono', label: '单色阶' },
  { value: 'spectrum', label: '多色对比' },
];

function onOff(value: unknown, fallback: 'on' | 'off'): 'on' | 'off' {
  if (value === 'on' || value === true) return 'on';
  if (value === 'off' || value === false) return 'off';
  return fallback;
}

function ratioParts(value: unknown, count: number): number[] {
  const parsed = String(value || '')
    .split(/[:,\s]+/)
    .map((part) => Number.parseFloat(part))
    .filter((part) => Number.isFinite(part) && part > 0);
  const ratios = parsed.slice(0, count);
  while (ratios.length < count) ratios.push(1);
  return ratios;
}

function paddingOf(options: Record<string, unknown>): PageTheme['padding'] {
  const pad = options.padding && typeof options.padding === 'object' ? (options.padding as Record<string, unknown>) : {};
  return {
    top: Number(pad.top) || 0,
    right: Number(pad.right) || 0,
    bottom: Number(pad.bottom) || 0,
    left: Number(pad.left) || 0,
  };
}

function BackgroundImageField({
  theme,
  onChange,
}: {
  theme: PageTheme;
  onChange: (patch: Partial<PageTheme>) => void;
}) {
  const { message } = App.useApp();
  const [uploading, setUploading] = useState(false);
  const [resolved, setResolved] = useState('');
  useEffect(() => {
    const direct = theme.image_url.trim();
    if (direct || !theme.image_file_uuid) {
      setResolved('');
      return undefined;
    }
    let cancelled = false;
    getFileDownloadUrlWithToken(theme.image_file_uuid)
      .then((url) => {
        if (!cancelled) setResolved(url || '');
      })
      .catch(() => {
        if (!cancelled) setResolved('');
      });
    return () => {
      cancelled = true;
    };
  }, [theme.image_url, theme.image_file_uuid]);
  const upload = async (file: File) => {
    setUploading(true);
    try {
      const uploaded = await uploadFile(file, { category: 'image' });
      onChange({ image_file_uuid: uploaded.uuid, image_url: '' });
      message.success('上传成功');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '上传失败');
    } finally {
      setUploading(false);
    }
  };
  return (
    <Space.Compact className="kb-inspector__upload">
      <Input
        value={theme.image_url || resolved}
        placeholder="图片 URL"
        onChange={(event) => onChange({ image_url: event.target.value, image_file_uuid: '' })}
      />
      <Upload
        accept="image/*"
        showUploadList={false}
        disabled={uploading}
        beforeUpload={(file) => {
          void upload(file);
          return false;
        }}
      >
        <Button icon={<UploadOutlined />} loading={uploading} disabled={uploading}>
          上传图片
        </Button>
      </Upload>
    </Space.Compact>
  );
}

function PageInspector({
  theme,
  onChange,
}: {
  theme: PageTheme;
  onChange: (patch: Partial<PageTheme>) => void;
}) {
  const gradientValue = theme.gradient === 'top-left' ? 'cyanRadial' : theme.gradient;
  const gradients = [...GRADIENTS];
  if (gradientValue === 'top-right' || gradientValue === 'center' || gradientValue === 'none') {
    gradients.push({
      value: gradientValue,
      label: gradientValue === 'top-right' ? '右上光晕' : gradientValue === 'center' ? '中心光晕' : '无',
    });
  }
  const positions = [
    { value: 'center', label: '居中' },
    { value: 'top', label: '顶部' },
    { value: 'bottom', label: '底部' },
    ...(theme.image_position === 'left' || theme.image_position === 'right'
      ? [{ value: theme.image_position, label: theme.image_position === 'left' ? '左侧' : '右侧' }]
      : []),
  ];
  return (
    <Inspector title="页面">
      <Field label="主题色">
        <div className="kb-puck-accent-field">
          <div className="kb-puck-accent-presets">
            {ACCENT_PRESETS.map((color) => (
              <button
                key={color}
                type="button"
                aria-label={color}
                title={color}
                className={theme.background.toLowerCase() === color.toLowerCase() ? 'kb-puck-accent-swatch is-selected' : 'kb-puck-accent-swatch'}
                style={{ background: color }}
                onClick={() => onChange({ background: color })}
              />
            ))}
          </div>
          <ColorPicker
            className="kb-inspector-color"
            value={theme.background}
            format="hex"
            showText
            disabledAlpha
            onChange={(_, hex) => onChange({ background: typeof hex === 'string' && hex ? hex : theme.background })}
          />
        </div>
      </Field>
      <Choice label="渐变样式" value={gradientValue} options={gradients} onChange={(value) => onChange({ gradient: value as PageTheme['gradient'] })} />
      <Field label="背景图">
        <BackgroundImageField theme={theme} onChange={onChange} />
      </Field>
      <Field>
        <div className="kb-inspector__split">
          <div>
            <div className="kb-inspector__sub">背景图适配</div>
            <Select
              value={theme.image_fit}
              style={{ width: '100%' }}
              classNames={{ popup: { root: 'kb-puck-field-dropdown' } }}
              options={[
                { value: 'cover', label: '覆盖' },
                { value: 'contain', label: '包含' },
                { value: 'fill', label: '拉伸' },
              ]}
              onChange={(value) => onChange({ image_fit: value })}
            />
          </div>
          <div>
            <div className="kb-inspector__sub">背景图位置</div>
            <Select
              value={theme.image_position}
              style={{ width: '100%' }}
              classNames={{ popup: { root: 'kb-puck-field-dropdown' } }}
              options={positions}
              onChange={(value) => onChange({ image_position: value })}
            />
          </div>
        </div>
      </Field>
      <Field>
        <div className="kb-puck-bg-layout-row">
          <div className="kb-puck-bg-layout-item">
            <span className="kb-puck-bg-layout-label">遮罩色</span>
            <ColorPicker
              className="kb-inspector-color"
              value={theme.mask_color}
              format="hex"
              showText
              disabledAlpha
              onChange={(_, hex) => onChange({ mask_color: typeof hex === 'string' && hex ? hex : theme.mask_color })}
            />
          </div>
          <div className="kb-puck-bg-layout-item kb-puck-bg-layout-item--narrow">
            <span className="kb-puck-bg-layout-label">遮罩透明度</span>
            <InputNumber
              min={0}
              max={100}
              value={theme.mask_opacity}
              style={{ width: '100%' }}
              onChange={(value) => onChange({ mask_opacity: typeof value === 'number' ? value : 0 })}
            />
          </div>
        </div>
      </Field>
      <Choice label="纹理" value={theme.texture} options={TEXTURES} onChange={(value) => onChange({ texture: value as PageTheme['texture'] })} />
      <PaddingField value={theme.padding} onChange={(padding) => onChange({ padding })} />
    </Inspector>
  );
}

function WidgetInspector({
  widget,
  dataSources,
  onChange,
}: {
  widget: CanvasWidget;
  dataSources: DataSourceOption[];
  onChange: (patch: Partial<CanvasWidget>) => void;
}) {
  const options = widget.options;
  const text = (key: string, fallback = '') => (typeof options[key] === 'string' ? String(options[key]) : fallback);
  const number = (key: string, fallback: number) => {
    const value = Number(options[key]);
    return Number.isFinite(value) ? value : fallback;
  };
  const setOption = (key: string, value: unknown) => onChange({ options: { ...options, [key]: value } });
  const setOptions = (patch: Record<string, unknown>) => onChange({ options: { ...options, ...patch } });
  const setHeight = (key: 'height' | 'minHeight', value: number) => {
    onChange({ options: { ...options, [key]: value }, layout: { ...widget.layout, h: value } });
  };
  const dataset = options.valueSource === 'dataset' || (options.valueSource !== 'manual' && Boolean(widget.data_source_id));
  const setSource = (value: string) => {
    if (value === 'manual') onChange({ options: { ...options, valueSource: 'manual' }, data_source_id: undefined });
    else onChange({ options: { ...options, valueSource: 'dataset' } });
  };
  const sourceFields = (
    <>
      <Choice label="取值来源" value={dataset ? 'dataset' : 'manual'} options={[{ value: 'manual', label: '手动' }, { value: 'dataset', label: '数据集' }]} onChange={setSource} />
      {dataset ? (
        <>
          <Field label="数据集">
            <Select
              showSearch
              optionFilterProp="label"
              style={{ width: '100%' }}
              placeholder="选择数据集"
              value={widget.data_source_id}
              classNames={{ popup: { root: 'kb-puck-field-dropdown' } }}
              options={dataSources.map((item) => ({ value: item.id, label: item.name }))}
              onChange={(value) => onChange({ data_source_id: value })}
            />
          </Field>
          <NumberField label="刷新（秒）" min={0} value={widget.refresh_seconds} onChange={(value) => onChange({ refresh_seconds: value || 30 })} />
        </>
      ) : null}
    </>
  );
  const name = widget.label;
  const stacked = name === '分行容器' || (widget.type === 'columns' && name !== '分栏容器' && Number(options.rows) >= 2);
  let body: React.ReactNode = null;
  if (widget.type === 'columns') {
    const countKey = stacked ? 'rows' : 'columns';
    const ratioKey = stacked ? 'rowRatios' : 'columnRatios';
    const count = Math.max(1, Math.min(6, number(countKey, stacked ? 3 : 2)));
    const parts = ratioParts(options[ratioKey], count);
    body = (
      <>
        <NumberField
          label={stacked ? '行数' : '列数'}
          min={1}
          max={6}
          value={count}
          onChange={(value) => {
            const next = Math.max(1, Math.min(6, value || 1));
            setOptions({ [countKey]: next, [ratioKey]: ratioParts(options[ratioKey], next).join(':') });
          }}
        />
        <Field label={stacked ? '行高比例' : '栏宽比例'}>
          <div className="kb-inspector__edges">
            {parts.map((part, index) => (
              <InputNumber
                key={index}
                min={1}
                value={part}
                onChange={(value) => {
                  const next = parts.slice();
                  next[index] = typeof value === 'number' && value > 0 ? value : 1;
                  setOption(ratioKey, next.join(':'));
                }}
              />
            ))}
          </div>
        </Field>
        <NumberField label={stacked ? '行间距' : '列间距'} min={0} value={number('gap', 12)} onChange={(value) => setOption('gap', value)} />
        <PaddingField value={paddingOf(options)} onChange={(padding) => setOption('padding', padding)} />
        <Choice label="占满高度" value={onOff(options.fillHeight, stacked ? 'on' : 'off')} options={ON_OFF} onChange={(value) => setOption('fillHeight', value)} />
        <NumberField label="最小高度" min={80} value={number('minHeight', 200)} onChange={(value) => setHeight('minHeight', value || 80)} />
      </>
    );
  } else if (widget.type === 'border') {
    body = (
      <>
        <Choice label="外观套装" value={text('variant', 'bevel')} options={APPEARANCE} onChange={(value) => setOption('variant', value)} />
        <Field label="嵌入标题">
          <Input value={widget.title} onChange={(event) => onChange({ title: event.target.value })} />
        </Field>
        <Choice label="动效" value={onOff(options.animate, 'off')} options={ON_OFF} onChange={(value) => setOption('animate', value)} />
        <Choice label="水平翻转" value={onOff(options.flipHorizontal, 'off')} options={ON_OFF} onChange={(value) => setOption('flipHorizontal', value)} />
        <Choice label="占满高度" value={onOff(options.fillHeight, 'off')} options={ON_OFF} onChange={(value) => setOption('fillHeight', value)} />
        <NumberField label="最小高度" min={80} value={number('minHeight', 200)} onChange={(value) => setHeight('minHeight', value || 80)} />
      </>
    );
  } else if (widget.type === 'carousel') {
    body = (
      <>
        <NumberField label="轮播间隔(ms)" min={500} value={number('interval', 5000)} onChange={(value) => setOption('interval', value || 5000)} />
        <NumberField label="最小高度" min={80} value={number('minHeight', widget.layout.h || 240)} onChange={(value) => setHeight('minHeight', value || 80)} />
      </>
    );
  } else if (widget.type === 'title') {
    body = (
      <>
        <Choice label="样式" value={text('variant', 'bevel')} options={APPEARANCE} onChange={(value) => setOption('variant', value)} />
        <Field label="标题">
          <Input value={widget.title} onChange={(event) => onChange({ title: event.target.value })} />
        </Field>
        <Field label="副标题">
          <Input value={text('subtitle')} onChange={(event) => setOption('subtitle', event.target.value)} />
        </Field>
        <Choice label="动效" value={onOff(options.animate, 'on')} options={ON_OFF} onChange={(value) => setOption('animate', value)} />
      </>
    );
  } else if (widget.type === 'image' && options.role === 'logo') {
    body = (
      <>
        <Choice label="Logo 来源" value={text('source', 'site')} options={[{ value: 'site', label: '站点 Logo' }, { value: 'custom', label: '自定义地址' }]} onChange={(value) => setOption('source', value)} />
        <Field label="图片地址">
          <Input placeholder="https://" value={text('url')} onChange={(event) => setOption('url', event.target.value)} />
        </Field>
        <Field label="公司名">
          <Input value={text('text')} onChange={(event) => setOption('text', event.target.value)} />
        </Field>
        <NumberField label="公司名字号" min={10} max={72} value={number('textSize', 18)} onChange={(value) => setOption('textSize', value || 18)} />
        <Choice
          label="公司名位置"
          value={text('textAlign', 'right')}
          options={[
            { value: 'left', label: '图左' },
            { value: 'center', label: '图下居中' },
            { value: 'right', label: '图右' },
          ]}
          onChange={(value) => setOption('textAlign', value)}
        />
        <NumberField label="宽度" min={24} value={number('width', 140)} onChange={(value) => setOption('width', value || 24)} />
        <NumberField label="高度" min={24} value={number('height', 48)} onChange={(value) => setOption('height', value || 24)} />
        <Choice label="对齐" value={text('align', 'left')} options={[{ value: 'left', label: '左' }, { value: 'center', label: '中' }, { value: 'right', label: '右' }]} onChange={(value) => setOption('align', value)} />
        <Choice label="颜色填充" value={onOff(options.fillEnabled, 'off')} options={ON_OFF} onChange={(value) => setOption('fillEnabled', value)} />
        <ColorField label="填充色" value={text('fillColor', '#00d4ff')} onChange={(value) => setOption('fillColor', value)} />
        <NumberField label="填充边距" min={0} max={24} value={number('fillPadding', 6)} onChange={(value) => setOption('fillPadding', value)} />
        <NumberField label="填充圆角" min={0} max={24} value={number('fillRadius', 4)} onChange={(value) => setOption('fillRadius', value)} />
      </>
    );
  } else if (widget.type === 'text' || widget.type === 'marquee') {
    body = (
      <>
        <Field label="内容">
          <Input.TextArea rows={3} value={text('text')} onChange={(event) => setOption('text', event.target.value)} />
        </Field>
        <ColorField label="颜色" value={text('color', '#ffffff')} onChange={(value) => setOption('color', value)} />
      </>
    );
  } else if (widget.type === 'fullscreen') {
    body = (
      <>
        <Choice label="外观套装" value={text('variant', 'bevel')} options={APPEARANCE} onChange={(value) => setOption('variant', value)} />
        <Field label="按钮文案">
          <Input value={text('label', '全屏')} onChange={(event) => setOption('label', event.target.value)} />
        </Field>
      </>
    );
  } else if (widget.type === 'image') {
    body = (
      <>
        <Field label="图片地址">
          <Input placeholder="https://" value={text('url')} onChange={(event) => setOption('url', event.target.value)} />
        </Field>
        <Choice label="填充方式" value={text('fit', 'cover')} options={[{ value: 'cover', label: 'cover' }, { value: 'contain', label: 'contain' }, { value: 'fill', label: 'fill' }]} onChange={(value) => setOption('fit', value)} />
        <NumberField label="圆角" min={0} value={number('radius', 0)} onChange={(value) => setOption('radius', value)} />
        <NumberField label="透明度" min={0} max={1} step={0.1} value={number('opacity', 1)} onChange={(value) => setOption('opacity', value)} />
        <NumberField label="高度" min={40} value={number('height', widget.layout.h || 200)} onChange={(value) => setHeight('height', value || 40)} />
        <Choice label="颜色填充" value={onOff(options.fillEnabled, 'off')} options={ON_OFF} onChange={(value) => setOption('fillEnabled', value)} />
        <ColorField label="填充色" value={text('fillColor', '#00d4ff')} onChange={(value) => setOption('fillColor', value)} />
        <NumberField label="填充边距" min={0} max={48} value={number('fillPadding', 8)} onChange={(value) => setOption('fillPadding', value)} />
      </>
    );
  } else if (widget.type === 'video' || widget.type === 'web') {
    body = (
      <>
        <Field label={widget.type === 'video' ? '视频地址' : '嵌入地址'}>
          <Input placeholder="https://" value={text('url')} onChange={(event) => setOption('url', event.target.value)} />
        </Field>
        <NumberField label="高度" min={80} value={number('height', widget.layout.h || (widget.type === 'video' ? 240 : 320))} onChange={(value) => setHeight('height', value || 80)} />
      </>
    );
  } else if (widget.type === 'chart') {
    const rawType = text('chart_type', 'line');
    const chartType = rawType === 'bar' ? 'column' : rawType;
    const gaugeLike = chartType === 'gauge' || chartType === 'liquid';
    const categoryLike = chartType === 'pie' || chartType === 'funnel' || chartType === 'column';
    const filled = onOff(options.fillHeight, 'off') === 'on';
    body = (
      <>
        <Choice label="图表类型" value={chartType} options={CHART_TYPES} onChange={(value) => setOption('chart_type', value)} />
        <Choice label="配色" value={text('palette', 'theme')} options={CHART_PALETTES} onChange={(value) => setOption('palette', value)} />
        <Field label="标题">
          <Input value={widget.title} onChange={(event) => onChange({ title: event.target.value })} />
        </Field>
        <Choice label="占满高度" value={onOff(options.fillHeight, 'off')} options={ON_OFF} onChange={(value) => setOption('fillHeight', value)} />
        {filled ? null : <NumberField label="高度" min={120} value={number('height', widget.layout.h || 280)} onChange={(value) => setHeight('height', value || 120)} />}
        {sourceFields}
        {dataset && !gaugeLike ? (
          <Field label="分类字段">
            <Input value={text('category_field', 'type')} onChange={(event) => setOption('category_field', event.target.value)} />
          </Field>
        ) : null}
        {dataset ? <Field label="数值字段"><Input value={text('value_field', 'value')} onChange={(event) => setOption('value_field', event.target.value)} /></Field> : null}
        {dataset && !gaugeLike && !categoryLike ? (
          <>
            <Field label="X字段">
              <Input value={text('x_field', 'x')} onChange={(event) => setOption('x_field', event.target.value)} />
            </Field>
            <Field label="Y字段">
              <Input value={text('y_field', 'y')} onChange={(event) => setOption('y_field', event.target.value)} />
            </Field>
          </>
        ) : null}
      </>
    );
  } else if (widget.type === 'metric') {
    const kind = text('indicatorType', 'number');
    body = (
      <>
        <Choice
          label="类型"
          value={kind}
          options={[
            { value: 'number', label: '数字' },
            { value: 'flop', label: '翻牌' },
            { value: 'gauge', label: '仪表' },
            { value: 'water', label: '水位' },
          ]}
          onChange={(value) => setOption('indicatorType', value)}
        />
        <Field label="标题">
          <Input value={widget.title} onChange={(event) => onChange({ title: event.target.value })} />
        </Field>
        {sourceFields}
        {dataset ? null : <NumberField label="数值" value={number('value', 8888)} onChange={(value) => setOption('value', value)} />}
        {dataset ? (
          <Field label="数值字段">
            <Input value={text('field')} onChange={(event) => setOption('field', event.target.value)} />
          </Field>
        ) : null}
        <Field label="单位">
          <Input value={text('unit')} onChange={(event) => setOption('unit', event.target.value)} />
        </Field>
        <ColorField label="颜色" value={text('color', '#00d4ff')} onChange={(value) => setOption('color', value)} />
        {kind === 'number' || kind === 'flop' ? <Choice label="外观套装" value={text('variant', 'bevel')} options={APPEARANCE} onChange={(value) => setOption('variant', value)} /> : null}
      </>
    );
  } else if (widget.type === 'table') {
    const filled = onOff(options.fillHeight, 'off') === 'on';
    body = (
      <>
        {filled ? null : <NumberField label="高度" min={80} value={number('height', widget.layout.h || 240)} onChange={(value) => setHeight('height', value || 80)} />}
        <Choice label="占满高度" value={onOff(options.fillHeight, 'off')} options={ON_OFF} onChange={(value) => setOption('fillHeight', value)} />
        <Choice label="明暗模式" value={text('themeMode', 'dark')} options={[{ value: 'dark', label: '暗黑' }, { value: 'light', label: '明亮' }]} onChange={(value) => setOption('themeMode', value)} />
        <Choice label="展示形态" value={text('displayMode', 'table')} options={[{ value: 'table', label: '表格' }, { value: 'stack', label: '窄栏列表' }]} onChange={(value) => setOption('displayMode', value)} />
        <Field label="显示字段（逗号分隔）">
          <Input value={text('columnKeys')} onChange={(event) => setOption('columnKeys', event.target.value)} />
        </Field>
        <Choice label="滚动模式" value={text('scrollMode', 'none')} options={[{ value: 'none', label: '静态' }, { value: 'auto', label: '自动滚动' }]} onChange={(value) => setOption('scrollMode', value)} />
        {sourceFields}
      </>
    );
  } else if (widget.type === 'card_list') {
    const filled = onOff(options.fillHeight, 'off') === 'on';
    const axis = text('scrollAxis', 'x');
    body = (
      <>
        {filled ? null : <NumberField label="高度" min={120} value={number('height', widget.layout.h || 320)} onChange={(value) => setHeight('height', value || 120)} />}
        <Choice label="卡片方向" value={text('orientation', 'vertical')} options={[{ value: 'vertical', label: '竖向（上图下文）' }, { value: 'horizontal', label: '横向（左图右文）' }]} onChange={(value) => setOption('orientation', value)} />
        <Choice label="滚动方向" value={axis} options={[{ value: 'x', label: '横向滚动' }, { value: 'y', label: '竖向滚动' }]} onChange={(value) => setOption('scrollAxis', value)} />
        <Choice label="占满高度" value={onOff(options.fillHeight, 'off')} options={ON_OFF} onChange={(value) => setOption('fillHeight', value)} />
        {axis === 'y' ? null : <NumberField label="卡片宽度" min={140} value={number('cardWidth', 196)} onChange={(value) => setOption('cardWidth', value || 140)} />}
        <Choice label="滚动模式" value={text('scrollMode', 'auto')} options={[{ value: 'none', label: '静态' }, { value: 'auto', label: '自动滚动' }]} onChange={(value) => setOption('scrollMode', value)} />
        <NumberField label="滚动间隔(ms)" min={500} value={number('scrollInterval', 3000)} onChange={(value) => setOption('scrollInterval', value || 3000)} />
        {sourceFields}
      </>
    );
  } else if (widget.type === 'resource_list') {
    body = (
      <>
        <Choice label="占满高度" value={onOff(options.fillHeight, 'on')} options={ON_OFF} onChange={(value) => setOption('fillHeight', value)} />
        <Choice label="滚动模式" value={text('scrollMode', 'page')} options={[{ value: 'none', label: '静态' }, { value: 'page', label: '整屏切换' }]} onChange={(value) => setOption('scrollMode', value)} />
        <NumberField label="滚动间隔(ms)" min={2500} value={number('scrollInterval', 5000)} onChange={(value) => setOption('scrollInterval', value || 2500)} />
        {sourceFields}
      </>
    );
  }
  return (
    <Inspector title={name || widget.title || '组件'}>
      {body}
    </Inspector>
  );
}

function Inspector({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div>
      <div className="kb-inspector__title">{title}</div>
      {children}
    </div>
  );
}

function Field({ label, children }: { label?: string; children: React.ReactNode }) {
  return (
    <div className="kb-inspector__field">
      {label ? <div className="kb-inspector__label">{label}</div> : null}
      {children}
    </div>
  );
}

function Choice({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <Field label={label}>
      <Select value={value} style={{ width: '100%' }} options={options} classNames={{ popup: { root: 'kb-puck-field-dropdown' } }} onChange={onChange} />
    </Field>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <Field label={label}>
      <InputNumber min={min} max={max} step={step} value={value} style={{ width: '100%' }} onChange={(next) => onChange(typeof next === 'number' ? next : min || 0)} />
    </Field>
  );
}

function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <Field label={label}>
      <Input value={value} onChange={(event) => onChange(event.target.value)} addonAfter={<ColorPicker value={value} onChange={(_, hex) => onChange(hex)} />} />
    </Field>
  );
}

function PaddingField({ value, onChange }: { value: PageTheme['padding']; onChange: (value: PageTheme['padding']) => void }) {
  const edges = [
    ['top', '上'],
    ['right', '右'],
    ['bottom', '下'],
    ['left', '左'],
  ] as const;
  return (
    <Field label="四边距">
      <div className="kb-inspector__edges">
        {edges.map(([edge, caption]) => (
          <label key={edge} className="kb-inspector__edge">
            <span>{caption}</span>
            <InputNumber min={0} value={value[edge]} onChange={(next) => onChange({ ...value, [edge]: typeof next === 'number' ? next : 0 })} />
          </label>
        ))}
      </div>
    </Field>
  );
}
