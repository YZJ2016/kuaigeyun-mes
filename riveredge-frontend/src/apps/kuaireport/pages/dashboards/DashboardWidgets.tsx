import React, { useEffect, useState } from 'react';
import { Table } from 'antd';
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

function ClockWidget({ refreshSeconds }: { refreshSeconds: number }) {
  const [text, setText] = useState(() => new Date().toLocaleString());
  useEffect(() => {
    const timer = window.setInterval(() => setText(new Date().toLocaleString()), refreshSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [refreshSeconds]);
  return <div style={{ fontSize: 28 }}>{text}</div>;
}

function ChartWidget({ result }: { result?: WidgetResult }) {
  const rows = result?.data || [];
  return (
    <div>
      {rows.length === 0 ? <span>暂无数据</span> : null}
      {rows.map((row, index) => {
        const value = Number(Object.values(row)[0] ?? 0);
        const width = Math.max(8, Math.min(100, Number.isFinite(value) ? value : 8));
        return (
          <div key={index} style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
            <div style={{ width: `${width}%`, height: 12, background: '#00d4ff' }} />
            <span>{JSON.stringify(row)}</span>
          </div>
        );
      })}
    </div>
  );
}

export function DashboardWidgets({
  widgets,
  shareToken,
}: {
  widgets: DashboardWidget[];
  shareToken?: string;
}) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12 }}>
      {widgets.map((widget) => {
        const title = widget.title || widget.type;
        const options = widget.options || {};
        let body: React.ReactNode = null;
        if (widget.type === 'metric') {
          const summary = widget.result?.summary || {};
          const first = Object.values(summary)[0];
          body = <div style={{ fontSize: 36 }}>{first ?? widget.result?.total ?? '—'}</div>;
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
          body = <ChartWidget result={widget.result} />;
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
          const src = typeof options.url === 'string' ? options.url : '';
          body = src ? <video src={src} controls style={{ maxWidth: '100%' }} /> : <span>{title}</span>;
        } else if (widget.type === 'web') {
          const src = typeof options.url === 'string' ? options.url : '';
          body = src ? (
            <iframe title={title} src={src} style={{ width: '100%', height: 160, border: 0 }} />
          ) : (
            <span>{title}</span>
          );
        }
        return (
          <section key={widget.id} style={frameStyle} data-widget-type={widget.type}>
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
