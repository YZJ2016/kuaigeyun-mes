import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Table } from 'antd';
import { AppstoreOutlined, CopyOutlined, DeleteOutlined } from '@ant-design/icons';
import * as echarts from 'echarts';
import { SecureImage } from '../../../../components/secure-image';
import { BoardButton, BoardTitle, IndicatorFrame, PanelFrame, accentStyle } from './boardFrames';
import './dashboardWidgets.css';

export type WidgetResult = {
  data?: Record<string, unknown>[];
  total?: number;
  summary?: Record<string, number | null>;
};

export type DashboardWidget = {
  id: string;
  type: string;
  label?: string;
  data_source_id?: number;
  refresh_seconds: number;
  title?: string;
  options?: Record<string, unknown>;
  layout?: { x?: number; y?: number; w?: number; h?: number };
  result?: WidgetResult;
};

const ALLOWED_URL_RE = /^https?:\/\//i;

const SAMPLE_CHART = [
  { x: '1月', y: 30 },
  { x: '2月', y: 40 },
  { x: '3月', y: 35 },
  { x: '4月', y: 50 },
];

const SAMPLE_TABLE = [
  { equipment_name: '挤出机-01', equipment_code: 'EQ-001', check_date: '08-04', inspector_name: '张三', status: '正常', has_abnormality: '否' },
  { equipment_name: '成型机-03', equipment_code: 'EQ-012', check_date: '08-04', inspector_name: '李四', status: '异常', has_abnormality: '是' },
  { equipment_name: '组装线-A', equipment_code: 'EQ-021', check_date: '08-03', inspector_name: '王五', status: '正常', has_abnormality: '否' },
  { equipment_name: '包装机-02', equipment_code: 'EQ-033', check_date: '08-03', inspector_name: '赵六', status: '正常', has_abnormality: '否' },
];

const SAMPLE_TABLE_COLUMNS = [
  { title: '设备', dataIndex: 'equipment_name' },
  { title: '编码', dataIndex: 'equipment_code' },
  { title: '日期', dataIndex: 'check_date' },
  { title: '点检人', dataIndex: 'inspector_name' },
  { title: '状态', dataIndex: 'status' },
  { title: '异常', dataIndex: 'has_abnormality' },
];

const SAMPLE_CARDS = [
  { title: '示例设备 A', code: 'EQ-001', tag1: '一车间', tag2: '加工设备', status: '正常' },
  { title: '示例设备 B', code: 'EQ-002', tag1: '二车间', tag2: '加工设备', status: '待机' },
  { title: '示例设备 C', code: 'EQ-003', tag1: '三车间', tag2: '检测设备', status: '正常' },
];

type ProgressStep = { name: string; status: 'done' | 'active' | 'pending'; progress: number };

const SAMPLE_PROGRESS: { title: string; subtitle: string; planned: number; steps: ProgressStep[] }[] = [
  {
    title: 'GD202608040016',
    subtitle: '3P 馈电连接器',
    planned: 10,
    steps: [
      { name: '总成组装', status: 'active', progress: 40 },
      { name: '检验', status: 'pending', progress: 0 },
      { name: '包装', status: 'pending', progress: 0 },
    ],
  },
  {
    title: 'GD202608040006',
    subtitle: 'K型滑触线',
    planned: 200,
    steps: [
      { name: '烘干投料', status: 'done', progress: 100 },
      { name: 'K型挤出', status: 'active', progress: 55 },
      { name: '喷码', status: 'pending', progress: 0 },
      { name: '切割', status: 'pending', progress: 0 },
      { name: '整根堆垛', status: 'pending', progress: 0 },
      { name: '毛刺处理', status: 'pending', progress: 0 },
    ],
  },
  {
    title: 'GD202608040005',
    subtitle: '3P连接器',
    planned: 50,
    steps: [{ name: '总成组装', status: 'done', progress: 100 }],
  },
];

function safeHttpUrl(value: unknown): string {
  const text = typeof value === 'string' ? value.trim() : '';
  return ALLOWED_URL_RE.test(text) ? text : '';
}

function optionText(options: Record<string, unknown>, key: string, fallback = ''): string {
  const value = options[key];
  return typeof value === 'string' ? value : fallback;
}

function paddingStyle(options: Record<string, unknown>): React.CSSProperties {
  const pad = options.padding;
  if (!pad || typeof pad !== 'object') return {};
  const box = pad as Record<string, unknown>;
  const edge = (key: string) => Math.max(0, Number(box[key]) || 0);
  return { padding: `${edge('top')}px ${edge('right')}px ${edge('bottom')}px ${edge('left')}px` };
}

function chartColors(name: unknown): string[] {
  if (name === 'steel') return ['#7aa2d6', '#4d6f99', '#c5d4e8', '#2f4d73'];
  if (name === 'signal') return ['#52c41a', '#faad14', '#ff4d4f', '#1677ff'];
  if (name === 'amber') return ['#fa8c16', '#ffc069', '#d46b08', '#fff1b8'];
  if (name === 'mono') return ['#d9d9d9', '#8c8c8c', '#595959', '#ffffff'];
  if (name === 'spectrum') return ['#1677ff', '#52c41a', '#fa8c16', '#ff4d4f', '#722ed1', '#13c2c2'];
  return ['#00d4ff', '#3b9eff', '#52c41a', '#fa8c16', '#ff4d4f'];
}

function ratiosOf(value: unknown, count: number): number[] {
  const parsed = String(value || '')
    .split(/[:,\s]+/)
    .map((part) => Number.parseFloat(part.trim()))
    .filter((part) => Number.isFinite(part) && part > 0)
    .slice(0, count);
  const ratios = parsed.length ? parsed : [];
  while (ratios.length < count) ratios.push(1);
  return ratios;
}

function cardStatus(status: string): 'running' | 'idle' | 'fault' | 'offline' {
  if (status === '正常' || status === '运行中') return 'running';
  if (status === '待机') return 'idle';
  if (['故障', '维修中', '校验中', '异常'].includes(status)) return 'fault';
  return 'offline';
}

function ClockWidget() {
  const dateRef = useRef<HTMLDivElement>(null);
  const timeRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const week = ['日', '一', '二', '三', '四', '五', '六'];
    const paint = () => {
      const now = new Date();
      const month = String(now.getMonth() + 1).padStart(2, '0');
      const day = String(now.getDate()).padStart(2, '0');
      const clock = [now.getHours(), now.getMinutes(), now.getSeconds()].map((part) => String(part).padStart(2, '0')).join(':');
      if (dateRef.current) dateRef.current.textContent = `${now.getFullYear()}年${month}月${day}日 星期${week[now.getDay()]}`;
      if (timeRef.current) timeRef.current.textContent = clock;
    };
    paint();
    const timer = window.setInterval(paint, 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <div className="kb-title-slot kb-title-slot--clock">
      <div className="kb-clock">
        <div ref={dateRef} className="kb-clock__date" />
        <div ref={timeRef} className="kb-clock__time" />
      </div>
    </div>
  );
}

