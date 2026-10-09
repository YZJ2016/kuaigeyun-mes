import { alignIotTableColumns } from '../../components/table-parity';
/**
 * 设备连接：IoT 设备运营列表页，左侧设备分组过滤。
 * 设备凭据只在建机/批量建机/轮换当次弹窗显示一次，列表与详情不回显。
 */

import { DeleteOutlined, MoreOutlined } from '@ant-design/icons';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  ActionType,
  ProColumns,
  ProDescriptionsItemProps,
} from '@ant-design/pro-components';
import { ProFormDependency, ProFormDigit, ProFormText, ProFormTextArea } from '@ant-design/pro-components';
import {
  App,
  Alert,
  Button,
  DatePicker,
  Dropdown,
  Empty,
  Form,
  Grid,
  InputNumber,
  Popconfirm,
  Select,
  Space,
  Spin,
  Table,
  Tree,
  Typography,
} from 'antd';
import type { DataNode } from 'antd/es/tree';
import dayjs from 'dayjs';
import { UniTable } from '../../../../components/uni-table';
import { rowActionKind } from '../../../../components/uni-action';
import { UniBatchDeleteButton } from '../../../../components/uni-batch';
import {
  DetailDrawerSection,
  DetailDrawerTemplate,
  DRAWER_CONFIG,
  FormModalTemplate,
  ListPageTemplate,
  MODAL_CONFIG,
  TwoColumnLayout,
} from '../../../../components/layout-templates';
import SafeProFormSelect from '../../../../components/safe-pro-form-select';
import { buildListPageHelpViewConfig } from '../../../../components/page-help-wiki';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { formatDateTimeBySiteSetting } from '../../../../utils/format';
import {
  extractProTableSort,
  filterRowsByListKeyword,
  pickListSearchKeyword,
  pickSearchString,
  pickSearchTriStateBoolean,
} from '../../../../utils/tableQueryKey';
import { equipmentApi } from '../../../kuaizhizao/services/equipment';
import {
  batchCreateDevices,
  listConnections,
  listDeviceGroups,
  listProducts,
  listSnapshots,
  listTemplates,
  type ConnectionOut,
  type DeviceGroup,
  type SnapshotOut,
} from '../../services/kuaiiot';
import {
  ConnectionSelect,
  EquipmentSelect,
  ProductSelect,
} from '../../components/entity-selects';
import { OnlineTag } from '../../components/status-tags';
import {
  createDeviceRow,
  deleteDeviceRow,
  getDeviceRow,
  listDeviceRows,
  rotateDeviceToken,
  updateDeviceRow,
  type DeviceRow,
} from './api';
import { ExternalDeviceInput } from './ExternalDeviceInput';

const GROUP_ALL = 'all';
const GROUP_NONE = 'ungrouped';

function fmtTime(value?: string | null): string {
  return value ? formatDateTimeBySiteSetting(value, '—') : '—';
}

/** 快照值统一成文本展示；三类值互斥，都不存在时显示 —。 */
function snapshotValueText(row: SnapshotOut): string {
  if (row.value_number != null) return String(row.value_number);
  if (row.value_bool != null) return row.value_bool ? 'true' : 'false';
  if (row.value_text != null) return String(row.value_text);
  return '—';
}

function buildGroupTree(groups: DeviceGroup[]): DataNode[] {
  const ids = new Set(groups.map((g) => g.id));
  const childrenOf = new Map<number | null, DeviceGroup[]>();
  for (const g of groups) {
    // 父节点已删除/不可见时按根节点展示，避免设备分组“消失”
    const pid = g.parent_id != null && ids.has(g.parent_id) ? g.parent_id : null;
    const list = childrenOf.get(pid) ?? [];
    list.push(g);
    childrenOf.set(pid, list);
  }
  const toNode = (g: DeviceGroup): DataNode => ({
    key: g.id,
    title: `${g.name} (${g.code})`,
    children: (childrenOf.get(g.id) ?? [])
      .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
      .map(toNode),
  });
  return (childrenOf.get(null) ?? [])
    .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
    .map(toNode);
}

function sortRows(rows: DeviceRow[], sort: Record<string, 'ascend' | 'descend' | null>) {
  const { sortBy, sortOrder } = extractProTableSort(sort);
  const sorted = [...rows].sort((a, b) => {
    const av = (a as Record<string, unknown>)[sortBy ?? 'created_at'];
    const bv = (b as Record<string, unknown>)[sortBy ?? 'created_at'];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    return String(av).localeCompare(String(bv), 'zh-CN');
  });
  return sortOrder === 'asc' ? sorted : sorted.reverse();
}

