/**
 * KU-AI Agent 档案新建/编辑弹窗（spec 138；spec 189 Tool 目录改读接口）。
 *
 * - 提交只发 schema 字段（AgentProfileCreate/Update），不带 tenantId。
 * - enabled_tools 勾选项来自 GET /apps/kuaiai/tools（label 后端下发），
 *   目录加载失败显示错误与重试、禁用保存按钮（避免 enabled_tools 原值静默回写）。
 * - grant_mode 可在编辑时切换；后端同事务清空对侧授权名单。
 * - 新建时默认「停用」：启用档案空授权名单会被后端 400，先停用建档再配名单。
 */

import React, { useEffect, useState } from 'react';
import { Alert, App, Button, Checkbox, Form, Input, Modal, Radio, Select } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  createAgent,
  updateAgent,
  type AgentProfileOut,
} from '../../services/agents';
import { listKnowledgeBaseOptions } from '../../services/knowledge';
import { listMcpServerOptions } from '../../services/mcp';
import { listToolCatalog } from '../../services/tools';
import { KUAI_AI_OPTION_KEYS } from '../../constants';
import { hasPermission } from '../../../../utils/permission';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';

interface AgentEditModalProps {
  open: boolean;
  /** null 表示新建 */
  agent: AgentProfileOut | null;
  onCancel: () => void;
  onSaved: () => void;
}