function ChartWidget({
  rows,
  options,
  title,
}: {
  rows: Record<string, unknown>[];
  options?: Record<string, unknown>;
  title?: string;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;
    if (!chartRef.current) chartRef.current = echarts.init(host);
    const chart = chartRef.current;
    const keys = rows.length ? Object.keys(rows[0]) : [];
    const xField = (typeof options?.x_field === 'string' && options.x_field) || keys[0] || '';
    const yField =
      (typeof options?.y_field === 'string' && options.y_field) ||
      keys.find((key) => typeof rows[0]?.[key] === 'number') ||
      keys[1] ||
      keys[0] ||
      '';
    const kind = typeof options?.chart_type === 'string' ? options.chart_type : 'line';
    const colors = chartColors(options?.palette);
    const categoryField = (typeof options?.category_field === 'string' && options.category_field) || xField;
    const valueField = (typeof options?.value_field === 'string' && options.value_field) || yField;
    const categories = rows.map((row) => String(row[categoryField] ?? row[xField] ?? ''));
    const values = rows.map((row) => {
      const raw = valueField in row ? row[valueField] : row[yField];
      if (raw == null || raw === '') return null;
      const value = Number(raw);
      return Number.isFinite(value) ? value : null;
    });
    const axisText = { color: 'rgba(255,255,255,0.65)' };
    const categoryAxis = {
      type: 'category' as const,
      data: categories,
      axisLabel: axisText,
      axisLine: { lineStyle: { color: 'rgba(0,212,255,0.28)' } },
    };
    const valueAxis = {
      type: 'value' as const,
      axisLabel: axisText,
      splitLine: { lineStyle: { color: 'rgba(0,212,255,0.12)' } },
    };
    const points = categories.map((name, index) => ({ name, value: values[index] })).filter(point => point.value != null);
    let option: echarts.EChartsCoreOption;
    if (kind === 'pie' || kind === 'funnel') {
      option = {
        backgroundColor: 'transparent',
        color: colors,
        series: [{ type: kind, radius: kind === 'pie' ? '62%' : undefined, data: points, label: { color: '#fff' } }],
      };
    } else if (kind === 'gauge') {
      option = {
        backgroundColor: 'transparent',
        series: [
          {
            type: 'gauge',
            data: values[0] == null ? [] : [{ value: values[0] }],
            detail: { color: colors[0], fontSize: 18 },
            axisLine: { lineStyle: { color: [[1, colors[0]]] } },
          },
        ],
      };
    } else if (kind === 'liquid') {
      const value = Math.max(0, Math.min(100, values[0] || 0));
      option = {
        backgroundColor: 'transparent',
        series: [
          {
            type: 'pie',
            radius: ['0%', '72%'],
            silent: true,
            label: { show: true, position: 'center', formatter: values[0] == null ? '—' : String(values[0]), color: '#fff', fontSize: 22 },
            data: [
              { value, itemStyle: { color: colors[0] }, label: { show: false } },
              { value: Math.max(0, 100 - value), itemStyle: { color: 'rgba(255,255,255,0.08)' }, label: { show: false } },
            ],
          },
        ],
      };
    } else if (kind === 'radar') {
      const max = Math.max(1, ...values.filter((value): value is number => value != null));
      option = {
        backgroundColor: 'transparent',
        color: colors,
        radar: { indicator: categories.map((name) => ({ name, max })), axisName: { color: 'rgba(255,255,255,0.65)' } },
        series: [{ type: 'radar', data: [{ value: values }] }],
      };
    } else if (kind === 'dualAxes') {
      const extra = keys.find((key) => key !== yField && key !== xField && rows.some((row) => typeof row[key] === 'number')) || yField;
      option = {
        backgroundColor: 'transparent',
        color: colors,
        grid: { left: 40, right: 40, top: 16, bottom: 28 },
        xAxis: categoryAxis,
        yAxis: [valueAxis, { ...valueAxis, splitLine: { show: false } }],
        series: [
          { type: 'bar', data: values, itemStyle: { color: colors[0] } },
          { type: 'line', yAxisIndex: 1, smooth: true, data: rows.map((row) => Number(row[extra] ?? 0)), itemStyle: { color: colors[1] } },
        ],
      };
    } else {
      const bar = kind === 'bar' || kind === 'column';
      option = {
        backgroundColor: 'transparent',
        color: colors,
        grid: { left: 40, right: 16, top: 16, bottom: 28 },
        xAxis: categoryAxis,
        yAxis: valueAxis,
        series: [
          {
            type: kind === 'scatter' ? 'scatter' : bar ? 'bar' : 'line',
            data: values,
            smooth: !bar && kind !== 'scatter',
            areaStyle: kind === 'area' ? { color: colors[0], opacity: 0.25 } : undefined,
            itemStyle: { color: colors[0] },
          },
        ],
      };
    }
    chart.setOption(option, true);
    chart.resize();
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(host);
    return () => observer.disconnect();
  }, [rows, options]);

  useEffect(
    () => () => {
      chartRef.current?.dispose();
      chartRef.current = null;
    },
    [],
  );

  return (
    <div className="kb-bound-chart kb-bound-chart--fill">
      {title ? <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 13, marginBottom: 6 }}>{title}</div> : null}
      <div className="kb-bound-chart__body" style={{ height: title ? 'calc(100% - 28px)' : '100%' }}>
        {rows.length ? <div ref={hostRef} className="kb-chart-host" /> : <span style={{ color: 'rgba(255,255,255,0.45)' }}>暂无数据</span>}
      </div>
    </div>
  );
}

function GridWidget({ options, stacked }: { options: Record<string, unknown>; stacked: boolean }) {
  const count = Math.max(1, Math.min(6, Number(stacked ? options.rows : options.columns) || (stacked ? 3 : 2)));
  const ratios = ratiosOf(stacked ? options.rowRatios : options.columnRatios, count);
  const fill = options.fillHeight === 'on' || options.fillHeight === true || (stacked && options.fillHeight !== 'off' && options.fillHeight !== false);
  const gap = Number(options.gap) || 12;
  const minHeight = fill ? 0 : Number(options.minHeight) || 200;
  const template = ratios.map((part) => `minmax(0, ${part}fr)`).join(' ');
  return (
    <div
      className={[stacked ? 'dashboard-grid-stack' : 'dashboard-grid-row', fill ? (stacked ? 'dashboard-grid-stack--fill' : 'dashboard-grid-row--fill') : '']
        .filter(Boolean)
        .join(' ')}
      style={{
        display: 'grid',
        gridTemplateColumns: stacked ? undefined : template,
        gridTemplateRows: stacked ? template : undefined,
        gap,
        minHeight,
        height: fill ? '100%' : undefined,
        ...paddingStyle(options),
        width: '100%',
        alignItems: 'stretch',
        boxSizing: 'border-box',
      }}
    >
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="dashboard-grid-cell">
          <div className="kb-slot-empty" />
        </div>
      ))}
    </div>
  );
}

