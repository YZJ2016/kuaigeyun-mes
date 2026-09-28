import React, { useState } from 'react';
import { Button, Form, Input, InputNumber, Select, Space, message } from 'antd';
import { apiRequest } from '../../../../services/api';
import { DashboardWidgets, type DashboardWidget } from './DashboardWidgets';

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

type DraftWidget = {
  type: string;
  data_source_id: number;
  refresh_seconds: number;
  title: string;
};

/**
 * 已登录大屏设计。预览走本页内嵌组件和 `/dashboards/{id}/preview`，不走分享地址。
 */
export default function DashboardDesignPage() {
  const [widgets, setWidgets] = useState<DraftWidget[]>([
    { type: 'metric', data_source_id: 1, refresh_seconds: 30, title: '指标' },
  ]);
  const [savedId, setSavedId] = useState<number | null>(null);
  const [previewWidgets, setPreviewWidgets] = useState<DashboardWidget[]>([]);
  const [form] = Form.useForm();

  const onSave = async () => {
    const values = await form.validateFields();
    const widgetsConfig = widgets.map((widget, index) => ({
      id: `w${index + 1}`,
      type: widget.type,
      data_source_id: widget.data_source_id,
      refresh_seconds: widget.refresh_seconds,
      title: widget.title,
    }));
    const payload = {
      code: values.code,
      name: values.name,
      layout_config: { cols: 12 },
      widgets_config: widgetsConfig,
      theme_config: { background: '#001529' },
      tv_config: { rotate_seconds: values.rotate_seconds || 60 },
    };
    const path = savedId
      ? `/apps/kuaireport/dashboards/${savedId}`
      : '/apps/kuaireport/dashboards';
    const saved = await apiRequest<{ id: number }>(path, {
      method: savedId ? 'PUT' : 'POST',
      data: payload,
    });
    setSavedId(saved.id);
    setPreviewWidgets(widgetsConfig);
    message.success('大屏已保存');
  };

  const loadServerPreview = async () => {
    if (!savedId) return;
    const body = await apiRequest<{ widgets_config: DashboardWidget[] }>(
      `/apps/kuaireport/dashboards/${savedId}/preview`,
      { method: 'GET' },
    );
    setPreviewWidgets(body.widgets_config || []);
  };

  return (
    <div style={{ padding: 16 }}>
      <Form form={form} layout="vertical" initialValues={{ rotate_seconds: 60 }}>
        <Form.Item name="code" label="编码" rules={[{ required: true }]}>
          <Input disabled={savedId != null} />
        </Form.Item>
        <Form.Item name="name" label="名称" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="rotate_seconds" label="轮播秒数">
          <InputNumber min={1} />
        </Form.Item>
      </Form>
      {widgets.map((widget, index) => (
        <Space key={index} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
          <Select
            value={widget.type}
            style={{ width: 140 }}
            options={WIDGET_TYPES.map((type) => ({ value: type, label: type }))}
            onChange={(type) => {
              const next = [...widgets];
              next[index] = { ...widget, type };
              setWidgets(next);
            }}
          />
          <InputNumber
            min={1}
            value={widget.data_source_id}
            onChange={(value) => {
              const next = [...widgets];
              next[index] = { ...widget, data_source_id: Number(value) || 1 };
              setWidgets(next);
            }}
          />
          <InputNumber
            min={1}
            value={widget.refresh_seconds}
            onChange={(value) => {
              const next = [...widgets];
              next[index] = { ...widget, refresh_seconds: Number(value) || 1 };
              setWidgets(next);
            }}
          />
          <Input
            value={widget.title}
            onChange={(event) => {
              const next = [...widgets];
              next[index] = { ...widget, title: event.target.value };
              setWidgets(next);
            }}
          />
        </Space>
      ))}
      <Space style={{ marginBottom: 16 }}>
        <Button
          onClick={() =>
            setWidgets([...widgets, { type: 'table', data_source_id: 1, refresh_seconds: 30, title: '表格' }])
          }
        >
          添加组件
        </Button>
        <Button type="primary" onClick={() => void onSave()}>
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
