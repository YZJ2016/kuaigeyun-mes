import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Drawer,
  Form,
  InputNumber,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { TablePaginationConfig } from 'antd';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { getUserList } from '../../../../services/user';
import { formatDateTime } from '../../../../utils/format';
import {
  industryRelayApi,
  type RelayAutoReportBinding,
  type RelayAutoReportBindingOperations,
  type RelayAutoReportConfig,
  type RelayAutoReportDeviceOption,
  type RelayAutoReportLog,
} from '../../services/industryRelayApi';

const LOG_PAGE_SIZE_OPTIONS = ['10', '20', '50', '100'];

const EVENT_TAG_COLOR: Record<string, string> = {
  skip: 'default',
  BIND: 'blue',
  bind: 'blue',
  changeover: 'orange',
  baseline: 'purple',
  accumulate: 'cyan',
  report: 'success',
  error: 'error',
};

function eventKey(event: string) {
  return String(event || '').toLowerCase();
}

export default function RelayAutoReportPage() {
  const { t } = useTranslation();
  const perms = useResourcePermissions('ind-relay:auto-report');
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<RelayAutoReportConfig | null>(null);
  const [bindings, setBindings] = useState<RelayAutoReportBinding[]>([]);
  const [deviceOptions, setDeviceOptions] = useState<RelayAutoReportDeviceOption[]>([]);
  const [userOptions, setUserOptions] = useState<Array<{ label: string; value: number }>>([]);
  const [logs, setLogs] = useState<RelayAutoReportLog[]>([]);
  const [logTotal, setLogTotal] = useState(0);
  const [logPage, setLogPage] = useState(1);
  const [logPageSize, setLogPageSize] = useState(20);
  const [logsLoading, setLogsLoading] = useState(false);
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | undefined>();
  const [opDrawerOpen, setOpDrawerOpen] = useState(false);
  const [opDrawerLoading, setOpDrawerLoading] = useState(false);
  const [opDetail, setOpDetail] = useState<RelayAutoReportBindingOperations | null>(null);

  const loadLogs = useCallback(
    async (page: number, pageSize: number) => {
      setLogsLoading(true);
      try {
        const skip = (page - 1) * pageSize;
        const logRes = await industryRelayApi.listAutoReportLogs({ skip, limit: pageSize });
        setLogs(logRes.items || []);
        setLogTotal(Number(logRes.total) || 0);
        setLogPage(page);
        setLogPageSize(pageSize);
      } catch (e: unknown) {
        message.error(e instanceof Error ? e.message : t('app.ind-relay.autoReport.loadFailed'));
      } finally {
        setLogsLoading(false);
      }
    },
    [t],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cfg, binds, devices, users] = await Promise.all([
        industryRelayApi.getAutoReportConfig(),
        industryRelayApi.listAutoReportBindings(),
        industryRelayApi.listAutoReportDeviceOptions(),
        getUserList({ is_active: true, page: 1, page_size: 200 }).catch(() => ({ items: [] })),
      ]);
      setConfig(cfg);
      setBindings(binds);
      setDeviceOptions(devices);
      form.setFieldsValue({
        is_enabled: cfg.is_enabled,
        interval_minutes: cfg.interval_minutes,
        report_mode: cfg.report_mode,
        offline_threshold_seconds: cfg.offline_threshold_seconds,
        reporter_user_id: cfg.reporter_user_id ?? undefined,
      });
      setUserOptions(
        (users.items || []).map((u) => ({
          value: Number(u.id),
          label: `${u.full_name || u.username} (${u.username})`,
        })),
      );
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : t('app.ind-relay.autoReport.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [form, t]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void loadLogs(1, 20);
  }, [loadLogs]);

  const reportMode = Form.useWatch('report_mode', form);

  const unusedDevices = useMemo(() => {
    const used = new Set(bindings.map((b) => b.iot_device_id));
    return deviceOptions.filter((d) => !used.has(d.iot_device_id));
  }, [bindings, deviceOptions]);

  const statCards = useMemo(() => {
    const enabledCount = bindings.filter((b) => b.is_enabled).length;
    const pendingTotal = bindings.reduce((sum, b) => sum + Number(b.pending_quantity || 0), 0);
    const boundCount = bindings.filter((b) => b.bound_work_order_code).length;
    return [
      { title: t('app.ind-relay.autoReport.statEnabled'), value: enabledCount },
      { title: t('app.ind-relay.autoReport.pending'), value: pendingTotal },
      { title: t('app.ind-relay.autoReport.statBound'), value: boundCount },
    ];
  }, [bindings, t]);

  const handleSaveConfig = useCallback(async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      const next = await industryRelayApi.updateAutoReportConfig({
        is_enabled: values.is_enabled,
        interval_minutes: values.interval_minutes,
        report_mode: values.report_mode,
        offline_threshold_seconds: values.offline_threshold_seconds,
        reporter_user_id: values.reporter_user_id ?? null,
      });
      setConfig(next);
      message.success(t('app.ind-relay.autoReport.saveOk'));
      await load();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : t('app.ind-relay.autoReport.saveFailed'));
    } finally {
      setSaving(false);
    }
  }, [form, load, t]);

  const handleAddBinding = useCallback(async () => {
    if (!selectedDeviceId) {
      message.warning(t('app.ind-relay.autoReport.selectDeviceFirst'));
      return;
    }
    try {
      await industryRelayApi.createAutoReportBinding({
        iot_device_id: selectedDeviceId,
        is_enabled: true,
      });
      message.success(t('app.ind-relay.autoReport.bindOk'));
      setSelectedDeviceId(undefined);
      await load();
      await loadLogs(1, logPageSize);
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : t('app.ind-relay.autoReport.bindFailed'));
    }
  }, [load, loadLogs, logPageSize, selectedDeviceId, t]);

  const handleToggleBinding = useCallback(
    async (row: RelayAutoReportBinding, enabled: boolean) => {
      try {
        await industryRelayApi.updateAutoReportBinding(row.id, { is_enabled: enabled });
        message.success(t('common.updateSuccess'));
        await load();
      } catch (e: unknown) {
        message.error(e instanceof Error ? e.message : t('common.updateFailed'));
      }
    },
    [load, t],
  );

  const handleDeleteBinding = useCallback(
    async (row: RelayAutoReportBinding) => {
      try {
        await industryRelayApi.deleteAutoReportBinding(row.id);
        message.success(t('common.deleteSuccess'));
        await load();
        await loadLogs(1, logPageSize);
      } catch (e: unknown) {
        message.error(e instanceof Error ? e.message : t('common.deleteFailed'));
      }
    },
    [load, loadLogs, logPageSize, t],
  );

  const handleOpenOperations = useCallback(
    async (row: RelayAutoReportBinding) => {
      setOpDrawerOpen(true);
      setOpDrawerLoading(true);
      try {
        const detail = await industryRelayApi.listAutoReportBindingOperations(row.id);
        setOpDetail(detail);
      } catch (e: unknown) {
        setOpDetail(null);
        message.error(e instanceof Error ? e.message : t('app.ind-relay.autoReport.loadFailed'));
      } finally {
        setOpDrawerLoading(false);
      }
    },
    [t],
  );

  const renderNameCode = useCallback((name?: string | null, code?: string | number | null) => {
    return (
      <Space orientation="vertical" size={0}>
        <Typography.Text>{name || '—'}</Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {code || '—'}
        </Typography.Text>
      </Space>
    );
  }, []);

  const bindingColumns = useMemo(
    () => [
      {
        title: t('app.ind-relay.autoReport.iotDevice'),
        dataIndex: 'iot_device_name',
        render: (_: unknown, row: RelayAutoReportBinding) =>
          renderNameCode(row.iot_device_name, row.iot_device_code || row.iot_device_id),
      },
      {
        title: t('app.ind-relay.autoReport.mesEquipment'),
        dataIndex: 'equipment_name',
        render: (_: unknown, row: RelayAutoReportBinding) =>
          renderNameCode(row.equipment_name, row.equipment_code),
      },
      {
        title: t('app.ind-relay.autoReport.line'),
        dataIndex: 'production_line_name',
        width: 140,
        render: (_: unknown, row: RelayAutoReportBinding) =>
          row.production_line_name || row.production_line_code || '—',
      },
      {
        title: 'zscl',
        dataIndex: 'last_zscl',
        width: 100,
        render: (v: number | null | undefined) => (v == null ? '—' : v),
      },
      {
        title: t('app.ind-relay.autoReport.pending'),
        dataIndex: 'pending_quantity',
        width: 100,
      },
      {
        title: t('app.ind-relay.autoReport.processOps'),
        dataIndex: 'process_operation_count',
        width: 110,
        render: (v: number | undefined, row: RelayAutoReportBinding) => (
          <Button type="link" size="small" onClick={() => void handleOpenOperations(row)}>
            {t('app.ind-relay.autoReport.processOpCount', { count: Number(v || 0) })}
          </Button>
        ),
      },
      {
        title: t('app.ind-relay.autoReport.boundTask'),
        dataIndex: 'bound_work_order_code',
        render: (_: unknown, row: RelayAutoReportBinding) =>
          row.bound_work_order_code
            ? renderNameCode(row.bound_work_order_code, row.bound_operation_name)
            : '—',
      },
      {
        title: t('common.status'),
        dataIndex: 'is_enabled',
        width: 90,
        render: (_: unknown, row: RelayAutoReportBinding) =>
          row.is_enabled ? (
            <Tag color="success">{t('common.enable')}</Tag>
          ) : (
            <Tag>{t('common.disabled')}</Tag>
          ),
      },
      {
        title: t('common.actions'),
        width: 200,
        render: (_: unknown, row: RelayAutoReportBinding) => (
          <Space size={0}>
            <Button type="link" size="small" onClick={() => void handleOpenOperations(row)}>
              {t('common.detail')}
            </Button>
            {perms.canUpdate ? (
              <>
                <Button type="link" size="small" onClick={() => void handleToggleBinding(row, !row.is_enabled)}>
                  {row.is_enabled ? t('common.disable') : t('common.enable')}
                </Button>
                <Popconfirm
                  title={t('common.confirmDelete')}
                  onConfirm={() => void handleDeleteBinding(row)}
                >
                  <Button type="link" size="small" danger>
                    {t('common.delete')}
                  </Button>
                </Popconfirm>
              </>
            ) : null}
          </Space>
        ),
      },
    ],
    [handleDeleteBinding, handleOpenOperations, handleToggleBinding, perms.canUpdate, renderNameCode, t],
  );

  const logColumns = useMemo(
    () => [
      {
        title: t('app.ind-relay.autoReport.logTime'),
        dataIndex: 'created_at',
        width: 180,
        render: (v: string | undefined) => (v ? formatDateTime(v, 'YYYY-MM-DD HH:mm:ss') : '—'),
      },
      {
        title: t('app.ind-relay.autoReport.event'),
        dataIndex: 'event',
        width: 110,
        render: (v: string) => {
          const key = eventKey(v);
          const label = t(`app.ind-relay.autoReport.eventName.${key}`, {
            defaultValue: v || '—',
          });
          return <Tag color={EVENT_TAG_COLOR[v] || EVENT_TAG_COLOR[key] || 'default'}>{label}</Tag>;
        },
      },
      {
        title: t('app.ind-relay.autoReport.message'),
        dataIndex: 'message',
        ellipsis: true,
      },
      {
        title: t('app.ind-relay.autoReport.qty'),
        dataIndex: 'increment_qty',
        width: 90,
        render: (v: number | null | undefined) => (v == null ? '—' : v),
      },
      {
        title: t('app.ind-relay.autoReport.workOrder'),
        dataIndex: 'work_order_code',
        width: 160,
        render: (v: string | null | undefined) => v || '—',
      },
    ],
    [t],
  );

  const logPagination: TablePaginationConfig = {
    current: logPage,
    pageSize: logPageSize,
    total: logTotal,
    showSizeChanger: true,
    showQuickJumper: true,
    pageSizeOptions: LOG_PAGE_SIZE_OPTIONS,
    showTotal: (total, range) =>
      t('components.uniTable.paginationTotal', { total, start: range[0], end: range[1] }),
    onChange: (page, size) => {
      void loadLogs(page, size || logPageSize);
    },
  };

  return (
    <ListPageTemplate statCards={statCards}>
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message={
            <span>
              {t('app.ind-relay.autoReport.hint')}{' '}
              <Link to="/apps/kuaiiot/devices">{t('app.ind-relay.autoReport.openDevices')}</Link>
            </span>
          }
        />

        <Card
          title={t('app.ind-relay.autoReport.configTitle')}
          loading={loading}
          extra={
            perms.canUpdate ? (
              <Button type="primary" loading={saving} onClick={() => void handleSaveConfig()}>
                {t('common.save')}
              </Button>
            ) : null
          }
        >
          <Form form={form} layout="vertical" disabled={!perms.canUpdate}>
            <Row gutter={[24, 8]}>
              <Col xs={24} sm={12} md={8} lg={6}>
                <Form.Item name="is_enabled" label={t('app.ind-relay.autoReport.enabled')} valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12} md={8} lg={6}>
                <Form.Item name="report_mode" label={t('app.ind-relay.autoReport.mode')}>
                  <Select
                    options={[
                      {
                        value: 'REALTIME_INCREMENT',
                        label: t('app.ind-relay.autoReport.modeRealtime'),
                      },
                      {
                        value: 'PLAN_REACHED_OR_OFFLINE',
                        label: t('app.ind-relay.autoReport.modePlanOffline'),
                      },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12} md={8} lg={6}>
                <Form.Item
                  name="interval_minutes"
                  label={t('app.ind-relay.autoReport.interval')}
                  rules={[{ required: true }]}
                >
                  <InputNumber min={1} max={1440} style={{ width: '100%' }} addonAfter={t('app.ind-relay.autoReport.unitMinutes')} />
                </Form.Item>
              </Col>
              {reportMode === 'PLAN_REACHED_OR_OFFLINE' ? (
                <Col xs={24} sm={12} md={8} lg={6}>
                  <Form.Item
                    name="offline_threshold_seconds"
                    label={t('app.ind-relay.autoReport.offlineThreshold')}
                    rules={[{ required: true }]}
                  >
                    <InputNumber min={30} max={86400} style={{ width: '100%' }} addonAfter={t('app.ind-relay.autoReport.unitSeconds')} />
                  </Form.Item>
                </Col>
              ) : null}
              <Col xs={24} sm={12} md={12} lg={8}>
                <Form.Item
                  name="reporter_user_id"
                  label={t('app.ind-relay.autoReport.reporter')}
                  rules={[{ required: true, message: t('app.ind-relay.autoReport.reporterRequired') }]}
                >
                  <Select
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    options={userOptions}
                    placeholder={t('app.ind-relay.autoReport.reporterPlaceholder')}
                  />
                </Form.Item>
              </Col>
            </Row>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              {t('app.ind-relay.autoReport.policyHint')}
            </Typography.Paragraph>
          </Form>
          {config?.is_enabled && !config.reporter_user_id ? (
            <Alert
              type="warning"
              showIcon
              style={{ marginTop: 12 }}
              message={t('app.ind-relay.autoReport.reporterRequired')}
            />
          ) : null}
        </Card>

        <Card
          title={t('app.ind-relay.autoReport.bindingsTitle')}
          loading={loading}
          extra={
            perms.canUpdate ? (
              <Space wrap>
                <Select
                  style={{ minWidth: 280 }}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  placeholder={t('app.ind-relay.autoReport.selectBoundDevice')}
                  value={selectedDeviceId}
                  onChange={(v) => setSelectedDeviceId(v)}
                  options={unusedDevices.map((d) => ({
                    value: d.iot_device_id,
                    label: d.label,
                  }))}
                  notFoundContent={t('app.ind-relay.autoReport.noBoundDevices')}
                />
                <Button type="primary" onClick={() => void handleAddBinding()}>
                  {t('app.ind-relay.autoReport.addBinding')}
                </Button>
              </Space>
            ) : null
          }
        >
          <Table
            rowKey="id"
            size="middle"
            pagination={false}
            dataSource={bindings}
            columns={bindingColumns}
            locale={{ emptyText: t('app.ind-relay.autoReport.bindingsEmpty') }}
          />
        </Card>

        <Card
          title={t('app.ind-relay.autoReport.logsTitle')}
          extra={
            <Button onClick={() => void loadLogs(logPage, logPageSize)} loading={logsLoading}>
              {t('common.refresh')}
            </Button>
          }
        >
          <Table
            rowKey="id"
            size="middle"
            loading={logsLoading}
            dataSource={logs}
            columns={logColumns}
            pagination={logPagination}
            locale={{ emptyText: t('app.ind-relay.autoReport.logsEmpty') }}
          />
        </Card>
      </Space>
      <Drawer
        title={t('app.ind-relay.autoReport.processOpDetailTitle')}
        width={640}
        open={opDrawerOpen}
        onClose={() => {
          setOpDrawerOpen(false);
          setOpDetail(null);
        }}
        extra={
          <Link to="/apps/master-data/process/operations">
            {t('app.ind-relay.autoReport.openProcessMaster')}
          </Link>
        }
      >
        <Typography.Paragraph type="secondary">
          {opDetail
            ? `${opDetail.equipment_name || '—'} / ${opDetail.equipment_code || opDetail.equipment_id}`
            : '—'}
        </Typography.Paragraph>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message={t('app.ind-relay.autoReport.processOpHint')}
        />
        <Table
          rowKey="id"
          size="middle"
          loading={opDrawerLoading}
          pagination={false}
          dataSource={opDetail?.items || []}
          locale={{ emptyText: t('app.ind-relay.autoReport.processOpEmpty') }}
          columns={[
            { title: t('app.ind-relay.autoReport.processOpCode'), dataIndex: 'code', width: 140 },
            { title: t('app.ind-relay.autoReport.processOpName'), dataIndex: 'name' },
            {
              title: t('common.status'),
              dataIndex: 'is_active',
              width: 90,
              render: (v: boolean) =>
                v ? (
                  <Tag color="success">{t('common.enabled')}</Tag>
                ) : (
                  <Tag>{t('common.disabled')}</Tag>
                ),
            },
          ]}
        />
      </Drawer>
    </ListPageTemplate>
  );
}