export function AgentEditModal({ open, agent, onCancel, onSaved }: AgentEditModalProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const currentUser = useCurrentUser();
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const { data: knowledgeOptions } = useQuery({
    queryKey: KUAI_AI_OPTION_KEYS.knowledgeBases,
    queryFn: listKnowledgeBaseOptions,
    enabled: open && hasPermission(currentUser, 'kuaiai:knowledge:read'),
    staleTime: 60_000,
  });
  const { data: mcpOptions } = useQuery({
    queryKey: KUAI_AI_OPTION_KEYS.mcpServers,
    queryFn: listMcpServerOptions,
    enabled: open && hasPermission(currentUser, 'kuaiai:mcp:read'),
    staleTime: 60_000,
  });
  const {
    data: toolCatalog,
    isError: toolCatalogError,
    refetch: refetchToolCatalog,
  } = useQuery({
    queryKey: KUAI_AI_OPTION_KEYS.tools,
    queryFn: listToolCatalog,
    enabled: open && hasPermission(currentUser, 'kuaiai:agent:read'),
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!open) return;
    if (agent) {
      form.setFieldsValue({
        name: agent.name,
        description: agent.description ?? undefined,
        system_prompt: agent.system_prompt ?? undefined,
        knowledge_ids: agent.knowledge_ids ?? [],
        enabled_tools: agent.enabled_tools ?? [],
        mcp_server_ids: agent.mcp_server_ids ?? [],
        status: agent.status,
        grant_mode: agent.grant_mode || 'ROLE',
      });
    } else {
      form.resetFields();
    }
  }, [open, agent, form]);

  const handleOk = async () => {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      const base = {
        name: values.name,
        description: values.description,
        system_prompt: values.system_prompt,
        knowledge_ids: values.knowledge_ids ?? [],
        enabled_tools: values.enabled_tools ?? [],
        mcp_server_ids: values.mcp_server_ids ?? [],
        status: values.status,
        grant_mode: values.grant_mode,
      };
      if (agent) {
        await updateAgent(agent.id, base);
        message.success(t('app.kuaiai.agents.editSuccess', { defaultValue: '档案已更新' }));
      } else {
        await createAgent(base);
        message.success(
          t('app.kuaiai.agents.createSuccess', { defaultValue: '档案已创建' }),
        );
      }
      onSaved();
    } catch (e: any) {
      message.error(
        e?.message || t('app.kuaiai.agents.saveFailed', { defaultValue: '保存失败' }),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title={
        agent
          ? t('app.kuaiai.agents.editTitle', { defaultValue: '编辑档案' })
          : t('app.kuaiai.agents.createTitle', { defaultValue: '新建档案' })
      }
      width={640}
      confirmLoading={submitting}
      okButtonProps={{ disabled: toolCatalogError }}
      onCancel={onCancel}
      onOk={() => void handleOk()}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        preserve={false}
        initialValues={{
          status: '停用',
          grant_mode: 'ROLE',
          enabled_tools: [],
          knowledge_ids: [],
          mcp_server_ids: [],
        }}
      >
        <Form.Item
          name="name"
          label={t('app.kuaiai.agents.fieldName', { defaultValue: '名称' })}
          rules={[
            {
              required: true,
              message: t('app.kuaiai.agents.nameRequired', {
                defaultValue: '请输入档案名称',
              }),
            },
          ]}
        >
          <Input maxLength={100} />
        </Form.Item>
        <Form.Item
          name="description"
          label={t('app.kuaiai.agents.fieldDescription', { defaultValue: '描述' })}
        >
          <Input.TextArea rows={2} />
        </Form.Item>
        <Form.Item
          name="system_prompt"
          label={t('app.kuaiai.agents.fieldSystemPrompt', { defaultValue: '系统提示词' })}
        >
          <Input.TextArea rows={4} />
        </Form.Item>
        <Form.Item
          name="knowledge_ids"
          label={t('app.kuaiai.agents.fieldKnowledge', { defaultValue: '知识库' })}
        >
          <Select
            mode="multiple"
            allowClear
            showSearch
            optionFilterProp="label"
            options={(knowledgeOptions ?? []).map((o) => ({
              value: o.id,
              label: o.description ? `${o.name}（${o.description}）` : o.name,
            }))}
          />
        </Form.Item>
        <Form.Item
          name="enabled_tools"
          label={t('app.kuaiai.agents.fieldEnabledTools', { defaultValue: '启用工具' })}
        >
          {toolCatalogError ? (
            <Alert
              type="error"
              showIcon
              message={t('app.kuaiai.agents.toolsLoadFailed', {
                defaultValue: '工具目录加载失败，重试成功前不可保存',
              })}
              action={
                <Button size="small" onClick={() => void refetchToolCatalog()}>
                  {t('common.retry', { defaultValue: '重试' })}
                </Button>
              }
            />
          ) : (
            <Checkbox.Group
              options={(toolCatalog ?? []).map((tool) => ({
                value: tool.name,
                label: tool.label || tool.name,
              }))}
            />
          )}
        </Form.Item>
        <Form.Item
          name="mcp_server_ids"
          label={t('app.kuaiai.agents.fieldMcpServers', { defaultValue: 'MCP 服务器' })}
        >
          <Select
            mode="multiple"
            allowClear
            showSearch
            optionFilterProp="label"
            options={(mcpOptions ?? []).map((o) => ({
              value: o.id,
              label: `${o.name}（${o.code}）`,
            }))}
          />
        </Form.Item>
        <Form.Item
          name="grant_mode"
          label={t('app.kuaiai.agents.fieldGrantMode', { defaultValue: '授权模式' })}
          rules={[{ required: true }]}
          extra={t('app.kuaiai.agents.grantModeHint', {
            defaultValue: '按角色（ROLE）或按人员（USER）互斥授权；切换后原授权名单将被清空',
          })}
        >
          <Radio.Group
            options={[
              {
                value: 'ROLE',
                label: t('app.kuaiai.agents.grantModeRole', { defaultValue: '按角色' }),
              },
              {
                value: 'USER',
                label: t('app.kuaiai.agents.grantModeUser', { defaultValue: '按人员' }),
              },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="status"
          label={t('common.status', { defaultValue: '状态' })}
          rules={[{ required: true }]}
          extra={
            agent
              ? undefined
              : t('app.kuaiai.agents.createStatusHint', {
                  defaultValue: '新建档案建议先停用，配置授权名单后再启用',
                })
          }
        >
          <Radio.Group
            options={[
              { value: '启用', label: t('common.enabled', { defaultValue: '启用' }) },
              { value: '停用', label: t('common.disabled', { defaultValue: '停用' }) },
            ]}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
