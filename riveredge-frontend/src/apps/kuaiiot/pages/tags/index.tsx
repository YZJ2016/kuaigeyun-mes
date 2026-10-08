/**
 * 点位映射：跨设备点位运营列表页。
 * 新建/编辑通过 DeviceSelect 选择设备，不再要求先在本页登记设备。
 * 读操作要求 kuaiiot:tag:display，写操作仍要求 kuaiiot:tag:create；
 * 行内写按钮用 rowActionKind('skip') + 显式权限判断（manifest 无 :update/:delete）。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  ActionType,
  ProColumns,
  ProDescriptionsItemProps,
} from '@ant-design/pro-components';
import { ProFormSwitch, ProFormText } from '@ant-design/pro-components';
import { App, Button, Form, Input, Popconfirm, Result, AutoComplete, Tag } from 'antd';
import { UniTable } from '../../../../components/uni-table';
import { rowActionKind } from '../../../../components/uni-action';
import { UniBatchDeleteButton } from '../../../../components/uni-batch';
import {
  DetailDrawerTemplate,
  DRAWER_CONFIG,
  FormModalTemplate,
  ListPageTemplate,
  MODAL_CONFIG,
} from '../../../../components/layout-templates';
import SafeProFormSelect from '../../../../components/safe-pro-form-select';
import { buildListPageHelpViewConfig } from '../../../../components/page-help-wiki';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import {
  extractProTableSort,
  filterRowsByListKeyword,
  pickListSearchKeyword,
  pickSearchString,
  pickSearchTriStateBoolean,
} from '../../../../utils/tableQueryKey';
import { listDevices, type DeviceOut } from '../../services/kuaiiot';
import { DeviceSelect } from '../../components/entity-selects';
import { ValueTypeTag } from '../../components/status-tags';
import {
  createTagRow,
  deleteTagRow,
  getTagRow,
  listTagRows,
  updateTagRow,
  type TagRow,
} from './api';

const VALUE_TYPE_OPTIONS = [
  { value: 'number', label: '数值 number' },
  { value: 'boolean', label: '布尔 boolean' },
  { value: 'text', label: '文本 text' },
];

const MAP_TARGET_OPTIONS = [
  { value: 'status', label: '设备状态 status' },
  { value: 'is_online', label: '在线状态 is_online' },
  { value: 'temperature', label: '温度 temperature' },
  { value: 'pressure', label: '压力 pressure' },
  { value: 'vibration', label: '振动 vibration' },
];

function sortRows(rows: TagRow[], sort: Record<string, 'ascend' | 'descend' | null>) {
  const { sortBy, sortOrder } = extractProTableSort(sort);
  const sorted = [...rows].sort((a, b) => {
    const av = (a as Record<string, unknown>)[sortBy ?? 'tag_key'];
    const bv = (b as Record<string, unknown>)[sortBy ?? 'tag_key'];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    return String(av).localeCompare(String(bv), 'zh-CN');
  });
  return sortOrder === 'asc' ? sorted : sorted.reverse();
}

/** map_target 允许标准监控字段或 other_parameters.<key>；兼容旧表单数组值。 */
function normalizeMapTarget(value: unknown): string {
  if (Array.isArray(value)) return String(value[value.length - 1] ?? '').trim();
  return String(value ?? '').trim();
}

