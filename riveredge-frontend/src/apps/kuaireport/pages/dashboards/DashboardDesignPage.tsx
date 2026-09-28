import React, { useEffect, useState } from 'react';
import { App, Button, Card, Form, Input, InputNumber, Select, Space, Typography } from 'antd';
import { useSearchParams } from 'react-router-dom';
import { DashboardWidgets, type DashboardWidget } from './DashboardWidgets';
import {
  createDashboard,
  getDashboardPreview,
  listDataSources,
  updateDashboard,
  type DataSourceOption,
} from './api';

const WIDGET_TYPES = [
  'metric',
  'table',
  'chart',
  'border',
  'title',
  'carousel',
  'clock',
  'image',
  'video',
  'web',
];

const CHART_KINDS = [
  { value: 'bar', label: '柱状' },
  { value: 'line', label: '折线' },
];

type DraftWidget = {
  type: string;
  data_source_id?: number;
  refresh_seconds: number;
  title: string;
  options: Record<string, unknown>;
  layout?: { x?: number; y?: number; w?: number; h?: number };
};

const DEFAULT_WIDGET: DraftWidget = {
  type: 'metric',
  refresh_seconds: 30,
  title: '指标',
  options: {},
};

function cleanOptions(options: Record<string, unknown>): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(options || {})) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value) && value.length === 0) continue;
    out[key] = value;
  }
  return Object.keys(out).length ? out : undefined;
}

function cleanLayout(layout?: DraftWidget['layout']) {
  if (!layout) return undefined;
  const out: Record<string, number> = {};
  for (const key of ['x', 'y', 'w', 'h'] as const) {
    const value = layout[key];
    if (typeof value === 'number' && Number.isFinite(value)) out[key] = Math.trunc(value);
  }
  return Object.keys(out).length ? out : undefined;
}

/** options.slides 用 Select tags 编辑，回显时转为 string[] */
function toDraft(widget: DashboardWidget): DraftWidget {
  const raw = widget.options || {};
  const slides = Array.isArray(raw.slides) ? raw.slides.map(String) : undefined;
  return {
    type: widget.type,
    data_source_id: widget.data_source_id,
    refresh_seconds: widget.refresh_seconds || 30,
    title: widget.title || '',
    options: { ...raw, ...(slides ? { slides } : {}) },
    layout: widget.layout ? { ...widget.layout } : undefined,
  };
}

/** WidgetOptionsEditor：按组件类型给最小可用 options 表单 */
function WidgetOptionsEditor({
  widget,
  onChange,
}: {
  widget: DraftWidget;
  onChange: (options: Record<string, unknown>) => void;
}) {
  const set = (key: string, value: unknown) => onChange({ ...widget.options, [key]: value });
  if (widget.type === 'image') {
    return (
      <Input
        placeholder="图片 file_uuid"
        style={{ width: 200 }}
        value={String(widget.options.file_uuid || '')}
        onChange={(e) => set('file_uuid', e.target.value)}
      />
    );
  }
  if (widget.type === 'video' || widget.type === 'web') {
    return (
      <Input
        placeholder="https?:// URL"
        style={{ width: 240 }}
        value={String(widget.options.url || '')}
        onChange={(e) => set('url', e.target.value)}
      />
    );
  }
  if (widget.type === 'carousel') {
    return (
      <Select
        mode="tags"
        placeholder="轮播内容"
        style={{ minWidth: 180 }}
        tokenSeparators={[',', '，']}
        value={Array.isArray(widget.options.slides) ? (widget.options.slides as string[]) : []}
        onChange={(value) => set('slides', value)}
      />
    );
  }
  if (widget.type === 'metric') {
    return (
      <Input
        placeholder="合计字段名（取 summary[field]）"
        style={{ width: 200 }}
        value={String(widget.options.field || '')}
        onChange={(e) => set('field', e.target.value)}
      />
    );
  }
  if (widget.type === 'chart') {
    return (
      <>
        <Select
          allowClear
          placeholder="图型"
          style={{ width: 90 }}
          options={CHART_KINDS}
          value={typeof widget.options.chart_type === 'string' ? widget.options.chart_type : undefined}
          onChange={(value) => set('chart_type', value)}
        />
        <Input
          placeholder="X 轴字段"
          style={{ width: 110 }}
          value={String(widget.options.x_field || '')}
          onChange={(e) => set('x_field', e.target.value)}
        />
        <Input
          placeholder="Y 轴字段"
          style={{ width: 110 }}
          value={String(widget.options.y_field || '')}
          onChange={(e) => set('y_field', e.target.value)}
        />
      </>
    );
  }
  return null;
}

/**
 * 已登录大屏设计。预览走本页内嵌组件和 `/dashboards/{id}/preview`，不走分享地址。
 * ?id= 存在时回显该大屏（后端无详情端点，走 preview 拿同形态配置）。
 */