const DevicesPage: React.FC = () => {
  const { message: messageApi, modal } = App.useApp();
  const perms = useResourcePermissions('kuaiiot:device');
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.md;
  const actionRef = useRef<ActionType>();
  /** 跨页批量删除解析：request 内增量累积（只增不覆盖），不依赖当前展示页。 */
  const allRowsRef = useRef<Map<number, DeviceRow>>(new Map());
  const groupFilterRef = useRef<React.Key>(GROUP_ALL);
  const [oeeForm] = Form.useForm();
  const [deviceForm] = Form.useForm();

  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [groups, setGroups] = useState<DeviceGroup[]>([]);
  const [groupsError, setGroupsError] = useState<string>();
  const [selectedGroup, setSelectedGroup] = useState<React.Key>(GROUP_ALL);
  const [connections, setConnections] = useState<ConnectionOut[]>([]);
  const [equipmentLabels, setEquipmentLabels] = useState<Map<string, string>>(new Map());
  const [products, setProducts] = useState<{ id: number; code: string; name: string }[]>([]);
  const [templates, setTemplates] = useState<{ code: string; name: string }[]>([]);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<DeviceRow | null>(null);
  const [batchOpen, setBatchOpen] = useState(false);
  const [detail, setDetail] = useState<DeviceRow | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [snapshots, setSnapshots] = useState<SnapshotOut[]>([]);
  const [snapshotsLoading, setSnapshotsLoading] = useState(false);
  const [snapshotsError, setSnapshotsError] = useState<string>();
  const [oeeLoading, setOeeLoading] = useState(false);
  const [oeeSaving, setOeeSaving] = useState(false);

  const connectionLabelById = useMemo(() => {
    const map = new Map<number, string>();
    for (const row of connections) map.set(row.id, `${row.name} (${row.code})`);
    return map;
  }, [connections]);

  const productLabelById = useMemo(() => {
    const map = new Map<number, string>();
    for (const row of products) map.set(row.id, `${row.name} (${row.code})`);
    return map;
  }, [products]);

  const groupLabelById = useMemo(() => {
    const map = new Map<number, string>();
    for (const g of groups) map.set(g.id, `${g.name} (${g.code})`);
    return map;
  }, [groups]);

  const loadSidebarSources = useCallback(async () => {
    void equipmentApi.list({ limit: 500 }).then((res: any) => {
      setEquipmentLabels(new Map((res?.items ?? []).map((row: { uuid: string; name: string; code: string }) => [row.uuid, `${row.name} (${row.code})`])));
    }).catch(() => setEquipmentLabels(new Map()));
    try {
      setGroups(await listDeviceGroups());
      setGroupsError(undefined);
    } catch (error) {
      setGroupsError(error instanceof Error ? error.message : '分组加载失败');
      setGroups([]);
    }
    try {
      setConnections(await listConnections());
    } catch {
      setConnections([]);
    }
    try {
      const rows = await listProducts();
      setProducts((rows || []).map((r) => ({ id: r.id, code: r.code, name: r.name })));
    } catch {
      setProducts([]);
    }
  }, []);

  useEffect(() => {
    void loadSidebarSources();
  }, [loadSidebarSources]);

  const groupTreeData = useMemo<DataNode[]>(
    () => [
      { key: GROUP_ALL, title: '全部设备' },
      { key: GROUP_NONE, title: '未分组' },
      ...buildGroupTree(groups),
    ],
    [groups],
  );

  const groupOptions = useMemo(
    () => [
      { value: GROUP_ALL, label: '全部设备' },
      { value: GROUP_NONE, label: '未分组' },
      ...groups.map((g) => ({ value: g.id, label: `${g.name} (${g.code})` })),
    ],
    [groups],
  );

  const handleGroupSelect = useCallback((keys: React.Key[]) => {
    const key = keys[0] ?? GROUP_ALL;
    setSelectedGroup(key);
    groupFilterRef.current = key;
    actionRef.current?.reload();
  }, []);

  const showTokenOnce = useCallback(
    (rows: Array<{ code: string; name: string; device_token: string }>, title: string) => {
      modal.warning({
        title,
        width: 640,
        content: (
          <div>
            <Alert
              type="warning"
              showIcon
              message="设备凭据只在本次结果显示，关闭后无法再次查看，请立即复制保存。"
              style={{ marginBottom: 12 }}
            />
            <Table
              size="small"
              rowKey="code"
              pagination={false}
              scroll={{ x: 'max-content' }}
              dataSource={rows}
              columns={[
                { title: '编码', dataIndex: 'code' },
                { title: '名称', dataIndex: 'name' },
                {
                  title: '设备凭据',
                  dataIndex: 'device_token',
                  render: (token: string) => (
                    <Typography.Paragraph copyable style={{ marginBottom: 0, wordBreak: 'break-all' }}>
                      {token}
                    </Typography.Paragraph>
                  ),
                },
              ]}
            />
          </div>
        ),
      });
    },
    [modal],
  );

  const openCreate = useCallback(() => {
    setEditing(null);
    setModalOpen(true);
    listTemplates()
      .then((rows) => setTemplates((rows || []).map((r) => ({ code: r.code, name: r.name }))))
      .catch(() => setTemplates([]));
  }, []);

  const openEdit = useCallback((row: DeviceRow) => {
    setEditing(row);
    setModalOpen(true);
  }, []);

  /** OEE 计算依据读写与旧 pipeline 页一致：equipment.technical_parameters.oee。 */
  const loadOeeBasis = useCallback(async (equipmentUuid: string) => {
    setOeeLoading(true);
    try {
      const row = (await equipmentApi.get(equipmentUuid)) as {
        technical_parameters?: {
          oee?: {
            ideal_cycle_seconds?: number;
            planned_windows?: Array<{ start: string; end: string }>;
          };
        };
      };
      const config = row.technical_parameters?.oee;
      oeeForm.setFieldsValue({
        ideal_cycle_seconds: config?.ideal_cycle_seconds,
        planned_windows: (config?.planned_windows ?? []).map((w) => ({
          range: [dayjs(w.start), dayjs(w.end)],
        })),
      });
    } catch {
      messageApi.error('设备 OEE 配置读取失败');
    } finally {
      setOeeLoading(false);
    }
  }, [messageApi, oeeForm]);

  const openDetail = useCallback(
    async (row: DeviceRow) => {
      setDetail(row);
      setDetailOpen(true);
      setDetailLoading(true);
      oeeForm.resetFields();
      setSnapshots([]);
      setSnapshotsError(undefined);
      setSnapshotsLoading(true);
      try {
        setSnapshots(await listSnapshots(row.id));
      } catch (error) {
        setSnapshotsError(error instanceof Error ? error.message : '快照读取失败');
      } finally {
        setSnapshotsLoading(false);
      }
      let equipmentUuid = row.equipment_uuid;
      try {
        const fresh = await getDeviceRow(row.id);
        setDetail(fresh);
        equipmentUuid = fresh.equipment_uuid;
      } catch (error) {
        messageApi.error(error instanceof Error ? error.message : '读取设备详情失败');
      } finally {
        setDetailLoading(false);
      }
      if (equipmentUuid) {
        void loadOeeBasis(equipmentUuid);
      }
    },
    [messageApi, oeeForm, loadOeeBasis],
  );

  const handleSaveOee = useCallback(
    async (values: { ideal_cycle_seconds?: number; planned_windows?: Array<{ range: [dayjs.Dayjs, dayjs.Dayjs] }> }) => {
      const equipmentUuid = detail?.equipment_uuid;
      if (!equipmentUuid) return;
      setOeeSaving(true);
      try {
        const row = (await equipmentApi.get(equipmentUuid)) as {
          technical_parameters?: Record<string, unknown>;
        };
        await equipmentApi.update(equipmentUuid, {
          technical_parameters: {
            ...(row.technical_parameters ?? {}),
            oee: {
              ideal_cycle_seconds: values.ideal_cycle_seconds,
              planned_windows: (values.planned_windows ?? []).map((w) => ({
                start: w.range[0].toISOString(),
                end: w.range[1].toISOString(),
              })),
            },
          },
        });
        messageApi.success('OEE 依据已保存');
      } catch {
        messageApi.error('保存失败，请检查窗口重叠、理想节拍和编辑权限');
      } finally {
        setOeeSaving(false);
      }
    },
    [detail, messageApi],
  );

  const handleDelete = useCallback(
    async (row: DeviceRow) => {
      try {
        await deleteDeviceRow(row.id);
        messageApi.success('删除成功');
        setSelectedRowKeys((keys) => keys.filter((k) => k !== row.id));
        actionRef.current?.reload();
      } catch (error) {
        messageApi.error(error instanceof Error ? error.message : '删除失败');
      }
    },
    [messageApi],
  );

  const handleRotateToken = useCallback(
    async (row: DeviceRow) => {
      try {
        const res = await rotateDeviceToken(row.id);
        showTokenOnce([{ code: res.code, name: res.name, device_token: res.device_token }], '设备凭据已轮换');
      } catch (error) {
        messageApi.error(error instanceof Error ? error.message : '轮换凭据失败');
      }
    },
    [messageApi, showTokenOnce],
  );

  /** 批删串行执行：任一失败即停止，报告成功数与失败明细；跨页选中行从 allRowsRef 解析名称。 */
  const handleBatchDelete = useCallback(
    async (keys: React.Key[]) => {
      let done = 0;
      for (const key of keys) {
        const row = allRowsRef.current.get(Number(key));
        const label = row ? `${row.name} (${row.code})` : `#${key}`;
        try {
          await deleteDeviceRow(Number(key));
          done += 1;
        } catch (error) {
          modal.warning({
            title: '批量删除未完成',
            content: `已删除 ${done} 条；“${label}”删除失败：${
              error instanceof Error ? error.message : '未知错误'
            }。后续 ${keys.length - done - 1} 条未执行。`,
          });
          actionRef.current?.reload();
          setSelectedRowKeys([]);
          return;
        }
      }
      messageApi.success(`成功删除 ${done} 条记录`);
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    },
    [messageApi, modal],
  );

  const connectionOptions = useMemo(
    () => connections.map((c) => ({ value: c.id, label: `${c.name} (${c.code})` })),
    [connections],
  );

  const columns = useMemo<ProColumns<DeviceRow>[]>(
    () => [
      { title: '编码', dataIndex: 'code', key: 'code', sorter: true, copyable: true, width: 140 },
      { title: '名称', dataIndex: 'name', key: 'name', sorter: true, ellipsis: true, minWidth: 140 },
      { title: '产品', dataIndex: 'product_id', key: 'product_id', hideInSearch: true, width: 160,
        render: (_, row) => row.product_id != null ? productLabelById.get(row.product_id) ?? `#${row.product_id}` : '—' },
      { title: 'MES 设备', dataIndex: 'equipment_uuid', key: 'equipment_uuid', hideInSearch: true, width: 160,
        render: (_, row) => row.equipment_uuid ? equipmentLabels.get(row.equipment_uuid) ?? row.equipment_uuid : '—' },
      {
        title: '外部标识',
        dataIndex: 'external_device_id',
        key: 'external_device_id',
        ellipsis: true,
        width: 140,
      },
      {
        title: '所属连接',
        dataIndex: 'connection_id',
        key: 'connection_id',
        valueType: 'select',
        fieldProps: { options: connectionOptions, showSearch: true, optionFilterProp: 'label' },
        width: 140,
        render: (_, row) =>
          row.connection_id != null ? connectionLabelById.get(row.connection_id) ?? `#${row.connection_id}` : '—',
      },
      {
        title: '分组',
        dataIndex: 'group_id',
        key: 'group_id',
        hideInSearch: true,
        width: 120,
        render: (_, row) =>
          row.group_id != null ? groupLabelById.get(row.group_id) ?? `#${row.group_id}` : '—',
      },
      {
        title: '在线状态',
        dataIndex: 'is_online',
        key: 'is_online',
        valueType: 'select',
        valueEnum: { true: { text: '在线' }, false: { text: '离线' } },
        width: 90,
        render: (_, row) => <OnlineTag online={row.is_online} />,
      },
      {
        title: '最近上报',
        dataIndex: 'last_seen_at',
        key: 'last_seen_at',
        sorter: true,
        hideInSearch: true,
        width: 160,
        render: (_, row) => fmtTime(row.last_seen_at),
      },
      {
        title: '创建时间',
        dataIndex: 'created_at',
        key: 'created_at',
        sorter: true,
        hideInSearch: true,
        width: 160,
        render: (_, row) => fmtTime(row.created_at),
      },
      {
        title: '操作',
        key: 'action',
        fixed: 'right',
        hideInSearch: true,
        render: (_, row) => [
          <Button
            key="detail"
            type="link"
            size="small"
            {...rowActionKind('display')}
            onClick={() => void openDetail(row)}
          >
            详情
          </Button>,
          ...(perms.canUpdate
            ? [
                <Button
                  key="edit"
                  type="link"
                  size="small"
                  {...rowActionKind('update')}
                  onClick={() => openEdit(row)}
                >
                  编辑
                </Button>,
                <Popconfirm
                  key="delete"
                  title="确定删除该设备？"
                  description="删除为软删除，点位与快照保留但不再写入"
                  onConfirm={() => void handleDelete(row)}
                >
                  <Button type="link" size="small" danger icon={<DeleteOutlined />} {...rowActionKind('skip')}>
                    删除
                  </Button>
                </Popconfirm>,
                <Dropdown
                  key="more"
                  {...rowActionKind('skip')}
                  trigger={['click']}
                  menu={{
                    items: [
                      {
                        key: 'rotate-token',
                        label: '轮换凭据',
                        onClick: () => {
                          modal.confirm({
                            title: '轮换设备凭据？',
                            content: '旧凭据立即失效；新凭据只在确认后的弹窗显示一次',
                            onOk: () => handleRotateToken(row),
                          });
                        },
                      },
                    ],
                  }}
                >
                  <Button type="link" size="small" icon={<MoreOutlined />}>
                    更多
                  </Button>
                </Dropdown>,
              ]
            : []),
        ],
      },
    ],
    [
      perms.canUpdate,
      connectionOptions,
      connectionLabelById,
      groupLabelById,
      productLabelById,
      equipmentLabels,
      openDetail,
      openEdit,
      handleDelete,
      handleRotateToken,
      modal,
    ],
  );

  const modalInitialValues = useMemo(() => {
    if (editing) {
      return {
        name: editing.name,
        connection_id: editing.connection_id ?? undefined,
        product_id: editing.product_id ?? undefined,
        equipment_uuid: editing.equipment_uuid ?? undefined,
        group_id: editing.group_id ?? undefined,
        remark: editing.remark ?? undefined,
      };
    }
    return {};
  }, [editing]);

  const handleFinish = useCallback(
    async (values: Record<string, any>) => {
      try {
        if (editing) {
          const payload: Record<string, unknown> = {
            name: String(values.name ?? '').trim(),
            connection_id: values.connection_id ?? null,
            product_id: values.product_id ?? null,
            group_id: values.group_id ?? null,
            // 备注可清空：空字符串也要下发，不能只带非空值
            remark: typeof values.remark === 'string' ? values.remark.trim() : '',
          };
          if (typeof values.equipment_uuid === 'string' && values.equipment_uuid.trim()) {
            payload.equipment_uuid = values.equipment_uuid.trim();
          } else if (editing.equipment_uuid) {
            payload.clear_equipment = true;
          }
          await updateDeviceRow(editing.id, payload);
          messageApi.success('更新成功');
        } else {
          const res = await createDeviceRow({
            connection_id: values.connection_id || undefined,
            external_device_id: String(values.external_device_id ?? '').trim(),
            code: String(values.code ?? '').trim(),
            name: String(values.name ?? '').trim(),
            equipment_uuid: values.equipment_uuid || undefined,
            product_id: values.product_id || undefined,
            group_id: values.group_id || undefined,
            template_code: values.template_code || undefined,
            remark: typeof values.remark === 'string' && values.remark.trim() ? values.remark.trim() : undefined,
          });
          showTokenOnce([{ code: res.code, name: res.name, device_token: res.device_token }], '设备已创建');
        }
        setModalOpen(false);
        actionRef.current?.reload();
      } catch (error) {
        messageApi.error(error instanceof Error ? error.message : '保存失败');
      }
    },
    [editing, messageApi, showTokenOnce],
  );

  const handleBatchCreate = useCallback(
    async (values: Record<string, any>) => {
      try {
        const rows = await batchCreateDevices({
          product_id: Number(values.product_id),
          name_prefix: String(values.name_prefix ?? '').trim(),
          code_prefix: String(values.code_prefix ?? '').trim(),
          count: Number(values.count),
        });
        setBatchOpen(false);
        actionRef.current?.reload();
        showTokenOnce(rows, `已批量创建 ${rows.length} 台设备`);
      } catch (error) {
        messageApi.error(error instanceof Error ? error.message : '批量创建失败');
      }
    },
    [messageApi, showTokenOnce],
  );

  const detailColumns = useMemo<ProDescriptionsItemProps<DeviceRow>[]>(
    () => [
      { title: '编码', dataIndex: 'code' },
      { title: '名称', dataIndex: 'name' },
      { title: '外部标识', dataIndex: 'external_device_id' },
      {
        title: '所属连接',
        dataIndex: 'connection_id',
        render: (_, row) =>
          row.connection_id != null
            ? connectionLabelById.get(row.connection_id) ?? `#${row.connection_id}`
            : '—',
      },
      {
        title: '产品模型',
        dataIndex: 'product_id',
        render: (_, row) =>
          row.product_id != null
            ? productLabelById.get(row.product_id) ?? `#${row.product_id}`
            : '—',
      },
      {
        title: '分组',
        dataIndex: 'group_id',
        render: (_, row) =>
          row.group_id != null ? groupLabelById.get(row.group_id) ?? `#${row.group_id}` : '—',
      },
      {
        title: 'MES 设备',
        dataIndex: 'equipment_uuid',
        render: (_, row) => row.equipment_uuid ? equipmentLabels.get(row.equipment_uuid) ?? row.equipment_uuid : '—',
      },
      {
        title: '在线状态',
        dataIndex: 'is_online',
        render: (_, row) => <OnlineTag online={row.is_online} />,
      },
      { title: '备注', dataIndex: 'remark', span: 2, render: (_, row) => row.remark || '—' },
      { title: '最近上报', dataIndex: 'last_seen_at', valueType: 'dateTime' },
      { title: '创建时间', dataIndex: 'created_at', valueType: 'dateTime' },
      { title: 'UUID', dataIndex: 'uuid' },
    ],
    [connectionLabelById, groupLabelById, productLabelById],
  );

  const table = (
    <UniTable<DeviceRow>
      actionRef={actionRef}
      rowKey="id"
      columns={alignIotTableColumns(columns, 'devices')}
      columnPersistenceId="kuaiiot-devices-v1"
      permissionResource="kuaiiot:device"
      showCreateButton
      createButtonText="新建设备"
      onCreate={openCreate}
      enableRowSelection
      selectedRowKeys={selectedRowKeys}
      onRowSelectionChange={setSelectedRowKeys}
      betweenFuzzyAndAdvancedButtons={
        isMobile ? (
          <Select
            style={{ minWidth: 140 }}
            value={selectedGroup}
            onChange={(v) => handleGroupSelect(v == null ? [GROUP_ALL] : [v])}
            options={groupOptions}
            placeholder="设备分组"
          />
        ) : undefined
      }
      toolBarActionsAfterCreate={[
        ...(perms.canCreate
          ? [
              <Button key="batch-create" onClick={() => setBatchOpen(true)}>
                批量新建
              </Button>,
            ]
          : []),
        ...(perms.canUpdate
          ? [
              <UniBatchDeleteButton
                key="batch-delete"
                selectedRowKeys={selectedRowKeys}
                onConfirm={handleBatchDelete}
                confirmTitle={(count) => `确定批量删除 ${count} 台设备？`}
                confirmDescription="逐条删除，任一失败即停止并报告明细"
              />,
            ]
          : []),
      ]}
      helpViewConfig={buildListPageHelpViewConfig('kuaiiot.devices')}
      defaultPageSize={20}
      request={async (params, sort, _filter, searchFormValues) => {
        try {
          const rows = await listDeviceRows();
          for (const row of rows) {
            allRowsRef.current.set(row.id, row);
          }
          let filtered = filterRowsByListKeyword(
            rows,
            pickListSearchKeyword(searchFormValues),
            (row) => [row.code, row.name, row.external_device_id],
          );
          const groupKey = groupFilterRef.current;
          if (groupKey === GROUP_NONE) {
            filtered = filtered.filter((row) => row.group_id == null);
          } else if (groupKey !== GROUP_ALL && groupKey != null) {
            filtered = filtered.filter((row) => row.group_id === Number(groupKey));
          }
          const connId = pickSearchString(searchFormValues, 'connection_id');
          if (connId) filtered = filtered.filter((row) => row.connection_id === Number(connId));
          const online = pickSearchTriStateBoolean(searchFormValues, 'is_online');
          if (online !== undefined) filtered = filtered.filter((row) => row.is_online === online);
          const sorted = sortRows(filtered, sort);
          const { current = 1, pageSize = 20 } = params;
          return {
            data: sorted.slice((current - 1) * pageSize, current * pageSize),
            success: true,
            total: sorted.length,
          };
        } catch (error) {
          messageApi.error(error instanceof Error ? error.message : '设备列表加载失败');
          return { data: [], success: false, total: 0 };
        }
      }}
    />
  );

  const sidebar = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {groupsError ? <Alert type="warning" showIcon message={`分组不可用：${groupsError}`} /> : null}
      <Tree
        blockNode
        defaultExpandAll
        treeData={groupTreeData}
        selectedKeys={[selectedGroup]}
        onSelect={(keys) => handleGroupSelect(keys as React.Key[])}
      />
    </div>
  );

  return (
    <ListPageTemplate fillMain>
      {isMobile ? (
        table
      ) : (
        <TwoColumnLayout
          style={{ flex: 1, minHeight: 0, height: '100%' }}
          layoutPersistenceId="kuaiiot.devices"
          leftPanel={{ leftContent: sidebar }}
          rightPanel={{ content: table, contentPadding: 0 }}
        />
      )}

      <FormModalTemplate
        title={editing ? '编辑设备' : '新建设备'}
        open={modalOpen}
        onOpenChange={setModalOpen}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        initialValues={modalInitialValues}
        form={deviceForm}
        onValuesChange={changed => { if (!editing && 'connection_id' in changed) deviceForm.setFieldValue('external_device_id', undefined); }}
        onFinish={handleFinish}
      >
        {editing ? (
          <>
            <ProFormText
              name="name"
              label="名称"
              rules={[{ required: true, message: '请填写名称' }]}
              fieldProps={{ maxLength: 100 }}
            />
            <Form.Item name="connection_id" label="数采连接" extra="清空并保存将解除当前绑定">
              <ConnectionSelect />
            </Form.Item>
            <Form.Item name="product_id" label="产品模型">
              <ProductSelect />
            </Form.Item>
            <Form.Item name="equipment_uuid" label="MES 设备" extra="清空并保存将解除当前绑定">
              <EquipmentSelect />
            </Form.Item>
            <Form.Item name="group_id" label="设备分组">
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                options={groups.map((g) => ({ value: g.id, label: `${g.name} (${g.code})` }))}
                placeholder="选择设备分组"
              />
            </Form.Item>
          </>
        ) : (
          <>
            <Form.Item name="connection_id" label="数采连接">
              <ConnectionSelect />
            </Form.Item>
            <ProFormDependency name={['connection_id']}>
              {({ connection_id }) => <Form.Item name="external_device_id" label="外部设备 ID" rules={[{ required: true, message: '请选择或填写外部设备标识' }]}>
                <ExternalDeviceInput connectionId={connection_id} connectionType={connections.find(row => row.id === Number(connection_id))?.connection_type} />
              </Form.Item>}
            </ProFormDependency>
            <ProFormText
              name="code"
              label="编码"
              rules={[{ required: true, message: '请填写编码' }]}
              fieldProps={{ maxLength: 50 }}
            />
            <ProFormText
              name="name"
              label="名称"
              rules={[{ required: true, message: '请填写名称' }]}
              fieldProps={{ maxLength: 100 }}
            />
            <Form.Item name="equipment_uuid" label="MES 设备">
              <EquipmentSelect />
            </Form.Item>
            <Form.Item name="product_id" label="产品模型" extra="创建时初始化产品点位；模板只补充产品未定义的点位">
              <ProductSelect />
            </Form.Item>
            <Form.Item name="group_id" label="设备分组">
              <Select allowClear showSearch optionFilterProp="label" options={groups.map(g => ({ value: g.id, label: `${g.name} (${g.code})` }))} placeholder="选择设备分组" />
            </Form.Item>
            <SafeProFormSelect
              name="template_code"
              label="点位模板"
              options={templates.map((t) => ({ value: t.code, label: `${t.name} (${t.code})` }))}
              fieldProps={{ allowClear: true, showSearch: true, optionFilterProp: 'label' }}
              placeholder="选择后立即生成该设备点位"
            />
          </>
        )}
        <ProFormTextArea name="remark" label="备注" fieldProps={{ rows: 2, maxLength: 500 }} />
      </FormModalTemplate>

      <FormModalTemplate
        title="批量新建设备"
        open={batchOpen}
        onOpenChange={setBatchOpen}
        width={MODAL_CONFIG.SMALL_WIDTH}
        onFinish={handleBatchCreate}
        submitText="创建"
      >
        <Form.Item
          name="product_id"
          label="产品模型"
          rules={[{ required: true, message: '请选择产品模型' }]}
        >
          <ProductSelect />
        </Form.Item>
        <ProFormText
          name="name_prefix"
          label="名称前缀"
          rules={[{ required: true, message: '请填写名称前缀' }]}
          fieldProps={{ maxLength: 80 }}
        />
        <ProFormText
          name="code_prefix"
          label="编码前缀"
          rules={[{ required: true, message: '请填写编码前缀' }]}
          fieldProps={{ maxLength: 40 }}
        />
        <ProFormDigit
          name="count"
          label="数量"
          min={1}
          max={100}
          rules={[{ required: true, message: '请填写数量（1-100）' }]}
          fieldProps={{ precision: 0 }}
        />
      </FormModalTemplate>

      <DetailDrawerTemplate
        title={detail ? `设备：${detail.name}` : '设备详情'}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        size={DRAWER_CONFIG.SMALL_WIDTH}
        loading={detailLoading}
        columns={detailColumns}
        dataSource={detail ?? undefined}
        column={2}
      >
        <DetailDrawerSection title="最新快照">
          {snapshotsLoading ? (
            <div style={{ textAlign: 'center', padding: '24px 0' }}>
              <Spin />
            </div>
          ) : snapshotsError ? (
            <Alert type="warning" showIcon message={`快照不可用：${snapshotsError}`} />
          ) : (
            <Table
              size="small"
              rowKey="id"
              pagination={false}
              scroll={{ x: 'max-content' }}
              dataSource={snapshots}
              locale={{
                emptyText: (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无快照" />
                ),
              }}
              columns={[
                { title: '点位键', dataIndex: 'tag_key' },
                {
                  title: '值',
                  key: 'value',
                  render: (_: unknown, row: SnapshotOut) => snapshotValueText(row),
                },
                { title: '质量', dataIndex: 'quality', width: 90 },
                {
                  title: '采样时间',
                  dataIndex: 'sampled_at',
                  width: 170,
                  render: (value: string) => fmtTime(value),
                },
              ]}
            />
          )}
        </DetailDrawerSection>
        <DetailDrawerSection title="OEE 计算依据">
          {!detail?.equipment_uuid ? (
            <Typography.Text type="secondary">
              该设备未绑定 MES 设备，无法维护 OEE 计算依据；请先在「编辑」中绑定 MES 设备。
            </Typography.Text>
          ) : (
            <Spin spinning={oeeLoading}>
              <Typography.Paragraph type="secondary">
                维护理想节拍和实际计划生产窗口。两端按同一口径计算；计划时间不使用默认每天 8
                小时。保存需要制造设备编辑权限。
              </Typography.Paragraph>
              <Form form={oeeForm} layout="vertical" onFinish={(values) => void handleSaveOee(values)}>
                <Form.Item
                  name="ideal_cycle_seconds"
                  label="理想节拍（秒/件）"
                  rules={[{ required: true, message: '请填写理想节拍' }]}
                >
                  <InputNumber min={0.001} style={{ width: '100%' }} />
                </Form.Item>
                <Form.List name="planned_windows">
                  {(fields, { add, remove }) => (
                    <>
                      {fields.map((field) => (
                        <Space key={field.key} align="baseline">
                          <Form.Item
                            name={[field.name, 'range']}
                            label="计划生产窗口"
                            rules={[{ required: true, message: '请选择计划生产窗口' }]}
                          >
                            <DatePicker.RangePicker showTime />
                          </Form.Item>
                          <Button onClick={() => remove(field.name)}>移除</Button>
                        </Space>
                      ))}
                      <Button onClick={() => add()}>添加计划窗口</Button>
                    </>
                  )}
                </Form.List>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={oeeSaving}
                  style={{ marginTop: 16 }}
                >
                  保存计算依据
                </Button>
              </Form>
            </Spin>
          )}
        </DetailDrawerSection>
      </DetailDrawerTemplate>
    </ListPageTemplate>
  );
};

export default DevicesPage;
