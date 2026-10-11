/**
 * KU-AI 智能体库（/apps/kuaiai/agent-library，spec 181 T8；设计 §4）。
 *
 * - 数据：GET /apps/kuaiai/operations/agent-library（六预置 + 租户复制项 +
 *   provisioning 状态；缺模板项一律 not_ready 占位，不伪装就绪）；
 * - 「打开并发送」：仅 status=ready 且助手可用时可点，打开既有 KU-Ask 抽屉
 *   并经 pendingAssistant 自动发送示例提问；context 携带
 *   agent_id / extra.agent_key / extra.preset_prompt / extra.capability_mode=query，
 *   由既有抽屉走 /core/ai/chat/completions；后端场景守卫拒绝（403/业务错误）
 *   时错误文案只出现在抽屉内，不降级为无档案对话；
 * - 「查看场景」仅 scene_available=true 时跳转服务端白名单路由；
 * - 管理（kuaiai:library:manage）：改绑/定制 PUT、按模板+源档案克隆 POST；
 *   改绑字段另需 kuaiai:agent:read，克隆另需 agent:read+agent:create；
 *   克隆失败强制刷新列表，避免 UI 与服务端不一致。
 */

import React, { useCallback, useMemo, useState } from 'react';
import {
  Alert,
  App,
  Button,
  Dropdown,
  Form,
  Input,
  Modal,
  Result,
  Select,
  Skeleton,
  Switch,
  Tag,
  Tooltip,
} from 'antd';
import { ReloadOutlined, SettingOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useAiContext } from '../../../../contexts/AiContext';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import { hasPermission } from '../../../../utils/permission';
import { useKuaiaiEntryAvailable } from '../../hooks/useKuaiaiEntryAvailable';
import OperationalPageHeader from '../../components/OperationalPageHeader';
import { openAssistantDrawer } from '../../assistant';
import {
  cloneSceneInstance,
  getAgentLibrary,
  updateSceneInstance,
} from '../../services/operations';
import { listAgents, type AgentProfileOut } from '../../services/agents';
import { getSceneImageUrl, SCENE_IMAGE_KEYS, SCENE_IMAGE_URLS } from '../../assets/scenes';
import type {
  LibraryItemOut,
  SceneCloneOverrides,
  SceneInstanceUpdatePayload,
} from '../../types/operations';
import '../../ops.less';

/** 服务端 capability_tags 白名单，须与
 * riveredge-backend/src/apps/kuaiai/services/agent_scene_service.py
 * SCENE_CAPABILITY_TAGS 保持一致（以后端为准） */
const CAPABILITY_TAG_OPTIONS = [
  'KU-Ask',
  'KU-Pulse',
  'KU-Draft',
  'KU-Act',
  'KU-Suggest',
  'KU-Know',
];

/** 服务端 scene_route 白名单，须与
 * riveredge-backend/src/apps/kuaiai/services/agent_scene_service.py
 * SCENE_ROUTE_PERMISSIONS 保持一致（以后端为准） */
const SCENE_ROUTE_OPTIONS = [
  '/apps/kuaizhizao/warehouse-management/inventory',
  '/apps/kuaizhizao/production-execution/work-orders',
  '/apps/kuaizhizao/purchase-management/purchase-orders',
  '/apps/kuaizhizao/plan-management/rolling-scheduling',
  '/apps/kuaizhizao/production-execution/quality-exceptions',
  '/apps/kuaizhizao/purchase-management/reports/supplier-delivery-summary',
];

const STATUS_TAG: Record<string, { color: string; key: string; fallback: string }> = {
  ready: { color: 'success', key: 'app.kuaiai.catalog.status.ready', fallback: '已就绪' },
  partial: { color: 'warning', key: 'app.kuaiai.catalog.status.degraded', fallback: '降级可用' },
  not_ready: { color: 'default', key: 'app.kuaiai.catalog.status.blocked', fallback: '不可用' },
};

