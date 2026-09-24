/**
 * KU-AI 模型目录区块（spec 138）。
 *
 * - model_name 自由填写（非下拉）；model_type ∈ chat|embed|vision。
 * - 支持按 provider_id / model_type 过滤（后端 query 参数；经 UniTable `params`
 *   透传，保证请求缓存 key 与过滤条件一致并自动触发重新加载）。
 * - 按钮显隐按 kuaiai:model:{add,edit,remove}。
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { App, Button, Form, Input, Modal, Popconfirm, Select, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { UniTable } from '../../../../components/uni-table';
import { hasPermission } from '../../../../utils/permission';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import {
  createModel,
  deleteModel,
  listModels,
  listProviders,
  updateModel,
  type LlmModelOut,
  type LlmModelType,
} from '../../services/models';
import { bareListPageTotal, KUAI_AI_OPTIONS_PREFIX } from '../../constants';

const MODEL_TYPES: LlmModelType[] = ['chat', 'embed', 'vision'];

export function ModelsSection() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const actionRef = useRef<ActionType>(null);
  const currentUser = useCurrentUser();
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<LlmModelOut | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [filterProviderId, setFilterProviderId] = useState<number | undefined>();
  const [filterModelType, setFilterModelType] = useState<string | undefined>();

  const canAdd = hasPermission(currentUser, 'kuaiai:model:add');
  const canEdit = hasPermission(currentUser, 'kuaiai:model:edit');
  const canRemove = hasPermission(currentUser, 'kuaiai:model:remove');

  // 厂商目录：过滤下拉 + 表单下拉 + 列表 provider 名称回显共用
  const { data: providers } = useQuery({
    queryKey: ['kuaiai', 'llmProviders'],
    queryFn: () => listProviders(1, 200),
    staleTime: 60_000,
  });
  const providerNameMap = useMemo(() => {
    const map = new Map<number, string>();
    (providers ?? []).forEach((p) => map.set(p.id, p.name));
    return map;
  }, [providers]);

  useEffect(() => {
    if (!open) return;
    if (editing) {
      form.setFieldsValue({
        provider_id: editing.provider_id,
        model_name: editing.model_name,
        model_type: editing.model_type,
        status: editing.status,
      });
    } else {
      form.resetFields();
    }
  }, [open, editing, form]);

  const columns: ProColumns<LlmModelOut>[] = useMemo(
    () => [
      {
        title: t('app.kuaiai.models.colProvider', { defaultValue: '厂商' }),
        dataIndex: 'provider_id',
        width: 160,
        render: (_, row) => providerNameMap.get(row.provider_id) ?? `#${row.provider_id}`,
      },
      {
        title: t('app.kuaiai.models.modelName', { defaultValue: '模型名' }),
        dataIndex: 'model_name',
        ellipsis: true,
      },
      {
        title: t('app.kuaiai.models.modelType', { defaultValue: '类型' }),
        dataIndex: 'model_type',
        width: 100,
        render: (_, row) => <Tag>{row.model_type || '—'}</Tag>,
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
              title={t('app.kuaiai.models.confirmDeleteModel', {
                defaultValue: '确定删除该模型吗？',
              })}
              onConfirm={async () => {
                try {
                  await deleteModel(row.id);
                  message.success(
                    t('common.deleteSuccess', { defaultValue: '删除成功' }),
                  );
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [canEdit, canRemove, providerNameMap, message, queryClient, t],
  );

  const handleOk = async () => {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      if (editing) {
        await updateModel(editing.id, {
          provider_id: values.provider_id,
          model_name: values.model_name,
          model_type: values.model_type,
          status: values.status,
        });
        message.success(
          t('app.kuaiai.models.modelUpdated', { defaultValue: '模型已更新' }),
        );
      } else {
        await createModel({
          provider_id: values.provider_id,
          model_name: values.model_name,
          model_type: values.model_type,
          status: values.status,
        });
        message.success(
          t('app.kuaiai.models.modelCreated', { defaultValue: '模型已创建' }),
        );
      }
      setOpen(false);
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
      <UniTable<LlmModelOut>
        actionRef={actionRef}
        rowKey="id"
        columnPersistenceId="apps.kuaiai.pages.models.models.v1"
        search={false}
        showFuzzySearch={false}
        showAdvancedSearch={false}
        columns={columns}
        params={{
          provider_id: filterProviderId ?? undefined,
          model_type: filterModelType ?? undefined,
        }}
        toolBarRender={() => [
          <Select
            key="filter-provider"
            allowClear
            showSearch
            optionFilterProp="label"
            style={{ width: 180 }}
            placeholder={t('app.kuaiai.models.filterProvider', {
              defaultValue: '按厂商过滤',
            })}
            value={filterProviderId}
            onChange={(v) => setFilterProviderId(v)}
            options={(providers ?? []).map((p) => ({ value: p.id, label: p.name }))}
          />,
          <Select
            key="filter-type"
            allowClear
            style={{ width: 130 }}
            placeholder={t('app.kuaiai.models.filterModelType', {
              defaultValue: '按类型过滤',
            })}
            value={filterModelType}
            onChange={(v) => setFilterModelType(v)}
            options={MODEL_TYPES.map((mt) => ({ value: mt, label: mt }))}
          />,
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
              {t('app.kuaiai.models.createModel', { defaultValue: '新建模型' })}
            </Button>
          ) : null,
        ]}
        request={async (params) => {
          try {
            // 后端回裸数组（无 total）：满页时多报一页诱导翻页探明，不足页即真实总数
            const page = params.current ?? 1;
            const pageSize = params.pageSize ?? 50;
            const items = await listModels({
              page,
              page_size: pageSize,
              provider_id: params.provider_id,
              model_type: params.model_type,
            });
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
            ? t('app.kuaiai.models.editModel', { defaultValue: '编辑模型' })
            : t('app.kuaiai.models.createModel', { defaultValue: '新建模型' })
        }
        width={520}
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
            name="provider_id"
            label={t('app.kuaiai.models.colProvider', { defaultValue: '厂商' })}
            rules={[
              {
                required: true,
                message: t('app.kuaiai.models.providerRequired', {
                  defaultValue: '请选择厂商',
                }),
              },
            ]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={(providers ?? []).map((p) => ({
                value: p.id,
                label: `${p.name}（${p.code}）`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="model_name"
            label={t('app.kuaiai.models.modelName', { defaultValue: '模型名' })}
            rules={[
              {
                required: true,
                message: t('app.kuaiai.models.modelNameRequired', {
                  defaultValue: '请输入模型名',
                }),
              },
            ]}
            extra={t('app.kuaiai.models.modelNameHint', {
              defaultValue: '自由填写厂商侧模型名，如 deepseek-chat / text-embedding-3-large',
            })}
          >
            <Input maxLength={200} placeholder="deepseek-chat" />
          </Form.Item>
          <Form.Item
            name="model_type"
            label={t('app.kuaiai.models.modelType', { defaultValue: '类型' })}
            rules={[
              {
                required: true,
                message: t('app.kuaiai.models.modelTypeRequired', {
                  defaultValue: '请选择模型类型',
                }),
              },
            ]}
          >
            <Select options={MODEL_TYPES.map((mt) => ({ value: mt, label: mt }))} />
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
