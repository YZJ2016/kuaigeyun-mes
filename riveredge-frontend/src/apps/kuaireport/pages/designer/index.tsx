import React, { useEffect, useState } from 'react';
import { Button, Card, Form, Input, InputNumber, Select, Space, Typography } from 'antd';
import { useSearchParams } from 'react-router-dom';
import { UniReport } from '../../../../components/uni-report';
import type { ReportConfigSchema } from '../../../../components/uni-report/types';
import {
  loadDesignerReport,
  saveDesignerReport,
  type DesignerFieldInput,
  type DesignerFilterInput,
  type DesignerReport,
} from './client';

const FORMATS = [
  { value: 'money', label: '金额' },
  { value: 'date', label: '日期' },
  { value: 'datetime', label: '日期时间' },
  { value: 'percent', label: '百分比' },
  { value: 'number', label: '数字' },
  { value: 'digit', label: '数值' },
];

interface DesignerFormValues {
  code: string;
  name: string;
  page_size: number;
  data_source_uuid?: string;
  fields?: DesignerFieldInput[];
  filters?: DesignerFilterInput[];
  summary_fields?: string[];
  note?: string;
}

function summaryOf(config?: ReportConfigSchema): string[] {
  const names = config?.extra?.uni_report?.summaryFields;
  return Array.isArray(names) ? names.map(String) : [];
}

export default function ReportDesignerPage() {
  const [form] = Form.useForm<DesignerFormValues>();
  const [searchParams] = useSearchParams();
  const [saved, setSaved] = useState<DesignerReport | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const watchedFields = Form.useWatch('fields', form) as DesignerFieldInput[] | undefined;
  const readOnly = saved?.category === 'system';
  const reportId = saved?.report_id;

  useEffect(() => {
    const raw = searchParams.get('reportId');
    if (!raw) return;
    const id = Number(raw);
    if (!Number.isInteger(id) || id <= 0) return;
    let cancelled = false;
    loadDesignerReport(id)
      .then((row) => {
        if (cancelled) return;
        setSaved(row);
        form.setFieldsValue({
          code: row.code,
          name: row.name,
          page_size: row.report_config?.page_size,
          data_source_uuid:
            row.data_source_uuid ??
            (typeof row.report_config?.extra?.data_source_uuid === 'string'
              ? row.report_config.extra.data_source_uuid
              : undefined),
          fields: row.report_config?.fields ?? [],
          filters: row.report_config?.filters ?? [],
          summary_fields: summaryOf(row.report_config),
        });
        if (row.category === 'system') setPreviewing(true);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || '账表加载失败');
      });
    return () => {
      cancelled = true;
    };
  }, [form, searchParams]);

  const onSave = async (values: DesignerFormValues) => {
    if (readOnly) return;
    setSaving(true);
    setError('');
    try {
      const row = await saveDesignerReport({
        code: values.code,
        name: values.name,
        page_size: values.page_size,
        data_source_uuid: String(values.data_source_uuid || ''),
        fields: values.fields ?? [],
        filters: values.filters ?? [],
        summary_fields: values.summary_fields ?? [],
        note: values.note,
        report_id: saved?.category === 'custom' ? saved.report_id : undefined,
      });
      setSaved(row);
      setPreviewing(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const summaryOptions = (watchedFields ?? [])
    .map((item) => item?.field)
    .filter((name): name is string => Boolean(name))
    .map((name) => ({ value: name, label: name }));

  return (
    <div style={{ padding: 16, maxWidth: 1100 }}>
      <Typography.Title level={4}>账表设计器</Typography.Title>
      {readOnly ? <Typography.Paragraph>系统报表只可查看。</Typography.Paragraph> : null}
      <Form form={form} layout="vertical" disabled={readOnly} onFinish={onSave}>
        <Space size="middle" align="start" wrap>
          <Form.Item name="code" label="编码" rules={[{ required: true, message: '请填写编码' }]}>
            <Input maxLength={50} disabled={readOnly || saved?.category === 'custom'} />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请填写名称' }]}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item
            name="page_size"
            label="每页行数"
            rules={[{ required: true, message: '请填写每页行数' }]}
          >
            <InputNumber min={1} precision={0} />
          </Form.Item>
          <Form.Item
            name="data_source_uuid"
            label="数据源"
            rules={[{ required: !readOnly, message: '请指定一个数据源' }]}
          >
            <Input maxLength={36} />
          </Form.Item>
        </Space>
        <Typography.Text>列</Typography.Text>
        <Form.List name="fields">
          {(rows, { add, remove }) => (
            <div>
              {rows.map((row) => (
                <Space key={row.key} align="baseline" wrap>
                  <Form.Item name={[row.name, 'field']} rules={[{ required: true, message: '字段' }]}>
                    <Input placeholder="字段" />
                  </Form.Item>
                  <Form.Item name={[row.name, 'label']} rules={[{ required: true, message: '标题' }]}>
                    <Input placeholder="标题" />
                  </Form.Item>
                  <Form.Item name={[row.name, 'format']}>
                    <Select allowClear placeholder="格式" options={FORMATS} style={{ width: 120 }} />
                  </Form.Item>
                  <Form.Item name={[row.name, 'width']}>
                    <InputNumber min={1} precision={0} placeholder="列宽" />
                  </Form.Item>
                  <Button type="link" onClick={() => remove(row.name)} disabled={readOnly}>
                    删除
                  </Button>
                </Space>
              ))}
              <Button type="dashed" onClick={() => add({ visible: true })} disabled={readOnly}>
                添加列
              </Button>
            </div>
          )}
        </Form.List>
        <Typography.Text>筛选</Typography.Text>
        <Form.List name="filters">
          {(rows, { add, remove }) => (
            <div>
              {rows.map((row) => (
                <Space key={row.key} align="baseline" wrap>
                  <Form.Item name={[row.name, 'field']} rules={[{ required: true, message: '字段' }]}>
                    <Input placeholder="字段" />
                  </Form.Item>
                  <Form.Item name={[row.name, 'label']} rules={[{ required: true, message: '标题' }]}>
                    <Input placeholder="标题" />
                  </Form.Item>
                  <Form.Item name={[row.name, 'operator']}>
                    <Input placeholder="运算符，区间用 between" />
                  </Form.Item>
                  <Button type="link" onClick={() => remove(row.name)} disabled={readOnly}>
                    删除
                  </Button>
                </Space>
              ))}
              <Button type="dashed" onClick={() => add()} disabled={readOnly}>
                添加筛选
              </Button>
            </div>
          )}
        </Form.List>
        <Form.Item name="summary_fields" label="合计">
          <Select mode="multiple" options={summaryOptions} />
        </Form.Item>
        <Form.Item name="note" label="备注">
          <Input maxLength={200} />
        </Form.Item>
        {error ? <Typography.Paragraph type="danger">{error}</Typography.Paragraph> : null}
        <Space>
          {readOnly ? null : (
            <Button type="primary" htmlType="submit" loading={saving}>
              保存
            </Button>
          )}
          <Button disabled={!reportId} onClick={() => setPreviewing(true)}>
            预览
          </Button>
        </Space>
      </Form>
      {previewing && reportId && saved?.report_config ? (
        <Card style={{ marginTop: 16 }} styles={{ body: { padding: 0 } }}>
          <UniReport
            mode="config"
            title={saved.name}
            columnPersistenceId={`kuaireport-designer-${reportId}`}
            reportConfig={saved.report_config}
            reportId={reportId}
          />
        </Card>
      ) : null}
    </div>
  );
}
