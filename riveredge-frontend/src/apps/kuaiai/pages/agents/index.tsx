/**
 * KU-AI Agent 档案管理页（spec 138）。
 *
 * 列表：名称/描述/状态/授权模式/工具·知识库·MCP 数量/时间。
 * 操作：授权（名单）、编辑、删除、启用开关——按 kuaiai:agent:{add,edit,remove} 显隐。
 */

import React, { useMemo, useRef, useState } from 'react';
import { App, Button, Popconfirm, Switch, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { UniTable } from '../../../../components/uni-table';
import { hasPermission } from '../../../../utils/permission';
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

  const canAdd = hasPermission(currentUser, 'kuaiai:agent:add');
  const canEdit = hasPermission(currentUser, 'kuaiai:agent:edit');
  const canRemove = hasPermission(currentUser, 'kuaiai:agent:remove');

  const [editOpen, setEditOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<AgentProfileOut | null>(null);
  const [grantsTarget, setGrantsTarget] = useState<AgentProfileOut | null>(null);

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
              onChange={async (checked) => {
                try {
                  await updateAgent(row.id, { status: checked ? '启用' : '停用' });
                  message.success(
                    t('app.kuaiai.agents.statusUpdated', { defaultValue: '状态已更新' }),
                  );
                  void queryClient.invalidateQueries({ queryKey: KUAI_AI_OPTIONS_PREFIX });
                  actionRef.current?.reload();
                } catch (e: any) {
                  message.error(
                    e?.message ||
                      t('app.kuaiai.agents.statusUpdateFailed', {
                        defaultValue: '状态更新失败',
                      }),
                  );
                }
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
        key: 'tools_count',
        width: 80,
        align: 'right',
        render: (_, row) => row.enabled_tools?.length ?? 0,
      },
      {
        title: t('app.kuaiai.agents.colKnowledge', { defaultValue: '知识库数' }),
        key: 'knowledge_count',
        width: 90,
        align: 'right',
        render: (_, row) => row.knowledge_ids?.length ?? 0,
      },
      {
        title: t('app.kuaiai.agents.colMcp', { defaultValue: 'MCP 数' }),
        key: 'mcp_count',
        width: 80,
        align: 'right',
        render: (_, row) => row.mcp_server_ids?.length ?? 0,
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
              onClick={() => {
                setEditTarget(row);
                setEditOpen(true);
              }}
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
              onConfirm={async () => {
                try {
                  await deleteAgent(row.id);
                  message.success(
                    t('common.deleteSuccess', { defaultValue: '删除成功' }),
                  );
                  void queryClient.invalidateQueries({ queryKey: KUAI_AI_OPTIONS_PREFIX });
                  actionRef.current?.reload();
                } catch (e: any) {
                  message.error(
                    e?.message ||
                      t('common.deleteFailed', { defaultValue: '删除失败' }),
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
        toolBarRender={() => [
          canAdd ? (
            <Button
              key="create"
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditTarget(null);
                setEditOpen(true);
              }}
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
          // 档案变化影响 chat 页档案下拉缓存
          void queryClient.invalidateQueries({ queryKey: KUAI_AI_OPTIONS_PREFIX });
          actionRef.current?.reload();
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