const TagsPage: React.FC = () => {
  const { message: messageApi, modal } = App.useApp();
  const perms = useResourcePermissions('kuaiiot:tag');
  const canDisplay = perms.canAction?.('display') ?? false;
  const canWrite = perms.canCreate;
  const actionRef = useRef<ActionType>();
  /** 跨页批量删除解析：request 内增量累积（只增不覆盖），不依赖当前展示页。 */
  const allRowsRef = useRef<Map<number, TagRow>>(new Map());

  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [devices, setDevices] = useState<DeviceOut[]>([]);
  const [devicesError, setDevicesError] = useState<string>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<TagRow | null>(null);
  const [detail, setDetail] = useState<TagRow | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listDevices()
      .then((rows) => {
        if (!cancelled) setDevices(Array.isArray(rows) ? rows : []);
      })
      .catch((error) => {
        if (!cancelled) {
          setDevicesError(error instanceof Error ? error.message : '设备列表加载失败');
          setDevices([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const deviceLabelById = useMemo(() => {
    const map = new Map<number, string>();
    for (const d of devices) map.set(d.id, `${d.name} (${d.code})`);
    return map;
  }, [devices]);

  const deviceOptions = useMemo(
    () => devices.map((d) => ({ value: d.id, label: `${d.name} (${d.code})` })),
    [devices],
  );

  const openCreate = useCallback(() => {
    setEditing(null);
    setModalOpen(true);
  }, []);

  const openEdit = useCallback((row: TagRow) => {
    setEditing(row);
    setModalOpen(true);
  }, []);

  const openDetail = useCallback(
    async (row: TagRow) => {
      setDetail(row);
      setDetailOpen(true);
      setDetailLoading(true);
      try {
        setDetail(await getTagRow(row.id));
      } catch (error) {
        messageApi.error(error instanceof Error ? error.message : '读取点位详情失败');
      } finally {
        setDetailLoading(false);
      }
    },
    [messageApi],
  );

  const handleDelete = useCallback(
    async (row: TagRow) => {
      try {
        await deleteTagRow(row.id);
        messageApi.success('删除成功');
        setSelectedRowKeys((keys) => keys.filter((k) => k !== row.id));
        actionRef.current?.reload();
      } catch (error) {
        messageApi.error(error instanceof Error ? error.message : '删除失败');
      }
    },
    [messageApi],
  );

  /** 批删串行执行：任一失败即停止，报告成功数与失败明细；跨页选中行从 allRowsRef 解析名称。 */
  const handleBatchDelete = useCallback(
    async (keys: React.Key[]) => {
      let done = 0;
      for (const key of keys) {
        const row = allRowsRef.current.get(Number(key));
        const label = row ? `${row.name} (${row.tag_key})` : `#${key}`;
        try {
          await deleteTagRow(Number(key));
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

  const columns = useMemo<ProColumns<TagRow>[]>(
    () => [
      {
        title: '所属设备',
        dataIndex: 'device_id',
        key: 'device_id',
        valueType: 'select',
        fieldProps: { options: deviceOptions, showSearch: true, optionFilterProp: 'label' },
        width: 160,
        render: (_, row) => deviceLabelById.get(row.device_id) ?? `#${row.device_id}`,
      },
      { title: '点位 Key', dataIndex: 'tag_key', key: 'tag_key', sorter: true, copyable: true, width: 140 },
      { title: '名称', dataIndex: 'name', key: 'name', sorter: true, ellipsis: true, minWidth: 140 },
      {
        title: '值类型',
        dataIndex: 'value_type',
        key: 'value_type',
        valueType: 'select',
        valueEnum: { number: { text: '数值' }, boolean: { text: '布尔' }, text: { text: '文本' } },
        width: 90,
        render: (_, row) => <ValueTypeTag value={row.value_type} />,
      },
      {
        title: '写回目标',
        dataIndex: 'map_target',
        key: 'map_target',
        valueType: 'select',
        fieldProps: { options: MAP_TARGET_OPTIONS, showSearch: true },
        ellipsis: true,
        width: 160,
      },
      { title: '单位', dataIndex: 'unit', key: 'unit', hideInSearch: true, width: 80 },
      {
        title: '填充目标',
        dataIndex: 'fill_target',
        key: 'fill_target',
        hideInSearch: true,
        ellipsis: true,
        width: 160,
        render: (_, row) => row.fill_target || '—',
      },
      {
        title: '启用',
        dataIndex: 'is_enabled',
        key: 'is_enabled',
        valueType: 'select',
        valueEnum: { true: { text: '启用' }, false: { text: '停用' } },
        width: 80,
        render: (_, row) => (row.is_enabled ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>),
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
          ...(canWrite
            ? [
                <Button
                  key="edit"
                  type="link"
                  size="small"
                  {...rowActionKind('skip')}
                  onClick={() => openEdit(row)}
                >
                  编辑
                </Button>,
                <Popconfirm
                  key="delete"
                  title="确定删除该点位？"
                  onConfirm={() => void handleDelete(row)}
                >
                  <Button type="link" size="small" danger {...rowActionKind('skip')}>
                    删除
                  </Button>
                </Popconfirm>,
              ]
            : []),
        ],
      },
    ],
    [canWrite, deviceOptions, deviceLabelById, openDetail, openEdit, handleDelete],
  );

  const modalInitialValues = useMemo(() => {
    if (editing) {
      return {
        name: editing.name,
        value_type: editing.value_type,
        unit: editing.unit ?? undefined,
        map_target: editing.map_target || undefined,
        fill_target: editing.fill_target ?? undefined,
        is_enabled: editing.is_enabled,
      };
    }
    return { value_type: 'number', map_target: 'temperature', is_enabled: true };
  }, [editing]);

  const handleFinish = useCallback(
    async (values: Record<string, any>) => {
      const mapTarget = normalizeMapTarget(values.map_target);
      try {
        if (editing) {
          await updateTagRow(editing.id, {
            name: String(values.name ?? '').trim(),
            value_type: values.value_type,
            unit: typeof values.unit === 'string' && values.unit.trim() ? values.unit.trim() : null,
            map_target: mapTarget,
            fill_target:
              typeof values.fill_target === 'string' && values.fill_target.trim()
                ? values.fill_target.trim()
                : null,
            is_enabled: Boolean(values.is_enabled),
          });
          messageApi.success('更新成功');
        } else {
          await createTagRow(Number(values.device_id), {
            tag_key: String(values.tag_key ?? '').trim(),
            name: String(values.name ?? '').trim(),
            value_type: values.value_type,
            unit: typeof values.unit === 'string' && values.unit.trim() ? values.unit.trim() : undefined,
            map_target: mapTarget,
            fill_target:
              typeof values.fill_target === 'string' && values.fill_target.trim()
                ? values.fill_target.trim()
                : undefined,
            is_enabled: Boolean(values.is_enabled ?? true),
          });
          messageApi.success('创建成功');
        }
        setModalOpen(false);
        actionRef.current?.reload();
      } catch (error) {
        messageApi.error(error instanceof Error ? error.message : '保存失败');
      }
    },
    [editing, messageApi],
  );

  const detailColumns = useMemo<ProDescriptionsItemProps<TagRow>[]>(
    () => [
      {
        title: '所属设备',
        dataIndex: 'device_id',
        render: (_, row) => deviceLabelById.get(row.device_id) ?? `#${row.device_id}`,
      },
      { title: '点位 Key', dataIndex: 'tag_key' },
      { title: '名称', dataIndex: 'name' },
      {
        title: '值类型',
        dataIndex: 'value_type',
        render: (_, row) => <ValueTypeTag value={row.value_type} />,
      },
      { title: '写回目标', dataIndex: 'map_target' },
      { title: '单位', dataIndex: 'unit', render: (_, row) => row.unit || '—' },
      { title: '填充目标', dataIndex: 'fill_target', render: (_, row) => row.fill_target || '—' },
      {
        title: '启用',
        dataIndex: 'is_enabled',
        render: (_, row) => (row.is_enabled ? '启用' : '停用'),
      },
      { title: 'UUID', dataIndex: 'uuid' },
    ],
    [deviceLabelById],
  );

  if (!canDisplay) {
    return <Result status="403" title="无权限查看点位映射" />;
  }

  return (
    <ListPageTemplate>
      <UniTable<TagRow>
        actionRef={actionRef}
        rowKey="id"
        columns={columns}
        columnPersistenceId="kuaiiot-tags-v1"
        permissionResource="kuaiiot:tag"
        showCreateButton
        createButtonText="新建点位映射"
        onCreate={openCreate}
        enableRowSelection
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        toolBarActionsAfterCreate={
          canWrite
            ? [
                <UniBatchDeleteButton
                  key="batch-delete"
                  selectedRowKeys={selectedRowKeys}
                  onConfirm={handleBatchDelete}
                  confirmTitle={(count) => `确定批量删除 ${count} 条点位？`}
                  confirmDescription="逐条删除，任一失败即停止并报告明细"
                />,
              ]
            : []
        }
        helpViewConfig={buildListPageHelpViewConfig('kuaiiot.tags')}
        defaultPageSize={20}
        request={async (params, sort, _filter, searchFormValues) => {
          try {
            const deviceParam = pickSearchString(searchFormValues, 'device_id');
            const rows = await listTagRows(deviceParam ? Number(deviceParam) : undefined);
            for (const row of rows) {
              allRowsRef.current.set(row.id, row);
            }
            let filtered = filterRowsByListKeyword(
              rows,
              pickListSearchKeyword(searchFormValues),
              (row) => [
                row.tag_key,
                row.name,
                row.map_target,
                deviceLabelById.get(row.device_id),
              ],
            );
            if (deviceParam) {
              filtered = filtered.filter((row) => row.device_id === Number(deviceParam));
            }
            const valueType = pickSearchString(searchFormValues, 'value_type');
            if (valueType) filtered = filtered.filter((row) => row.value_type === valueType);
            const mapTarget = pickSearchString(searchFormValues, 'map_target');
            if (mapTarget) filtered = filtered.filter((row) => row.map_target === mapTarget);
            const enabled = pickSearchTriStateBoolean(searchFormValues, 'is_enabled');
            if (enabled !== undefined) filtered = filtered.filter((row) => row.is_enabled === enabled);
            const sorted = sortRows(filtered, sort);
            const { current = 1, pageSize = 20 } = params;
            return {
              data: sorted.slice((current - 1) * pageSize, current * pageSize),
              success: true,
              total: sorted.length,
            };
          } catch (error) {
            messageApi.error(error instanceof Error ? error.message : '点位列表加载失败');
            return { data: [], success: false, total: 0 };
          }
        }}
      />

      {devicesError ? (
        <div style={{ marginTop: 8 }}>
          <Tag color="orange">{`设备数据不可用：${devicesError}；所属设备按编号显示`}</Tag>
        </div>
      ) : null}

      <FormModalTemplate
        title={editing ? '编辑点位映射' : '新建点位映射'}
        open={modalOpen}
        onOpenChange={setModalOpen}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        initialValues={modalInitialValues}
        onFinish={handleFinish}
      >
        {!editing ? (
          <>
            <Form.Item
              name="device_id"
              label="所属设备"
              rules={[{ required: true, message: '请选择 IoT 设备' }]}
            >
              <DeviceSelect />
            </Form.Item>
            <Form.Item name="tag_key" label="点位 Key" rules={[{ required: true, message: '请填写点位键' }]}>
              <AutoComplete options={Array.from(new Set(Array.from(allRowsRef.current.values()).map(row => row.tag_key))).map(value => ({ value }))} placeholder="选择或输入点位 Key"><Input maxLength={100} /></AutoComplete>
            </Form.Item>
          </>
        ) : null}
        <ProFormText
          name="name"
          label="名称"
          rules={[{ required: true, message: '请填写名称' }]}
          fieldProps={{ maxLength: 100 }}
        />
        <SafeProFormSelect
          name="value_type"
          label="值类型"
          options={VALUE_TYPE_OPTIONS}
          rules={[{ required: true, message: '请选择值类型' }]}
        />
        <Form.Item
          name="map_target"
          label="写回目标"
          rules={[{ required: true, message: '请选择或输入映射目标' }]}
          extra="选择监控字段，或输入 other_parameters.<字段名> 写入其他参数"
        >
          <AutoComplete
            allowClear
            options={MAP_TARGET_OPTIONS}
            placeholder="选择或输入 other_parameters.xxx"
          />
        </Form.Item>
        <Form.Item name="fill_target" label="填充目标" extra="可选；输入 spot_check.<项编码> 或 sop_parameters.<字段>">
          <AutoComplete options={Array.from(new Set(Array.from(allRowsRef.current.values()).map(row => row.fill_target).filter((value): value is string => Boolean(value)))).map(value => ({ value }))} placeholder="选择或输入填充目标"><Input maxLength={100} /></AutoComplete>
        </Form.Item>
        <ProFormText
          name="unit"
          label="单位"
          fieldProps={{ maxLength: 30, placeholder: '可空，如 ℃ / kPa' }}
        />
        <ProFormSwitch name="is_enabled" label="启用" />
      </FormModalTemplate>

      <DetailDrawerTemplate
        title={detail ? `点位：${detail.name}` : '点位详情'}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        size={DRAWER_CONFIG.SMALL_WIDTH}
        loading={detailLoading}
        columns={detailColumns}
        dataSource={detail ?? undefined}
        column={2}
      />
    </ListPageTemplate>
  );
};

export default TagsPage;
