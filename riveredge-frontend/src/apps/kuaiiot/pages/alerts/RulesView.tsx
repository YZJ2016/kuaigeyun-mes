import { alignIotTableColumns } from '../../components/table-parity';
/**
 * 告警规则视图：阈值/离线两类规则的查询、新建、编辑与软删除。
 * 权限码与后端一致：读 = kuaiiot:alert:display，全部写操作 = kuaiiot:alert:create。
 * 后端约束：离线规则的 tag_key / operator / threshold_* 由服务固定，编辑时不下发这些字段。
 */

import { EditOutlined, DeleteOutlined } from '@ant-design/icons';
import React, { useMemo, useRef, useState } from 'react';
import { App, AutoComplete, Button, Descriptions, Popconfirm, Select, Tag } from 'antd';
import {
  ProForm,
  ProFormDependency,
  ProFormDigit,
  ProFormRadio,
  ProFormSwitch,
  ProFormText,
  type ActionType,
  type ProColumns,
  type ProFormInstance,
} from '@ant-design/pro-components';
import { UniTable } from '../../../../components/uni-table';
import { UniBatchDeleteButton } from '../../../../components/uni-batch';
import { rowActionKind, rowActionToneDestructive } from '../../../../components/uni-action';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../utils/uniTableLayoutColumns';
import {
  DetailDrawerTemplate,
  DRAWER_CONFIG,
  FormModalTemplate,
  MODAL_CONFIG,
} from '../../../../components/layout-templates';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import {
  filterRowsByListKeyword,
  pickListSearchKeyword,
  pickSearchString,
  pickSearchTriStateBoolean,
} from '../../../../utils/tableQueryKey';
import {
  createAlertRule,
  createOfflineRule,
  deleteAlertRule,
  listAlertRules,
  listTags,
  updateAlertRule,
  type AlertRuleOut,
} from '../../services/kuaiiot';
import { DeviceSelect, EquipmentSelect } from '../../components/entity-selects';
import { RuleTypeTag, SeverityTag } from '../../components/status-tags';
import {
  ALERT_OPERATOR_OPTIONS,
  ALERT_SEVERITY_OPTIONS,
  deleteRowsInSequence,
  deviceLabel,
  formatRuleCondition,
  loadDeviceLabelMap,
  type DeviceLabelMap,
} from './api';

const RULE_TYPE_OPTIONS = [
  { value: 'threshold', label: '阈值规则' },
  { value: 'offline', label: '离线规则' },
];

function EnabledTag({ value }: { value?: boolean | null }) {
  return value ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>;
}

