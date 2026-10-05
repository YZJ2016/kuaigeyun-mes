import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Form,
  InputNumber,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { getUserList } from '../../../../services/user';
import {
  industryRelayApi,
  type RelayAutoReportBinding,
  type RelayAutoReportConfig,
  type RelayAutoReportDeviceOption,
  type RelayAutoReportLog,
} from '../../services/industryRelayApi';

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
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cfg, binds, devices, logRes, users] = await Promise.all([
        industryRelayApi.getAutoReportConfig(),
        industryRelayApi.listAutoReportBindings(),
        industryRelayApi.listAutoReportDeviceOptions(),
        industryRelayApi.listAutoReportLogs({ limit: 30 }),
        getUserList({ is_active: true, page: 1, page_size: 200 }).catch(() => ({ items: [] })),
      ]);
      setConfig(cfg);
      setBindings(binds);
      setDeviceOptions(devices);
      setLogs(logRes.items || []);
      form.setFieldsValue({
        is_enabled: cfg.is_enabled,
        match_by_device: cfg.match_by_device,
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

  const matchByDevice = Form.useWatch('match_by_device', form);
  const reportMode = Form.useWatch('report_mode', form);

  const unusedDevices = useMemo(() => {
    const used = new Set(bindings.map((b) => b.iot_device_id));
    return deviceOptions.filter((d) => !used.has(d.iot_device_id));
  }, [bindings, deviceOptions]);

  const handleSaveConfig = useCallback(async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      const next = await industryRelayApi.updateAutoReportConfig({
        is_enabled: values.is_enabled,
        match_by_device: values.match_by_device,
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
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : t('app.ind-relay.autoReport.bindFailed'));
    }
  }, [load, selectedDeviceId, t]);

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
      } catch (e: unknown) {
        message.error(e instanceof Error ? e.message : t('common.deleteFailed'));
      }
    },
    [load, t],
  );

  const bindingColumns = useMemo(
    () => [
      {
        title: t('app.ind-relay.autoReport.iotDevice'),
        dataIndex: 'iot_device_name',
        render: (_: unknown, row: RelayAutoReportBinding) =>
          `${row.iot_device_name || '-'} / ${row.iot_device_code || row.iot_device_id}`,
      },
      {
        title: t('app.ind-relay.autoReport.mesEquipment'),
        dataIndex: 'equipment_name',
        render: (_: unknown, row: RelayAutoReportBinding) =>
          `${row.equipment_name || '-'} / ${row.equipment_code || '-'}`,
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
        width: 90,
      },
      {
        title: t('app.ind-relay.autoReport.boundTask'),
        dataIndex: 'bound_work_order_code',
        render: (_: unknown, row: RelayAutoReportBinding) =>
          row.bound_work_order_code
            ? `${row.bound_work_order_code} / ${row.bound_operation_name || '-'}`
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
        width: 180,
        render: (_: unknown, row: RelayAutoReportBinding) =>
          perms.canUpdate ? (
            <Space size={0}>
              <Button type="link" size="small" onClick={() => void handleToggleBinding(row, !row.is_enabled)}>
                {row.is_enabled ? t('common.disable') : t('common.enable')}
              </Button>
              <Button type="link" size="small" danger onClick={() => void handleDeleteBinding(row)}>
                {t('common.delete')}
              </Button>
            </Space>
          ) : null,
      },
    ],
    [handleDeleteBinding, handleToggleBinding, perms.canUpdate, t],
  );

  const logColumns = useMemo(
    () => [
      {
        title: t('app.ind-relay.autoReport.logTime'),
        dataIndex: 'created_at',
        width: 180,
        render: (v: string | undefined) => v || '—',
      },
      {
        title: t('app.ind-relay.autoReport.event'),
        dataIndex: 'event',
        width: 110,
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
        width: 140,
        render: (v: string | null | undefined) => v || '—',
      },
    ],
    [t],
  );

  return (
    <ListPageTemplate>
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          {t('app.ind-relay.autoReport.title')}
        </Typography.Title>
        <Alert
          type="info"
          showIcon
          title={t('app.ind-relay.autoReport.hint')}
          description={
            <span>
              {t('app.ind-relay.autoReport.hintDetail')}{' '}
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
            <Space wrap size={24} style={{ width: '100%' }}>
              <Form.Item name="is_enabled" label={t('app.ind-relay.autoReport.enabled')} valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item
                name="match_by_device"
                label={t('app.ind-relay.autoReport.matchByDevice')}
                valuePropName="checked"
                extra={
                  matchByDevice
                    ? t('app.ind-relay.autoReport.matchByDeviceOnHint')
                    : t('app.ind-relay.autoReport.matchByDeviceOffHint')
                }
              >
                <Switch />
              </Form.Item>
              <Form.Item
                name="report_mode"
                label={t('app.ind-relay.autoReport.mode')}
                style={{ minWidth: 260 }}
              >
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
              <Form.Item
                name="interval_minutes"
                label={t('app.ind-relay.autoReport.interval')}
                rules={[{ required: true }]}
              >
                <InputNumber min={1} max={1440} addonAfter={t('app.ind-relay.autoReport.unitMinutes')} />
              </Form.Item>
              {reportMode === 'PLAN_REACHED_OR_OFFLINE' ? (
                <Form.Item
                  name="offline_threshold_seconds"
                  label={t('app.ind-relay.autoReport.offlineThreshold')}
                  rules={[{ required: true }]}
                >
                  <InputNumber min={30} max={86400} addonAfter={t('app.ind-relay.autoReport.unitSeconds')} />
                </Form.Item>
              ) : null}
              <Form.Item
                name="reporter_user_id"
                label={t('app.ind-relay.autoReport.reporter')}
                rules={[{ required: true, message: t('app.ind-relay.autoReport.reporterRequired') }]}
                style={{ minWidth: 280 }}
              >
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  options={userOptions}
                  placeholder={t('app.ind-relay.autoReport.reporterPlaceholder')}
                />
              </Form.Item>
            </Space>
          </Form>
          {config?.is_enabled && !config.reporter_user_id ? (
            <Alert type="warning" showIcon title={t('app.ind-relay.autoReport.reporterRequired')} />
          ) : null}
        </Card>

        <Card
          title={t('app.ind-relay.autoReport.bindingsTitle')}
          loading={loading}
          extra={
            perms.canUpdate ? (
              <Space>
                <Select
                  style={{ minWidth: 320 }}
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
            size="small"
            pagination={false}
            dataSource={bindings}
            columns={bindingColumns}
          />
        </Card>

        <Card
          title={t('app.ind-relay.autoReport.logsTitle')}
          extra={
            <Button onClick={() => void load()}>{t('common.refresh')}</Button>
          }
        >
          <Table rowKey="id" size="small" pagination={false} dataSource={logs} columns={logColumns} />
        </Card>
      </Space>
    </ListPageTemplate>
  );
}
