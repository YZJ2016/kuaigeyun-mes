import React, { useMemo, useRef, useState } from 'react';
import { App, Button, Form, Input, Modal, Popconfirm, Select, Tag, Tooltip, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { UniTable } from '../../../../components/uni-table';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import { hasPermission } from '../../../../utils/permission';
import {
  createMcpServer,
  deleteMcpServer,
  listMcpServers,
  updateMcpServer,
  type McpServerOut,
} from '../../services/mcp';
import { KUAI_AI_OPTIONS_PREFIX } from '../../constants';

const M = 'app.kuaiai.mcp';

const STATUS_ENABLED = '启用';
const STATUS_DISABLED = '停用';

export default function KuaiaiMcpPage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const currentUser = useCurrentUser();
  const canAdd = hasPermission(currentUser, 'kuaiai:mcp:add');
  const canEdit = hasPermission(currentUser, 'kuaiai:mcp:edit');
  const canRemove = hasPermission(currentUser, 'kuaiai:mcp:remove');

  const actionRef = useRef<ActionType>(null);
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<McpServerOut | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ transport: 'http', status: STATUS_ENABLED });
    setModalOpen(true);
  };

  const openEdit = (row: McpServerOut) => {
    setEditing(row);
    form.resetFields();
    form.setFieldsValue({
      code: row.code,
      name: row.name,
      transport: row.transport || 'http',
      endpoint: row.endpoint,
      token: undefined, // 编辑留空 = 保留原 Token（后端口径：空白/打码占位=保留）
      allowed_tools: row.allowed_tools,
      status: row.status,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      // trim 防空白字符串被当作有效 token 提交；留空=保留原值（与厂商 api_key 同口径）
      const token = typeof values.token === 'string' ? values.token.trim() : '';
      if (editing) {
        await updateMcpServer(editing.id, {
          name: values.name,
          transport: 'http',
          endpoint: values.endpoint,
          ...(token ? { token } : {}),
          allowed_tools: values.allowed_tools,
          status: values.status,
        });
        message.success(t('common.updateSuccess'));
      } else {
        await createMcpServer({
          code: values.code,
          name: values.name,
          transport: 'http',
          endpoint: values.endpoint,
          ...(token ? { token } : {}),
          allowed_tools: values.allowed_tools,
          status: values.status,
        });
        message.success(t('common.createSuccess'));
      }
      setModalOpen(false);
      // MCP 变化影响档案表单的 mcp_server_ids 下拉缓存
      void queryClient.invalidateQueries({ queryKey: KUAI_AI_OPTIONS_PREFIX });
      actionRef.current?.reload();
    } catch (error: any) {
      if (error?.errorFields) return;
      message.error(error?.message || t('common.saveFailed', { defaultValue: '保存失败' }));
    } finally {
      setSubmitting(false);
    }
  };

  const columns: ProColumns<McpServerOut>[] = useMemo(
    () => [
      {
        title: t(`${M}.code`, { defaultValue: '代码' }),
        dataIndex: 'code',
        width: 140,
        ellipsis: true,
        hideInSearch: true,
      },
      {
        title: t(`${M}.name`, { defaultValue: '名称' }),
        dataIndex: 'name',
        width: 160,
        ellipsis: true,
        hideInSearch: true,
      },
      {
        title: t(`${M}.transport`, { defaultValue: '传输' }),
        dataIndex: 'transport',
        width: 80,
        hideInSearch: true,
        render: (_, r) => <Tag>{r.transport || 'http'}</Tag>,
      },
      {
        title: t(`${M}.endpoint`, { defaultValue: '端点' }),
        dataIndex: 'endpoint',
        ellipsis: true,
        hideInSearch: true,
        render: (_, r) => (
          <Tooltip title={r.endpoint}>
            <span>{r.endpoint}</span>
          </Tooltip>
        ),
      },
      {
        title: t(`${M}.token`, { defaultValue: 'Token' }),
        dataIndex: 'token_configured',
        width: 100,
        hideInSearch: true,
        render: (_, r) =>
          r.token_configured ? (
            // 后端恒回打码占位（如 "****"），原样展示，绝不展示明文
            <Typography.Text code>{r.token || '****'}</Typography.Text>
          ) : (
            <Typography.Text type="secondary">
              {t(`${M}.tokenNotConfigured`, { defaultValue: '未配置' })}
            </Typography.Text>
          ),
      },
      {
        title: t(`${M}.allowedTools`, { defaultValue: '允许工具' }),
        dataIndex: 'allowed_tools',
        ellipsis: true,
        hideInSearch: true,
        render: (_, r) => (
          <Tooltip title={r.allowed_tools}>
            <span>{r.allowed_tools}</span>
          </Tooltip>
        ),
      },
      {
        title: t('common.status'),
        dataIndex: 'status',
        width: 90,
        hideInSearch: true,
        render: (_, r) => (
          <Tag color={r.status === STATUS_ENABLED ? 'success' : 'default'}>{r.status}</Tag>
        ),
      },
      {
        title: t('common.updatedAt'),
        dataIndex: 'updated_at',
        width: 160,
        hideInSearch: true,
        render: (_, r) => (r.updated_at ? dayjs(r.updated_at).format('YYYY-MM-DD HH:mm') : '—'),
      },
      {
        title: t('common.actions'),
        valueType: 'option',
        width: 130,
        fixed: 'right',
        render: (_, r) => [
          canEdit ? (
            <Button key="edit" type="link" size="small" onClick={() => openEdit(r)}>
              {t('common.edit')}
            </Button>
          ) : null,
          canRemove ? (
            <Popconfirm
              key="del"
              title={t('common.confirmDelete')}
              onConfirm={async () => {
                try {
                  await deleteMcpServer(r.id);
                  message.success(t('common.deleteSuccess'));
                  void queryClient.invalidateQueries({ queryKey: KUAI_AI_OPTIONS_PREFIX });
                  actionRef.current?.reload();
                } catch (error: any) {
                  message.error(error?.message || t('common.deleteFailed', { defaultValue: '删除失败' }));
                }
              }}
            >
              <Button type="link" size="small" danger>
                {t('common.delete')}
              </Button>
            </Popconfirm>
          ) : null,
        ],
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [canEdit, canRemove, t, message, queryClient],
  );

  return (
    <ListPageTemplate>
      <UniTable<McpServerOut>
        actionRef={actionRef}
        rowKey="id"
        columns={columns}
        columnPersistenceId="apps.kuaiai.pages.mcp.list-v1"
        viewTypes={['table']}
        showFuzzySearch={false}
        showAdvancedSearch={false}
        showImportButton={false}
        showExportButton={false}
        request={async (params) => {
          try {
            const res = await listMcpServers({
              page: params.current,
              page_size: params.pageSize,
            });
            return { data: res.items, total: res.total, success: true };
          } catch (error: any) {
            message.error(error?.message || t(`${M}.loadFailed`, { defaultValue: '加载失败' }));
            return { data: [], total: 0, success: false };
          }
        }}
        toolBarActions={
          canAdd
            ? [
                <Button key="create" type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                  {t(`${M}.create`, { defaultValue: '新建 MCP 服务器' })}
                </Button>,
              ]
            : []
        }
      />

      <Modal
        open={modalOpen}
        title={
          editing
            ? t(`${M}.editTitle`, { defaultValue: '编辑 MCP 服务器' })
            : t(`${M}.createTitle`, { defaultValue: '新建 MCP 服务器' })
        }
        onCancel={() => setModalOpen(false)}
        onOk={() => void handleSubmit()}
        confirmLoading={submitting}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ transport: 'http', status: STATUS_ENABLED }}
        >
          <Form.Item
            name="code"
            label={t(`${M}.code`, { defaultValue: '代码' })}
            rules={[{ required: true, message: t(`${M}.codeRequired`, { defaultValue: '请输入代码' }) }]}
            extra={editing ? t(`${M}.codeImmutable`, { defaultValue: '代码创建后不可修改' }) : undefined}
          >
            <Input maxLength={64} disabled={!!editing} />
          </Form.Item>
          <Form.Item
            name="name"
            label={t(`${M}.name`, { defaultValue: '名称' })}
            rules={[{ required: true, message: t(`${M}.nameRequired`, { defaultValue: '请输入名称' }) }]}
          >
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item
            name="transport"
            label={t(`${M}.transport`, { defaultValue: '传输' })}
            extra={t(`${M}.transportHint`, { defaultValue: '当前仅支持 http' })}
          >
            <Select disabled options={[{ value: 'http', label: 'http' }]} />
          </Form.Item>
          <Form.Item
            name="endpoint"
            label={t(`${M}.endpoint`, { defaultValue: '端点' })}
            rules={[
              { required: true, message: t(`${M}.endpointRequired`, { defaultValue: '请输入端点 URL' }) },
            ]}
          >
            <Input maxLength={500} placeholder="https://…" />
          </Form.Item>
          <Form.Item
            name="token"
            label={t(`${M}.token`, { defaultValue: 'Token' })}
            extra={
              editing
                ? t(`${M}.tokenKeepHint`, { defaultValue: '留空则保留原 Token；不回显明文' })
                : t(`${M}.tokenHint`, { defaultValue: 'Bearer Token（可选，只写不回明文）' })
            }
          >
            <Input.Password
              maxLength={4096}
              autoComplete="new-password"
              placeholder={
                editing
                  ? t(`${M}.tokenKeepPlaceholder`, { defaultValue: '留空则保留原 Token' })
                  : undefined
              }
            />
          </Form.Item>
          <Form.Item
            name="allowed_tools"
            label={t(`${M}.allowedTools`, { defaultValue: '允许工具' })}
            rules={[
              {
                required: true,
                message: t(`${M}.allowedToolsRequired`, { defaultValue: '请输入允许的工具名' }),
              },
            ]}
            extra={t(`${M}.allowedToolsHint`, {
              defaultValue: '逗号分隔的工具名白名单（CSV）；SQL 类工具名会被后端拒绝',
            })}
          >
            <Input.TextArea rows={3} maxLength={4096} placeholder="tool_a, tool_b" />
          </Form.Item>
          <Form.Item
            name="status"
            label={t('common.status')}
            rules={[{ required: true, message: t(`${M}.statusRequired`, { defaultValue: '请选择状态' }) }]}
          >
            <Select
              options={[
                { value: STATUS_ENABLED, label: t('common.enabled') },
                { value: STATUS_DISABLED, label: t('common.disabled') },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </ListPageTemplate>
  );
}
