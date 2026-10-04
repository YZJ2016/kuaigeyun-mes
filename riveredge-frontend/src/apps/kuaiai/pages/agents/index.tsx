/**
 * KU-AI Agent 档案管理页（spec 138）。
 *
 * 列表：名称/描述/状态/授权模式/工具·知识库·MCP 数量/时间。
 * 操作：授权（名单）、编辑、删除、启用开关——按 kuaiai:agent:{add,edit,remove} 显隐。
 */

import React, { useCallback, useMemo, useRef, useState } from 'react';
import { App, Button, Card, Popconfirm, Space, Switch, Tag, Tooltip, Typography, theme } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { UniTable } from '../../../../components/uni-table';
import { hasPermission } from '../../../../utils/permission';
import { formatDateTime } from '../../../../utils/format';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import {
  deleteAgent,
  listAgents,
  updateAgent,
  type AgentProfileOut,
} from '../../services/agents';
import { bareListPageTotal, KUAI_AI_OPTIONS_PREFIX } from '../../constants';
import { AgentEditModal } from './AgentEditModal';
import { AgentGrantsModal } from './AgentGrantsModal';

export default function KuaiaiAgentsPage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const actionRef = useRef<ActionType>(null);
  const currentUser = useCurrentUser();
  const queryClient = useQueryClient();

  const canAdd = hasPermission(currentUser, 'kuaiai:agent:create');
  const canEdit = hasPermission(currentUser, 'kuaiai:agent:update');
  const canRemove = hasPermission(currentUser, 'kuaiai:agent:delete');

  const [editOpen, setEditOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<AgentProfileOut | null>(null);
  const [grantsTarget, setGrantsTarget] = useState<AgentProfileOut | null>(null);
  const { token } = theme.useToken();
  const { Text, Paragraph } = Typography;

  const reload = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: KUAI_AI_OPTIONS_PREFIX });
    actionRef.current?.reload();
  }, [queryClient]);

  const handleStatusChange = useCallback(
    async (row: AgentProfileOut, checked: boolean) => {
      try {
        await updateAgent(row.id, { status: checked ? '启用' : '停用' });
        message.success(t('app.kuaiai.agents.statusUpdated', { defaultValue: '状态已更新' }));
        reload();
      } catch (e: any) {
        message.error(
          e?.message ||
            t('app.kuaiai.agents.statusUpdateFailed', { defaultValue: '状态更新失败' }),
        );
      }
    },
    [message, reload, t],
  );

  const handleDelete = useCallback(
    async (row: AgentProfileOut) => {
      try {
        await deleteAgent(row.id);
        message.success(t('common.deleteSuccess', { defaultValue: '删除成功' }));
        reload();
      } catch (e: any) {
        message.error(e?.message || t('common.deleteFailed', { defaultValue: '删除失败' }));
      }
    },
    [message, reload, t],
  );

  const openEdit = useCallback((row: AgentProfileOut | null) => {
    setEditTarget(row);
    setEditOpen(true);
  }, []);

  const columns: ProColumns<AgentProfileOut>[] = useMemo(
    () => [
      {
        title: t('app.kuaiai.agents.fieldName', { defaultValue: '名称' }),
        dataIndex: 'name',
        width: 160,
        ellipsis: true,
      },
      {
        title: t('app.kuaiai.agents.fieldDescription', { defaultValue: '描述' }),
        dataIndex: 'description',
        ellipsis: true,
        render: (_, row) => row.description || '—',
      },
      {
        title: t('common.status', { defaultValue: '状态' }),
        dataIndex: 'status',
        width: 110,
        render: (_, row) => {
          const enabled = row.status === '启用';
          if (!canEdit) {
            return (
              <Tag color={enabled ? 'green' : 'default'}>
                {enabled
                  ? t('common.enabled', { defaultValue: '启用' })
                  : t('common.disabled', { defaultValue: '停用' })}
              </Tag>
            );
          }
          return (
            <Switch
              size="small"
              checked={enabled}
              checkedChildren={t('common.enabled', { defaultValue: '启用' })}
              unCheckedChildren={t('common.disabled', { defaultValue: '停用' })}
              onChange={(checked) => {
                void handleStatusChange(row, checked);
              }}
            />
          );
        },
      },
      {
        title: t('app.kuaiai.agents.fieldGrantMode', { defaultValue: '授权模式' }),
        dataIndex: 'grant_mode',
        width: 110,
        render: (_, row) =>
          row.grant_mode === 'USER' ? (
            <Tag color="purple">
              {t('app.kuaiai.agents.grantModeUser', { defaultValue: '按人员' })}
            </Tag>
          ) : (
            <Tag color="blue">
              {t('app.kuaiai.agents.grantModeRole', { defaultValue: '按角色' })}
            </Tag>
          ),
      },
      {
        title: t('app.kuaiai.agents.colTools', { defaultValue: '工具数' }),
        dataIndex: 'enabled_tools',
        key: 'tools_count',
        width: 80,
        align: 'right',
        // 必须带 dataIndex：无 dataIndex 的 render 列会被当成操作列，数字被滤成空白
        render: (_, row) =>
          Array.isArray(row.enabled_tools) ? row.enabled_tools.length : 0,
      },
      {
        title: t('app.kuaiai.agents.colKnowledge', { defaultValue: '知识库数' }),
        dataIndex: 'knowledge_ids',
        key: 'knowledge_count',
        width: 90,
        align: 'right',
        render: (_, row) =>
          Array.isArray(row.knowledge_ids) ? row.knowledge_ids.length : 0,
      },
      {
        title: t('app.kuaiai.agents.colMcp', { defaultValue: 'MCP 数' }),
        dataIndex: 'mcp_server_ids',
        key: 'mcp_count',
        width: 80,
        align: 'right',
        render: (_, row) =>
          Array.isArray(row.mcp_server_ids) ? row.mcp_server_ids.length : 0,
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
        width: 170,
        render: (_, row) => [
          canEdit && (
            <Button
              key="grants"
              type="link"
              size="small"
              onClick={() => setGrantsTarget(row)}
            >
              {t('app.kuaiai.agents.actionGrants', { defaultValue: '授权' })}
            </Button>
          ),
          canEdit && (
            <Button
              key="edit"
              type="link"
              size="small"
              onClick={() => openEdit(row)}
            >
              {t('common.edit', { defaultValue: '编辑' })}
            </Button>
          ),
          canRemove && (
            <Popconfirm
              key="delete"
              title={t('app.kuaiai.agents.confirmDelete', {
                defaultValue: '确定删除该档案吗？',
              })}
              onConfirm={() => handleDelete(row)}
            >
              <Button type="link" size="small" danger>
                {t('common.delete', { defaultValue: '删除' })}
              </Button>
            </Popconfirm>
          ),
        ],
      },
    ],
    [canEdit, canRemove, handleDelete, handleStatusChange, openEdit, t],
  );

  const renderCard = useCallback(
    (row: AgentProfileOut) => {
      const enabled = row.status === '启用';
      const actions: React.ReactNode[] = [];
      if (canEdit) {
        actions.push(
          <Tooltip
            key="grants"
            title={t('app.kuaiai.agents.actionGrants', { defaultValue: '授权' })}
          >
            <SafetyCertificateOutlined
              onClick={() => setGrantsTarget(row)}
              style={{ fontSize: 16 }}
            />
          </Tooltip>,
          <Tooltip key="edit" title={t('common.edit', { defaultValue: '编辑' })}>
            <EditOutlined onClick={() => openEdit(row)} style={{ fontSize: 16 }} />
          </Tooltip>,
        );
      }
      if (canRemove) {
        actions.push(
          <Popconfirm
            key="delete"
            title={t('app.kuaiai.agents.confirmDelete', { defaultValue: '确定删除该档案吗？' })}
            onConfirm={() => handleDelete(row)}
          >
            <Tooltip title={t('common.delete', { defaultValue: '删除' })}>
              <DeleteOutlined style={{ fontSize: 16, color: token.colorError }} />
            </Tooltip>
          </Popconfirm>,
        );
      }

      const meta = (label: string, value: React.ReactNode) => (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <Text type="secondary" style={{ fontSize: 12 }}>
            {label}
          </Text>
          {typeof value === 'string' || typeof value === 'number' ? (
            <Text style={{ fontSize: 12 }}>{value}</Text>
          ) : (
            value
          )}
        </div>
      );

      return (
        <Card
          hoverable
          style={{ height: '100%' }}
          actions={actions.length > 0 ? actions : undefined}
        >
          <Space orientation="vertical" size="small" style={{ width: '100%' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <Text strong ellipsis style={{ fontSize: 16, flex: 1, minWidth: 0 }}>
                {row.name}
              </Text>
              {row.grant_mode === 'USER' ? (
                <Tag color="purple">
                  {t('app.kuaiai.agents.grantModeUser', { defaultValue: '按人员' })}
                </Tag>
              ) : (
                <Tag color="blue">
                  {t('app.kuaiai.agents.grantModeRole', { defaultValue: '按角色' })}
                </Tag>
              )}
            </div>
            <Paragraph
              ellipsis={{ rows: 2, expandable: false }}
              style={{ marginBottom: 0, minHeight: 40, fontSize: 12 }}
            >
              {row.description || '—'}
            </Paragraph>
          </Space>
          <div
            style={{
              marginTop: 12,
              paddingTop: 12,
              borderTop: `1px solid ${token.colorBorderSecondary}`,
            }}
          >
            <Space orientation="vertical" size="small" style={{ width: '100%' }}>
              {meta(
                t('common.status', { defaultValue: '状态' }),
                canEdit ? (
                  <Switch
                    size="small"
                    checked={enabled}
                    checkedChildren={t('common.enabled', { defaultValue: '启用' })}
                    unCheckedChildren={t('common.disabled', { defaultValue: '停用' })}
                    onChange={(checked) => {
                      void handleStatusChange(row, checked);
                    }}
                  />
                ) : (
                  <Tag color={enabled ? 'green' : 'default'}>
                    {enabled
                      ? t('common.enabled', { defaultValue: '启用' })
                      : t('common.disabled', { defaultValue: '停用' })}
                  </Tag>
                ),
              )}
              {meta(
                t('app.kuaiai.agents.colTools', { defaultValue: '工具数' }),
                Array.isArray(row.enabled_tools) ? row.enabled_tools.length : 0,
              )}
              {meta(
                t('app.kuaiai.agents.colKnowledge', { defaultValue: '知识库数' }),
                Array.isArray(row.knowledge_ids) ? row.knowledge_ids.length : 0,
              )}
              {meta(
                t('app.kuaiai.agents.colMcp', { defaultValue: 'MCP 数' }),
                Array.isArray(row.mcp_server_ids) ? row.mcp_server_ids.length : 0,
              )}
              {meta(
                t('common.updatedAt', { defaultValue: '更新时间' }),
                formatDateTime(row.updated_at),
              )}
            </Space>
          </div>
        </Card>
      );
    },
    [canEdit, canRemove, handleDelete, handleStatusChange, openEdit, t, token],
  );

  return (
    <ListPageTemplate>
      <UniTable<AgentProfileOut>
        actionRef={actionRef}
        rowKey="id"
        columnPersistenceId="apps.kuaiai.pages.agents.v1"
        search={false}
        showFuzzySearch={false}
        showAdvancedSearch={false}
        columns={columns}
        viewTypes={['card', 'table', 'help']}
        defaultViewType="table"
        cardViewConfig={{ renderCard }}
        toolBarRender={() => [
          canAdd ? (
            <Button
              key="create"
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => openEdit(null)}
            >
              {t('app.kuaiai.agents.createButton', { defaultValue: '新建档案' })}
            </Button>
          ) : null,
        ]}
        request={async (params) => {
          try {
            // 后端回裸数组（无 total）：满页时多报一页诱导翻页探明，不足页即真实总数
            const page = params.current ?? 1;
            const pageSize = params.pageSize ?? 50;
            const items = await listAgents(page, pageSize);
            return {
              data: items,
              success: true,
              total: bareListPageTotal(page, pageSize, items.length),
            };
          } catch (e: any) {
            message.error(
              e?.message ||
                t('app.kuaiai.agents.loadFailed', { defaultValue: '加载失败' }),
            );
            return { data: [], success: false, total: 0 };
          }
        }}
      />
      <AgentEditModal
        open={editOpen}
        agent={editTarget}
        onCancel={() => setEditOpen(false)}
        onSaved={() => {
          setEditOpen(false);
          reload();
        }}
      />
      <AgentGrantsModal
        open={!!grantsTarget}
        agent={grantsTarget}
        onClose={() => setGrantsTarget(null)}
      />
    </ListPageTemplate>
  );
}
