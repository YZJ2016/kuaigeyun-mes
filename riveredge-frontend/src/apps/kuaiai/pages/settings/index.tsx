/**
 * KU-Settings 模型与能力设置聚合页（/apps/kuaiai/settings，spec 185 T5；设计 §10）。
 *
 * - 数据：GET /apps/kuaiai/operations/settings（chat/vision 候选、OCR 脱敏、
 *   六模板总开关、能力项、不透明 version）；保存 PUT 携带 version，
 *   409 → 明确冲突提示，不覆盖他人更新；
 * - 四区块：对话模型（必填连接 Select + 打开应用连接器）、OCR 视觉识别
 *   （vision Select + Base URL/OCR 模型/API Key 三列只读脱敏，不产生第二份
 *   Key）、智能体开关（3×2 六模板总开关）、KU-AI 能力配置（三项开关 +
 *   RAG 条数 1..20 + 引擎固定原生 + 企业系统说明）；
 * - 页头右对齐：重置（恢复最近服务端快照，不写库）/ 保存（primary，
 *   pending 禁用）/ 刷新（dirty 时二次确认后重新加载）；
 * - OCR/密钥在应用连接器维护：本页任何密钥字段都不进表单、不提交。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  App,
  Button,
  Form,
  Input,
  InputNumber,
  Result,
  Select,
  Skeleton,
  Switch,
  Tooltip,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import { hasPermission } from '../../../../utils/permission';
import OperationalPageHeader from '../../components/OperationalPageHeader';
import {
  getOperationsSettings,
  updateOperationsSettings,
} from '../../services/operations';
import type {
  SettingsOptionOut,
  SettingsOut,
  SettingsUpdatePayload,
} from '../../types/operations';
import '../../ops.less';

/** 服务端六出厂模板 key（agent_scene_service.SCENE_TEMPLATES，顺序稳定） */
const AGENT_TEMPLATE_KEYS = [
  'inventory-insight',
  'planner-advisor',
  'purchase-followup',
  'schedule-explainer',
  'quality-analysis',
  'supplier-collaboration',
] as const;

/** 模板名中文兜底（后端 SCENE_TEMPLATES.name） */
const AGENT_NAME_FALLBACK: Record<string, string> = {
  'inventory-insight': '库存洞察助手',
  'planner-advisor': '计划员顾问',
  'purchase-followup': '采购跟单助手',
  'schedule-explainer': '排程解读助手',
  'quality-analysis': '质量异常分析',
  'supplier-collaboration': '供应商协同 Agent',
};

interface SettingsFormValues {
  chat_connection_uuid?: string;
  vision_connection_uuid?: string | null;
  agent_switches?: Record<string, boolean>;
  capabilities?: {
    tools_enabled?: boolean;
    rag_enabled?: boolean;
    rag_use_embedding?: boolean;
    rag_backend?: string;
    rag_top_k?: number;
    stream_enabled?: boolean;
    custom_system_prompt?: string;
  };
}

const CONNECTORS_ROUTE = '/system/application-connections';

function optionLabel(option: SettingsOptionOut): string {
  const parts = [option.name, option.provider, option.model].filter(Boolean);
  return parts.join(' · ');
}

function toFormValues(data: SettingsOut): SettingsFormValues {
  const switches: Record<string, boolean> = {};
  for (const key of AGENT_TEMPLATE_KEYS) {
    switches[key] = data.agent_switches?.[key] !== false;
  }
  return {
    chat_connection_uuid: data.chat_connection_uuid ?? undefined,
    vision_connection_uuid: data.vision_connection_uuid ?? null,
    agent_switches: switches,
    capabilities: { ...data.capabilities },
  };
}

const SettingsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const [form] = Form.useForm<SettingsFormValues>();
  const currentUser = useCurrentUser();
  const canUpdate = hasPermission(currentUser, 'kuaiai:settings:update');

  const { data, isPending, isFetching, error, refetch } = useQuery({
    queryKey: ['kuaiai', 'operations', 'settings'],
    queryFn: () => getOperationsSettings(),
    staleTime: 30_000,
  });

  const snapshotRef = useRef<SettingsFormValues | null>(null);
  const versionRef = useRef<string>('');
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  // 表单有未保存修改期间收到了新的服务端快照（窗口聚焦/重连等后台 refetch）：
  // 不自动套用（否则吞掉未保存修改、versionRef 前进使保存时本该命中的 409 丢失），
  // 只出示非阻塞提示，由用户选择「放弃修改并重载」或手动刷新。
  const [serverChanged, setServerChanged] = useState(false);
  const dirtyRef = useRef(false);
  useEffect(() => {
    dirtyRef.current = dirty;
  }, [dirty]);

  const applySnapshot = useCallback(
    (snapshot: SettingsOut) => {
      const values = toFormValues(snapshot);
      snapshotRef.current = values;
      versionRef.current = snapshot.version;
      form.setFieldsValue(values);
      setDirty(false);
      setServerChanged(false);
    },
    [form],
  );

  useEffect(() => {
    if (!data) return;
    if (dirtyRef.current) {
      setServerChanged(true);
      return;
    }
    applySnapshot(data);
  }, [data, applySnapshot]);

  const errorStatus = (error as any)?.response?.status as number | undefined;

  const visionUuid = Form.useWatch('vision_connection_uuid', form);

  const chatOptions = useMemo(() => {
    const items = (data?.chat_options ?? []).map((o) => ({
      value: o.uuid,
      label: optionLabel(o),
    }));
    // 已选用但当前不在候选（如已停用）：保留占位项便于识别与重新选择
    if (
      data?.chat_connection_uuid &&
      !items.some((o) => o.value === data.chat_connection_uuid)
    ) {
      items.push({
        value: data.chat_connection_uuid,
        label: `${data.chat_connection_uuid}（${t('app.kuaiai.settings.optionUnavailable', { defaultValue: '不可用' })}）`,
      });
    }
    return items;
  }, [data?.chat_options, data?.chat_connection_uuid, t]);

  const visionOptions = useMemo(() => {
    const items = (data?.vision_options ?? []).map((o) => ({
      value: o.uuid,
      label: optionLabel(o),
    }));
    if (
      data?.vision_connection_uuid &&
      !items.some((o) => o.value === data.vision_connection_uuid)
    ) {
      items.push({
        value: data.vision_connection_uuid,
        label: `${data.vision_connection_uuid}（${t('app.kuaiai.settings.optionUnavailable', { defaultValue: '不可用' })}）`,
      });
    }
    return items;
  }, [data?.vision_options, data?.vision_connection_uuid, t]);

  /** OCR 三列只读展示：选中项 = 已保存选用时显示后端脱敏信息，换选后显示该候选模型 */
  const ocrDisplay = useMemo(() => {
    const selected = data?.vision_options.find((o) => o.uuid === visionUuid);
    const isSavedSelection =
      !!visionUuid && visionUuid === data?.vision_connection_uuid;
    return {
      baseUrl: isSavedSelection ? data?.ocr?.base_url_masked || '—' : selected ? '—' : '—',
      model: isSavedSelection
        ? data?.ocr?.model || '—'
        : selected?.model || '—',
    };
  }, [data, visionUuid]);

  const handleValuesChange = useCallback(() => {
    const current = form.getFieldsValue(true);
    setDirty(
      JSON.stringify(current) !== JSON.stringify(snapshotRef.current ?? {}),
    );
  }, [form]);

  const handleReset = useCallback(() => {
    if (!snapshotRef.current) return;
    form.resetFields();
    form.setFieldsValue(snapshotRef.current);
    setDirty(false);
  }, [form]);

  const doRefetch = useCallback(() => void refetch(), [refetch]);

  /** 放弃本地修改并套用最新服务端快照（dirty 守卫下后台快照只挂起，不自动套用） */
  const handleDiscardAndReload = useCallback(() => {
    if (data) applySnapshot(data);
  }, [data, applySnapshot]);

  const handleRefresh = useCallback(() => {
    if (!dirty) {
      doRefetch();
      return;
    }
    modal.confirm({
      title: t('app.kuaiai.settings.refreshConfirmTitle', {
        defaultValue: '放弃未保存修改？',
      }),
      content: t('app.kuaiai.settings.refreshConfirmContent', {
        defaultValue: '刷新将丢弃当前未保存的修改并重新加载最新配置。',
      }),
      okText: t('common.confirm', { defaultValue: '确定' }),
      cancelText: t('common.cancel', { defaultValue: '取消' }),
      // 先回到服务端快照（丢弃修改），新数据到达时即可干净套用
      onOk: () => {
        handleReset();
        doRefetch();
      },
    });
  }, [dirty, doRefetch, handleReset, modal, t]);

  const handleSave = useCallback(async () => {
    let values: SettingsFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return; // 校验失败由 Form 标注，不弹 toast
    }
    const caps = values.capabilities ?? {};
    const payload: SettingsUpdatePayload = {
      version: versionRef.current,
      chat_connection_uuid: values.chat_connection_uuid as string,
      vision_connection_uuid: values.vision_connection_uuid || null,
      agent_switches: Object.fromEntries(
        AGENT_TEMPLATE_KEYS.map((key) => [
          key,
          values.agent_switches?.[key] !== false,
        ]),
      ),
      capabilities: {
        tools_enabled: caps.tools_enabled !== false,
        rag_enabled: caps.rag_enabled !== false,
        rag_use_embedding: caps.rag_use_embedding !== false,
        rag_backend: 'native',
        rag_top_k: caps.rag_top_k ?? 5,
        stream_enabled: caps.stream_enabled !== false,
        custom_system_prompt: caps.custom_system_prompt ?? '',
      },
    };
    setSaving(true);
    try {
      const saved = await updateOperationsSettings(payload);
      message.success(
        t('app.kuaiai.settings.saveSuccess', { defaultValue: '设置已保存' }),
      );
      applySnapshot(saved);
    } catch (e: any) {
      const status = e?.response?.status;
      if (status === 409) {
        message.error(
          t('app.kuaiai.settings.saveConflict', {
            defaultValue: '设置已被他人修改，请刷新后重试',
          }),
        );
      } else {
        message.error(
          e?.message ||
            t('app.kuaiai.settings.saveFailed', { defaultValue: '保存失败' }),
        );
      }
    } finally {
      setSaving(false);
    }
  }, [applySnapshot, form, message, t]);

  const header = (
    <OperationalPageHeader
      title={t('app.kuaiai.settings.title', { defaultValue: '模型设置' })}
      subtitle={t('app.kuaiai.settings.subtitle', {
        defaultValue: '选用对话模型连接，并配置 KU-AI 能力与 OCR 视觉端点',
      })}
      extra={
        <>
          <Button
            style={{ minWidth: 82 }}
            disabled={saving || isPending}
            onClick={handleReset}
            aria-label={t('common.reset', { defaultValue: '重置' })}
          >
            {t('common.reset', { defaultValue: '重置' })}
          </Button>
          <Tooltip
            title={
              canUpdate
                ? undefined
                : t('app.kuaiai.settings.noUpdatePerm', {
                    defaultValue: '缺少设置修改权限',
                  })
            }
          >
            <Button
              type="primary"
              style={{ minWidth: 82 }}
              loading={saving}
              disabled={isPending || !!error || !canUpdate}
              onClick={() => void handleSave()}
              aria-label={t('common.save', { defaultValue: '保存' })}
            >
              {t('common.save', { defaultValue: '保存' })}
            </Button>
          </Tooltip>
          <Button
            style={{ minWidth: 82 }}
            icon={<ReloadOutlined />}
            loading={isFetching}
            disabled={saving}
            onClick={handleRefresh}
            aria-label={t('common.refresh', { defaultValue: '刷新' })}
          >
            {t('common.refresh', { defaultValue: '刷新' })}
          </Button>
        </>
      }
    />
  );

  if (isPending && !data) {
    return (
      <div className="kuaiai-ops-page">
        <div className="kuaiai-ops-inner">
          {header}
          <div className="kuaiai-ops-settings-form">
            {[0, 1, 2, 3].map((i) => (
              <div className="kuaiai-ops-settings-block" key={i}>
                <Skeleton active paragraph={{ rows: 3 }} title={{ width: '30%' }} />
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
                : t('app.kuaiai.settings.loadFailed', {
                    defaultValue: '加载设置失败',
                  })
            }
            subTitle={
              is403
                ? t('app.kuaiai.ops.forbiddenHint', {
                    defaultValue:
                      '当前账号缺少模型设置页面权限，请联系管理员授权',
                  })
                : (error as Error)?.message
            }
            extra={
              !is403 ? (
                <Button type="primary" onClick={doRefetch}>
                  {t('common.retry', { defaultValue: '重试' })}
                </Button>
              ) : undefined
            }
          />
        </div>
      </div>
    );
  }

  return (
    <div className="kuaiai-ops-page">
      <div className="kuaiai-ops-inner">
        {header}
        {serverChanged && dirty ? (
          <Alert
            style={{ marginBottom: 12 }}
            type="info"
            showIcon
            message={t('app.kuaiai.settings.serverChanged', {
              defaultValue: '服务端配置已更新',
            })}
            action={
              <Button size="small" onClick={handleDiscardAndReload}>
                {t('app.kuaiai.settings.discardAndReload', {
                  defaultValue: '放弃修改并重载',
                })}
              </Button>
            }
          />
        ) : null}
        <Form
          form={form}
          layout="vertical"
          className="kuaiai-ops-settings-form"
          onValuesChange={handleValuesChange}
          disabled={saving}
        >
          {/* 1. 对话模型 */}
          <div className="kuaiai-ops-settings-block">
            <div className="kuaiai-ops-settings-block-title">
              {t('app.kuaiai.settings.providerCardTitle', {
                defaultValue: '对话模型',
              })}
            </div>
            <div className="kuaiai-ops-settings-block-desc">
              {t('app.kuaiai.settings.providerCardHint', {
                defaultValue:
                  '请先在应用连接器中新建 AI 连接（同一提供商可建多条不同模型），再在此选用当前对话使用的连接。',
              })}
              <Button
                type="link"
                style={{ padding: 0, height: 'auto', marginLeft: 8 }}
                onClick={() => navigate(CONNECTORS_ROUTE)}
              >
                {t('app.kuaiai.settings.openConnectors', {
                  defaultValue: '打开应用连接器',
                })}
              </Button>
            </div>
            <Form.Item
              name="chat_connection_uuid"
              label={t('app.kuaiai.settings.activeProvider', {
                defaultValue: '当前 AI 连接',
              })}
              rules={[
                {
                  required: true,
                  message: t('app.kuaiai.settings.activeConnectionRequired', {
                    defaultValue: '请选择一条 AI 连接',
                  }),
                },
              ]}
              style={{ marginBottom: 0 }}
            >
              <Select
                options={chatOptions}
                placeholder={t('app.kuaiai.settings.activeConnectionPlaceholder', {
                  defaultValue: '选择应用连接器中的 AI 连接',
                })}
                notFoundContent={t('app.kuaiai.settings.activeConnectionEmpty', {
                  defaultValue: '暂无 AI 连接，请先到应用连接器新建',
                })}
                showSearch
                optionFilterProp="label"
              />
            </Form.Item>
          </div>

          {/* 2. OCR 视觉识别：只读脱敏展示，密钥由应用连接器维护 */}
          <div className="kuaiai-ops-settings-block">
            <div className="kuaiai-ops-settings-block-title">
              {t('app.kuaiai.settings.ocrTitle', {
                defaultValue: 'OCR 视觉识别',
              })}
            </div>
            <div className="kuaiai-ops-settings-block-desc">
              {t('app.kuaiai.settings.ocrHint', {
                defaultValue:
                  '视觉（OCR）连接用于单据图像识别；连接与密钥在应用连接器中维护，本页仅显示脱敏信息，留空密钥不会被修改。',
              })}
            </div>
            <Form.Item
              name="vision_connection_uuid"
              label={t('app.kuaiai.settings.visionConnection', {
                defaultValue: '视觉连接',
              })}
              style={{ marginBottom: 12 }}
            >
              <Select
                allowClear
                options={visionOptions}
                placeholder={t('app.kuaiai.settings.visionPlaceholder', {
                  defaultValue: '不选用视觉连接',
                })}
                notFoundContent={t('app.kuaiai.settings.visionEmpty', {
                  defaultValue: '暂无视觉角色连接，请先到应用连接器新建',
                })}
                showSearch
                optionFilterProp="label"
              />
            </Form.Item>
            <div className="kuaiai-ops-settings-ocr-grid">
              <div className="kuaiai-ops-settings-field">
                <div className="kuaiai-ops-settings-label">Base URL</div>
                <Input
                  value={ocrDisplay.baseUrl}
                  readOnly
                  disabled
                  aria-label={t('app.kuaiai.settings.ocrBaseUrl', {
                    defaultValue: 'OCR 服务地址',
                  })}
                />
              </div>
              <div className="kuaiai-ops-settings-field">
                <div className="kuaiai-ops-settings-label">
                  {t('app.kuaiai.settings.ocrModel', {
                    defaultValue: 'OCR 模型',
                  })}
                </div>
                <Input
                  value={ocrDisplay.model}
                  readOnly
                  disabled
                  aria-label={t('app.kuaiai.settings.ocrModel', {
                    defaultValue: 'OCR 模型',
                  })}
                />
              </div>
              <div className="kuaiai-ops-settings-field">
                <div className="kuaiai-ops-settings-label">API Key</div>
                <Input
                  value=""
                  readOnly
                  disabled
                  placeholder={t('app.kuaiai.settings.ocrKeyPlaceholder', {
                    defaultValue: '已配置，留空则不修改',
                  })}
                  aria-label={t('app.kuaiai.settings.ocrApiKey', {
                    defaultValue: 'OCR API 密钥',
                  })}
                />
              </div>
            </div>
          </div>

          {/* 3. 智能体开关：3×2 六模板总开关 */}
          <div className="kuaiai-ops-settings-block">
            <div className="kuaiai-ops-settings-block-title">
              {t('app.kuaiai.settings.agentsTitle', {
                defaultValue: '智能体开关',
              })}
            </div>
            <div className="kuaiai-ops-settings-block-desc">
              {t('app.kuaiai.settings.agentsHint', {
                defaultValue:
                  '按场景启停预置智能体；关闭后能力矩阵与智能体库中对应入口将不可用。',
              })}
            </div>
            <div className="kuaiai-ops-settings-switches">
              {AGENT_TEMPLATE_KEYS.map((key) => (
                <div className="kuaiai-ops-settings-switch-item" key={key}>
                  <Form.Item
                    name={['agent_switches', key]}
                    valuePropName="checked"
                    noStyle
                  >
                    <Switch
                      aria-label={t(`app.kuaiai.settings.agent.${key}`, {
                        defaultValue: AGENT_NAME_FALLBACK[key],
                      })}
                    />
                  </Form.Item>
                  <span className="kuaiai-ops-settings-switch-name">
                    {t(`app.kuaiai.settings.agent.${key}`, {
                      defaultValue: AGENT_NAME_FALLBACK[key],
                    })}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* 4. KU-AI 能力配置 */}
          <div className="kuaiai-ops-settings-block">
            <div className="kuaiai-ops-settings-block-title">
              {t('app.kuaiai.settings.capabilitiesTitle', {
                defaultValue: 'KU-AI 能力配置',
              })}
            </div>
            <div className="kuaiai-ops-settings-cap-switches">
              <div className="kuaiai-ops-settings-switch-item">
                <Form.Item
                  name={['capabilities', 'tools_enabled']}
                  valuePropName="checked"
                  noStyle
                >
                  <Switch
                    aria-label={t('app.kuaiai.settings.capTools', {
                      defaultValue: '业务单据工具',
                    })}
                  />
                </Form.Item>
                <span className="kuaiai-ops-settings-switch-name">
                  {t('app.kuaiai.settings.capTools', {
                    defaultValue: '业务单据工具',
                  })}
                </span>
              </div>
              <div className="kuaiai-ops-settings-switch-item">
                <Form.Item
                  name={['capabilities', 'rag_enabled']}
                  valuePropName="checked"
                  noStyle
                >
                  <Switch
                    aria-label={t('app.kuaiai.settings.capRag', {
                      defaultValue: '知识语料 RAG',
                    })}
                  />
                </Form.Item>
                <span className="kuaiai-ops-settings-switch-name">
                  {t('app.kuaiai.settings.capRag', {
                    defaultValue: '知识语料 RAG',
                  })}
                </span>
              </div>
              <div className="kuaiai-ops-settings-switch-item">
                <Form.Item
                  name={['capabilities', 'rag_use_embedding']}
                  valuePropName="checked"
                  noStyle
                >
                  <Switch
                    aria-label={t('app.kuaiai.settings.capEmbedding', {
                      defaultValue: '向量检索',
                    })}
                  />
                </Form.Item>
                <span className="kuaiai-ops-settings-switch-name">
                  {t('app.kuaiai.settings.capEmbedding', {
                    defaultValue: '向量检索',
                  })}
                </span>
              </div>
            </div>
            {/* stream_enabled 不暴露开关，随快照原样提交 */}
            <Form.Item
              name={['capabilities', 'stream_enabled']}
              valuePropName="checked"
              hidden
            >
              <Switch />
            </Form.Item>
            <div className="kuaiai-ops-settings-cap-grid">
              <Form.Item
                name={['capabilities', 'rag_top_k']}
                label={t('app.kuaiai.settings.ragTopK', {
                  defaultValue: 'RAG 条数',
                })}
                rules={[
                  {
                    required: true,
                    message: t('app.kuaiai.settings.ragTopKRequired', {
                      defaultValue: '请填写 RAG 条数（1-20）',
                    }),
                  },
                ]}
                style={{ marginBottom: 0 }}
              >
                <InputNumber min={1} max={20} precision={0} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item
                name={['capabilities', 'rag_backend']}
                label={t('app.kuaiai.settings.ragBackend', {
                  defaultValue: '引擎',
                })}
                style={{ marginBottom: 0 }}
              >
                <Select
                  options={[
                    {
                      value: 'native',
                      label: t('app.kuaiai.settings.ragBackendNative', {
                        defaultValue: '原生',
                      }),
                    },
                  ]}
                />
              </Form.Item>
            </div>
            <Form.Item
              name={['capabilities', 'custom_system_prompt']}
              label={t('app.kuaiai.settings.customPrompt', {
                defaultValue: '企业系统说明',
              })}
              style={{ marginBottom: 0, marginTop: 12 }}
            >
              <Input.TextArea
                style={{ height: 120, resize: 'none' }}
                placeholder={t('app.kuaiai.settings.customPromptPlaceholder', {
                  defaultValue:
                    '可选：描述企业系统背景，将附加到 KU-AI 系统提示词',
                })}
                maxLength={2000}
              />
            </Form.Item>
          </div>
        </Form>
      </div>
    </div>
  );
};

export default SettingsPage;