interface EditFormValues {
  name?: string;
  description?: string;
  image_key?: string;
  sample_prompt?: string;
  capability_tags?: string[];
  scene_route?: string;
  enabled?: boolean;
  agent_profile_id?: number | null;
}

interface CloneFormValues {
  source_agent_id: number;
  name?: string;
  description?: string;
  image_key?: string;
  sample_prompt?: string;
  capability_tags?: string[];
  scene_route?: string;
}

const AgentLibraryPage: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const currentUser = useCurrentUser();
  const { setPendingAssistant, setContext } = useAiContext();
  const kuaiaiEntryAvailable = useKuaiaiEntryAvailable();

  const canManage = hasPermission(currentUser, 'kuaiai:library:manage');
  // 「打开并发送」经抽屉打 canonical /core/ai/chat/completions，发送另需 kuaiai:act:execute
  const canSendChat = hasPermission(currentUser, 'kuaiai:act:execute');
  const canAgentRead = hasPermission(currentUser, 'kuaiai:agent:read');
  const canAgentCreate = hasPermission(currentUser, 'kuaiai:agent:create');
  const canClone = canManage && canAgentRead && canAgentCreate;
  const canRebind = canManage && canAgentRead;

  const [sendingKey, setSendingKey] = useState<string | null>(null);
  const [editItem, setEditItem] = useState<LibraryItemOut | null>(null);
  const [cloneItem, setCloneItem] = useState<LibraryItemOut | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [editForm] = Form.useForm<EditFormValues>();
  const [cloneForm] = Form.useForm<CloneFormValues>();

  const { data, isPending, isFetching, error, refetch } = useQuery({
    queryKey: ['kuaiai', 'operations', 'agent-library'],
    queryFn: () => getAgentLibrary(),
    staleTime: 30_000,
  });

  const { data: agentProfiles } = useQuery({
    queryKey: ['kuaiai', 'agent-profiles', 'library-picker'],
    queryFn: () => listAgents(1, 200),
    enabled: canAgentRead && (editItem != null || cloneItem != null),
    staleTime: 30_000,
  });

  const errorStatus = (error as any)?.response?.status as number | undefined;

  const profileOptions = useMemo(
    () =>
      (agentProfiles ?? []).map((p: AgentProfileOut) => ({
        value: p.id,
        label: p.name,
      })),
    [agentProfiles],
  );

  const refresh = useCallback(() => void refetch(), [refetch]);

  /** 「打开并发送」：打开既有抽屉 + pendingAssistant 自动发送（见 ai-assistant pendingAssistant 流程） */
  const handleOpenAndSend = useCallback(
    (item: LibraryItemOut) => {
      if (item.status !== 'ready' || !kuaiaiEntryAvailable || !item.agent_profile_id || !canSendChat) {
        return;
      }
      const prompt = (item.sample_prompt || '').trim();
      if (!prompt) return;
      setSendingKey(item.key);
      setContext({
        screen: '/apps/kuaiai/agent-library',
        screenLabel: t('app.kuaiai.library.title', { defaultValue: '智能体库' }),
      });
      setPendingAssistant({
        prompt,
        context: {
          screen: '/apps/kuaiai/agent-library',
          screenLabel: t('app.kuaiai.library.title', { defaultValue: '智能体库' }),
          agentId: String(item.agent_profile_id),
          agentKey: item.key,
          presetPrompt: prompt,
          capabilityMode: 'query',
        },
      });
      openAssistantDrawer();
      // 防连点：抽屉消费 pendingAssistant 后恢复
      window.setTimeout(() => setSendingKey(null), 1500);
    },
    [kuaiaiEntryAvailable, canSendChat, setContext, setPendingAssistant, t],
  );

  const handleViewScene = useCallback(
    (item: LibraryItemOut) => {
      if (!item.scene_available || !item.scene_route) return;
      navigate(item.scene_route);
    },
    [navigate],
  );

  /** provisioning 重试：有 manage 权限时对缺失模板发空 PUT 触发服务端幂等补齐 */
  const handleProvisionRetry = useCallback(async () => {
    const missing = data?.provisioning?.missing_template_keys ?? [];
    try {
      if (canManage && missing.length > 0) {
        await updateSceneInstance(missing[0], {});
      }
    } catch (e: any) {
      message.error(
        e?.message ||
          t('app.kuaiai.library.provisionRetryFailed', { defaultValue: '补齐预置失败' }),
      );
    } finally {
      refresh();
    }
  }, [canManage, data?.provisioning?.missing_template_keys, message, refresh, t]);

  const openEdit = useCallback(
    (item: LibraryItemOut) => {
      setEditItem(item);
      editForm.setFieldsValue({
        name: item.name,
        description: item.description ?? undefined,
        image_key: item.image_key ?? undefined,
        sample_prompt: item.sample_prompt ?? undefined,
        capability_tags: item.capability_tags,
        scene_route: item.scene_route ?? undefined,
        enabled: item.enabled,
        agent_profile_id: item.agent_profile_id ?? null,
      });
    },
    [editForm],
  );

  const openClone = useCallback(
    (item: LibraryItemOut) => {
      setCloneItem(item);
      cloneForm.resetFields();
      cloneForm.setFieldsValue({
        name: item.name,
        description: item.description ?? undefined,
        image_key: item.image_key ?? undefined,
        sample_prompt: item.sample_prompt ?? undefined,
        capability_tags: item.capability_tags,
        scene_route: item.scene_route ?? undefined,
      });
    },
    [cloneForm],
  );

  const submitEdit = useCallback(async () => {
    if (!editItem) return;
    const values = await editForm.validateFields();
    const payload: SceneInstanceUpdatePayload = {};
    if (values.name !== undefined) payload.name = values.name?.trim() || null;
    if (values.description !== undefined)
      payload.description = values.description?.trim() || null;
    if (values.image_key !== undefined) payload.image_key = values.image_key || null;
    if (values.sample_prompt !== undefined)
      payload.sample_prompt = values.sample_prompt?.trim() || null;
    if (values.capability_tags !== undefined)
      payload.capability_tags = values.capability_tags ?? null;
    if (values.scene_route !== undefined) payload.scene_route = values.scene_route || null;
    if (values.enabled !== undefined) payload.enabled = values.enabled;
    // 改绑仅在用户具备 agent:read 且实际触碰该字段时提交：
    // 无读权限用户拿到的 agent_profile_id 为脱敏 null，误传 null 会解绑档案
    if (canRebind && editForm.isFieldTouched('agent_profile_id')) {
      payload.agent_profile_id = values.agent_profile_id ?? null;
    }
    setSubmitting(true);
    try {
      await updateSceneInstance(editItem.key, payload);
      message.success(
        t('app.kuaiai.library.editSaved', { defaultValue: '场景已更新' }),
      );
      setEditItem(null);
      refresh();
    } catch (e: any) {
      message.error(
        e?.message ||
          t('app.kuaiai.library.editFailed', { defaultValue: '场景更新失败' }),
      );
    } finally {
      setSubmitting(false);
    }
  }, [canRebind, editForm, editItem, message, refresh, t]);

  const submitClone = useCallback(async () => {
    if (!cloneItem) return;
    const values = await cloneForm.validateFields();
    const overrides: SceneCloneOverrides = {};
    if (values.name?.trim()) overrides.name = values.name.trim();
    if (values.description?.trim()) overrides.description = values.description.trim();
    if (values.image_key) overrides.image_key = values.image_key;
    if (values.sample_prompt?.trim()) overrides.sample_prompt = values.sample_prompt.trim();
    if (values.capability_tags?.length) overrides.capability_tags = values.capability_tags;
    if (values.scene_route) overrides.scene_route = values.scene_route;
    setSubmitting(true);
    try {
      await cloneSceneInstance({
        template_key: cloneItem.template_key,
        source_agent_id: values.source_agent_id,
        overrides: Object.keys(overrides).length ? overrides : undefined,
      });
      message.success(
        t('app.kuaiai.library.cloneCreated', { defaultValue: '已创建场景副本' }),
      );
      setCloneItem(null);
      refresh();
    } catch (e: any) {
      message.error(
        e?.message ||
          t('app.kuaiai.library.cloneFailed', { defaultValue: '克隆失败' }),
      );
      // 克隆失败必须刷新：服务端可能已部分提交或状态已变化，避免 UI 不一致
      refresh();
    } finally {
      setSubmitting(false);
    }
  }, [cloneForm, cloneItem, message, refresh, t]);

  const renderStatusTag = (item: LibraryItemOut) => {
    const conf = STATUS_TAG[item.status] ?? STATUS_TAG.not_ready;
    return <Tag color={conf.color}>{t(conf.key, { defaultValue: conf.fallback })}</Tag>;
  };

  const renderCard = (item: LibraryItemOut) => {
    const sendDisabled =
      !canSendChat ||
      item.status !== 'ready' ||
      !kuaiaiEntryAvailable ||
      !item.agent_profile_id ||
      sendingKey === item.key;
    const sendReason = !canSendChat
      ? t('app.kuaiai.chat.noSendPermission', {
          defaultValue: '当前账号无对话发送权限（kuaiai:act:execute）',
        })
      : !kuaiaiEntryAvailable
        ? t('app.kuaiai.ops.noAssistant', { defaultValue: 'AI 助手当前不可用' })
        : item.status !== 'ready' || !item.agent_profile_id
          ? item.disabled_reason ||
            t('app.kuaiai.ops.notReady', { defaultValue: '暂未就绪' })
          : null;

    const sceneDisabled = !item.scene_available || !item.scene_route;
    const sceneReason = sceneDisabled
      ? t('app.kuaiai.library.sceneUnavailable', {
          defaultValue: '场景路由不可用或无页面权限',
        })
      : null;

    const manageItems = [
      {
        key: 'edit',
        label: t('app.kuaiai.library.manageEdit', { defaultValue: '编辑场景实例' }),
      },
      {
        key: 'clone',
        label: t('app.kuaiai.library.manageClone', { defaultValue: '复制场景副本' }),
        disabled: !canClone,
      },
    ];

    const sendButton = (
      <Button
        type="primary"
        disabled={sendDisabled}
        loading={sendingKey === item.key}
        onClick={() => handleOpenAndSend(item)}
        aria-label={t('app.kuaiai.library.openAndSendAria', {
          defaultValue: '打开助手并发送示例提问：{{name}}',
          name: item.name,
        })}
      >
        {t('app.kuaiai.library.openAndSend', { defaultValue: '打开并发送' })}
      </Button>
    );
    const sceneButton = (
      <Button
        disabled={sceneDisabled}
        onClick={() => handleViewScene(item)}
        aria-label={t('app.kuaiai.library.viewSceneAria', {
          defaultValue: '查看场景：{{name}}',
          name: item.name,
        })}
      >
        {t('app.kuaiai.agents.viewScene', { defaultValue: '查看场景' })}
      </Button>
    );

    return (
      <div className="kuaiai-ops-agent-card" key={item.key}>
        {canManage ? (
          <Tooltip title={t('app.kuaiai.library.manage', { defaultValue: '管理' })}>
            <Dropdown
              trigger={['click']}
              menu={{
                items: manageItems,
                onClick: ({ key }) => {
                  if (key === 'edit') openEdit(item);
                  if (key === 'clone') openClone(item);
                },
              }}
            >
              <Button
                type="text"
                size="small"
                className="kuaiai-ops-agent-manage"
                icon={<SettingOutlined />}
                aria-label={t('app.kuaiai.library.manageAria', {
                  defaultValue: '管理场景实例：{{name}}',
                  name: item.name,
                })}
              />
            </Dropdown>
          </Tooltip>
        ) : null}
        <img
          className="kuaiai-ops-agent-illustration"
          src={getSceneImageUrl(item.image_key)}
          alt={item.name}
        />
        <div className="kuaiai-ops-agent-body">
          <div className="kuaiai-ops-agent-head">
            <span className="kuaiai-ops-agent-name">{item.name}</span>
            {renderStatusTag(item)}
          </div>
          <div className="kuaiai-ops-agent-desc">{item.description || '—'}</div>
          {item.capability_tags.length ? (
            <div className="kuaiai-ops-agent-tags">
              {item.capability_tags.map((tag) => (
                <Tag key={tag}>{tag}</Tag>
              ))}
            </div>
          ) : null}
          {item.sample_prompt ? (
            <div className="kuaiai-ops-agent-sample">
              {t('app.kuaiai.agents.samplePrompt', { defaultValue: '示例提问' })}
              ：{item.sample_prompt}
            </div>
          ) : null}
          {item.status !== 'ready' && item.disabled_reason ? (
            <div className="kuaiai-ops-agent-sample">{item.disabled_reason}</div>
          ) : null}
          <div className="kuaiai-ops-agent-actions">
            {sendReason ? <Tooltip title={sendReason}>{sendButton}</Tooltip> : sendButton}
            {sceneReason ? <Tooltip title={sceneReason}>{sceneButton}</Tooltip> : sceneButton}
          </div>
        </div>
      </div>
    );
  };

  const header = (
    <OperationalPageHeader
      title={t('app.kuaiai.library.title', { defaultValue: '智能体库' })}
      subtitle={t('app.kuaiai.agents.subtitle', {
        defaultValue: '预置制造场景智能体，一键对话或跳转业务页',
      })}
      extra={
        <Button
          icon={<ReloadOutlined />}
          loading={isFetching}
          onClick={refresh}
          aria-label={t('common.refresh', { defaultValue: '刷新' })}
        >
          {t('common.refresh', { defaultValue: '刷新' })}
        </Button>
      }
    />
  );

  if (isPending && !data) {
    return (
      <div className="kuaiai-ops-page">
        <div className="kuaiai-ops-inner">
          {header}
          <div className="kuaiai-ops-library-grid">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div className="kuaiai-ops-agent-card" key={i}>
                <Skeleton.Image active style={{ width: 140, height: 210 }} />
                <div style={{ flex: 1 }}>
                  <Skeleton active paragraph={{ rows: 4 }} title={{ width: '45%' }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error && !data) {
    const is403 = errorStatus === 403;
    return (
      <div className="kuaiai-ops-page">
        <div className="kuaiai-ops-inner">
          {header}
          <Result
            status={is403 ? '403' : 'error'}
            title={
              is403
                ? t('app.kuaiai.ops.forbidden', { defaultValue: '缺少功能权限' })
                : t('app.kuaiai.library.loadFailed', { defaultValue: '加载智能体库失败' })
            }
            subTitle={
              is403
                ? t('app.kuaiai.ops.forbiddenHint', {
                    defaultValue: '当前账号缺少智能体库页面权限，请联系管理员授权',
                  })
                : (error as Error)?.message
            }
            extra={
              !is403 ? (
                <Button type="primary" onClick={refresh}>
                  {t('common.retry', { defaultValue: '重试' })}
                </Button>
              ) : undefined
            }
          />
        </div>
      </div>
    );
  }

  const items = data?.items ?? [];
  const provisioning = data?.provisioning;

  return (
    <div className="kuaiai-ops-page">
      <div className="kuaiai-ops-inner">
        {header}

        {error && data ? (
          <Alert
            style={{ marginTop: 12 }}
            type="warning"
            showIcon
            message={t('app.kuaiai.ops.partialFailed', {
              defaultValue: '部分数据刷新失败，已保留上次结果',
            })}
            action={
              <Button size="small" onClick={refresh}>
                {t('common.retry', { defaultValue: '重试' })}
              </Button>
            }
          />
        ) : null}

        {provisioning && !provisioning.complete ? (
          <Alert
            style={{ marginTop: 12 }}
            type="warning"
            showIcon
            message={t('app.kuaiai.library.provisioningIncomplete', {
              defaultValue: '场景预置未完成，部分智能体暂不可用',
            })}
            description={
              canManage
                ? t('app.kuaiai.library.provisioningHintManage', {
                    defaultValue: '可重试补齐缺失的预置场景实例',
                  })
                : t('app.kuaiai.library.provisioningHintView', {
                    defaultValue: '请联系管理员重新同步应用后再试',
                  })
            }
            action={
              canManage && provisioning.retryable ? (
                <Button size="small" onClick={() => void handleProvisionRetry()}>
                  {t('common.retry', { defaultValue: '重试' })}
                </Button>
              ) : undefined
            }
          />
        ) : null}

        {items.length === 0 ? (
          <Result
            status="info"
            title={t('app.kuaiai.library.empty', {
              defaultValue: '暂无可展示的智能体场景',
            })}
            subTitle={
              canManage
                ? t('app.kuaiai.library.emptyHintManage', {
                    defaultValue: '请重新同步应用完成场景预置',
                  })
                : undefined
            }
            extra={
              canManage ? (
                <Button onClick={() => void handleProvisionRetry()}>
                  {t('common.retry', { defaultValue: '重试' })}
                </Button>
              ) : undefined
            }
          />
        ) : (
          <div className="kuaiai-ops-library-grid">{items.map(renderCard)}</div>
        )}

        {/* 编辑/改绑实例 */}
        <Modal
          title={t('app.kuaiai.library.editModalTitle', { defaultValue: '编辑场景实例' })}
          open={editItem != null}
          onCancel={() => setEditItem(null)}
          onOk={() => void submitEdit()}
          confirmLoading={submitting}
          destroyOnHidden
          width={560}
        >
          <Form form={editForm} layout="vertical" preserve={false}>
            <Form.Item
              name="name"
              label={t('app.kuaiai.library.field.name', { defaultValue: '名称' })}
              rules={[
                { required: true, message: t('common.required', { defaultValue: '必填' }) },
                { max: 100 },
              ]}
            >
              <Input maxLength={100} />
            </Form.Item>
            <Form.Item
              name="description"
              label={t('app.kuaiai.library.field.description', { defaultValue: '描述' })}
            >
              <Input.TextArea rows={2} maxLength={2000} />
            </Form.Item>
            <Form.Item
              name="image_key"
              label={t('app.kuaiai.library.field.image', { defaultValue: '插画' })}
            >
              <Select
                allowClear
                placeholder={t('app.kuaiai.library.field.imagePlaceholder', {
                  defaultValue: '默认按模板插画',
                })}
                options={SCENE_IMAGE_KEYS.map((key) => ({
                  value: key,
                  label: (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                      <img
                        src={SCENE_IMAGE_URLS[key]}
                        alt=""
                        aria-hidden="true"
                        style={{ width: 20, height: 30, borderRadius: 3 }}
                      />
                      {key}
                    </span>
                  ),
                }))}
              />
            </Form.Item>
            <Form.Item
              name="sample_prompt"
              label={t('app.kuaiai.agents.samplePrompt', { defaultValue: '示例提问' })}
              rules={[{ max: 500 }]}
            >
              <Input.TextArea rows={2} maxLength={500} />
            </Form.Item>
            <Form.Item
              name="capability_tags"
              label={t('app.kuaiai.library.field.tags', { defaultValue: '能力标签' })}
            >
              <Select
                mode="multiple"
                allowClear
                options={CAPABILITY_TAG_OPTIONS.map((v) => ({ value: v, label: v }))}
              />
            </Form.Item>
            <Form.Item
              name="scene_route"
              label={t('app.kuaiai.library.field.sceneRoute', { defaultValue: '场景路由' })}
            >
              <Select
                allowClear
                options={SCENE_ROUTE_OPTIONS.map((v) => ({ value: v, label: v }))}
              />
            </Form.Item>
            <Form.Item
              name="agent_profile_id"
              label={t('app.kuaiai.library.field.bindProfile', {
                defaultValue: '绑定 Agent 档案',
              })}
              tooltip={
                canRebind
                  ? undefined
                  : t('app.kuaiai.library.bindNoPermission', {
                      defaultValue: '需要 Agent 档案读权限',
                    })
              }
            >
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                disabled={!canRebind}
                placeholder={t('app.kuaiai.library.bindPlaceholder', {
                  defaultValue: '选择本租户 Agent 档案，清空即解绑',
                })}
                options={profileOptions}
              />
            </Form.Item>
            <Form.Item
              name="enabled"
              label={t('app.kuaiai.library.field.enabled', { defaultValue: '启用' })}
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>
          </Form>
        </Modal>

        {/* 克隆场景副本 */}
        <Modal
          title={t('app.kuaiai.library.cloneModalTitle', {
            defaultValue: '复制场景副本',
          })}
          open={cloneItem != null}
          onCancel={() => setCloneItem(null)}
          onOk={() => void submitClone()}
          confirmLoading={submitting}
          destroyOnHidden
          width={560}
        >
          <Alert
            style={{ marginBottom: 12 }}
            type="info"
            showIcon
            message={t('app.kuaiai.library.cloneHint', {
              defaultValue:
                '将从所选本租户 Agent 档案克隆出停用副本档案，并创建一个新的场景实例',
            })}
          />
          <Form form={cloneForm} layout="vertical" preserve={false}>
            <Form.Item
              name="source_agent_id"
              label={t('app.kuaiai.library.field.sourceProfile', {
                defaultValue: '源 Agent 档案',
              })}
              rules={[
                { required: true, message: t('common.required', { defaultValue: '必填' }) },
              ]}
            >
              <Select
                showSearch
                optionFilterProp="label"
                placeholder={t('app.kuaiai.library.sourcePlaceholder', {
                  defaultValue: '选择要克隆的本租户 Agent 档案',
                })}
                options={profileOptions}
              />
            </Form.Item>
            <Form.Item
              name="name"
              label={t('app.kuaiai.library.field.name', { defaultValue: '名称' })}
              rules={[{ max: 100 }]}
            >
              <Input maxLength={100} />
            </Form.Item>
            <Form.Item
              name="description"
              label={t('app.kuaiai.library.field.description', { defaultValue: '描述' })}
            >
              <Input.TextArea rows={2} maxLength={2000} />
            </Form.Item>
            <Form.Item
              name="image_key"
              label={t('app.kuaiai.library.field.image', { defaultValue: '插画' })}
            >
              <Select
                allowClear
                options={SCENE_IMAGE_KEYS.map((key) => ({ value: key, label: key }))}
              />
            </Form.Item>
            <Form.Item
              name="sample_prompt"
              label={t('app.kuaiai.agents.samplePrompt', { defaultValue: '示例提问' })}
              rules={[{ max: 500 }]}
            >
              <Input.TextArea rows={2} maxLength={500} />
            </Form.Item>
            <Form.Item
              name="capability_tags"
              label={t('app.kuaiai.library.field.tags', { defaultValue: '能力标签' })}
            >
              <Select
                mode="multiple"
                allowClear
                options={CAPABILITY_TAG_OPTIONS.map((v) => ({ value: v, label: v }))}
              />
            </Form.Item>
            <Form.Item
              name="scene_route"
              label={t('app.kuaiai.library.field.sceneRoute', { defaultValue: '场景路由' })}
            >
              <Select
                allowClear
                options={SCENE_ROUTE_OPTIONS.map((v) => ({ value: v, label: v }))}
              />
            </Form.Item>
          </Form>
        </Modal>
      </div>
    </div>
  );
};

export default AgentLibraryPage;
