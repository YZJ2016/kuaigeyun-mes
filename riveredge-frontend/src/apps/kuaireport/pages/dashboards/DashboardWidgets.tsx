import React, { useEffect, useRef, useState } from 'react';
import { Table } from 'antd';
import * as echarts from 'echarts';
import { SecureImage } from '../../../../components/secure-image';

export type WidgetResult = {
  data?: Record<string, unknown>[];
  total?: number;
  summary?: Record<string, number>;
};

export type DashboardWidget = {
  id: string;
  type: string;
  data_source_id: number;
  refresh_seconds: number;
  title?: string;
  options?: Record<string, unknown>;
  layout?: { x?: number; y?: number; w?: number; h?: number };
  result?: WidgetResult;
};

const frameStyle: React.CSSProperties = {
  border: '1px solid rgba(0, 212, 255, 0.45)',
  borderRadius: 8,
  padding: 12,
  minHeight: 96,
  background: 'rgba(0, 20, 40, 0.72)',
  color: '#e6f7ff',
};

const ALLOWED_URL_RE = /^https?:\/\//i;

/** web/video 的 options.url 只渲染 http(s)，其它 scheme 不渲染 */
function safeHttpUrl(value: unknown): string {
  const text = typeof value === 'string' ? value.trim() : '';
  return ALLOWED_URL_RE.test(text) ? text : '';
}

function ClockWidget({ refreshSeconds }: { refreshSeconds: number }) {
  const [text, setText] = useState(() => new Date().toLocaleString());
  useEffect(() => {
    const timer = window.setInterval(() => setText(new Date().toLocaleString()), refreshSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [refreshSeconds]);
  return <div style={{ fontSize: 28 }}>{text}</div>;
}

/** 图表组件：echarts 最小实现。x 轴取 options.x_field 或首列，数值取 options.y_field 或首个数值列 */
function ChartWidget({ result, options }: { result?: WidgetResult; options?: Record<string, unknown> }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const rows = result?.data || [];

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    if (!chartRef.current) {
      chartRef.current = echarts.init(host);
    }
    const chart = chartRef.current;
    const keys = rows.length ? Object.keys(rows[0]) : [];
    const xField =
      (typeof options?.x_field === 'string' && options.x_field) || keys[0] || '';
    const yField =
      (typeof options?.y_field === 'string' && options.y_field) ||
      keys.find((key) => typeof rows[0][key] === 'number') ||
      keys[1] ||
      keys[0] ||
      '';
    const kind = options?.chart_type === 'line' ? 'line' : 'bar';
    chart.setOption({
      grid: { left: 40, right: 12, top: 12, bottom: 24 },
      xAxis: {
        type: 'category',
        data: rows.map((row) => String(row[xField] ?? '')),
        axisLabel: { color: '#e6f7ff' },
      },
      yAxis: { type: 'value', axisLabel: { color: '#e6f7ff' }, splitLine: { lineStyle: { color: 'rgba(230,247,255,0.15)' } } },
      series: [
        {
          type: kind,
          data: rows.map((row) => Number(row[yField] ?? 0)),
          itemStyle: { color: '#00d4ff' },
        },
      ],
    });
    const onResize = () => chart.resize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [rows, options]);

  useEffect(
    () => () => {
      chartRef.current?.dispose();
      chartRef.current = null;
    },
    [],
  );

  if (!rows.length) return <span>暂无数据</span>;
  return <div ref={hostRef} style={{ width: '100%', height: 180 }} />;
}

/** layout 对齐 12 栅格：x/y 为起始格（0 基），w 为列跨度，h 为行高（每单位 24px） */
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
}: {
  widgets: DashboardWidget[];
  shareToken?: string;
}) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: 12 }}>
      {widgets.map((widget) => {
        const title = widget.title || widget.type;
        const options = widget.options || {};
        let body: React.ReactNode = null;
        if (widget.type === 'metric') {
          const summary = widget.result?.summary || {};
          const preferred = typeof options.field === 'string' ? options.field : '';
          const value =
            preferred && preferred in summary
              ? summary[preferred]
              : Object.values(summary)[0];
          body = <div style={{ fontSize: 36 }}>{value ?? widget.result?.total ?? '—'}</div>;
        } else if (widget.type === 'table') {
          const rows = widget.result?.data || [];
          const columns = Object.keys(rows[0] || { value: 'value' }).map((key) => ({
            title: key,
            dataIndex: key,
          }));
          body = (
            <Table
              size="small"
              pagination={false}
              rowKey={(_, index) => String(index)}
              dataSource={rows}
              columns={columns}
            />
          );
        } else if (widget.type === 'chart') {
          body = <ChartWidget result={widget.result} options={options} />;
        } else if (widget.type === 'border') {
          body = <div style={{ border: '2px solid #00d4ff', minHeight: 48 }}>{title}</div>;
        } else if (widget.type === 'title') {
          body = <h2 style={{ margin: 0 }}>{title}</h2>;
        } else if (widget.type === 'carousel') {
          const slides = Array.isArray(options.slides) ? options.slides : [title];
          body = <CarouselSlides slides={slides.map(String)} refreshSeconds={widget.refresh_seconds} />;
        } else if (widget.type === 'clock') {
          body = <ClockWidget refreshSeconds={widget.refresh_seconds} />;
        } else if (widget.type === 'image') {
          const fileUuid = typeof options.file_uuid === 'string' ? options.file_uuid : undefined;
          body = fileUuid ? (
            <SecureImage fileUuid={fileUuid} sharePreviewToken={shareToken} alt={title} width={160} />
          ) : (
            <span>{title}</span>
          );
        } else if (widget.type === 'video') {
          const src = safeHttpUrl(options.url);
          body = src ? <video src={src} controls style={{ maxWidth: '100%' }} /> : <span>{title}</span>;
        } else if (widget.type === 'web') {
          const src = safeHttpUrl(options.url);
          body = src ? (
            <iframe title={title} src={src} style={{ width: '100%', height: 160, border: 0 }} />
          ) : (
            <span>{title}</span>
          );
        }
        return (
          <section
            key={widget.id}
            style={{ ...frameStyle, gridColumn: 'span 4', ...layoutStyle(widget.layout) }}
            data-widget-type={widget.type}
          >
            <div style={{ opacity: 0.75, marginBottom: 8 }}>
              {title} · {widget.refresh_seconds}s · 源 {widget.data_source_id}
            </div>
            {body}
          </section>
        );
      })}
    </div>
  );
}

function CarouselSlides({ slides, refreshSeconds }: { slides: string[]; refreshSeconds: number }) {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    if (slides.length < 2) return undefined;
    const timer = window.setInterval(() => setIndex((current) => (current + 1) % slides.length), refreshSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [refreshSeconds, slides.length]);
  return <div>{slides[index] || ''}</div>;
}