function PhotoCards({
  cards,
  orientation = 'vertical',
  axis = 'x',
  scrollMode = 'auto',
  scrollInterval = 3000,
  cardWidth = 196,
}: {
  cards: { title: string; code: string; tag1: string; tag2: string; status: string }[];
  orientation?: string;
  axis?: string;
  scrollMode?: string;
  scrollInterval?: number;
  cardWidth?: number;
}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = viewportRef.current;
    if (!node || cards.length < 2 || scrollMode === 'none') return undefined;
    const timer = window.setInterval(() => {
      if (axis === 'y') {
        const max = node.scrollHeight - node.clientHeight;
        if (max <= 4) return;
        const next = node.scrollTop + node.clientHeight;
        node.scrollTo({ top: next >= max - 2 ? 0 : next, behavior: 'smooth' });
        return;
      }
      const max = node.scrollWidth - node.clientWidth;
      if (max <= 4) return;
      const next = node.scrollLeft + cardWidth + 12;
      node.scrollTo({ left: next >= max - 2 ? 0 : next, behavior: 'smooth' });
    }, scrollInterval);
    return () => window.clearInterval(timer);
  }, [cards.length, axis, scrollMode, scrollInterval, cardWidth]);
  if (!cards.length) return <div className="card-strip__empty">暂无数据</div>;
  return (
    <div className="card-strip card-strip--fill">
      <div
        ref={viewportRef}
        className={axis === 'y' ? 'card-strip__viewport card-strip__viewport--y' : 'card-strip__viewport card-strip__viewport--x'}
        style={axis === 'y' ? { display: 'flex', flexDirection: 'column', overflowY: 'auto' } : undefined}
      >
        {cards.map((card) => {
          const tone = cardStatus(card.status);
          return (
            <article key={card.code} className={orientation === 'horizontal' ? 'list-photo-card' : 'list-photo-card list-photo-card--vertical'} style={{ width: cardWidth, minWidth: cardWidth }}>
              <div className="list-photo-card__media">
                <div className="list-photo-card__placeholder" aria-hidden>
                  <AppstoreOutlined />
                </div>
                {card.status ? <span className={`list-photo-card__status list-photo-card__status--${tone}`}>{card.status}</span> : null}
              </div>
              <div className="list-photo-card__body">
                <div className="list-photo-card__title">{card.title || '-'}</div>
                <div className="list-photo-card__code">{card.code}</div>
                <div className="list-photo-card__meta">
                  {card.tag1 ? <span className="list-photo-card__tag">{card.tag1}</span> : null}
                  {card.tag2 ? <span className="list-photo-card__tag list-photo-card__tag--muted">{card.tag2}</span> : null}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

function visibleSteps(steps: ProgressStep[]): { key: string; step?: ProgressStep; placeholder: boolean }[] {
  const width = 5;
  if (!steps.length) return Array.from({ length: width }, (_, index) => ({ key: `empty-${index}`, placeholder: true }));
  if (steps.length < width) {
    return [
      ...steps.map((step, index) => ({ key: `s-${index}`, step, placeholder: false })),
      ...Array.from({ length: width - steps.length }, (_, index) => ({ key: `ph-${index}`, placeholder: true })),
    ];
  }
  const active = steps.findIndex((step) => step.status === 'active');
  const focus = active === -1 ? steps.length - 1 : active;
  let start = Math.max(0, focus - 3);
  let end = Math.min(steps.length, focus + 2);
  if (end - start < width) {
    if (start === 0) end = Math.min(steps.length, width);
    else if (end === steps.length) start = Math.max(0, steps.length - width);
  }
  return steps.slice(start, end).map((step, index) => ({ key: `s-${start + index}`, step, placeholder: false }));
}

function ProgressList({
  items,
  scrollMode = 'page',
  scrollInterval = 5000,
}: {
  items: typeof SAMPLE_PROGRESS;
  scrollMode?: string;
  scrollInterval?: number;
}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const pageRef = useRef(0);
  useEffect(() => {
    pageRef.current = 0;
    const node = viewportRef.current;
    if (!node || items.length === 0 || scrollMode === 'none') return undefined;
    const timer = window.setInterval(() => {
      const view = viewportRef.current;
      if (!view) return;
      const height = view.clientHeight;
      const max = Math.max(0, view.scrollHeight - height);
      if (height <= 0 || max <= 4) return;
      if (view.scrollTop >= max - 2) {
        pageRef.current = 0;
        view.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      pageRef.current += 1;
      view.scrollTo({ top: Math.min(max, pageRef.current * height), behavior: 'smooth' });
    }, scrollInterval);
    return () => window.clearInterval(timer);
  }, [items.length, scrollMode, scrollInterval]);
  if (!items.length) {
    return (
      <div className="progress-list progress-list--fill">
        <div className="progress-list__empty">暂无数据</div>
      </div>
    );
  }
  return (
    <div className="progress-list progress-list--fill">
      <div ref={viewportRef} className="progress-list__viewport">
        {items.map((item) => (
          <article key={item.title} className="progress-list__item progress-list__item--hud">
            <div className="progress-list__left">
              <span className="progress-list__id">{item.title}</span>
              <div className="progress-list__meta-line">
                <span className="progress-list__product">{item.subtitle}</span>
                <span className="progress-list__planned">
                  [ 计划: <span className="progress-list__planned-num">{item.planned}</span> ]
                </span>
              </div>
            </div>
            <div className="progress-list__rail">
              <div className="progress-list__rail-track" />
              {visibleSteps(item.steps).map((node) => {
                const done = node.step?.status === 'done';
                const active = node.step?.status === 'active';
                return (
                  <div
                    key={node.key}
                    className={['progress-list__node', node.placeholder ? 'progress-list__node--placeholder' : done ? 'progress-list__node--done' : active ? 'progress-list__node--active' : 'progress-list__node--pending'].join(' ')}
                  >
                    <div className="progress-list__node-circle">
                      {node.placeholder ? null : done ? <span className="progress-list__node-check">✓</span> : active ? <span className="progress-list__node-pct">{Math.round(node.step?.progress || 0)}%</span> : null}
                    </div>
                    <span className="progress-list__node-name">{node.placeholder ? '—' : node.step?.name}</span>
                  </div>
                );
              })}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function rowsFrom(widget: DashboardWidget, sample: Record<string, unknown>[]): Record<string, unknown>[] {
  if (!widget.result) return sample;
  return widget.result.data || [];
}

function BoundTable({
  rows,
  columns,
  options,
}: {
  rows: Record<string, unknown>[];
  columns: { title: string; dataIndex: string }[];
  options: Record<string, unknown>;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const theme = options.themeMode === 'light' ? 'light' : 'dark';
  const stack = options.displayMode === 'stack';
  const picked = String(options.columnKeys || '')
    .split(/[,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
  const shown = picked.length ? columns.filter((column) => picked.includes(column.dataIndex) || picked.includes(column.title)) : columns;
  useEffect(() => {
    if (options.scrollMode !== 'auto') return undefined;
    const timer = window.setInterval(() => {
      const node = hostRef.current?.querySelector('.ant-table-body, .dashboard-table-stack') as HTMLElement | null;
      if (!node) return;
      const max = node.scrollHeight - node.clientHeight;
      if (max <= 4) return;
      node.scrollTo({ top: node.scrollTop + 28 >= max ? 0 : node.scrollTop + 28, behavior: 'smooth' });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [options.scrollMode, rows, stack]);
  const className = `dashboard-table-widget dashboard-table-widget--${theme}${stack ? ' dashboard-table-widget--stack' : ''}`;
  if (stack) {
    return (
      <div ref={hostRef} className={className} style={{ height: '100%' }}>
        <div className="dashboard-table-stack">
          {rows.map((row, index) => (
            <div key={index} className="dashboard-table-stack__row">
              <div className="dashboard-table-stack__title">{String(row[shown[0]?.dataIndex] ?? '')}</div>
              <div className="dashboard-table-stack__meta">
                {shown.slice(1).map((column) => (
                  <span key={column.dataIndex} className="dashboard-table-stack__meta-item">
                    <em>{column.title}</em>
                    {String(row[column.dataIndex] ?? '')}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div ref={hostRef} className={className} style={{ height: '100%' }}>
      <Table
        size="small"
        pagination={false}
        rowKey={(_, index) => String(index)}
        dataSource={rows}
        columns={shown}
        scroll={options.scrollMode === 'auto' ? { y: 160 } : undefined}
      />
    </div>
  );
}

function WidgetBody({
  widget,
  shareToken,
  interactive,
}: {
  widget: DashboardWidget;
  shareToken?: string;
  interactive?: boolean;
}) {
  const options = widget.options || {};
  const title = widget.title || '';
  if (widget.type === 'metric') {
    const summary = widget.result?.summary || {};
    const preferred = typeof options.field === 'string' ? options.field : '';
    const raw = widget.result
      ? preferred && preferred in summary
        ? summary[preferred]
        : preferred ? undefined : Object.values(summary)[0] ?? widget.result.total
      : Number(options.value ?? 8888);
    const numeric = raw == null || raw === '' ? NaN : typeof raw === 'number' ? raw : Number(raw);
    const shown = Number.isFinite(numeric) ? numeric.toLocaleString('zh-CN') : raw == null || raw === '' ? '—' : String(raw);
    const color = optionText(options, 'color', '#00d4ff');
    const kind = optionText(options, 'indicatorType', 'number');
    const percent = Number.isFinite(numeric) ? Math.max(0, Math.min(100, numeric)) : 0;
    if (kind === 'water') {
      return (
        <div className="kb-meter">
          <div className="kb-meter__label">{title || '指标卡'}</div>
          <div className="kb-meter__tank">
            <div className="kb-meter__water" style={{ height: `${percent}%`, background: color }} />
            <div className="kb-meter__readout">
              {shown}
              {optionText(options, 'unit')}
            </div>
          </div>
        </div>
      );
    }
    if (kind === 'gauge') {
      return (
        <div className="kb-meter">
          <div className="kb-meter__label">{title || '指标卡'}</div>
          <div className="kb-meter__gauge" style={{ background: `conic-gradient(${color} ${percent * 3.6}deg, rgba(255,255,255,0.12) 0)` }}>
            <div className="kb-meter__core">
              {shown}
              <span>{optionText(options, 'unit')}</span>
            </div>
          </div>
        </div>
      );
    }
    return (
      <div className={kind === 'flop' ? 'kb-indicator-flop' : undefined}>
        <IndicatorFrame title={title || '指标卡'} value={shown} unit={optionText(options, 'unit')} variant={options.variant || 'bevel'} color={color} />
      </div>
    );
  }
  if (widget.type === 'table') {
    const sample = !widget.result;
    const rows = sample ? SAMPLE_TABLE : widget.result?.data || [];
    const columns = sample
      ? SAMPLE_TABLE_COLUMNS
      : Object.keys(rows[0] || { value: 'value' }).map((key) => ({ title: key, dataIndex: key }));
    return <BoundTable rows={rows} columns={columns} options={options} />;
  }
  if (widget.type === 'chart') {
    const sample = !widget.result;
    return (
      <ChartWidget
        rows={sample ? SAMPLE_CHART : widget.result?.data || []}
        options={sample ? { chart_type: 'line', x_field: 'x', y_field: 'y', ...options } : options}
        title={title}
      />
    );
  }
  if (widget.type === 'card_list') {
    const rows = rowsFrom(widget, SAMPLE_CARDS);
    const cards = rows.map((row, index) => ({
      title: String(row.title ?? row.name ?? Object.values(row)[0] ?? ''),
      code: String(row.code ?? row.equipment_code ?? ''),
      tag1: String(row.tag1 ?? row.workshop_name ?? ''),
      tag2: String(row.tag2 ?? row.category ?? ''),
      status: String(row.status ?? ''),
      key: index,
    }));
    return (
      <PhotoCards
        cards={cards}
        orientation={optionText(options, 'orientation', 'vertical')}
        axis={optionText(options, 'scrollAxis', 'x')}
        scrollMode={optionText(options, 'scrollMode', 'auto')}
        scrollInterval={Number(options.scrollInterval) || 3000}
        cardWidth={Number(options.cardWidth) || 196}
      />
    );
  }
  if (widget.type === 'resource_list') {
    const scrollMode = optionText(options, 'scrollMode', 'page');
    const scrollInterval = Number(options.scrollInterval) || 5000;
    if (!widget.result) return <ProgressList items={SAMPLE_PROGRESS} scrollMode={scrollMode} scrollInterval={scrollInterval} />;
    const rows = widget.result.data || [];
    const items = rows.map((row, index) => ({
      title: String(Object.values(row)[0] ?? `行${index + 1}`),
      subtitle: String(Object.values(row)[1] ?? ''),
      planned: Number(Object.values(row)[2] ?? 0) || 0,
      steps: [] as ProgressStep[],
    }));
    return <ProgressList items={items} scrollMode={scrollMode} scrollInterval={scrollInterval} />;
  }
  if (widget.type === 'border') {
    return (
      <PanelFrame
        title={title || '面板'}
        variant={options.variant || 'bevel'}
        animate={options.animate === 'on' || options.animate === true}
        flip={options.flipHorizontal === 'on' || options.flipHorizontal === true}
        fill
        minHeight={200}
      />
    );
  }
  if (widget.type === 'columns') return <GridWidget options={options} stacked={Number(options.rows) >= 2} />;
  if (widget.type === 'title') {
    return <BoardTitle title={title || '生产看板'} subtitle={optionText(options, 'subtitle')} variant={options.variant || 'bevel'} animate={options.animate !== 'off'} />;
  }
  if (widget.type === 'text') {
    return (
      <h4 style={{ margin: 0, color: optionText(options, 'color', '#ffffff'), textAlign: 'center', fontWeight: 600 }}>
        {optionText(options, 'text', title || '文本内容')}
      </h4>
    );
  }
  if (widget.type === 'marquee') {
    const text = optionText(options, 'text', title || '欢迎使用生产看板');
    return (
      <div style={{ overflow: 'hidden', whiteSpace: 'nowrap', width: '100%', color: optionText(options, 'color', '#ffffff') }}>
        <div style={{ display: 'inline-block', paddingLeft: '100%', animation: 'marquee 10s linear infinite', fontSize: 16 }}>{text}</div>
      </div>
    );
  }
  if (widget.type === 'fullscreen') {
    return (
      <div className="kb-title-slot kb-title-slot--fullscreen">
        <BoardButton label={optionText(options, 'label', '全屏')} variant={options.variant || 'bevel'} disabled={!interactive} onClick={() => void document.documentElement.requestFullscreen?.()} />
      </div>
    );
  }
  if (widget.type === 'carousel') {
    const slides = Array.isArray(options.slides) ? options.slides.map(String).filter(Boolean) : [];
    return <CarouselSlides slides={slides} interval={Number(options.interval) || 5000} />;
  }
  if (widget.type === 'clock') return <ClockWidget />;
  if (widget.type === 'image' && options.role === 'logo') {
    const width = Number(options.width) || 140;
    const height = Number(options.height) || 48;
    const text = optionText(options, 'text');
    const textAlign = optionText(options, 'textAlign', 'right');
    const align = optionText(options, 'align', 'left');
    const fileUuid = typeof options.file_uuid === 'string' ? options.file_uuid : '';
    const url = options.source === 'custom' ? safeHttpUrl(options.url) : '';
    const mark = fileUuid ? (
      <SecureImage fileUuid={fileUuid} sharePreviewToken={shareToken} alt={text || 'logo'} width={width} height={height} />
    ) : url ? (
      <img src={url} alt="" style={{ width, height, objectFit: 'contain', display: 'block' }} />
    ) : (
      <div className="kb-logo__placeholder" style={{ width, height }}>
        LOGO
      </div>
    );
    const filled = options.fillEnabled === 'on' || options.fillEnabled === true;
    return (
      <div className="kb-title-slot kb-title-slot--logo" style={{ justifyContent: align === 'center' ? 'center' : align === 'right' ? 'flex-end' : 'flex-start' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            flexDirection: textAlign === 'center' ? 'column' : textAlign === 'left' ? 'row-reverse' : 'row',
            gap: 8,
            padding: filled ? Number(options.fillPadding) || 0 : 0,
            borderRadius: filled ? Number(options.fillRadius) || 0 : 0,
            background: filled ? optionText(options, 'fillColor', '#00d4ff') : undefined,
          }}
        >
          {mark}
          {text ? <span className="kb-logo__text" style={{ fontSize: Number(options.textSize) || 18 }}>{text}</span> : null}
        </div>
      </div>
    );
  }
  if (widget.type === 'image') {
    const fileUuid = typeof options.file_uuid === 'string' ? options.file_uuid : '';
    const url = safeHttpUrl(options.url);
    const fit = options.fit === 'contain' || options.fit === 'fill' ? options.fit : 'cover';
    const frame: React.CSSProperties = {
      width: '100%',
      height: '100%',
      borderRadius: Number(options.radius) || 0,
      opacity: options.opacity == null || options.opacity === '' ? 1 : Number(options.opacity),
      overflow: 'hidden',
      padding: options.fillEnabled === 'on' ? Number(options.fillPadding) || 0 : 0,
      background: options.fillEnabled === 'on' ? optionText(options, 'fillColor', 'transparent') : undefined,
      boxSizing: 'border-box',
    };
    if (!fileUuid && !url) {
      return (
        <div style={{ ...frame, minHeight: 80, border: '1px dashed rgba(0,212,255,0.35)', color: 'rgba(255,255,255,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13 }}>
          请配置图片地址
        </div>
      );
    }
    if (fileUuid) {
      return (
        <div style={frame}>
          <SecureImage fileUuid={fileUuid} sharePreviewToken={shareToken} alt={title} fillParent />
        </div>
      );
    }
    return <img src={url} alt="" style={{ width: '100%', height: '100%', objectFit: fit, display: 'block', borderRadius: Number(options.radius) || 0, opacity: frame.opacity }} />;
  }
  if (widget.type === 'video') {
    const src = safeHttpUrl(options.url);
    return src ? (
      <div style={{ width: '100%', height: '100%', minHeight: 120, background: '#000' }}>
        <video src={src} controls style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
      </div>
    ) : (
      <div style={{ width: '100%', height: '100%', minHeight: 120, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.35)', color: 'rgba(255,255,255,0.45)', fontSize: 13 }}>
        请配置视频地址
      </div>
    );
  }
  if (widget.type === 'web') {
    const src = safeHttpUrl(options.url);
    return src ? (
      <iframe title={title || 'embed'} src={src} style={{ width: '100%', height: '100%', border: 'none', background: '#0a1628' }} sandbox="allow-scripts allow-same-origin allow-forms allow-popups" />
    ) : (
      <div style={{ width: '100%', height: '100%', minHeight: 80, border: '1px dashed rgba(0,212,255,0.35)', color: 'rgba(255,255,255,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13 }}>
        请配置嵌入地址
      </div>
    );
  }
  return <span>{title}</span>;
}

function layoutStyle(layout?: DashboardWidget['layout']): React.CSSProperties {
  const style: React.CSSProperties = {};
  if (!layout) return style;
  if (typeof layout.x === 'number' && layout.x >= 0) {
    style.gridColumnStart = Math.min(12, Math.trunc(layout.x) + 1);
  }
  if (typeof layout.y === 'number' && layout.y >= 0) {
    style.gridRowStart = Math.trunc(layout.y) + 1;
  }
  if (typeof layout.w === 'number' && layout.w > 0) {
    const span = Math.min(12, Math.max(1, Math.trunc(layout.w)));
    style.gridColumnEnd = `span ${span}`;
    if (!style.gridColumnStart) style.gridColumn = `span ${span}`;
  }
  if (typeof layout.h === 'number' && layout.h > 0) {
    style.minHeight = Math.trunc(layout.h) * 24;
  }
  return style;
}

export function DashboardWidgets({
  widgets,
  shareToken,
  canvas,
  interactive = true,
  accent,
}: {
  widgets: DashboardWidget[];
  shareToken?: string;
  canvas?: { width: number; height: number };
  interactive?: boolean;
  accent?: string;
}) {
  const positioned = Boolean(canvas);
  return (
    <div
      style={{
        ...accentStyle(accent),
        ...(positioned
          ? { position: 'relative', width: '100%', height: '100%' }
          : { display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: 12 }),
      }}
    >
      {widgets.map((widget) => {
        const title = widget.title || widget.type;
        const box: React.CSSProperties = positioned
          ? { position: 'relative', width: '100%', height: '100%', overflow: 'hidden', background: 'transparent' }
          : {
              gridColumn: 'span 4',
              ...layoutStyle(widget.layout),
              border: '1px solid rgba(0, 212, 255, 0.45)',
              borderRadius: 8,
              padding: 12,
              background: 'rgba(0, 20, 40, 0.55)',
              color: '#e6f7ff',
            };
        return (
          <section
            key={widget.id}
            style={{ ...box, display: 'flex', flexDirection: 'column', minHeight: positioned ? 0 : 96, boxSizing: 'border-box' }}
            data-widget-type={widget.type}
          >
            {positioned ? null : (
              <div style={{ opacity: 0.75, marginBottom: 8, fontSize: 12 }}>
                {`${title} · ${widget.refresh_seconds}s · 源 ${widget.data_source_id ?? '-'}`}
              </div>
            )}
            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <WidgetBody widget={widget} shareToken={shareToken} interactive={interactive} />
            </div>
          </section>
        );
      })}
    </div>
  );
}

export type FlowDropTarget = { parentId: string | null; slot: string | null; index: number };

export function flowParentId(widget: { options?: Record<string, unknown> }): string | null {
  const value = widget.options?.parent_id;
  return typeof value === 'string' && value ? value : null;
}

export function flowSlot(widget: { options?: Record<string, unknown> }): string | null {
  const value = widget.options?.slot;
  return typeof value === 'string' && value ? value : null;
}

function effectiveParent(widget: DashboardWidget, widgets: DashboardWidget[]): string | null {
  const parent = flowParentId(widget);
  return parent && widgets.some((item) => item.id === parent) ? parent : null;
}

function itemFills(widget: DashboardWidget, inSlot: boolean): boolean {
  if (inSlot) return true;
  const options = widget.options || {};
  if (options.fillHeight === 'off' || options.fillHeight === false) return false;
  if (options.fillHeight === 'on' || options.fillHeight === true) return true;
  if (widget.type === 'columns' && Number(options.rows) >= 2) return true;
  if (widget.type === 'resource_list') return true;
  return false;
}

function itemHeight(widget: DashboardWidget): number {
  const height = widget.layout?.h;
  if (typeof height === 'number' && height >= 36) return height;
  if (widget.type === 'title' || widget.type === 'clock' || widget.type === 'fullscreen') return 56;
  if (widget.type === 'marquee') return 40;
  if (widget.type === 'text') return 48;
  if (widget.type === 'metric') return 140;
  if (widget.type === 'columns' && Number(widget.options?.rows) >= 2) return 480;
  if (widget.type === 'card_list') return 320;
  if (widget.type === 'web') return 320;
  return 240;
}

function widgetLabel(widget: DashboardWidget): string {
  if (widget.label) return widget.label;
  const named = widget.options?.palette_label;
  return typeof named === 'string' && named ? named : widget.title || widget.type;
}

function SelectionBar({
  label,
  scale,
  onCopy,
  onDelete,
}: {
  label: string;
  scale: number;
  onCopy: () => void;
  onDelete: () => void;
}) {
  const barRef = useRef<HTMLDivElement>(null);
  const [pinInside, setPinInside] = useState(false);
  useLayoutEffect(() => {
    const node = barRef.current;
    if (!node || pinInside) return;
    const stage = node.closest('[data-board-stage]');
    const limit = (stage?.getBoundingClientRect().top ?? 0) + 4;
    if (node.getBoundingClientRect().top < limit) setPinInside(true);
  }, [pinInside, scale, label]);
  const safe = scale > 0.05 ? scale : 1;
  return (
    <div
      ref={barRef}
      className="kb-flow-actions"
      style={{
        right: 0,
        top: pinInside ? 8 / safe : 0,
        transform: pinInside ? `scale(${1 / safe})` : `translateY(-100%) scale(${1 / safe})`,
        transformOrigin: pinInside ? 'right top' : 'right bottom',
      }}
      onPointerDown={(event) => event.stopPropagation()}
      onClick={(event) => event.stopPropagation()}
    >
      <div className="kb-flow-actions__group">
        <span className="kb-flow-actions__label">{label}</span>
      </div>
      <div className="kb-flow-actions__group">
        <button type="button" className="kb-flow-actions__btn" title="复制" aria-label="复制" onClick={onCopy}>
          <CopyOutlined />
        </button>
        <button type="button" className="kb-flow-actions__btn" title="删除" aria-label="删除" onClick={onDelete}>
          <DeleteOutlined />
        </button>
      </div>
    </div>
  );
}

function indexFromPoint(list: HTMLElement, clientY: number): number {
  const items = [...list.children].filter((node): node is HTMLElement => node instanceof HTMLElement && node.hasAttribute('data-flow-item'));
  for (let index = 0; index < items.length; index += 1) {
    const rect = items[index].getBoundingClientRect();
    if (clientY < rect.top + rect.height / 2) return index;
  }
  return items.length;
}

function FlowList({
  parentId,
  slot,
  widgets,
  shareToken,
  interactive,
  selectedId,
  hover,
  canvasScale,
  onSelect,
  onDuplicate,
  onDelete,
  onDragOverTarget,
  onDropTarget,
}: {
  parentId: string | null;
  slot: string | null;
  widgets: DashboardWidget[];
  shareToken?: string;
  interactive?: boolean;
  selectedId?: string | null;
  hover?: FlowDropTarget | null;
  canvasScale?: number;
  onSelect?: (id: string) => void;
  onDuplicate?: (id: string) => void;
  onDelete?: (id: string) => void;
  onDragOverTarget?: (target: FlowDropTarget) => void;
  onDropTarget?: (target: FlowDropTarget, event: React.DragEvent) => void;
}) {
  const items = widgets.filter((widget) => effectiveParent(widget, widgets) === parentId && (parentId ? flowSlot(widget) === slot : true));
  const marker = (index: number) =>
    hover && hover.parentId === parentId && hover.slot === slot && hover.index === index ? (
      <div style={{ flex: '0 0 3px', height: 3, background: '#00d4ff' }} />
    ) : null;
  return (
    <div
      style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', minHeight: 0 }}
      onDragOver={(event) => {
        if (!onDropTarget) return;
        event.preventDefault();
        event.stopPropagation();
        onDragOverTarget?.({ parentId, slot, index: indexFromPoint(event.currentTarget, event.clientY) });
      }}
      onDrop={(event) => {
        if (!onDropTarget) return;
        event.preventDefault();
        event.stopPropagation();
        onDropTarget({ parentId, slot, index: indexFromPoint(event.currentTarget, event.clientY) }, event);
      }}
    >
      {items.map((widget, index) => (
        <React.Fragment key={widget.id}>
          {marker(index)}
          <FlowItem
            widget={widget}
            widgets={widgets}
            inSlot={parentId !== null}
            shareToken={shareToken}
            interactive={interactive}
            selectedId={selectedId}
            hover={hover}
            canvasScale={canvasScale}
            onSelect={onSelect}
            onDuplicate={onDuplicate}
            onDelete={onDelete}
            onDragOverTarget={onDragOverTarget}
            onDropTarget={onDropTarget}
          />
        </React.Fragment>
      ))}
      {marker(items.length)}
    </div>
  );
}

function FlowItem({
  widget,
  widgets,
  inSlot,
  shareToken,
  interactive,
  selectedId,
  hover,
  canvasScale = 1,
  onSelect,
  onDuplicate,
  onDelete,
  onDragOverTarget,
  onDropTarget,
}: {
  widget: DashboardWidget;
  widgets: DashboardWidget[];
  inSlot: boolean;
  shareToken?: string;
  interactive?: boolean;
  selectedId?: string | null;
  hover?: FlowDropTarget | null;
  canvasScale?: number;
  onSelect?: (id: string) => void;
  onDuplicate?: (id: string) => void;
  onDelete?: (id: string) => void;
  onDragOverTarget?: (target: FlowDropTarget) => void;
  onDropTarget?: (target: FlowDropTarget, event: React.DragEvent) => void;
}) {
  const fills = itemFills(widget, inSlot);
  const height = itemHeight(widget);
  const selected = widget.id === selectedId;
  return (
    <div
      data-flow-item
      data-widget-type={widget.type}
      draggable={Boolean(onSelect)}
      onDragStart={(event) => {
        if ((event.target as HTMLElement).closest('.kb-flow-actions')) {
          event.preventDefault();
          return;
        }
        event.stopPropagation();
        event.dataTransfer.setData('text/plain', JSON.stringify({ kind: 'widget', id: widget.id }));
        event.dataTransfer.effectAllowed = 'move';
      }}
      onPointerDown={(event) => {
        if (!onSelect || event.button !== 0) return;
        event.stopPropagation();
        onSelect(widget.id);
      }}
      style={{
        flex: fills ? '1 1 0' : '0 0 auto',
        height: inSlot ? '100%' : fills ? undefined : height,
        minHeight: fills ? (inSlot ? 0 : Math.min(height, 120)) : height,
        width: '100%',
        minWidth: 0,
        position: 'relative',
        boxSizing: 'border-box',
        overflow: selected && onDuplicate ? 'visible' : 'hidden',
        boxShadow: selected ? 'inset 0 0 0 2px #1677ff' : undefined,
        cursor: onSelect ? 'grab' : undefined,
        zIndex: selected ? 4 : undefined,
      }}
    >
      {selected && onDuplicate && onDelete ? (
        <SelectionBar
          label={widgetLabel(widget)}
          scale={canvasScale}
          onCopy={() => onDuplicate(widget.id)}
          onDelete={() => onDelete(widget.id)}
        />
      ) : null}
      <div style={{ height: '100%', minHeight: 0 }}>
        <FlowBody
          widget={widget}
          widgets={widgets}
          shareToken={shareToken}
          interactive={interactive}
          selectedId={selectedId}
          hover={hover}
          canvasScale={canvasScale}
          onSelect={onSelect}
          onDuplicate={onDuplicate}
          onDelete={onDelete}
          onDragOverTarget={onDragOverTarget}
          onDropTarget={onDropTarget}
        />
      </div>
    </div>
  );
}

function FlowBody(props: {
  widget: DashboardWidget;
  widgets: DashboardWidget[];
  shareToken?: string;
  interactive?: boolean;
  selectedId?: string | null;
  hover?: FlowDropTarget | null;
  canvasScale?: number;
  onSelect?: (id: string) => void;
  onDuplicate?: (id: string) => void;
  onDelete?: (id: string) => void;
  onDragOverTarget?: (target: FlowDropTarget) => void;
  onDropTarget?: (target: FlowDropTarget, event: React.DragEvent) => void;
}) {
  const { widget, widgets } = props;
  const options = widget.options || {};
  if (widget.type === 'columns') {
    const stacked = Number(options.rows) >= 2;
    const count = Math.max(1, Math.min(6, Number(stacked ? options.rows : options.columns) || (stacked ? 3 : 2)));
    const ratios = ratiosOf(stacked ? options.rowRatios : options.columnRatios, count);
    const template = ratios.map((part) => `minmax(0, ${part}fr)`).join(' ');
    const fill = options.fillHeight === 'on' || options.fillHeight === true || (stacked && options.fillHeight !== 'off' && options.fillHeight !== false);
    return (
      <div
        className={[stacked ? 'dashboard-grid-stack' : 'dashboard-grid-row', fill ? (stacked ? 'dashboard-grid-stack--fill' : 'dashboard-grid-row--fill') : ''].filter(Boolean).join(' ')}
        style={{
          display: 'grid',
          gridTemplateColumns: stacked ? undefined : template,
          gridTemplateRows: stacked ? template : undefined,
          gap: Number(options.gap) || 12,
          width: '100%',
          height: '100%',
          minHeight: 0,
          boxSizing: 'border-box',
          ...paddingStyle(options),
        }}
      >
        {Array.from({ length: count }, (_, index) => {
          const slot = String(index);
          const occupied = widgets.some((item) => effectiveParent(item, widgets) === widget.id && flowSlot(item) === slot);
          return (
            <div key={slot} className="dashboard-grid-cell" style={{ position: 'relative' }}>
              {occupied ? null : <div className="kb-slot-empty" />}
              <div style={{ position: 'absolute', inset: 0 }}>
                <FlowList parentId={widget.id} slot={slot} {...props} />
              </div>
            </div>
          );
        })}
      </div>
    );
  }
  if (widget.type === 'border') {
    const occupied = widgets.some((item) => effectiveParent(item, widgets) === widget.id && flowSlot(item) === 'content');
    return (
      <PanelFrame
        title={widget.title || '面板'}
        variant={options.variant || 'bevel'}
        animate={options.animate === 'on' || options.animate === true}
        flip={options.flipHorizontal === 'on' || options.flipHorizontal === true}
        fill
        minHeight={0}
      >
        <div style={{ position: 'relative', height: '100%', minHeight: 80 }}>
          {occupied ? null : <div className="kb-slot-empty" />}
          <div style={{ position: 'absolute', inset: 0 }}>
            <FlowList parentId={widget.id} slot="content" {...props} />
          </div>
        </div>
      </PanelFrame>
    );
  }
  if (widget.type === 'carousel') {
    return <FlowCarousel {...props} />;
  }
  return (
    <div style={{ height: '100%', minHeight: 0, overflow: 'hidden' }}>
      <WidgetBody widget={widget} shareToken={props.shareToken} interactive={props.interactive} />
    </div>
  );
}

function FlowCarousel(props: {
  widget: DashboardWidget;
  widgets: DashboardWidget[];
  shareToken?: string;
  interactive?: boolean;
  selectedId?: string | null;
  hover?: FlowDropTarget | null;
  canvasScale?: number;
  onSelect?: (id: string) => void;
  onDuplicate?: (id: string) => void;
  onDelete?: (id: string) => void;
  onDragOverTarget?: (target: FlowDropTarget) => void;
  onDropTarget?: (target: FlowDropTarget, event: React.DragEvent) => void;
}) {
  const slides = props.widgets.filter((item) => effectiveParent(item, props.widgets) === props.widget.id && flowSlot(item) === 'content');
  const [index, setIndex] = useState(0);
  const interval = Number(props.widget.options?.interval) || 5000;
  useEffect(() => {
    if (slides.length < 2) return undefined;
    const timer = window.setInterval(() => setIndex((current) => (current + 1) % slides.length), Math.max(1500, interval));
    return () => window.clearInterval(timer);
  }, [interval, slides.length]);
  const current = slides.length ? Math.min(index, slides.length - 1) : 0;
  return (
    <div className="dashboard-carousel" style={{ position: 'relative', width: '100%', height: '100%', minHeight: 0 }}>
      {slides.length === 0 ? (
        <div style={{ position: 'absolute', inset: 0 }}>
          <div style={{ position: 'absolute', inset: 0, border: '1px dashed rgba(0,212,255,0.3)', color: 'rgba(255,255,255,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, pointerEvents: 'none' }}>
            向轮播容器拖入子组件
          </div>
          <FlowList parentId={props.widget.id} slot="content" {...props} />
        </div>
      ) : (
        slides.map((slide, slideIndex) => (
          <div key={slide.id} style={{ display: slideIndex === current ? 'block' : 'none', height: '100%' }}>
            <FlowItem widget={slide} widgets={props.widgets} inSlot shareToken={props.shareToken} interactive={props.interactive} selectedId={props.selectedId} hover={props.hover} canvasScale={props.canvasScale} onSelect={props.onSelect} onDuplicate={props.onDuplicate} onDelete={props.onDelete} onDragOverTarget={props.onDragOverTarget} onDropTarget={props.onDropTarget} />
          </div>
        ))
      )}
      {slides.length > 1 ? (
        <div style={{ position: 'absolute', right: 10, bottom: 8, display: 'flex', gap: 6, zIndex: 2 }}>
          {slides.map((slide, dot) => (
            <button
              key={slide.id}
              type="button"
              aria-label={`slide-${dot + 1}`}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => setIndex(dot)}
              style={{ width: 8, height: 8, borderRadius: '50%', border: 'none', padding: 0, cursor: 'pointer', background: dot === current ? 'var(--kb-accent, #00d4ff)' : 'rgba(255,255,255,0.35)' }}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function FlowBoard({
  widgets,
  shareToken,
  interactive = true,
  accent,
  selectedId,
  hover,
  canvasScale,
  onSelect,
  onDuplicate,
  onDelete,
  onDragOverTarget,
  onDropTarget,
}: {
  widgets: DashboardWidget[];
  shareToken?: string;
  interactive?: boolean;
  accent?: string;
  selectedId?: string | null;
  hover?: FlowDropTarget | null;
  canvasScale?: number;
  onSelect?: (id: string) => void;
  onDuplicate?: (id: string) => void;
  onDelete?: (id: string) => void;
  onDragOverTarget?: (target: FlowDropTarget) => void;
  onDropTarget?: (target: FlowDropTarget, event: React.DragEvent) => void;
}) {
  return (
    <div style={{ ...accentStyle(accent), width: '100%', height: '100%', minHeight: 0 }}>
      <FlowList
        parentId={null}
        slot={null}
        widgets={widgets}
        shareToken={shareToken}
        interactive={interactive}
        selectedId={selectedId}
        hover={hover}
        canvasScale={canvasScale}
        onSelect={onSelect}
        onDuplicate={onDuplicate}
        onDelete={onDelete}
        onDragOverTarget={onDragOverTarget}
        onDropTarget={onDropTarget}
      />
    </div>
  );
}

function CarouselSlides({ slides, interval }: { slides: string[]; interval: number }) {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    if (slides.length < 2) return undefined;
    const timer = window.setInterval(() => setIndex((current) => (current + 1) % slides.length), Math.max(1500, interval));
    return () => window.clearInterval(timer);
  }, [interval, slides.length]);
  return (
    <div className="dashboard-carousel" style={{ position: 'relative', width: '100%', height: '100%', minHeight: 240 }}>
      <div style={{ width: '100%', height: '100%', minHeight: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff' }}>
        {slides.length ? slides[index] : null}
      </div>
      {slides.length === 0 ? (
        <div style={{ position: 'absolute', inset: 0, border: '1px dashed rgba(0,212,255,0.3)', color: 'rgba(255,255,255,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, pointerEvents: 'none' }}>
          向轮播容器拖入子组件
        </div>
      ) : null}
      {slides.length > 1 ? (
        <div style={{ position: 'absolute', right: 10, bottom: 8, display: 'flex', gap: 6 }}>
          {slides.map((slide, dot) => (
            <button
              key={slide}
              type="button"
              aria-label={`slide-${dot + 1}`}
              onClick={() => setIndex(dot)}
              style={{ width: 8, height: 8, borderRadius: '50%', border: 'none', padding: 0, cursor: 'pointer', background: dot === index ? 'var(--kb-accent, #00d4ff)' : 'rgba(255,255,255,0.35)' }}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