export default function RulesView() {
  const { message: messageApi } = App.useApp();
  const perms = useResourcePermissions('kuaiiot:alert');
  // 后端所有写操作统一挂 kuaiiot:alert:create（见 api/prefill.py、api/product.py）
  const canWrite = perms.canCreate;
  const canDisplay = perms.canAction?.('display') ?? false;

  const actionRef = useRef<ActionType>();
  const formRef = useRef<ProFormInstance>();
  const pageRowsRef = useRef<AlertRuleOut[]>([]);
  const [deviceMap, setDeviceMap] = useState<DeviceLabelMap>(new Map());
  const [tagKeyOptions, setTagKeyOptions] = useState<{ value: string; device_id: number }[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<AlertRuleOut | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<AlertRuleOut | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);

  const loadTagOptions = () => {
    // 无点位读取权限时仍保留手动输入，保存由后端权限与规则校验。
    void listTags()
      .then((tags) => {
        setTagKeyOptions((tags || []).filter(tag => tag.tag_key).map(tag => ({ value: tag.tag_key, device_id: tag.device_id })));
      })
      .catch(() => setTagKeyOptions([]));
  };

  const openCreate = () => {
    if (!canWrite) return;
    setEditing(null);
    setModalOpen(true);
    loadTagOptions();
  };

  const openEdit = (row: AlertRuleOut) => {
    if (!canWrite) return;
    setEditing(row);
    setModalOpen(true);
    loadTagOptions();
  };

  // Alt+N 已由 UniTable 内部按 onCreate 注册，此处不再重复挂载。
  const handleBatchDelete = async (keys: React.Key[]) => {
    if (batchBusy) return;
    setBatchBusy(true);
    try {
      const items = Array.from(new Set(keys)).map((key) => {
        const id = Number(key);
        const found = pageRowsRef.current.find((row) => row.id === id);
        return { id, label: found ? `${found.name} (${found.code})` : `#${key}` };
      });
      const result = await deleteRowsInSequence(items, (item) => deleteAlertRule(item.id));
      if (result.failed) {
        messageApi.error(
          `已删除 ${result.done.length} 条，「${result.failed.item.label}」删除失败：${result.failed.message}，后续已停止`,
        );
      } else {
        messageApi.success(`已删除 ${result.done.length} 条规则`);
      }
      actionRef.current?.clearSelected?.();
      actionRef.current?.reload();
    } finally {
      setBatchBusy(false);
    }
  };

  const columns: ProColumns<AlertRuleOut>[] = useMemo(
    () => [
      {
        title: '规则名称',
        dataIndex: 'name',
        minWidth: 140,
        uniTableRemainderFlex: true,
        uniTablePrimaryFlex: true,
        resizable: false,
        ellipsis: true,
        render: (_, row) => canDisplay ? <Button type="link" size="small" onClick={() => { setDetail(row); setDetailOpen(true); }}>{row.name}</Button> : row.name,
      },
      {
        title: '编码',
        dataIndex: 'code',
        width: 110,
        minWidth: 110,
        uniTableKeepWidth: true,
        resizable: false,
      },
      {
        title: '类型',
        dataIndex: 'rule_type',
        ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
        valueType: 'select',
        valueEnum: {
          threshold: { text: '阈值' },
          offline: { text: '离线' },
        },
        render: (_, row) => <RuleTypeTag value={row.rule_type} />,
      },
      {
        title: '点位键',
        dataIndex: 'tag_key',
        width: 120,
        minWidth: 120,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
      },
      { title: '比较符', dataIndex: 'operator', ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS, hideInSearch: true },
      { title: '阈值', key: 'threshold', dataIndex: 'threshold_number', hideInSearch: true, render: (_, row) => row.threshold_number != null ? Number(row.threshold_number) : row.threshold_text ?? '—' },
      {
        title: '触发条件',
        key: 'condition',
        width: 110,
        minWidth: 110,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        render: (_, row) => formatRuleCondition(row),
      },
      {
        title: '绑定设备',
        dataIndex: 'device_id',
        width: 140,
        minWidth: 140,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        hideInSearch: true,
        render: (_, row) => deviceLabel(deviceMap, row.device_id),
      },
      {
        title: '级别',
        dataIndex: 'severity',
        ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
        valueType: 'select',
        valueEnum: {
          info: { text: '提示' },
          warning: { text: '警告' },
          critical: { text: '严重' },
        },
        render: (_, row) => <SeverityTag value={row.severity} />,
      },
      {
        title: '冷却(秒)',
        dataIndex: 'cooldown_seconds',
        width: 84,
        minWidth: 84,
        uniTableKeepWidth: true,
        resizable: false,
        align: 'right',
        hideInSearch: true,
      },
      {
        title: '通知',
        dataIndex: 'notify_enabled',
        ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
        hideInSearch: true,
        render: (_, row) => (row.notify_enabled ? <Tag color="blue">通知</Tag> : <Tag>不通知</Tag>),
      },
      {
        title: '启用',
        dataIndex: 'is_enabled',
        ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
        valueType: 'select',
        valueEnum: {
          true: { text: '启用' },
          false: { text: '停用' },
        },
        render: (_, row) => <EnabledTag value={row.is_enabled} />,
      },
      {
        title: '操作',
        key: 'action',
        fixed: 'right',
        hideInSearch: true,
        render: (_, row) => {
          const nodes: React.ReactNode[] = [];
          if (canWrite) {
            nodes.push(
              <Button key="edit" icon={<EditOutlined />} {...rowActionKind('skip')} onClick={() => openEdit(row)}>
                编辑
              </Button>,
              <Popconfirm
                key="delete"
                title={`确认删除规则「${row.name}」？`}
                onConfirm={async () => {
                  try {
                    await deleteAlertRule(row.id);
                    messageApi.success('删除成功');
                    actionRef.current?.reload();
                  } catch (error) {
                    messageApi.error(error instanceof Error ? error.message : '删除失败');
                  }
                }}
              >
                <Button icon={<DeleteOutlined />} {...rowActionKind('skip')} {...rowActionToneDestructive()}>
                  删除
                </Button>
              </Popconfirm>,
            );
          }
          return nodes;
        },
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [canDisplay, canWrite, deviceMap, messageApi],
  );

  return (
    <>
      <UniTable<AlertRuleOut>
        columnPersistenceId="apps.kuaiiot.pages.alerts.rules"
        permissionResource="kuaiiot:alert"
        actionRef={actionRef}
        rowKey="id"
        columns={alignIotTableColumns(columns, 'rules')}
        viewTypes={['table', 'help']}
        helpViewConfig={{
          title: '使用帮助',
          content: (
            <div>
              <p>告警规则分为两类：</p>
              <p>· 阈值规则：对入站点位值按比较符与阈值判定，冷却期内不重复告警。</p>
              <p>· 离线规则：设备被离线检查标记为离线时写入告警，点位、比较符与阈值由系统固定，不可编辑。</p>
              <p>模糊搜索覆盖编码、名称与点位键；高级搜索可按类型、级别与启用状态组合过滤。</p>
            </div>
          ),
        }}
        fuzzySearchPlaceholder="编码 / 名称 / 点位键"
        showCreateButton={canWrite}
        createButtonText="新建告警规则"
        onCreate={openCreate}
        enableRowSelection={canWrite}
        toolBarRender={(_action, selected) =>
          canWrite
            ? [
                <UniBatchDeleteButton
                  key="batch-delete"
                  selectedRowKeys={selected.selectedRowKeys ?? []}
                  onConfirm={handleBatchDelete}
                  disabled={batchBusy}
                  confirmTitle={(count) => `确认删除选中的 ${count} 条规则？`}
                  confirmDescription="逐条删除，任一失败即停止并保留明细提示"
                />,
              ]
            : []
        }
        onTableDataChange={(rows) => {
          pageRowsRef.current = rows;
        }}
        defaultPageSize={20}
        request={async (params, _sort, _filter, searchFormValues) => {
          try {
            const [rows, devices] = await Promise.all([
              listAlertRules(),
              loadDeviceLabelMap().catch(() => new Map<number, string>()),
            ]);
            setDeviceMap(devices);
            const keyword = pickListSearchKeyword(searchFormValues);
            let filtered = filterRowsByListKeyword(rows || [], keyword, (row) => [
              row.code,
              row.name,
              row.tag_key,
            ]);
            const code = pickSearchString(searchFormValues, 'code');
            const name = pickSearchString(searchFormValues, 'name');
            const tagKey = pickSearchString(searchFormValues, 'tag_key');
            const ruleType = pickSearchString(searchFormValues, 'rule_type');
            const severity = pickSearchString(searchFormValues, 'severity');
            const enabled = pickSearchTriStateBoolean(searchFormValues, 'is_enabled');
            if (code) filtered = filtered.filter((row) => row.code.toLowerCase().includes(code.toLowerCase()));
            if (name) filtered = filtered.filter((row) => row.name.toLowerCase().includes(name.toLowerCase()));
            if (tagKey) filtered = filtered.filter((row) => row.tag_key.includes(tagKey));
            if (ruleType) filtered = filtered.filter((row) => row.rule_type === ruleType);
            if (severity) filtered = filtered.filter((row) => row.severity === severity);
            if (enabled !== undefined) filtered = filtered.filter((row) => row.is_enabled === enabled);
            const current = Number(params?.current || 1);
            const pageSize = Number(params?.pageSize || 20);
            const start = (current - 1) * pageSize;
            return { data: filtered.slice(start, start + pageSize), success: true, total: filtered.length };
          } catch (error) {
            messageApi.error(error instanceof Error ? error.message : '读取告警规则失败');
            return { data: [], success: false, total: 0 };
          }
        }}
      />

      <FormModalTemplate
        title={editing ? '编辑告警规则' : '新建告警规则'}
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        formRef={formRef}
        isEdit={!!editing}
        width={MODAL_CONFIG.SMALL_WIDTH}
        initialValues={
          editing
            ? {
                rule_type: editing.rule_type || 'threshold',
                name: editing.name,
                tag_key: editing.tag_key,
                operator: editing.operator,
                threshold_number:
                  editing.threshold_number === null || editing.threshold_number === undefined
                    ? undefined
                    : Number(editing.threshold_number),
                threshold_text: editing.threshold_text ?? undefined,
                device_id: editing.device_id ?? undefined,
                equipment_uuid: editing.equipment_uuid ?? undefined,
                severity: editing.severity || 'warning',
                cooldown_seconds: editing.cooldown_seconds ?? 300,
                notify_enabled: editing.notify_enabled,
                is_enabled: editing.is_enabled,
              }
            : {
                rule_type: 'threshold',
                operator: 'gt',
                severity: 'warning',
                cooldown_seconds: 300,
                notify_enabled: false,
                is_enabled: true,
              }
        }
        onFinish={async (values) => {
          const ruleType = (values.rule_type as string) || 'threshold';
          const name = String(values.name ?? '').trim();
          if (!name) {
            messageApi.error('规则名称不能为空');
            return;
          }
          if (ruleType === 'threshold') {
            const tagKey = String(values.tag_key ?? '').trim();
            if (!tagKey) {
              messageApi.error('请填写点位键');
              return;
            }
            if (values.threshold_number == null && !String(values.threshold_text ?? '').trim()) {
              messageApi.warning('数值阈值与文本阈值至少填写其一');
              return;
            }
          }
          try {
            if (editing) {
              if (editing.rule_type === 'threshold') {
                await updateAlertRule(editing.id, {
                  name,
                  tag_key: String(values.tag_key ?? '').trim(),
                  operator: values.operator,
                  threshold_number: values.threshold_number ?? null,
                  threshold_text: String(values.threshold_text ?? '').trim() || null,
                  device_id: values.device_id ?? null,
                  equipment_uuid: String(values.equipment_uuid ?? '').trim() || null,
                  severity: values.severity,
                  cooldown_seconds: values.cooldown_seconds,
                  notify_enabled: values.notify_enabled,
                  is_enabled: values.is_enabled,
                });
              } else {
                // 离线规则结构字段由后端固定，这里不下发（否则触发「不可编辑」校验）
                await updateAlertRule(editing.id, {
                  name,
                  device_id: values.device_id ?? null,
                  severity: values.severity,
                  is_enabled: values.is_enabled,
                });
              }
            } else if (ruleType === 'offline') {
              await createOfflineRule({
                code: String(values.code ?? '').trim(),
                name,
                device_id: values.device_id ?? undefined,
                severity: values.severity,
              });
            } else {
              await createAlertRule({
                code: String(values.code ?? '').trim(),
                name,
                tag_key: String(values.tag_key ?? '').trim(),
                operator: values.operator,
                threshold_number: values.threshold_number ?? undefined,
                threshold_text: String(values.threshold_text ?? '').trim() || undefined,
                device_id: values.device_id ?? undefined,
                equipment_uuid: String(values.equipment_uuid ?? '').trim() || undefined,
                severity: values.severity,
                cooldown_seconds: values.cooldown_seconds,
                notify_enabled: values.notify_enabled,
                is_enabled: values.is_enabled,
              });
            }
            messageApi.success('保存成功');
            setModalOpen(false);
            setEditing(null);
            actionRef.current?.reload();
          } catch (error) {
            messageApi.error(error instanceof Error ? error.message : '保存失败');
          }
        }}
      >
        <ProFormRadio.Group
          name="rule_type"
          label="规则类型"
          disabled={!!editing}
          options={RULE_TYPE_OPTIONS}
          rules={[{ required: true, message: '请选择规则类型' }]}
        />
        {!editing ? (
          <ProFormText
            name="code"
            label="规则编码"
            rules={[{ required: true, message: '请填写规则编码' }]}
            fieldProps={{ maxLength: 50 }}
            extra="创建后不可修改"
          />
        ) : null}
        <ProFormText
          name="name"
          label="规则名称"
          rules={[{ required: true, message: '请填写规则名称' }]}
          fieldProps={{ maxLength: 100 }}
        />
        <ProForm.Item name="device_id" label="绑定设备（可选）">
          <DeviceSelect />
        </ProForm.Item>
        <ProFormDependency name={['rule_type', 'device_id']}>
          {({ rule_type, device_id }) =>
            rule_type === 'threshold' ? (
              <>
                <ProForm.Item
                  name="tag_key"
                  label="点位键"
                  rules={[{ required: true, message: '请填写点位键' }]}
                >
                  <AutoComplete
                    options={Array.from(new Set(tagKeyOptions.filter(tag => !device_id || tag.device_id === Number(device_id)).map(tag => tag.value))).map(value => ({ value }))}
                    placeholder="如 is_online、temperature"
                    allowClear
                    filterOption={(input, option) =>
                      String(option?.value ?? '').toLowerCase().includes(input.toLowerCase())
                    }
                  />
                </ProForm.Item>
                <ProForm.Item
                  name="operator"
                  label="比较符"
                  rules={[{ required: true, message: '请选择比较符' }]}
                >
                  <Select
                    options={ALERT_OPERATOR_OPTIONS}
                    placeholder="gt / lt / gte / lte / eq / ne"
                  />
                </ProForm.Item>
                <ProFormDigit name="threshold_number" label="数值阈值" />
                <ProFormText
                  name="threshold_text"
                  label="文本阈值"
                  fieldProps={{ maxLength: 200 }}
                  extra="数值阈值与文本阈值至少填写其一"
                />
                <ProForm.Item name="equipment_uuid" label="绑定星制造设备（可选）">
                  <EquipmentSelect />
                </ProForm.Item>
                <ProFormDigit name="cooldown_seconds" label="冷却时间（秒）" min={0} />
                <ProFormSwitch name="notify_enabled" label="触发通知" />
              </>
            ) : null
          }
        </ProFormDependency>

        <ProForm.Item
          name="severity"
          label="严重级别"
          rules={[{ required: true, message: '请选择严重级别' }]}
        >
          <Select options={ALERT_SEVERITY_OPTIONS} placeholder="info / warning / critical" />
        </ProForm.Item>

        <ProFormDependency name={['rule_type', 'device_id']}>
          {({ rule_type, device_id }) =>
            // 离线新建接口不收 is_enabled（后端固定启用），避免静默丢字段；编辑与阈值规则保留
            !editing && rule_type === 'offline' ? null : (
              <ProFormSwitch name="is_enabled" label="启用" />
            )
          }
        </ProFormDependency>
      </FormModalTemplate>

      <DetailDrawerTemplate
        title={`规则详情${detail ? ` - ${detail.name}` : ''}`}
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false);
          setDetail(null);
        }}
        size={DRAWER_CONFIG.STANDARD_WIDTH}
        basic={
          detail ? (
            <Descriptions
              column={2}
              size="small"
              items={[
                { key: 'code', label: '编码', children: detail.code },
                { key: 'name', label: '名称', children: detail.name },
                {
                  key: 'rule_type',
                  label: '类型',
                  children: <RuleTypeTag value={detail.rule_type} />,
                },
                { key: 'tag_key', label: '点位键', children: detail.tag_key || '—' },
                {
                  key: 'condition',
                  label: '触发条件',
                  children: formatRuleCondition(detail),
                },
                {
                  key: 'device_id',
                  label: '绑定设备',
                  children: deviceLabel(deviceMap, detail.device_id),
                },
                {
                  key: 'equipment_uuid',
                  label: '绑定星制造设备',
                  children: detail.equipment_uuid || '—',
                },
                {
                  key: 'severity',
                  label: '严重级别',
                  children: <SeverityTag value={detail.severity} />,
                },
                {
                  key: 'cooldown_seconds',
                  label: '冷却时间',
                  children: `${detail.cooldown_seconds} 秒`,
                },
                {
                  key: 'notify_enabled',
                  label: '触发通知',
                  children: detail.notify_enabled ? '是' : '否',
                },
                {
                  key: 'is_enabled',
                  label: '启用',
                  children: <EnabledTag value={detail.is_enabled} />,
                },
                { key: 'id', label: 'ID', children: detail.id },
              ]}
            />
          ) : (
            <div style={{ minHeight: 80 }} />
          )
        }
        extra={
          detail && canWrite ? (
            <Button
              type="primary"
              onClick={() => {
                setDetailOpen(false);
                openEdit(detail);
              }}
            >
              编辑
            </Button>
          ) : null
        }
      />
    </>
  );
}
