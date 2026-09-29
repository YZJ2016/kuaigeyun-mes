/**
 * 本租户数据源登记。类型只覆盖接口已支持的 static / dataset / http。
 * config 键与后端校验一致：rows、dataset_uuid、display_name、url。
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  App,
  Button,
  Descriptions,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd';
import { ListPageTemplate } from '../../../../components/layout-templates';
import {
  createDataSource,
  deleteDataSource,
  getDataSource,
  listDataSources,
  updateDataSource,
  type DataSourceRow,
  type DataSourceType,
  type DataSourceWrite,
} from './api';

const { Title } = Typography;

const TYPE_OPTIONS: { value: DataSourceType; label: string }[] = [
  { value: 'static', label: '静态' },
  { value: 'dataset', label: '数据集' },
  { value: 'http', label: 'HTTP' },
];

const TYPE_LABEL: Record<string, string> = {
  static: '静态',
  dataset: '数据集',
  http: 'HTTP',
};

interface DataSourceFormValues {
  name: string;
  type: DataSourceType;
  description?: string;
  is_default: boolean;
  rows_text?: string;
  dataset_uuid?: string;
  display_name?: string;
  url?: string;
}

const EMPTY_FORM: DataSourceFormValues = {
  name: '',
  type: 'static',
  description: '',
  is_default: false,
  rows_text: '[]',
  dataset_uuid: '',
  display_name: '',
  url: '',
};

function typeLabel(value: string) {
  return TYPE_LABEL[value] || value;
}

function formatTime(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function configText(config: Record<string, unknown> | null) {
  return JSON.stringify(config ?? {}, null, 2);
}

function toForm(row: DataSourceRow): DataSourceFormValues {
  const config = row.config ?? {};
  const rows = config.rows;
  return {
    name: row.name,
    type: (row.type === 'dataset' || row.type === 'http' ? row.type : 'static') as DataSourceType,
    description: row.description ?? '',
    is_default: row.is_default,
    rows_text: JSON.stringify(Array.isArray(rows) ? rows : [], null, 2),
    dataset_uuid: typeof config.dataset_uuid === 'string' ? config.dataset_uuid : '',
    display_name: typeof config.display_name === 'string' ? config.display_name : '',
    url: typeof config.url === 'string' ? config.url : '',
  };
}

function buildWrite(values: DataSourceFormValues): DataSourceWrite {
  const type = values.type;
  let config: Record<string, unknown>;
  if (type === 'dataset') {
    config = { dataset_uuid: String(values.dataset_uuid || '').trim() };
    const displayName = String(values.display_name || '').trim();
    if (displayName) config.display_name = displayName;
  } else if (type === 'http') {
    config = { url: String(values.url || '').trim() };
  } else {
    const text = String(values.rows_text || '').trim() || '[]';
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new Error('静态行必须是 JSON 对象数组');
    }
    if (!Array.isArray(parsed) || parsed.some((row) => !row || typeof row !== 'object' || Array.isArray(row))) {
      throw new Error('静态行必须是 JSON 对象数组');
    }
    config = { rows: parsed };
  }
  const description = String(values.description || '').trim();
  return {
    name: values.name.trim(),
    type,
    config,
    description: description || null,
    is_default: Boolean(values.is_default),
  };
}

export default function DataSourcePage() {
  const { message } = App.useApp();
  const [form] = Form.useForm<DataSourceFormValues>();
  const [rows, setRows] = useState<DataSourceRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<'create' | 'edit' | 'view'>('create');
  const [current, setCurrent] = useState<DataSourceRow | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listDataSources();
      setRows(Array.isArray(data) ? data : []);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '数据源列表加载失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void load();
  }, [load]);

  const openCreate = () => {
    setMode('create');
    setCurrent(null);
    setOpen(true);
  };

  const openExisting = async (sourceId: number, next: 'edit' | 'view') => {
    try {
      const row = await getDataSource(sourceId);
      setMode(next);
      setCurrent(row);
      setOpen(true);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '数据源加载失败');
    }
  };

  const onDelete = async (row: DataSourceRow) => {
    try {
      await deleteDataSource(row.id);
      message.success(`「${row.name}」已删除`);
      void load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败');
    }
  };

  const onSubmit = async (values: DataSourceFormValues) => {
    setSaving(true);
    try {
      const payload = buildWrite(values);
      if (mode === 'edit' && current) {
        await updateDataSource(current.id, payload);
        message.success(`「${payload.name}」已保存`);
      } else {
        await createDataSource(payload);
        message.success(`「${payload.name}」已创建`);
      }
      setOpen(false);
      void load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <ListPageTemplate>
      <Title level={4}>数据源</Title>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" onClick={openCreate}>
          新建
        </Button>
      </Space>
      <Table<DataSourceRow>
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={false}
        columns={[
          { title: '名称', dataIndex: 'name' },
          {
            title: '类型',
            dataIndex: 'type',
            render: (value: string) => typeLabel(value),
          },
          { title: '说明', dataIndex: 'description', render: (value: string | null) => value || '' },
          {
            title: '默认',
            dataIndex: 'is_default',
            render: (value: boolean) => (value ? <Tag color="blue">默认</Tag> : null),
          },
          {
            title: '系统',
            dataIndex: 'is_system',
            render: (value: boolean) => (value ? <Tag>系统</Tag> : null),
          },
          {
            title: '更新时间',
            dataIndex: 'updated_at',
            render: (value: string) => formatTime(value),
          },
          {
            title: '操作',
            render: (_, row) => (
              <Space size={0} wrap>
                <Button type="link" onClick={() => void openExisting(row.id, 'view')}>
                  查看
                </Button>
                <Button type="link" onClick={() => void openExisting(row.id, 'edit')}>
                  修改
                </Button>
                <Popconfirm title="确定删除该数据源？" onConfirm={() => void onDelete(row)}>
                  <Button type="link" danger>
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={mode === 'view' ? '查看数据源' : mode === 'edit' ? '修改数据源' : '新建数据源'}
        open={open}
        destroyOnHidden
        onCancel={() => setOpen(false)}
        onOk={() => {
          if (mode === 'view') setOpen(false);
          else void form.submit();
        }}
        okText={mode === 'view' ? '关闭' : '保存'}
        confirmLoading={saving}
        cancelButtonProps={mode === 'view' ? { style: { display: 'none' } } : undefined}
        width={640}
      >
        {mode === 'view' && current ? (
          <Descriptions column={1} size="small">
            <Descriptions.Item label="id">{current.id}</Descriptions.Item>
            <Descriptions.Item label="名称">{current.name}</Descriptions.Item>
            <Descriptions.Item label="类型">{typeLabel(current.type)}</Descriptions.Item>
            <Descriptions.Item label="uuid">{current.uuid}</Descriptions.Item>
            <Descriptions.Item label="说明">{current.description || ''}</Descriptions.Item>
            <Descriptions.Item label="默认">{current.is_default ? '是' : '否'}</Descriptions.Item>
            <Descriptions.Item label="系统">{current.is_system ? '是' : '否'}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{formatTime(current.created_at)}</Descriptions.Item>
            <Descriptions.Item label="更新时间">{formatTime(current.updated_at)}</Descriptions.Item>
            <Descriptions.Item label="配置">
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{configText(current.config)}</pre>
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Form
            key={mode === 'edit' && current ? `edit-${current.id}` : 'create'}
            form={form}
            layout="vertical"
            initialValues={mode === 'edit' && current ? toForm(current) : EMPTY_FORM}
            onFinish={onSubmit}
          >
            <Form.Item
              name="name"
              label="名称"
              rules={[{ required: true, whitespace: true, message: '请填写名称' }]}
            >
              <Input maxLength={100} />
            </Form.Item>
            <Form.Item name="type" label="类型" rules={[{ required: true, message: '请选择类型' }]}>
              <Select options={TYPE_OPTIONS} />
            </Form.Item>
            <Form.Item noStyle shouldUpdate={(prev, next) => prev.type !== next.type}>
              {({ getFieldValue }) => {
                const picked = getFieldValue('type');
                if (picked === 'dataset') {
                  return (
                    <>
                      <Form.Item
                        name="dataset_uuid"
                        label="数据集 uuid"
                        rules={[{ required: true, whitespace: true, message: '请填写数据集 uuid' }]}
                      >
                        <Input />
                      </Form.Item>
                      <Form.Item name="display_name" label="显示名">
                        <Input />
                      </Form.Item>
                    </>
                  );
                }
                if (picked === 'http') {
                  return (
                    <Form.Item
                      name="url"
                      label="地址"
                      rules={[{ required: true, whitespace: true, message: '请填写地址' }]}
                    >
                      <Input />
                    </Form.Item>
                  );
                }
                return (
                  <Form.Item name="rows_text" label="静态行" extra="JSON 对象数组，对应 config.rows">
                    <Input.TextArea rows={6} />
                  </Form.Item>
                );
              }}
            </Form.Item>
            <Form.Item name="description" label="说明">
              <Input.TextArea rows={3} />
            </Form.Item>
            <Form.Item name="is_default" label="默认" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Form>
        )}
      </Modal>
    </ListPageTemplate>
  );
}
