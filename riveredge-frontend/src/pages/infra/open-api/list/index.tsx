/**
 * 开放 API 账套鉴权管理（金蝶式：账套 ID + 应用秘钥 + 细粒度 GET/POST 授权）
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Collapse,
  Input,
  Modal,
  Popover,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { ProFormItem, ProFormSelect, ProFormText } from '@ant-design/pro-components';
import {
  CopyOutlined,
  InfoCircleOutlined,
  KeyOutlined,
  ReloadOutlined,
  ApiOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import {
  FormModalTemplate,
  MODAL_CONFIG,
  MultiTabListPageTemplate,
} from '../../../../components/layout-templates';
import { UniTable } from '../../../../components/uni-table';
import { ActionConfirmPopconfirm } from '../../../../components/action-confirm';
import { rowActionKind } from '../../../../components/uni-action';
import { renderMasterActiveTag } from '../../../../apps/master-data/utils/masterListPresentation';
import { getApiErrorMessage } from '../../../../utils/errorHandler';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import {
  createOpenApiApp,
  deleteOpenApiApp,
  getOpenApiAccount,
  getOpenApiAppList,
  getOpenApiIntegrationGuide,
  getOpenApiModuleCatalog,
  OpenApiAccount,
  OpenApiApp,
  OpenApiIntegrationGuide,
  OpenApiModuleCatalogItem,
  provisionWorkbuddyOpenApiPreset,
  resetOpenApiAppSecret,
  rotateOpenApiAcctId,
  updateOpenApiApp,
} from '../../../../services/openApi';
import { getTenantList, TenantStatus } from '../../../../services/tenant';
import { CODE_FONT_FAMILY } from '../../../../constants/fonts';
import { getTenantId, setTenantId } from '../../../../utils/auth';
import { resolveIsInfraSuperAdminSession } from '../../../../utils/infraSuperAdminSession';
import { pickListSearchKeyword, pickSearchString } from '../../../../utils/tableQueryKey';
import { useTranslation } from 'react-i18next';

function filterOpenApiApps(
  items: OpenApiApp[],
  searchFormValues: Record<string, unknown> | undefined | null,
  grantLabelMap: Record<string, string>,
): OpenApiApp[] {
  let list = items;
  const keyword = pickListSearchKeyword(searchFormValues)?.toLowerCase();
  if (keyword) {
    list = list.filter((app) => {
      const haystack = [
        app.name,
        app.app_id,
        ...(app.grants || []).flatMap((g) => [g, grantLabelMap[g] || '']),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(keyword);
    });
  }
  const name = pickSearchString(searchFormValues, 'name');
  if (name) {
    const q = name.toLowerCase();
    list = list.filter((app) => app.name.toLowerCase().includes(q));
  }
  const appId = pickSearchString(searchFormValues, 'app_id');
  if (appId) {
    const q = appId.toLowerCase();
    list = list.filter((app) => app.app_id.toLowerCase().includes(q));
  }
  const status = pickSearchString(searchFormValues, 'status');
  if (status) {
    list = list.filter((app) => app.status === status);
  }
  return list;
}

const codeBlockStyle: React.CSSProperties = {
  fontFamily: CODE_FONT_FAMILY,
  fontSize: 12,
  background: 'var(--ant-color-fill-quaternary, #f5f5f5)',
  padding: 12,
  borderRadius: 6,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-all',
  margin: 0,
  maxHeight: 280,
  overflow: 'auto',
};

/** 按业务分组的细粒度权限勾选（value=permission_codes） */
const PermissionCodesPicker: React.FC<{
  catalog: OpenApiModuleCatalogItem[];
  value?: string[];
  onChange?: (codes: string[]) => void;
}> = ({ catalog, value = [], onChange }) => {
  const selected = useMemo(() => new Set(value), [value]);

  const setCodes = (next: string[]) => {
    onChange?.(Array.from(new Set(next)));
  };

  const toggleModule = (mod: OpenApiModuleCatalogItem, checked: boolean) => {
    const codes = mod.codes || (mod.actions || []).map((a) => a.code);
    if (checked) {
      setCodes([...value, ...codes]);
    } else {
      const drop = new Set(codes);
      setCodes(value.filter((c) => !drop.has(c)));
    }
  };

  const groups = useMemo(() => {
    const order = ['销售', '采购', '仓存', '生产', '质检', '委外', '计划交付', '售后物流', '主数据', '其他'];
    const map = new Map<string, OpenApiModuleCatalogItem[]>();
    catalog.forEach((m) => {
      const g = m.group || '其他';
      if (!map.has(g)) map.set(g, []);
      map.get(g)!.push(m);
    });
    return order
      .filter((g) => map.has(g))
      .concat([...map.keys()].filter((g) => !order.includes(g)))
      .map((g) => ({ group: g, modules: map.get(g)! }));
  }, [catalog]);

  const renderModule = (mod: OpenApiModuleCatalogItem) => {
    const actions = mod.actions || [];
    const codes = mod.codes || actions.map((a) => a.code);
    const picked = codes.filter((c) => selected.has(c));
    const all = codes.length > 0 && picked.length === codes.length;
    const some = picked.length > 0 && !all;
    return (
      <Card
        key={mod.module_key}
        size="small"
        style={{ marginBottom: 8 }}
        title={
          <Space wrap>
            <Checkbox
              checked={all}
              indeterminate={some}
              onChange={(e) => toggleModule(mod, e.target.checked)}
            >
              {mod.label}
            </Checkbox>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {mod.module_key}
            </Typography.Text>
          </Space>
        }
        extra={
          <Button type="link" size="small" onClick={() => toggleModule(mod, true)}>
            全选
          </Button>
        }
      >
        <Checkbox.Group
          style={{ width: '100%' }}
          value={picked}
          onChange={(vals) => {
            const drop = new Set(codes);
            const kept = value.filter((c) => !drop.has(c));
            setCodes([...kept, ...(vals as string[])]);
          }}
        >
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            {actions.map((a) => (
              <Checkbox key={a.code} value={a.code}>
                <Space size={6} wrap>
                  <span>{a.label}</span>
                  {(a.http_methods || []).map((m) => (
                    <Tag key={m} color={m === 'GET' ? 'blue' : m === 'DELETE' ? 'red' : 'orange'}>
                      {m}
                    </Tag>
                  ))}
                  <Typography.Text type="secondary" style={{ fontSize: 11, fontFamily: CODE_FONT_FAMILY }}>
                    {a.code}
                  </Typography.Text>
                </Space>
              </Checkbox>
            ))}
          </Space>
        </Checkbox.Group>
      </Card>
    );
  };

  return (
    <Collapse
      size="small"
      defaultActiveKey={groups.slice(0, 2).map((g) => g.group)}
      items={groups.map(({ group, modules }) => {
        const allCodes = modules.flatMap((m) => m.codes || (m.actions || []).map((a) => a.code));
        const pickedCount = allCodes.filter((c) => selected.has(c)).length;
        return {
          key: group,
          label: (
            <Space>
              <span>{group}</span>
              <Typography.Text type="secondary">
                {modules.length} 个单据
                {pickedCount > 0 ? ` 已选 ${pickedCount}` : ''}
              </Typography.Text>
            </Space>
          ),
          children: modules.map(renderModule),
        };
      })}
    />
  );
};

const OpenApiPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const isInfraSuperAdmin = resolveIsInfraSuperAdminSession();
  const { canAction } = useResourcePermissions('system:open-api');
  const canManage = isInfraSuperAdmin || Boolean(canAction?.('manage'));

  const [selectedTenantId, setSelectedTenantId] = useState<number | undefined>(() => {
    const tid = getTenantId();
    const n = tid != null ? Number(tid) : NaN;
    return Number.isFinite(n) && n > 0 ? n : undefined;
  });
  const [tenantOptions, setTenantOptions] = useState<Array<{ value: number; label: string }>>([]);
  const [tenantsLoading, setTenantsLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [account, setAccount] = useState<OpenApiAccount | null>(null);
  const [apps, setApps] = useState<OpenApiApp[]>([]);
  const [catalog, setCatalog] = useState<OpenApiModuleCatalogItem[]>([]);
  const [guide, setGuide] = useState<OpenApiIntegrationGuide | null>(null);

  const [activeTabKey, setActiveTabKey] = useState('apps');
  const appsActionRef = useRef<ActionType>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editApp, setEditApp] = useState<OpenApiApp | null>(null);
  const [secretOnce, setSecretOnce] = useState<string | null>(null);
  const [presetLoading, setPresetLoading] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  const grantLabelMap = useMemo(() => {
    const map: Record<string, string> = {};
    catalog.forEach((m) => {
      (m.actions || []).forEach((a) => {
        map[a.code] = a.label;
      });
    });
    return map;
  }, [catalog]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [acct, list, mods, g] = await Promise.all([
        getOpenApiAccount(),
        getOpenApiAppList(),
        getOpenApiModuleCatalog(),
        getOpenApiIntegrationGuide(),
      ]);
      setAccount(acct);
      setApps(list);
      setCatalog(mods);
      setGuide(g);
    } catch (e) {
      messageApi.error(getApiErrorMessage(e, '加载失败'));
    } finally {
      setLoading(false);
    }
  }, [messageApi]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    appsActionRef.current?.reload();
  }, [apps, loading]);

  useEffect(() => {
    if (!isInfraSuperAdmin) return;
    let cancelled = false;
    setTenantsLoading(true);
    void getTenantList(
      {
        page: 1,
        page_size: 100,
        status: TenantStatus.ACTIVE,
        sort: 'id',
        order: 'asc',
      },
      true,
    )
      .then((resp) => {
        if (cancelled) return;
        setTenantOptions(
          (resp.items ?? []).map((tenant) => ({
            value: Number(tenant.id),
            label: `${tenant.name} (#${tenant.id})`,
          })),
        );
      })
      .catch(() => {
        if (!cancelled) {
          messageApi.error(t('ui.message.tenantOptionsLoadFailed'));
        }
      })
      .finally(() => {
        if (!cancelled) setTenantsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isInfraSuperAdmin, messageApi, t]);

  const handleTenantChange = (tenantId: number) => {
    if (!Number.isFinite(tenantId) || tenantId <= 0) {
      messageApi.warning(t('pages.infra.openApi.selectTenantRequired'));
      return;
    }
    setSelectedTenantId(tenantId);
    setTenantId(tenantId);
    messageApi.success(t('pages.infra.openApi.tenantSwitched', { id: tenantId }));
    void loadAll();
  };

  const copyText = async (text: string, tip = '已复制') => {
    try {
      await navigator.clipboard.writeText(text);
      messageApi.success(tip);
    } catch {
      messageApi.warning('复制失败，请手动选择');
    }
  };

  const handleProvisionWorkbuddyPreset = async () => {
    setPresetLoading(true);
    try {
      const result = await provisionWorkbuddyOpenApiPreset();
      if (result.created && result.app_secret) {
        setSecretOnce(result.app_secret);
      }
      if (result.created) {
        messageApi.success(t('pages.infra.openApi.presetWorkbuddyCreated'));
      } else if (result.grants_updated) {
        messageApi.success(t('pages.infra.openApi.presetWorkbuddySynced'));
      } else {
        messageApi.info(t('pages.infra.openApi.presetWorkbuddyExists'));
      }
      void loadAll();
    } catch (e) {
      messageApi.error(getApiErrorMessage(e, t('pages.infra.openApi.presetWorkbuddyFailed')));
    } finally {
      setPresetLoading(false);
    }
  };

  const handleRotateAcct = async () => {
    try {
      const next = await rotateOpenApiAcctId();
      setAccount(next);
      messageApi.success('账套 ID 已重置');
      void loadAll();
    } catch (e) {
      messageApi.error(getApiErrorMessage(e, '重置失败'));
    }
  };

  const handleCreateFinish = async (values: {
    name: string;
    permission_codes?: string[];
    ip_allowlist?: string;
  }) => {
    try {
      const created = await createOpenApiApp({
        name: values.name,
        permission_codes: values.permission_codes || [],
        module_keys: [],
        ip_allowlist: values.ip_allowlist || undefined,
      });
      setCreateOpen(false);
      if (created.app_secret) {
        setSecretOnce(created.app_secret);
      }
      messageApi.success(t('pages.infra.openApi.createSuccess'));
      void loadAll();
    } catch (e) {
      messageApi.error(getApiErrorMessage(e, t('pages.infra.openApi.createFailed')));
      throw e;
    }
  };

  const handleResetSecret = async (record: OpenApiApp) => {
    try {
      const updated = await resetOpenApiAppSecret(record.uuid);
      if (updated.app_secret) {
        setSecretOnce(updated.app_secret);
      }
      messageApi.success('秘钥已重置，请立即保存');
      void loadAll();
    } catch (e) {
      messageApi.error(getApiErrorMessage(e, '重置秘钥失败'));
    }
  };

  const handleUpdateFinish = async (values: {
    name: string;
    status: string;
    ip_allowlist?: string;
    permission_codes?: string[];
  }) => {
    if (!editApp) return;
    try {
      await updateOpenApiApp(editApp.uuid, {
        name: values.name,
        status: values.status,
        ip_allowlist: values.ip_allowlist || '',
        permission_codes: values.permission_codes || [],
        module_keys: [],
        update_grants: true,
      });
      setEditApp(null);
      messageApi.success(t('common.saveSuccess'));
      void loadAll();
    } catch (e) {
      messageApi.error(getApiErrorMessage(e, t('common.saveFailed')));
      throw e;
    }
  };

  const handleDelete = async (record: OpenApiApp) => {
    try {
      await deleteOpenApiApp(record.uuid);
      messageApi.success(t('common.deleteSuccess'));
      void loadAll();
    } catch (e) {
      messageApi.error(getApiErrorMessage(e, t('common.deleteFailed')));
    }
  };

  const handleBatchDelete = async (keys: React.Key[]) => {
    if (!keys.length) return;
    try {
      await Promise.all(keys.map((key) => deleteOpenApiApp(String(key))));
      messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
      setSelectedRowKeys([]);
      appsActionRef.current?.clearSelected?.();
      void loadAll();
    } catch (e) {
      messageApi.error(getApiErrorMessage(e, t('common.deleteFailed')));
      throw e;
    }
  };

  const handleBatchStatus = async (enable: boolean) => {
    if (selectedRowKeys.length === 0) {
      messageApi.warning(t('pages.infra.openApi.selectToOperate'));
      return;
    }
    const status = enable ? 'active' : 'disabled';
    const action = enable ? t('common.enabled') : t('common.disabled');
    try {
      await Promise.all(
        selectedRowKeys.map((uuid) =>
          updateOpenApiApp(String(uuid), { status, update_grants: false }),
        ),
      );
      messageApi.success(t('pages.infra.openApi.batchStatusSuccess', { action, count: selectedRowKeys.length }));
      setSelectedRowKeys([]);
      appsActionRef.current?.clearSelected?.();
      void loadAll();
    } catch (e) {
      messageApi.error(getApiErrorMessage(e, t('common.operationFailed')));
    }
  };

  const statCards = useMemo(
    () => [
      {
        key: 'acct',
        title: t('pages.infra.openApi.acctIdTitle'),
        value: account?.acct_id ?? '—',
        valueStyle: { fontFamily: CODE_FONT_FAMILY, fontSize: 18 },
      },
      {
        key: 'apps',
        title: t('pages.infra.openApi.appCountTitle'),
        value: apps.length,
      },
    ],
    [account?.acct_id, apps.length, t],
  );

  const columns: ProColumns<OpenApiApp>[] = useMemo(
    () => [
      {
        title: t('pages.infra.openApi.columnAppName'),
        dataIndex: 'name',
        key: 'name',
        ellipsis: true,
        uniTablePrimaryFlex: true,
      },
      {
        title: t('pages.infra.openApi.columnAppId'),
        dataIndex: 'app_id',
        key: 'app_id',
        width: 200,
        copyable: true,
        render: (_, record) => (
          <Typography.Text copyable style={{ fontFamily: CODE_FONT_FAMILY }}>
            {record.app_id}
          </Typography.Text>
        ),
      },
      {
        title: t('common.status'),
        dataIndex: 'status',
        key: 'status',
        width: 88,
        uniTableKeepWidth: true,
        valueType: 'select',
        valueEnum: {
          active: { text: t('common.enabled') },
          disabled: { text: t('common.disabled') },
        },
        render: (_, record) =>
          renderMasterActiveTag(t, record.status === 'active', 'common.enabled', 'common.disabled'),
      },
      {
        title: t('pages.infra.openApi.columnGrants'),
        dataIndex: 'grants',
        key: 'grants',
        hideInSearch: true,
        render: (_, record) => {
          const grants = record.grants || [];
          return grants.length ? (
            <Space wrap size={[4, 4]}>
              {grants.map((g) => (
                <Tag key={g} title={g}>
                  {grantLabelMap[g] || g.split(':').slice(-1)[0]}
                </Tag>
              ))}
            </Space>
          ) : (
            <Typography.Text type="secondary">{t('pages.infra.openApi.grantsEmpty')}</Typography.Text>
          );
        },
      },
      {
        title: t('common.actions'),
        key: 'actions',
        width: 220,
        fixed: 'right',
        hideInSearch: true,
        render: (_, record) =>
          canManage ? (
            <Space size={0} wrap className="uni-table-operation-actions">
              <Button
                type="link"
                size="small"
                {...rowActionKind('update')}
                onClick={() => setEditApp(record)}
              >
                {t('pages.infra.openApi.actionEditGrants')}
              </Button>
              <ActionConfirmPopconfirm
                title={t('pages.infra.openApi.resetSecretConfirmTitle')}
                onConfirm={() => handleResetSecret(record)}
              >
                <Button type="link" size="small" icon={<KeyOutlined />} {...rowActionKind('update')}>
                  {t('pages.infra.openApi.actionResetSecret')}
                </Button>
              </ActionConfirmPopconfirm>
              <ActionConfirmPopconfirm
                title={t('common.deleteConfirm')}
                okType="danger"
                onConfirm={() => handleDelete(record)}
              >
                <Button type="link" size="small" danger {...rowActionKind('delete')} />
              </ActionConfirmPopconfirm>
            </Space>
          ) : null,
      },
    ],
    [canManage, grantLabelMap, t],
  );

  const docModulePanels = useMemo(() => {
    if (!guide?.modules?.length) return [];
    const order = ['销售', '采购', '仓存', '生产', '质检', '委外', '计划交付', '售后物流', '主数据', '其他'];
    const map = new Map<string, typeof guide.modules>();
    guide.modules.forEach((m) => {
      const g = m.group || '其他';
      if (!map.has(g)) map.set(g, []);
      map.get(g)!.push(m);
    });
    const groups = order
      .filter((g) => map.has(g))
      .concat([...map.keys()].filter((g) => !order.includes(g)));

    const renderEndpoints = (mod: (typeof guide.modules)[number]) => (
      <Collapse
        size="small"
        items={(mod.endpoints || []).map((ep) => ({
          key: ep.code,
          label: (
            <Space wrap>
              <span>{ep.label}</span>
              {(ep.http_methods || []).map((m) => (
                <Tag key={m} color={m === 'GET' ? 'blue' : 'orange'}>
                  {m}
                </Tag>
              ))}
              <Typography.Text type="secondary" style={{ fontFamily: CODE_FONT_FAMILY, fontSize: 11 }}>
                {ep.path}
              </Typography.Text>
            </Space>
          ),
          children: (
            <Tabs
              size="small"
              items={[
                {
                  key: 'curl',
                  label: 'curl',
                  children: (
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => copyText(ep.curl)}>
                        复制
                      </Button>
                      <pre style={codeBlockStyle}>{ep.curl}</pre>
                      {ep.curl_detail && (
                        <>
                          <Typography.Text type="secondary">详情 GET</Typography.Text>
                          <Button
                            type="link"
                            size="small"
                            icon={<CopyOutlined />}
                            onClick={() => copyText(ep.curl_detail || '')}
                          >
                            复制
                          </Button>
                          <pre style={codeBlockStyle}>{ep.curl_detail}</pre>
                        </>
                      )}
                    </Space>
                  ),
                },
                {
                  key: 'python',
                  label: 'Python',
                  children: (
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => copyText(ep.python)}>
                        复制
                      </Button>
                      <pre style={codeBlockStyle}>{ep.python}</pre>
                    </Space>
                  ),
                },
                ...(ep.sample_body
                  ? [
                      {
                        key: 'body',
                        label: '请求体示例',
                        children: (
                          <Space direction="vertical" style={{ width: '100%' }}>
                            <Button
                              type="link"
                              size="small"
                              icon={<CopyOutlined />}
                              onClick={() => copyText(ep.sample_body || '')}
                            >
                              复制
                            </Button>
                            <pre style={codeBlockStyle}>{ep.sample_body}</pre>
                          </Space>
                        ),
                      },
                    ]
                  : []),
                ...(ep.request_fields?.groups?.length
                  ? [
                      {
                        key: 'fields',
                        label: `请求字段（${ep.request_fields.field_count}）`,
                        children: (
                          <Space direction="vertical" size={12} style={{ width: '100%' }}>
                            <Typography.Text type="secondary">
                              Schema：{ep.request_fields.schema}
                              {ep.request_fields.schema_module
                                ? ` · ${ep.request_fields.schema_module}`
                                : ''}
                            </Typography.Text>
                            {(ep.request_fields.groups || []).map((g) => (
                              <div key={g.category}>
                                <Typography.Text strong style={{ display: 'block', marginBottom: 6 }}>
                                  {g.category}
                                  <Typography.Text type="secondary" style={{ marginLeft: 8, fontWeight: 400 }}>
                                    {g.fields.length} 项
                                  </Typography.Text>
                                </Typography.Text>
                                <Table
                                  size="small"
                                  pagination={false}
                                  rowKey={(r) => r.name}
                                  dataSource={g.fields}
                                  columns={[
                                    {
                                      title: '字段',
                                      dataIndex: 'name',
                                      width: 220,
                                      render: (v: string) => (
                                        <Typography.Text code style={{ fontSize: 12 }}>
                                          {v}
                                        </Typography.Text>
                                      ),
                                    },
                                    {
                                      title: '类型',
                                      dataIndex: 'type',
                                      width: 160,
                                      ellipsis: true,
                                      render: (v: string) => (
                                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                          {v}
                                        </Typography.Text>
                                      ),
                                    },
                                    {
                                      title: '必填',
                                      dataIndex: 'required',
                                      width: 64,
                                      render: (v: boolean) =>
                                        v ? <Tag color="red">是</Tag> : <Tag>否</Tag>,
                                    },
                                    {
                                      title: '说明',
                                      dataIndex: 'description',
                                      render: (v?: string | null) => v || '—',
                                    },
                                  ]}
                                />
                              </div>
                            ))}
                          </Space>
                        ),
                      },
                    ]
                  : []),
                ...(ep.read_fields?.query?.groups?.length
                  ? [
                      {
                        key: 'query',
                        label: `查询参数（${ep.read_fields.query.field_count}）`,
                        children: (
                          <Space direction="vertical" size={12} style={{ width: '100%' }}>
                            {ep.read_fields.note ? (
                              <Typography.Text type="secondary">{ep.read_fields.note}</Typography.Text>
                            ) : null}
                            {ep.read_fields.list_path ? (
                              <Typography.Text type="secondary">
                                列表：<Typography.Text code>{ep.read_fields.list_path}</Typography.Text>
                              </Typography.Text>
                            ) : null}
                            {ep.read_fields.detail_path ? (
                              <Typography.Text type="secondary">
                                详情：<Typography.Text code>{ep.read_fields.detail_path}</Typography.Text>
                              </Typography.Text>
                            ) : null}
                            {(ep.read_fields.query.groups || []).map((g) => (
                              <div key={g.category}>
                                <Typography.Text strong style={{ display: 'block', marginBottom: 6 }}>
                                  {g.category}
                                  <Typography.Text type="secondary" style={{ marginLeft: 8, fontWeight: 400 }}>
                                    {g.fields.length} 项
                                  </Typography.Text>
                                </Typography.Text>
                                <Table
                                  size="small"
                                  pagination={false}
                                  rowKey={(r) => `${r.in || 'q'}-${r.name}`}
                                  dataSource={g.fields}
                                  columns={[
                                    {
                                      title: '参数',
                                      dataIndex: 'name',
                                      width: 180,
                                      render: (v: string) => (
                                        <Typography.Text code style={{ fontSize: 12 }}>
                                          {v}
                                        </Typography.Text>
                                      ),
                                    },
                                    {
                                      title: '位置',
                                      dataIndex: 'in',
                                      width: 72,
                                      render: (v?: string) => <Tag>{v === 'path' ? 'path' : 'query'}</Tag>,
                                    },
                                    {
                                      title: '类型',
                                      dataIndex: 'type',
                                      width: 140,
                                      ellipsis: true,
                                    },
                                    {
                                      title: '必填',
                                      dataIndex: 'required',
                                      width: 64,
                                      render: (v: boolean) =>
                                        v ? <Tag color="red">是</Tag> : <Tag>否</Tag>,
                                    },
                                    {
                                      title: '说明',
                                      dataIndex: 'description',
                                      render: (v?: string | null) => v || '—',
                                    },
                                  ]}
                                />
                              </div>
                            ))}
                          </Space>
                        ),
                      },
                    ]
                  : []),
                ...(ep.read_fields?.detail_response?.groups?.length ||
                ep.read_fields?.list_response?.groups?.length
                  ? [
                      {
                        key: 'response',
                        label: `响应字段（${
                          (ep.read_fields?.detail_response?.field_count ||
                            ep.read_fields?.list_response?.field_count ||
                            0)
                        }）`,
                        children: (
                          <Space direction="vertical" size={16} style={{ width: '100%' }}>
                            {ep.read_fields?.detail_response?.groups?.length ? (
                              <div>
                                <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
                                  详情响应 · {ep.read_fields.detail_response.schema}
                                </Typography.Text>
                                {(ep.read_fields.detail_response.groups || []).map((g) => (
                                  <div key={`d-${g.category}`} style={{ marginBottom: 12 }}>
                                    <Typography.Text strong style={{ display: 'block', marginBottom: 6 }}>
                                      {g.category}
                                      <Typography.Text
                                        type="secondary"
                                        style={{ marginLeft: 8, fontWeight: 400 }}
                                      >
                                        {g.fields.length} 项
                                      </Typography.Text>
                                    </Typography.Text>
                                    <Table
                                      size="small"
                                      pagination={false}
                                      rowKey={(r) => `d-${r.name}`}
                                      dataSource={g.fields}
                                      columns={[
                                        {
                                          title: '字段',
                                          dataIndex: 'name',
                                          width: 220,
                                          render: (v: string) => (
                                            <Typography.Text code style={{ fontSize: 12 }}>
                                              {v}
                                            </Typography.Text>
                                          ),
                                        },
                                        {
                                          title: '类型',
                                          dataIndex: 'type',
                                          width: 160,
                                          ellipsis: true,
                                        },
                                        {
                                          title: '说明',
                                          dataIndex: 'description',
                                          render: (v?: string | null) => v || '—',
                                        },
                                      ]}
                                    />
                                  </div>
                                ))}
                              </div>
                            ) : null}
                            {ep.read_fields?.list_response?.groups?.length ? (
                              <div>
                                <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
                                  列表响应 · {ep.read_fields.list_response.schema}
                                </Typography.Text>
                                {(ep.read_fields.list_response.groups || []).map((g) => (
                                  <div key={`l-${g.category}`} style={{ marginBottom: 12 }}>
                                    <Typography.Text strong style={{ display: 'block', marginBottom: 6 }}>
                                      {g.category}
                                      <Typography.Text
                                        type="secondary"
                                        style={{ marginLeft: 8, fontWeight: 400 }}
                                      >
                                        {g.fields.length} 项
                                      </Typography.Text>
                                    </Typography.Text>
                                    <Table
                                      size="small"
                                      pagination={false}
                                      rowKey={(r) => `l-${r.name}`}
                                      dataSource={g.fields}
                                      columns={[
                                        {
                                          title: '字段',
                                          dataIndex: 'name',
                                          width: 220,
                                          render: (v: string) => (
                                            <Typography.Text code style={{ fontSize: 12 }}>
                                              {v}
                                            </Typography.Text>
                                          ),
                                        },
                                        {
                                          title: '类型',
                                          dataIndex: 'type',
                                          width: 160,
                                          ellipsis: true,
                                        },
                                        {
                                          title: '说明',
                                          dataIndex: 'description',
                                          render: (v?: string | null) => v || '—',
                                        },
                                      ]}
                                    />
                                  </div>
                                ))}
                              </div>
                            ) : null}
                          </Space>
                        ),
                      },
                    ]
                  : []),
              ]}
            />
          ),
        }))}
      />
    );

    return groups.map((g) => ({
      key: `group-${g}`,
      label: `${g}（${map.get(g)!.length}）`,
      children: (
        <Collapse
          size="small"
          items={map.get(g)!.map((mod) => ({
            key: mod.module_key,
            label: mod.label,
            children: renderEndpoints(mod),
          }))}
        />
      ),
    }));
  }, [guide]);

  const authDocItems = guide
    ? [
        {
          key: 'auth',
          label: '换取 Token',
          children: (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Typography.Text>
                POST{' '}
                <Typography.Text code>{guide.token_url_absolute || guide.token_url}</Typography.Text>
              </Typography.Text>
              <div>
                <Space style={{ marginBottom: 8 }}>
                  <Typography.Text strong>curl</Typography.Text>
                  <Button
                    type="link"
                    size="small"
                    icon={<CopyOutlined />}
                    onClick={() => copyText(guide.auth_examples?.curl || '')}
                  >
                    复制
                  </Button>
                </Space>
                <pre style={codeBlockStyle}>{guide.auth_examples?.curl}</pre>
              </div>
              <div>
                <Space style={{ marginBottom: 8 }}>
                  <Typography.Text strong>Python (httpx)</Typography.Text>
                  <Button
                    type="link"
                    size="small"
                    icon={<CopyOutlined />}
                    onClick={() => copyText(guide.auth_examples?.python || '')}
                  >
                    复制
                  </Button>
                </Space>
                <pre style={codeBlockStyle}>{guide.auth_examples?.python}</pre>
              </div>
              <div>
                <Typography.Text strong>响应示例</Typography.Text>
                <pre style={codeBlockStyle}>
                  {JSON.stringify(guide.auth_examples?.response_example, null, 2)}
                </pre>
              </div>
            </Space>
          ),
        },
        {
          key: 'matrix',
          label: '权限与 HTTP 对照',
          children: (
            <Table
              size="small"
              pagination={false}
              rowKey="action"
              dataSource={guide.permission_matrix || []}
              columns={[
                { title: '权限动作', dataIndex: 'action', key: 'action' },
                { title: 'HTTP', dataIndex: 'http', key: 'http' },
                { title: '说明', dataIndex: '说明', key: '说明' },
              ]}
            />
          ),
        },
        ...docModulePanels,
      ]
    : [];

  const authHintToolbar = useMemo(
    () => [
      <Popover
        key="open-api-auth-hint"
        trigger="click"
        title={t('pages.infra.openApi.pageHintTitle')}
        content={
          <Typography.Paragraph style={{ marginBottom: 0, maxWidth: 420, lineHeight: 1.625 }}>
            {t('pages.infra.openApi.pageHintDesc')}
          </Typography.Paragraph>
        }
      >
        <Button size="middle" icon={<InfoCircleOutlined />}>
          {t('pages.infra.openApi.pageHintButton')}
        </Button>
      </Popover>,
    ],
    [t],
  );

  const pageHeader = isInfraSuperAdmin ? (
    <Space wrap align="center">
      <TeamOutlined style={{ color: 'var(--ant-color-text-secondary)' }} />
      <Typography.Text>{t('pages.infra.openApi.orgLabel')}</Typography.Text>
      <Select
        style={{ width: 280 }}
        showSearch
        loading={tenantsLoading}
        placeholder={t('pages.infra.openApi.selectTenantPlaceholder')}
        optionFilterProp="label"
        value={selectedTenantId}
        options={tenantOptions}
        onChange={handleTenantChange}
      />
      <Typography.Text type="secondary">{t('pages.infra.openApi.orgContextHint')}</Typography.Text>
    </Space>
  ) : undefined;

  const tabItems = useMemo(
    () => [
      {
        key: 'apps',
        label: t('pages.infra.openApi.tabApps'),
        children: (
          <UniTable<OpenApiApp>
            actionRef={appsActionRef}
            rowKey="uuid"
            columns={columns}
            loading={loading}
            columnPersistenceId="infra.open-api.apps-v6"
            enableRowSelection={canManage}
            onRowSelectionChange={setSelectedRowKeys}
            rowSelection={{ selectedRowKeys, onChange: setSelectedRowKeys }}
            showCreateButton={canManage}
            createButtonText={t('pages.infra.openApi.createApp')}
            onCreate={() => setCreateOpen(true)}
            toolBarButtonSize="middle"
            toolBarActionsEnd={authHintToolbar}
            showImportButton={false}
            showExportButton={false}
            showDeleteButton={canManage}
            onDelete={handleBatchDelete}
            deleteButtonText={t('common.batchDelete')}
            deleteConfirmTitle={t('pages.infra.openApi.batchDeleteTitle')}
            deleteConfirmDescription={(count) =>
              t('pages.infra.openApi.batchDeleteDescription', { count })
            }
            toolBarActionsAfterDelete={[
              <Button
                key="open-api-refresh"
                size="middle"
                icon={<ReloadOutlined />}
                loading={loading}
                onClick={() => void loadAll()}
              >
                {t('common.refresh')}
              </Button>,
              ...(canManage
                ? [
                    <ActionConfirmPopconfirm
                      key="open-api-rotate-acct"
                      title={t('pages.infra.openApi.rotateAcctConfirmTitle')}
                      onConfirm={handleRotateAcct}
                    >
                      <Button key="open-api-rotate-acct-btn" size="middle">
                        {t('pages.infra.openApi.rotateAcctId')}
                      </Button>
                    </ActionConfirmPopconfirm>,
                    <ActionConfirmPopconfirm
                      key="open-api-preset-workbuddy"
                      title={t('pages.infra.openApi.presetWorkbuddyConfirmTitle')}
                      description={t('pages.infra.openApi.presetWorkbuddyConfirmDesc')}
                      onConfirm={handleProvisionWorkbuddyPreset}
                    >
                      <Button
                        key="open-api-preset-workbuddy-btn"
                        size="middle"
                        icon={<ApiOutlined />}
                        loading={presetLoading}
                      >
                        {t('pages.infra.openApi.presetWorkbuddy')}
                      </Button>
                    </ActionConfirmPopconfirm>,
                    ...(selectedRowKeys.length > 0
                      ? [
                          <Button
                            key="open-api-batch-enable"
                            size="middle"
                            {...rowActionKind('update')}
                            onClick={() => void handleBatchStatus(true)}
                          >
                            {t('pages.infra.openApi.batchEnable')}
                          </Button>,
                          <Button
                            key="open-api-batch-disable"
                            size="middle"
                            {...rowActionKind('update')}
                            onClick={() => void handleBatchStatus(false)}
                          >
                            {t('pages.infra.openApi.batchDisable')}
                          </Button>,
                        ]
                      : []),
                  ]
                : []),
            ]}
            showAdvancedSearch
            options={false}
            pagination={false}
            request={async (_params, _sort, _filter, searchFormValues) => {
              const filtered = filterOpenApiApps(apps, searchFormValues, grantLabelMap);
              return {
                data: filtered,
                success: true,
                total: filtered.length,
              };
            }}
          />
        ),
      },
      {
        key: 'docs',
        label: t('pages.infra.openApi.tabDocs'),
        children: guide ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Alert
              type="info"
              showIcon
              title={t('pages.infra.openApi.docNotesTitle')}
              description={
                <ul style={{ marginBottom: 0, paddingLeft: 20, lineHeight: 1.625 }}>
                  {(guide.notes || []).map((n) => (
                    <li key={n} style={{ marginBottom: 8 }}>
                      {n}
                    </li>
                  ))}
                </ul>
              }
            />
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              {t('pages.infra.openApi.docBaseUrlPrefix')}
              <Typography.Text code>{guide.base_url}</Typography.Text>
              {t('pages.infra.openApi.docBaseUrlSuffix')}
            </Typography.Paragraph>
            <Collapse items={authDocItems} defaultActiveKey={['auth']} />
          </Space>
        ) : (
          <Typography.Text type="secondary">{t('pages.infra.openApi.docLoading')}</Typography.Text>
        ),
      },
    ],
    [
      apps,
      authDocItems,
      authHintToolbar,
      canManage,
      columns,
      grantLabelMap,
      guide,
      loadAll,
      loading,
      handleBatchDelete,
      handleBatchStatus,
      presetLoading,
      selectedRowKeys,
      t,
    ],
  );

  return (
    <>
      <MultiTabListPageTemplate
        activeTabKey={activeTabKey}
        onTabChange={setActiveTabKey}
        statCards={statCards}
        preserveMounted
        header={pageHeader}
        tabs={tabItems}
      />

      <FormModalTemplate
        title={t('pages.infra.openApi.createModalTitle')}
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onFinish={handleCreateFinish}
        width={MODAL_CONFIG.LARGE_WIDTH}
        initialValues={{ permission_codes: [] }}
        grid={false}
      >
        <ProFormText
          name="name"
          label={t('pages.infra.openApi.columnAppName')}
          rules={[{ required: true, message: t('pages.infra.openApi.appNameRequired') }]}
          placeholder={t('pages.infra.openApi.appNamePlaceholder')}
        />
        <ProFormItem
          name="permission_codes"
          label={t('pages.infra.openApi.grantsPickerLabel')}
          extra={t('pages.infra.openApi.grantsPickerExtra')}
        >
          <PermissionCodesPicker catalog={catalog} />
        </ProFormItem>
        <ProFormText
          name="ip_allowlist"
          label={t('pages.infra.openApi.ipAllowlistLabel')}
          placeholder={t('pages.infra.openApi.ipAllowlistPlaceholder')}
        />
      </FormModalTemplate>

      <FormModalTemplate
        title={t('pages.infra.openApi.editModalTitle')}
        open={!!editApp}
        onClose={() => setEditApp(null)}
        onFinish={handleUpdateFinish}
        isEdit
        width={MODAL_CONFIG.LARGE_WIDTH}
        initialValues={
          editApp
            ? {
                name: editApp.name,
                status: editApp.status,
                ip_allowlist: editApp.ip_allowlist || '',
                permission_codes: editApp.grants || [],
              }
            : undefined
        }
        grid={false}
      >
        <ProFormText
          name="name"
          label={t('pages.infra.openApi.columnAppName')}
          rules={[{ required: true }]}
          fieldProps={{ maxLength: 100 }}
        />
        <ProFormSelect
          name="status"
          label={t('common.status')}
          rules={[{ required: true }]}
          options={[
            { label: t('common.enabled'), value: 'active' },
            { label: t('common.disabled'), value: 'disabled' },
          ]}
        />
        <ProFormItem name="permission_codes" label={t('pages.infra.openApi.grantsPickerLabel')}>
          <PermissionCodesPicker catalog={catalog} />
        </ProFormItem>
        <ProFormText
          name="ip_allowlist"
          label={t('pages.infra.openApi.ipAllowlistLabel')}
          placeholder={t('pages.infra.openApi.ipAllowlistPlaceholder')}
        />
      </FormModalTemplate>

      <Modal
        title={t('pages.infra.openApi.secretModalTitle')}
        open={!!secretOnce}
        onCancel={() => setSecretOnce(null)}
        destroyOnHidden
        footer={[
          <Button
            key="copy"
            type="primary"
            icon={<CopyOutlined />}
            onClick={() => secretOnce && copyText(secretOnce)}
          >
            {t('pages.infra.openApi.copySecret')}
          </Button>,
          <Button key="ok" onClick={() => setSecretOnce(null)}>
            {t('pages.infra.openApi.secretSaved')}
          </Button>,
        ]}
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          title={t('pages.infra.openApi.secretOnceWarning')}
        />
        <Typography.Paragraph copyable style={{ fontFamily: CODE_FONT_FAMILY, fontSize: 15 }}>
          {secretOnce}
        </Typography.Paragraph>
      </Modal>
    </>
  );
};

export default OpenApiPage;
