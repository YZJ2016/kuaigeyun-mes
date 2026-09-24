/**
 * KU-AI 厂商目录区块（spec 138）。
 *
 * - 厂商非闭集：「常用模板」仅自动带出 name/base_url/provider_type，不锁字段。
 * - api_key 只写：编辑留空=保留原值；列表只展示后端打码占位/已配置状态，不回显明文。
 * - 按钮显隐按 kuaiai:model:{add,edit,remove}。
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { App, Button, Form, Input, Modal, Popconfirm, Select, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { UniTable } from '../../../../components/uni-table';
import { hasPermission } from '../../../../utils/permission';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import {
  createProvider,
  deleteProvider,
  listProviders,
  updateProvider,
  LLM_PROVIDER_TEMPLATES,
  type LlmProviderOut,
} from '../../services/models';
import { bareListPageTotal, KUAI_AI_OPTIONS_PREFIX } from '../../constants';

/** 厂商下拉/回显共用缓存 key（与 ModelsSection 的 providers 查询一致） */
const PROVIDERS_QUERY_KEY = ['kuaiai', 'llmProviders'] as const;

export function ProvidersSection() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const actionRef = useRef<ActionType>(null);
  const currentUser = useCurrentUser();
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<LlmProviderOut | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const canAdd = hasPermission(currentUser, 'kuaiai:model:add');
  const canEdit = hasPermission(currentUser, 'kuaiai:model:edit');
  const canRemove = hasPermission(currentUser, 'kuaiai:model:remove');

  useEffect(() => {
    if (!open) return;
    if (editing) {
      form.setFieldsValue({
        template: undefined,
        code: editing.code,
        name: editing.name,
        base_url: editing.base_url,
        api_key: undefined,
        provider_type: editing.provider_type ?? undefined,
        status: editing.status,
      });
    } else {
      form.resetFields();
    }
  }, [open, editing, form]);

  const columns: ProColumns<LlmProviderOut>[] = useMemo(
    () => [
      {
        title: t('app.kuaiai.models.providerCode', { defaultValue: '代码' }),
        dataIndex: 'code',
        width: 120,
      },
      {
        title: t('app.kuaiai.models.providerName', { defaultValue: '名称' }),
        dataIndex: 'name',
        width: 160,
        ellipsis: true,
      },
      {
        title: 'Base URL',
        dataIndex: 'base_url',
        ellipsis: true,
      },
      {
        title: 'API Key',
        dataIndex: 'api_key',
        width: 140,
        render: (_, row) =>
          row.api_key ? (
            <span style={{ fontFamily: 'monospace' }}>{row.api_key}</span>
          ) : row.api_key_configured ? (
            t('app.kuaiai.models.apiKeyConfigured', { defaultValue: '已配置' })
          ) : (
            t('app.kuaiai.models.apiKeyMissing', { defaultValue: '未配置' })
          ),
      },
      {
        title: t('app.kuaiai.models.providerType', { defaultValue: '类型' }),
        dataIndex: 'provider_type',
        width: 110,
        render: (_, row) => row.provider_type || '—',
      },
      {
        title: t('common.status', { defaultValue: '状态' }),
        dataIndex: 'status',
        width: 90,
        render: (_, row) => (
          <Tag color={row.status === '启用' ? 'green' : 'default'}>{row.status}</Tag>
        ),
      },
      {
        title: t('common.updatedAt', { defaultValue: '更新时间' }),
        dataIndex: 'updated_at',
        valueType: 'dateTime',
        width: 170,
      },
      {
        title: t('common.actions', { defaultValue: '操作' }),
        valueType: 'option',
        width: 130,
        render: (_, row) => [
          canEdit && (
            <Button
              key="edit"
              type="link"
              size="small"
              onClick={() => {
                setEditing(row);
                setOpen(true);
              }}
            >
              {t('common.edit', { defaultValue: '编辑' })}
            </Button>
          ),
          canRemove && (
            <Popconfirm
              key="delete"
              title={t('app.kuaiai.models.confirmDeleteProvider', {
                defaultValue: '确定删除该厂商吗？',
              })}
              onConfirm={async () => {
                try {
                  await deleteProvider(row.id);
                  message.success(
                    t('common.deleteSuccess', { defaultValue: '删除成功' }),
                  );
                  void queryClient.invalidateQueries({ queryKey: PROVIDERS_QUERY_KEY });
                  void queryClient.invalidateQueries({ queryKey: KUAI_AI_OPTIONS_PREFIX });
                  actionRef.current?.reload();
                } catch (e: any) {
                  message.error(
                    e?.message || t('common.deleteFailed', { defaultValue: '删除失败' }),
                  );
                }
              }}
            >
              <Button type="link" size="small" danger>
                {t('common.delete', { defaultValue: '删除' })}
              </Button>
            </Popconfirm>
          ),
        ],
      },
    ],
    [canEdit, canRemove, message, queryClient, t],
  );

  const handleOk = async () => {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      // trim 防空白字符串被当作有效 key 提交；留空=保留原值
      const apiKey = typeof values.api_key === 'string' ? values.api_key.trim() : '';
      if (editing) {
        // api_key 留空/省略 = 保留原值；仅填写时才提交
        await updateProvider(editing.id, {
          name: values.name,
          base_url: values.base_url,
          ...(apiKey ? { api_key: apiKey } : {}),
          provider_type: values.provider_type,
          status: values.status,
        });
        message.success(
          t('app.kuaiai.models.providerUpdated', { defaultValue: '厂商已更新' }),
        );
      } else {
        await createProvider({
          code: values.code,
          name: values.name,
          base_url: values.base_url,
          ...(apiKey ? { api_key: apiKey } : {}),
          ...(values.provider_type ? { provider_type: values.provider_type } : {}),
          status: values.status,
        });
        message.success(
          t('app.kuaiai.models.providerCreated', { defaultValue: '厂商已创建' }),
        );
      }
      setOpen(false);
      void queryClient.invalidateQueries({ queryKey: PROVIDERS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: KUAI_AI_OPTIONS_PREFIX });
      actionRef.current?.reload();
    } catch (e: any) {
      message.error(
        e?.message || t('app.kuaiai.models.saveFailed', { defaultValue: '保存失败' }),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <UniTable<LlmProviderOut>
        actionRef={actionRef}
        rowKey="id"
        columnPersistenceId="apps.kuaiai.pages.models.providers.v1"
        search={false}
        showFuzzySearch={false}
        showAdvancedSearch={false}
        columns={columns}
        toolBarRender={() => [
          canAdd ? (
            <Button
              key="create"
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditing(null);
                setOpen(true);
              }}
            >
              {t('app.kuaiai.models.createProvider', { defaultValue: '新建厂商' })}
            </Button>
          ) : null,
        ]}
        request={async (params) => {
          try {
            // 后端回裸数组（无 total）：满页时多报一页诱导翻页探明，不足页即真实总数
            const page = params.current ?? 1;
            const pageSize = params.pageSize ?? 50;
            const items = await listProviders(page, pageSize);
            return {
              data: items,
              success: true,
              total: bareListPageTotal(page, pageSize, items.length),
            };
          } catch (e: any) {
            message.error(
              e?.message ||
                t('app.kuaiai.models.loadFailed', { defaultValue: '加载失败' }),
            );
            return { data: [], success: false, total: 0 };
          }
        }}
      />
      <Modal
        open={open}
        title={
          editing
            ? t('app.kuaiai.models.editProvider', { defaultValue: '编辑厂商' })
            : t('app.kuaiai.models.createProvider', { defaultValue: '新建厂商' })
        }
        width={560}
        confirmLoading={submitting}
        onCancel={() => setOpen(false)}
        onOk={() => void handleOk()}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          preserve={false}
          initialValues={{ status: '启用' }}
        >
          <Form.Item
            name="template"
            label={t('app.kuaiai.models.template', { defaultValue: '常用模板' })}
            extra={t('app.kuaiai.models.templateHint', {
              defaultValue: '选择模板仅自动填充名称与 Base URL，仍可自由修改',
            })}
          >
            <Select
              allowClear
              placeholder={t('app.kuaiai.models.templatePlaceholder', {
                defaultValue: '可选：选择常见厂商模板',
              })}
              options={LLM_PROVIDER_TEMPLATES.map((tpl) => ({
                value: tpl.key,
                label: tpl.label,
              }))}
              onChange={(key) => {
                const tpl = LLM_PROVIDER_TEMPLATES.find((x) => x.key === key);
                if (!tpl) return;
                form.setFieldsValue({
                  name: tpl.name,
                  base_url: tpl.base_url,
                  provider_type: tpl.provider_type,
                });
              }}
            />
          </Form.Item>
          <Form.Item
            name="code"
            label={t('app.kuaiai.models.providerCode', { defaultValue: '代码' })}
            rules={[
              {
                required: true,
                message: t('app.kuaiai.models.codeRequired', {
                  defaultValue: '请输入厂商代码',
                }),
              },
            ]}
          >
            <Input maxLength={64} disabled={!!editing} placeholder="deepseek" />
          </Form.Item>
          <Form.Item
            name="name"
            label={t('app.kuaiai.models.providerName', { defaultValue: '名称' })}
            rules={[
              {
                required: true,
                message: t('app.kuaiai.models.nameRequired', {
                  defaultValue: '请输入厂商名称',
                }),
              },
            ]}
          >
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="Base URL"
            rules={[
              {
                required: true,
                message: t('app.kuaiai.models.baseUrlRequired', {
                  defaultValue: '请输入 OpenAI 兼容端点 Base URL',
                }),
              },
            ]}
          >
            <Input maxLength={500} placeholder="https://api.example.com/v1" />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            extra={
              editing
                ? t('app.kuaiai.models.apiKeyEditHint', {
                    defaultValue: '留空则保留原 Key；不会回显明文',
                  })
                : undefined
            }
          >
            <Input.Password
              maxLength={500}
              autoComplete="new-password"
              placeholder={
                editing
                  ? t('app.kuaiai.models.apiKeyKeepPlaceholder', {
                      defaultValue: '留空保留原值',
                    })
                  : undefined
              }
            />
          </Form.Item>
          <Form.Item
            name="provider_type"
            label={t('app.kuaiai.models.providerType', { defaultValue: '类型' })}
          >
            <Input
              maxLength={50}
              placeholder={t('app.kuaiai.models.providerTypePlaceholder', {
                defaultValue: '可选：如 deepseek / openai / qwen',
              })}
            />
          </Form.Item>
          <Form.Item
            name="status"
            label={t('common.status', { defaultValue: '状态' })}
            rules={[{ required: true }]}
          >
            <Select
              options={[
                { value: '启用', label: t('common.enabled', { defaultValue: '启用' }) },
                { value: '停用', label: t('common.disabled', { defaultValue: '停用' }) },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