export default function DashboardDesignPage() {
  const { message } = App.useApp();
  const [searchParams] = useSearchParams();
  const [widgets, setWidgets] = useState<DraftWidget[]>([{ ...DEFAULT_WIDGET }]);
  const [savedId, setSavedId] = useState<number | null>(null);
  const [previewWidgets, setPreviewWidgets] = useState<DashboardWidget[]>([]);
  const [dataSources, setDataSources] = useState<DataSourceOption[]>([]);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

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
        setSavedId(id);
        form.setFieldsValue({
          code: body.code,
          name: body.name,
          rotate_seconds: body.tv_config?.rotate_seconds ?? 60,
        });
        const loaded = (body.widgets_config || []).map(toDraft);
        setWidgets(loaded.length ? loaded : [{ ...DEFAULT_WIDGET }]);
      })
      .catch((err: Error) => {
        if (!cancelled) message.error(err.message || '大屏加载失败');
      });
    return () => {
      cancelled = true;
    };
  }, [form, message, searchParams]);

  const patchWidget = (index: number, patch: Partial<DraftWidget>) => {
    setWidgets((list) => list.map((w, i) => (i === index ? { ...w, ...patch } : w)));
  };

  const moveWidget = (index: number, delta: -1 | 1) => {
    setWidgets((list) => {
      const target = index + delta;
      if (target < 0 || target >= list.length) return list;
      const next = [...list];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const onSave = async () => {
    let values: { code: string; name: string; rotate_seconds?: number };
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    const missingSource = widgets.findIndex((widget) => !widget.data_source_id);
    if (missingSource >= 0) {
      message.error(`第 ${missingSource + 1} 个组件未选择数据源`);
      return;
    }
    setSaving(true);
    try {
      const widgetsConfig = widgets.map((widget, index) => {
        const item: DashboardWidget = {
          id: `w${index + 1}`,
          type: widget.type,
          // 后端 validate_widgets 要求每个组件一个 int 数据源
          data_source_id: Number(widget.data_source_id) || 0,
          refresh_seconds: Math.max(1, Math.trunc(Number(widget.refresh_seconds) || 1)),
        };
        if (widget.title) item.title = widget.title;
        const options = cleanOptions(widget.options);
        if (options) item.options = options;
        const layout = cleanLayout(widget.layout);
        if (layout) item.layout = layout;
        return item;
      });
      const payload = {
        code: values.code,
        name: values.name,
        layout_config: { cols: 12 },
        widgets_config: widgetsConfig,
        theme_config: { background: '#001529' },
        tv_config: { rotate_seconds: values.rotate_seconds || 60 },
      };
      const saved = savedId
        ? await updateDashboard(savedId, payload)
        : await createDashboard(payload);
      setSavedId(saved.id);
      setPreviewWidgets(widgetsConfig);
      message.success('大屏已保存');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const loadServerPreview = async () => {
    if (!savedId) return;
    try {
      const body = await getDashboardPreview(savedId);
      setPreviewWidgets(body.widgets_config || []);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '预览失败');
    }
  };

  const dataSourceOptions = dataSources.map((ds) => ({ value: ds.id, label: ds.name }));

  return (
    <div style={{ padding: 16 }}>
      <Form form={form} layout="vertical" initialValues={{ rotate_seconds: 60 }}>
        <Space size="middle" align="start" wrap>
          <Form.Item name="code" label="编码" rules={[{ required: true }]}>
            <Input disabled={savedId != null} />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="rotate_seconds" label="轮播秒数">
            <InputNumber min={1} />
          </Form.Item>
        </Space>
      </Form>
      {widgets.map((widget, index) => (
        <Card key={index} size="small" style={{ marginBottom: 8 }}>
          <Space align="baseline" wrap>
            <Typography.Text type="secondary">#{index + 1}</Typography.Text>
            <Select
              value={widget.type}
              style={{ width: 120 }}
              options={WIDGET_TYPES.map((type) => ({ value: type, label: type }))}
              onChange={(type) => patchWidget(index, { type })}
            />
            <Select
              placeholder="数据源"
              style={{ minWidth: 160 }}
              showSearch
              optionFilterProp="label"
              options={dataSourceOptions}
              value={widget.data_source_id}
              onChange={(value) => patchWidget(index, { data_source_id: value })}
            />
            <InputNumber
              min={1}
              precision={0}
              addonBefore="刷新(s)"
              value={widget.refresh_seconds}
              onChange={(value) => patchWidget(index, { refresh_seconds: Number(value) || 1 })}
            />
            <Input
              placeholder="标题"
              style={{ width: 140 }}
              value={widget.title}
              onChange={(e) => patchWidget(index, { title: e.target.value })}
            />
            <WidgetOptionsEditor
              widget={widget}
              onChange={(options) => patchWidget(index, { options })}
            />
          </Space>
          <Space align="baseline" wrap style={{ marginTop: 8 }}>
            <Typography.Text type="secondary">布局 x/y/w/h</Typography.Text>
            {(['x', 'y', 'w', 'h'] as const).map((key) => (
              <InputNumber
                key={key}
                min={key === 'w' || key === 'h' ? 1 : 0}
                precision={0}
                placeholder={key}
                style={{ width: 70 }}
                value={widget.layout?.[key]}
                onChange={(value) =>
                  patchWidget(index, {
                    layout: {
                      ...(widget.layout || {}),
                      [key]: value == null ? undefined : Number(value),
                    },
                  })
                }
              />
            ))}
            <Button size="small" disabled={index === 0} onClick={() => moveWidget(index, -1)}>
              上移
            </Button>
            <Button
              size="small"
              disabled={index === widgets.length - 1}
              onClick={() => moveWidget(index, 1)}
            >
              下移
            </Button>
            <Button
              size="small"
              danger
              onClick={() => setWidgets((list) => list.filter((_, i) => i !== index))}
            >
              删除
            </Button>
          </Space>
        </Card>
      ))}
      <Space style={{ marginBottom: 16 }}>
        <Button
          onClick={() =>
            setWidgets([
              ...widgets,
              { type: 'table', refresh_seconds: 30, title: '表格', options: {} },
            ])
          }
        >
          添加组件
        </Button>
        <Button type="primary" loading={saving} onClick={() => void onSave()}>
          保存
        </Button>
        <Button disabled={savedId == null} onClick={() => void loadServerPreview()}>
          登录预览
        </Button>
      </Space>
      <DashboardWidgets widgets={previewWidgets} />
    </div>
  );
}
