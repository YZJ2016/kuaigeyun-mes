import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns, ProDescriptionsItemProps } from '@ant-design/pro-components';
import { Line } from '@ant-design/charts';
import {
  CompressOutlined,
  ExpandOutlined,
  FolderFilled,
  FolderOpenFilled,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { AutoComplete, Button, Drawer, Form, Input, InputNumber, Modal, Select, Space, Table, Tabs, Tooltip, Typography, message } from 'antd';
import type { DataNode, TreeProps } from 'antd/es/tree';
import { useTranslation } from 'react-i18next';
import { rowActionKind, rowActionLabelKeep } from '../../../../components/uni-action';
import { TwoColumnLayout } from '../../../../components/layout-templates';
import { LIST_PAGE_TABLE_SCROLL } from '../../../../components/layout-templates/constants';
import { UniTable } from '../../../../components/uni-table';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { API_BASE_URL } from '../../../../services/api';
import { formatDateTimeBySiteSetting } from '../../../../utils/format';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { buildDetailDrawerEditExtra } from '../../../kuaizhizao/pages/equipment-management/shared/equipmentMasterDataDetail';
import { IOT_LIST_COL, renderIotOnlineMarker } from '../../utils/iotListPresentation';
import { IotMasterDetailDrawer } from '../shared/iotMasterDetailDrawer';
import {
  batchCreateDevices,
  createDevice,
  createDeviceCommand,
  createDeviceGroup,
  deleteDevice,
  ingestDeviceData,
  listConnectionDiscoveredDevices,
  listAllDiscoveredMqttDevices,
  listConnections,
  listDeviceCommands,
  listDeviceGroupsTree,
  listDeviceHistory,
  listDeviceMessageLogs,
  listDeviceSnapshots,
  listDevices,
  listEquipmentOptions,
  listProducts,
  listTags,
  rotateDeviceToken,
  updateDevice,
  type Connection,
  type Device,
  type DeviceBatchItem,
  type DeviceCommand,
  type DeviceGroup,
  type DiscoveredMqttDevice,
  type MessageLog,
  type Product,
  type TagDefinition,
  type TagHistory,
  type TagSnapshot,
  type TagTemplate,
} from '../../services/kuaiiot';
import { getAntdModal } from '../../../../utils/antdAppApis';
import { buildListPageHelpViewConfig } from '../../../../components/page-help-wiki';

const formatTagValue = (row: TagSnapshot | TagHistory) => {
  if (row.value_text != null && row.value_text !== '') return row.value_text;
  if (row.value_number != null) return String(row.value_number);
  if (row.value_bool != null) return row.value_bool ? 'true' : 'false';
  return '-';
};

const DEVICE_GROUP_FOLDER_ICON_STYLE = { fontSize: 16, verticalAlign: 'middle' } as const;
const DEVICE_GROUP_FOLDER_COLOR_CLOSED = '#e8b347';
const DEVICE_GROUP_FOLDER_COLOR_OPEN = '#d4a028';

function renderDeviceGroupFolderIcon(props: { expanded: boolean; isLeaf: boolean }) {
  if (!props.isLeaf && props.expanded) {
    return (
      <FolderOpenFilled
        style={{ ...DEVICE_GROUP_FOLDER_ICON_STYLE, color: DEVICE_GROUP_FOLDER_COLOR_OPEN }}
      />
    );
  }
  return (
    <FolderFilled style={{ ...DEVICE_GROUP_FOLDER_ICON_STYLE, color: DEVICE_GROUP_FOLDER_COLOR_CLOSED }} />
  );
}

const collectTreeKeys = (nodes: DataNode[]): React.Key[] =>
  nodes.flatMap((node) => [node.key, ...(node.children?.length ? collectTreeKeys(node.children) : [])]);

const filterTreeByKeyword = (nodes: DataNode[], keyword: string): DataNode[] => {
  const q = keyword.trim().toLowerCase();
  if (!q) return nodes;
  const walk = (items: DataNode[]): DataNode[] =>
    items
      .map((node) => {
        const title = String(node.title ?? '').toLowerCase();
        const children = node.children ? walk(node.children) : [];
        if (title.includes(q) || children.length > 0) {
          return { ...node, children: children.length > 0 ? children : undefined };
        }
        return null;
      })
      .filter((node): node is DataNode => node != null);
  return walk(nodes);
};

const flattenGroups = (groups: DeviceGroup[], prefix = ''): { label: string; value: number }[] =>
  groups.flatMap((group) => {
    const label = prefix ? `${prefix} / ${group.name}` : group.name;
    const current = [{ label, value: group.id }];
    const children = group.children?.length ? flattenGroups(group.children, label) : [];
    return [...current, ...children];
  });

const normalizeDeviceName = (name?: string) =>
  (name || '').replace(/[\s/\\_-]+/g, '').toLowerCase();

const matchMqttByMesName = (
  devices: DiscoveredMqttDevice[],
  mesName?: string,
  mesCode?: string,
) => {
  if (!devices.length) return undefined;
  const name = (mesName || '').trim();
  const code = (mesCode || '').trim();
  if (name) {
    const exact = devices.find((item) => item.device_name === name);
    if (exact) return exact;
    const normalized = normalizeDeviceName(name);
    if (normalized.length >= 2) {
      const fuzzy = devices.find((item) => {
        const deviceName = normalizeDeviceName(item.device_name);
        return (
          deviceName.length >= 2 &&
          (deviceName === normalized || deviceName.includes(normalized) || normalized.includes(deviceName))
        );
      });
      if (fuzzy) return fuzzy;
    }
  }
  if (code) {
    return devices.find(
      (item) => item.device_key === code || item.external_device_id === code,
    );
  }
  return undefined;
};

const buildDeviceCodeFromMqtt = (device: DiscoveredMqttDevice) => {
  const source = (device.device_key || device.device_name || device.external_device_id).trim();
  const slug = source
    .replace(/[^\w\u4e00-\u9fff-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 40);
  if (slug) return slug;
  return device.external_device_id.slice(0, 36);
};

const buildGroupTreeData = (groups: DeviceGroup[]): DataNode[] =>
  groups.map((group) => ({
    key: String(group.id),
    title: group.name,
    children: group.children?.length ? buildGroupTreeData(group.children) : undefined,
  }));

const DevicesPage: React.FC = () => {
  const { t } = useTranslation();
  const perms = useResourcePermissions('kuaiiot:device');
  const groupPerms = useResourcePermissions('kuaiiot:device-group');
  const actionRef = useRef<ActionType>();
  const [form] = Form.useForm();
  const [batchForm] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchResult, setBatchResult] = useState<DeviceBatchItem[]>([]);
  const [editing, setEditing] = useState<Device | null>(null);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [detail, setDetail] = useState<Device | null>(null);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [equipmentOptions, setEquipmentOptions] = useState<
    { label: string; value: string; name?: string; code?: string }[]
  >([]);
  const [discoveredDevices, setDiscoveredDevices] = useState<DiscoveredMqttDevice[]>([]);
  const [discoveredLoading, setDiscoveredLoading] = useState(false);
  const watchedConnectionId = Form.useWatch('connection_id', form);
  const [tagTemplates, setTagTemplates] = useState<TagTemplate[]>([]);
  const [dataOpen, setDataOpen] = useState(false);
  const [debugOpen, setDebugOpen] = useState(false);
  const [dataDevice, setDataDevice] = useState<Device | null>(null);
  const [snapshots, setSnapshots] = useState<TagSnapshot[]>([]);
  const [history, setHistory] = useState<TagHistory[]>([]);
  const [deviceTags, setDeviceTags] = useState<TagDefinition[]>([]);
  const [trendTagKey, setTrendTagKey] = useState<string>();
  const [trendHistory, setTrendHistory] = useState<TagHistory[]>([]);
  const [tsdbConfigured, setTsdbConfigured] = useState(false);
  const [dataLoading, setDataLoading] = useState(false);
  const [debugPayload, setDebugPayload] = useState('{\n  "tags": {}\n}');
  const [debugResponse, setDebugResponse] = useState<string>('');
  const [groupTree, setGroupTree] = useState<DeviceGroup[]>([]);
  const [selectedGroupKeys, setSelectedGroupKeys] = useState<React.Key[]>(['all']);
  const [groupSearchValue, setGroupSearchValue] = useState('');
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>(['all']);
  const [leftPanelCollapsed, setLeftPanelCollapsed] = useState(false);
  const [groupModalOpen, setGroupModalOpen] = useState(false);
  const [groupForm] = Form.useForm();
  const [commands, setCommands] = useState<DeviceCommand[]>([]);
  const [messageLogs, setMessageLogs] = useState<MessageLog[]>([]);
  const [commandForm] = Form.useForm();
  const [selectedFunctionKey, setSelectedFunctionKey] = useState<string>();
  const hasGroupSelectionInitializedRef = useRef(false);

  const selectedGroupId = useMemo(() => {
    const key = selectedGroupKeys[0];
    if (!key || key === 'all') return undefined;
    return Number(key);
  }, [selectedGroupKeys]);

  const groupTreeData = useMemo<DataNode[]>(
    () => [{ key: 'all', title: t('app.kuaiiot.option.allGroups'), children: buildGroupTreeData(groupTree) }],
    [groupTree, t],
  );

  const filteredGroupTreeData = useMemo(
    () => filterTreeByKeyword(groupTreeData, groupSearchValue),
    [groupTreeData, groupSearchValue],
  );

  const reloadGroupTree = useCallback(async () => {
    const groupRes = await listDeviceGroupsTree().catch(() => ({ items: [] }));
    setGroupTree(groupRes.items || []);
  }, []);

  const equipmentLabelMap = useMemo(
    () => Object.fromEntries(equipmentOptions.map((item) => [item.value, item.label])),
    [equipmentOptions],
  );
  const productLabelMap = useMemo(
    () => Object.fromEntries(products.map((item) => [item.id, `${item.code} - ${item.name}`])),
    [products],
  );
  const groupLabelMap = useMemo(
    () => Object.fromEntries(flattenGroups(groupTree).map((item) => [item.value, item.label])),
    [groupTree],
  );
  const numberTags = useMemo(() => deviceTags.filter((item) => item.value_type === 'number'), [deviceTags]);
  const detailColumns = useMemo<ProDescriptionsItemProps<Device>[]>(
    () => [
      { title: t('common.code'), dataIndex: 'code', copyable: true },
      { title: t('common.name'), dataIndex: 'name' },
      { title: t('app.kuaiiot.field.externalId'), dataIndex: 'external_device_id' },
      {
        title: t('app.kuaiiot.field.online'),
        dataIndex: 'is_online',
        render: (_, row) => renderIotOnlineMarker(t, row.is_online),
      },
      {
        title: t('app.kuaiiot.field.equipment'),
        dataIndex: 'equipment_uuid',
        render: (_, row) => equipmentLabelMap[row.equipment_uuid || ''] || row.equipment_uuid || '-',
      },
      {
        title: t('app.kuaiiot.field.lastSeen'),
        dataIndex: 'last_seen_at',
        render: (_, row) => (row.last_seen_at ? formatDateTimeBySiteSetting(row.last_seen_at) : '-'),
      },
      { title: t('common.remark'), dataIndex: 'remark' },
    ],
    [equipmentLabelMap, t],
  );
  const currentProduct = useMemo(
    () => products.find((item) => item.id === dataDevice?.product_id),
    [products, dataDevice?.product_id],
  );
  const functionOptions = useMemo(
    () => (currentProduct?.functions || []).map((item) => ({ label: item.name, value: item.function_key })),
    [currentProduct],
  );
  const selectedFunction = useMemo(
    () => currentProduct?.functions?.find((item) => item.function_key === selectedFunctionKey),
    [currentProduct, selectedFunctionKey],
  );

  const reloadFormOptions = useCallback(async () => {
    const [connRes, eqOptions, productRes] = await Promise.all([
      listConnections({ page: 1, page_size: 200 }).catch(() => ({ items: [] as Connection[], total: 0 })),
      listEquipmentOptions().catch(() => []),
      listProducts({ page: 1, page_size: 200 }).catch(() => ({ items: [] as Product[], total: 0 })),
    ]);
    setConnections(connRes.items || []);
    setEquipmentOptions(eqOptions || []);
    setProducts(productRes.items || []);
    await reloadGroupTree();
  }, [reloadGroupTree]);

  useEffect(() => {
    void reloadFormOptions();
  }, [reloadFormOptions]);

  useEffect(() => {
    if (!hasGroupSelectionInitializedRef.current) {
      hasGroupSelectionInitializedRef.current = true;
      return;
    }
    actionRef.current?.reload();
  }, [selectedGroupKeys]);

  const loadDiscoveredDevices = useCallback(
    async (connectionId?: number) => {
      setDiscoveredLoading(true);
      try {
        if (connectionId) {
          const connection = connections.find((item) => item.id === connectionId);
          if (connection?.connection_type === 'mqtt') {
            const res = await listConnectionDiscoveredDevices(connection.uuid, 50);
            const items = res.items || [];
            setDiscoveredDevices(items);
            return items;
          }
        }
        const res = await listAllDiscoveredMqttDevices(200);
        const items = res.items || [];
        setDiscoveredDevices(items);
        return items;
    } catch (error) {
        setDiscoveredDevices([]);
        message.warning(t('app.kuaiiot.message.mqttDevicePickEmpty'));
        return [] as DiscoveredMqttDevice[];
      } finally {
        setDiscoveredLoading(false);
      }
    },
    [connections],
  );

  useEffect(() => {
    if (!open) return;
    void loadDiscoveredDevices(watchedConnectionId);
  }, [open, watchedConnectionId, loadDiscoveredDevices]);

  const mqttDeviceOptions = useMemo(
    () =>
      discoveredDevices.map((item) => ({
        label: item.already_bound
          ? `${item.label}${t('app.kuaiiot.option.mqttDeviceBoundSuffix')}`
          : item.label,
        value: item.external_device_id,
        disabled: Boolean(item.already_bound && item.external_device_id !== editing?.external_device_id),
      })),
    [discoveredDevices, editing?.external_device_id, t],
  );

  const applyMqttDevice = (device: DiscoveredMqttDevice, fillIdentity: boolean) => {
    const remarkParts = [device.workshop_name, device.line_name].filter(Boolean);
    const next: Record<string, unknown> = {
      external_device_id: device.external_device_id,
    };
    if (device.connection_id) next.connection_id = device.connection_id;
    if (fillIdentity) {
      if (!form.getFieldValue('name') || !editing) {
        next.name = device.device_name || form.getFieldValue('name');
      }
      if (!editing && !form.getFieldValue('code')) {
        next.code = buildDeviceCodeFromMqtt(device);
      }
      if (remarkParts.length && !form.getFieldValue('remark')) {
        next.remark = remarkParts.join(' / ');
      }
    }
    form.setFieldsValue(next);
  };

  const handleMqttDevicePick = (externalId?: string) => {
    if (!externalId) return;
    const device = discoveredDevices.find((item) => item.external_device_id === externalId);
    if (!device) return;
    applyMqttDevice(device, !form.getFieldValue('equipment_uuid'));
  };

  const handleMesEquipmentPick = async (equipmentUuid?: string) => {
    if (!equipmentUuid) return;
    const eq = equipmentOptions.find((item) => item.value === equipmentUuid);
    if (!eq) return;
    const next: Record<string, string> = {};
    if (eq.name) next.name = eq.name;
    if (!editing && eq.code) next.code = eq.code;
    if (Object.keys(next).length) form.setFieldsValue(next);

    const devices = discoveredDevices.length
      ? discoveredDevices
      : await loadDiscoveredDevices(form.getFieldValue('connection_id'));
    const matched = matchMqttByMesName(devices, eq.name, eq.code);
    if (matched) {
      applyMqttDevice(matched, false);
      message.success(t('app.kuaiiot.message.mqttDeviceMatched'));
      return;
    }
    message.warning(t('app.kuaiiot.message.mqttDeviceMatchMiss'));
  };

  const handleGroupSelect: TreeProps['onSelect'] = (keys) => {
    if (keys.length > 0) {
      setSelectedGroupKeys(keys);
    }
  };

  const handleGroupExpand: TreeProps['onExpand'] = (keys) => {
    setExpandedKeys(keys);
  };

  const handleToggleExpand = () => {
    const targetData = filteredGroupTreeData.length > 0 || !groupSearchValue.trim() ? filteredGroupTreeData : groupTreeData;
    const allKeys = collectTreeKeys(targetData);
    if (expandedKeys.length <= 1) {
      setExpandedKeys(allKeys);
    } else {
      setExpandedKeys(['all']);
    }
  };

  const handleSubmitGroup = async () => {
    const values = await groupForm.validateFields();
    await createDeviceGroup(values);
    message.success(t('common.createSuccess'));
    setGroupModalOpen(false);
    groupForm.resetFields();
    await reloadGroupTree();
  };

  const reloadDeviceData = async (row: Device) => {
    setDataLoading(true);
    try {
      const [snapshotRes, historyRes, tagRes, commandRes, messageLogRes] = await Promise.all([
        listDeviceSnapshots(row.uuid),
        listDeviceHistory(row.uuid, { limit: 100 }),
        listTags({ page: 1, page_size: 200, device_id: row.id }),
        listDeviceCommands(row.uuid, { page: 1, page_size: 50 }).catch(() => ({ items: [], total: 0 })),
        listDeviceMessageLogs(row.uuid, { page: 1, page_size: 50 }).catch(() => ({ items: [], total: 0 })),
      ]);
      setSnapshots(snapshotRes);
      setHistory(historyRes.items);
      setTsdbConfigured(historyRes.tsdb_configured);
      setDeviceTags(tagRes.items);
      setCommands(commandRes.items);
      setMessageLogs(messageLogRes.items);
      const firstNumberTag = tagRes.items.find((item) => item.value_type === 'number')?.tag_key;
      setTrendTagKey(firstNumberTag);
      if (firstNumberTag && historyRes.tsdb_configured) {
        const trendRes = await listDeviceHistory(row.uuid, { tag_key: firstNumberTag, limit: 200 });
        setTrendHistory(trendRes.items);
      } else {
        setTrendHistory([]);
      }
    } finally {
      setDataLoading(false);
    }
  };

  const openDataDrawer = async (row: Device) => {
    setDataDevice(row);
    setDataOpen(true);
    await reloadDeviceData(row);
  };

  const openDebugDrawer = async (row: Device) => {
    setDataDevice(row);
    setDebugOpen(true);
    setDebugResponse('');
    const tagRes = await listTags({ page: 1, page_size: 200, device_id: row.id });
    setDeviceTags(tagRes.items);
    const sampleTags: Record<string, unknown> = {};
    for (const tag of tagRes.items) {
      if (tag.value_type === 'boolean') sampleTags[tag.tag_key] = true;
      else if (tag.value_type === 'number') sampleTags[tag.tag_key] = 1;
      else sampleTags[tag.tag_key] = 'sample';
    }
    setDebugPayload(JSON.stringify({ tags: sampleTags }, null, 2));
    await reloadDeviceData(row);
  };

  const handleTrendTagChange = async (tagKey: string) => {
    setTrendTagKey(tagKey);
    if (!dataDevice) return;
    const trendRes = await listDeviceHistory(dataDevice.uuid, { tag_key: tagKey, limit: 200 });
    setTrendHistory(trendRes.items);
  };

  const handleSimulateIngest = async () => {
    if (!dataDevice) return;
    try {
      const payload = JSON.parse(debugPayload) as { tags: Record<string, unknown>; timestamp?: string };
      const res = await ingestDeviceData(dataDevice.device_token, payload);
      setDebugResponse(JSON.stringify(res, null, 2));
      message.success(
        t('app.kuaiiot.message.ingestSuccess', {
          accepted: res.accepted,
          synced: res.synced_to_mes ? 'yes' : 'no',
        }),
      );
      await reloadDeviceData(dataDevice);
    } catch (error) {
      setDebugResponse(String(error));
      message.error(String(error));
    }
  };

  const accessGuide = useMemo(() => {
    if (!dataDevice) return '';
    const base = `${window.location.origin}${API_BASE_URL}`;
    return [
      `HTTP POST ${base}/apps/kuaiiot/ingest/${dataDevice.device_token}`,
      `curl -X POST "${base}/apps/kuaiiot/ingest/${dataDevice.device_token}" -H "Content-Type: application/json" -d '{"tags":{"temp":26.5}}'`,
      `MQTT topic: kuaiiot/ingest/${dataDevice.device_token}`,
      `Edge Agent config.yaml:\nbase_url: "${window.location.origin}"\ndevice_token: "${dataDevice.device_token}"\nedge_config_code: "<your-edge-config-code>"`,
    ].join('\n\n');
  }, [dataDevice]);

  const trendChartData = useMemo(
    () =>
      [...trendHistory]
        .reverse()
        .map((item) => ({
          time: formatDateTimeBySiteSetting(item.sampled_at),
          value: item.value_number ?? 0,
        })),
    [trendHistory],
  );

  const handleDispatchCommand = async () => {
    if (!dataDevice) return;
    const values = await commandForm.validateFields();
    await createDeviceCommand(dataDevice.uuid, {
      function_key: values.function_key,
      params: values.params || {},
      dispatch_channel: values.dispatch_channel,
    });
    message.success(t('app.kuaiiot.message.commandDispatched'));
    commandForm.resetFields();
    setSelectedFunctionKey(undefined);
    await reloadDeviceData(dataDevice);
  };

  const columns: ProColumns<Device>[] = alignProColumns(
    [
      {
        title: t('common.code'),
        dataIndex: 'code',
        ...IOT_LIST_COL.code,
      },
      {
        title: t('common.name'),
        dataIndex: 'name',
        ...IOT_LIST_COL.name,
      },
      {
        title: t('app.kuaiiot.field.product'),
        dataIndex: 'product_id',
        ...IOT_LIST_COL.ref,
        render: (_, row) => productLabelMap[row.product_id || 0] || '-',
      },
      {
        title: t('app.kuaiiot.field.group'),
        dataIndex: 'group_id',
        ...IOT_LIST_COL.ref,
        render: (_, row) => groupLabelMap[row.group_id || 0] || '-',
      },
      {
        title: t('app.kuaiiot.field.externalId'),
        dataIndex: 'external_device_id',
        ...IOT_LIST_COL.externalId,
      },
      {
        title: t('app.kuaiiot.field.online'),
        dataIndex: 'is_online',
        ...IOT_LIST_COL.marker,
        render: (_, row) => renderIotOnlineMarker(t, row.is_online),
      },
      {
        title: t('app.kuaiiot.field.equipment'),
        dataIndex: 'equipment_uuid',
        ...IOT_LIST_COL.ref,
        render: (_, row) => equipmentLabelMap[row.equipment_uuid || ''] || row.equipment_uuid || '-',
      },
      {
        title: t('app.kuaiiot.field.lastSeen'),
        dataIndex: 'last_seen_at',
        ...IOT_LIST_COL.datetime,
        render: (_, row) => (row.last_seen_at ? formatDateTimeBySiteSetting(row.last_seen_at) : '-'),
      },
      {
        title: t('common.action'),
        key: 'action',
        fixed: 'right',
        hideInSearch: true,
        render: (_, row) => {
          const nodes: React.ReactNode[] = [
            <Button
              key="detail"
              {...rowActionKind('read')}
              onClick={() => {
                setDetail(row);
                setDrawerVisible(true);
              }}
            />,
            <Button
              key="data"
              {...rowActionKind('skip')}
              {...rowActionLabelKeep()}
              onClick={() => openDataDrawer(row)}
            >
              数据
            </Button>,
            <Button
              key="debug"
              {...rowActionKind('skip')}
              {...rowActionLabelKeep()}
              onClick={() => openDebugDrawer(row)}
            >
              调试
            </Button>,
          ];
          if (perms.canUpdate) {
            nodes.push(
              <Button key="edit" {...rowActionKind('update')} onClick={() => openEdit(row)} />,
              <Button
                key="rotate"
                {...rowActionKind('skip')}
                {...rowActionLabelKeep()}
                onClick={async () => {
                  const updated = await rotateDeviceToken(row.uuid);
                  getAntdModal().info({
                    title: t('app.kuaiiot.action.rotateToken'),
                    content: updated.device_token,
                  });
    actionRef.current?.reload();
                }}
              >
                轮换
              </Button>,
            );
          }
          if (perms.canDelete) {
            nodes.push(
              <Button
                key="delete"
                {...rowActionKind('delete')}
                onClick={async () => {
                  await deleteDevice(row.uuid);
                  message.success(t('common.deleteSuccess'));
    actionRef.current?.reload();
                }}
              />,
            );
          }
          return nodes;
        },
      },
    ],
    GLOBAL_DOC_LIST_FIELD_RANK,
  );

  const openCreate = async () => {
    setEditing(null);
    form.resetFields();
    setDiscoveredDevices([]);
    setOpen(true);
    await reloadFormOptions();
    const latestConnections = await listConnections({ page: 1, page_size: 200 }).catch(() => ({
      items: [] as Connection[],
      total: 0,
    }));
    const items = latestConnections.items || [];
    setConnections(items);
    const defaultConnection = items.find((item) => item.connection_type === 'mqtt') || items[0];
    if (defaultConnection) {
      form.setFieldsValue({ connection_id: defaultConnection.id });
    }
    await loadDiscoveredDevices(defaultConnection?.id);
  };

  const openBatchCreate = () => {
    batchForm.resetFields();
    batchForm.setFieldsValue({ count: 10, name_prefix: '设备', code_prefix: 'dev' });
    setBatchResult([]);
    setBatchOpen(true);
  };

  const openEdit = (row: Device) => {
    setEditing(row);
    form.setFieldsValue(row);
    setOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    if (editing) {
      await updateDevice(editing.uuid, values);
      message.success(t('common.updateSuccess'));
    } else {
      await createDevice(values);
      message.success(t('common.createSuccess'));
    }
    setOpen(false);
    actionRef.current?.reload();
  };

  const handleBatchSubmit = async () => {
    const values = await batchForm.validateFields();
    const res = await batchCreateDevices(values);
    setBatchResult(res.items);
    message.success(t('app.kuaiiot.message.batchCreateSuccess', { total: res.total }));
    actionRef.current?.reload();
  };

  const exportBatchCsv = () => {
    const header = 'code,name,device_token,uuid\n';
    const rows = batchResult
      .map((item) => `${item.code},${item.name},${item.device_token},${item.uuid}`)
      .join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'kuaiiot-devices.csv';
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <TwoColumnLayout
        leftPanel={{
          collapsed: !groupPerms.canRead || leftPanelCollapsed,
          search: groupPerms.canRead
            ? {
                placeholder: t('app.kuaiiot.deviceGroup.searchGroup'),
                value: groupSearchValue,
                onChange: setGroupSearchValue,
                allowClear: true,
              }
            : undefined,
          actions: groupPerms.canRead
            ? [
                <div key="group-actions" style={{ display: 'flex', gap: 8 }}>
                  {groupPerms.canCreate ? (
                    <Button type="primary" icon={<PlusOutlined />} style={{ flex: 1 }} onClick={() => setGroupModalOpen(true)}>
                      {t('app.kuaiiot.deviceGroup.createGroup')}
                    </Button>
                  ) : (
                    <div style={{ flex: 1 }} />
                  )}
                  <Button
                    icon={expandedKeys.length > 1 ? <CompressOutlined /> : <ExpandOutlined />}
                    onClick={handleToggleExpand}
                    title={
                      expandedKeys.length > 1
                        ? t('app.kuaiiot.deviceGroup.collapseAll')
                        : t('app.kuaiiot.deviceGroup.expandAll')
                    }
                  />
                </div>,
              ]
            : undefined,
          tree: groupPerms.canRead
            ? {
                className: 'kuaiiot-device-group-tree',
                showLine: true,
                icon: renderDeviceGroupFolderIcon,
                treeData: filteredGroupTreeData.length > 0 || !groupSearchValue.trim() ? filteredGroupTreeData : groupTreeData,
                selectedKeys: selectedGroupKeys,
                expandedKeys,
                onSelect: handleGroupSelect,
                onExpand: handleGroupExpand,
                showIcon: true,
                blockNode: true,
              }
            : undefined,
          width: 320,
          minWidth: 200,
        }}
        rightPanel={{
          content: (
            <div
              style={{
                ['--uni-table-scroll-offset' as string]: `${LIST_PAGE_TABLE_SCROLL.BASE_OFFSET_PX + 2 * LIST_PAGE_TABLE_SCROLL.GAP_PX}px`,
              }}
            >
              <UniTable<Device>
        viewTypes={['table', 'help']}
          helpViewConfig={buildListPageHelpViewConfig('kuaiiot.devices')}
                actionRef={actionRef}
                columns={columns}
                rowKey="uuid"
                columnPersistenceId="apps.kuaiiot.pages.devices.list-v3"
                request={async (params) => {
                  const res = await listDevices({
                    page: params.current,
                    page_size: params.pageSize,
                    q: params.keyword as string | undefined,
                    group_id: selectedGroupId,
                  });
                  return { data: res.items, total: res.total, success: true };
                }}
                beforeSearchButtons={
                  groupPerms.canRead ? (
                    <Tooltip
                      title={
                        leftPanelCollapsed
                          ? t('app.kuaiiot.deviceGroup.expandPanel')
                          : t('app.kuaiiot.deviceGroup.collapsePanel')
                      }
                    >
                      <Button
                        icon={leftPanelCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                        onClick={() => setLeftPanelCollapsed(!leftPanelCollapsed)}
                        style={{ marginRight: 8 }}
                      />
                    </Tooltip>
                  ) : undefined
                }
                toolBarActionsAfterCreate={
                  perms.canCreate
                    ? [
                        <Button key="batch-create" onClick={openBatchCreate}>
                          {t('app.kuaiiot.action.batchCreate')}
                        </Button>,
                      ]
                    : []
                }
                showCreateButton={perms.canCreate}
                createButtonText={t('app.kuaiiot.action.createDevice')}
                onCreate={openCreate}
                enableRowSelection={perms.canDelete}
                showDeleteButton={perms.canDelete}
                onDelete={async (keys) => {
                  await Promise.all(keys.map((key) => deleteDevice(String(key))));
                  message.success(t('common.batchDeleteSuccess', { count: keys.length }));
    actionRef.current?.reload();
                }}
              />
            </div>
          ),
        }}
      />

      <Modal
        open={groupModalOpen}
        title={t('app.kuaiiot.deviceGroup.createGroup')}
        onCancel={() => setGroupModalOpen(false)}
        onOk={handleSubmitGroup}
        destroyOnHidden
      >
        <Form form={groupForm} layout="vertical">
          <Form.Item name="code" label={t('common.code')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="parent_id" label={t('app.kuaiiot.deviceGroup.parentGroup')}>
            <Select allowClear options={flattenGroups(groupTree)} />
          </Form.Item>
          <Form.Item name="remark" label={t('common.remark')}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal open={open} title={editing ? t('common.edit') : t('common.create')} onCancel={() => setOpen(false)} onOk={handleSubmit} destroyOnHidden>
        <Form form={form} layout="vertical">
          <Form.Item
            name="equipment_uuid"
            label={t('app.kuaiiot.field.equipment')}
            extra={t('app.kuaiiot.hint.equipment')}
          >
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={equipmentOptions}
              notFoundContent={t('app.kuaiiot.message.optionsLoadEmpty.equipment')}
              onChange={(value) => {
                void handleMesEquipmentPick(value as string | undefined);
              }}
            />
          </Form.Item>
          <Form.Item
            name="connection_id"
            label={t('app.kuaiiot.menu.connections')}
            extra={t('app.kuaiiot.hint.connection')}
            rules={[{ required: true }]}
          >
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={connections.map((item) => ({
                label: `${item.name}${item.connection_type === 'mqtt' ? ' (MQTT)' : ''}`,
                value: item.id,
              }))}
              notFoundContent={t('app.kuaiiot.message.optionsLoadEmpty.connection')}
            />
          </Form.Item>
          <Form.Item
            name="external_device_id"
            label={t('app.kuaiiot.field.externalId')}
            extra={t('app.kuaiiot.hint.externalId')}
            rules={[{ required: true }]}
          >
            <AutoComplete
              allowClear
              options={mqttDeviceOptions}
              placeholder={t('app.kuaiiot.placeholder.externalId')}
              filterOption={(input, option) =>
                String(option?.label ?? '')
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
              onSelect={(value) => handleMqttDevicePick(String(value))}
            />
          </Form.Item>
          <Form.Item name="code" label={t('common.code')} rules={[{ required: !editing }]}>
            <Input disabled={!!editing} />
          </Form.Item>
          <Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="product_id"
            label={t('app.kuaiiot.field.product')}
            extra={t('app.kuaiiot.hint.product')}
          >
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={products.map((item) => ({ label: `${item.code} - ${item.name}`, value: item.id }))}
              notFoundContent={t('app.kuaiiot.message.optionsLoadEmpty.product')}
            />
          </Form.Item>
          <Form.Item name="group_id" label={t('app.kuaiiot.field.group')} extra={t('app.kuaiiot.hint.group')}>
            <Select allowClear options={flattenGroups(groupTree)} />
          </Form.Item>
          {!editing && (
            <Form.Item name="tag_template_code" label={t('app.kuaiiot.field.tagTemplate')}>
              <Select
                allowClear
                options={tagTemplates.map((item) => ({
                  label: `${item.name} (${item.tag_count})`,
                  value: item.code,
                }))}
              />
            </Form.Item>
          )}
          <Form.Item name="remark" label={t('common.remark')}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal open={batchOpen} title={t('app.kuaiiot.action.batchCreate')} onCancel={() => setBatchOpen(false)} onOk={handleBatchSubmit} width={720} destroyOnHidden>
        <Form form={batchForm} layout="vertical">
          <Form.Item name="product_id" label={t('app.kuaiiot.field.product')} rules={[{ required: true }]}>
            <Select options={products.map((item) => ({ label: `${item.code} - ${item.name}`, value: item.id }))} />
          </Form.Item>
          <Form.Item name="name_prefix" label={t('app.kuaiiot.field.namePrefix')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="code_prefix" label={t('app.kuaiiot.field.codePrefix')}>
            <Input />
          </Form.Item>
          <Form.Item name="count" label={t('app.kuaiiot.field.batchCount')} rules={[{ required: true }]}>
            <InputNumber min={1} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="connection_id" label={t('app.kuaiiot.menu.connections')}>
            <Select allowClear options={connections.map((item) => ({ label: item.name, value: item.id }))} />
          </Form.Item>
          <Form.Item name="equipment_uuid" label={t('app.kuaiiot.field.equipment')}>
            <Select allowClear showSearch optionFilterProp="label" options={equipmentOptions} />
          </Form.Item>
        </Form>
        {batchResult.length ? (
          <>
            <Button style={{ marginBottom: 12 }} onClick={exportBatchCsv}>
              {t('app.kuaiiot.action.copyCsv')}
            </Button>
            <Table
              size="small"
              rowKey="uuid"
              pagination={false}
              dataSource={batchResult}
              columns={[
                { title: t('common.code'), dataIndex: 'code' },
                { title: t('common.name'), dataIndex: 'name' },
                { title: t('app.kuaiiot.field.deviceToken'), dataIndex: 'device_token', ellipsis: true },
              ]}
            />
          </>
        ) : null}
      </Modal>

      <IotMasterDetailDrawer
        title={t('common.detail')}
        open={drawerVisible}
        onClose={() => {
          setDrawerVisible(false);
          setDetail(null);
        }}
        detail={detail}
        detailColumns={detailColumns}
        extra={buildDetailDrawerEditExtra(t, Boolean(detail) && perms.canUpdate, () => {
          if (!detail) return;
          setDrawerVisible(false);
          openEdit(detail);
        })}
      />

      <Drawer
        open={dataOpen}
        size={760}
        title={dataDevice ? `${dataDevice.name} ${t('app.kuaiiot.action.viewData')}` : t('app.kuaiiot.action.viewData')}
        onClose={() => setDataOpen(false)}
        extra={
          dataDevice ? (
            <Button loading={dataLoading} onClick={() => reloadDeviceData(dataDevice)}>
              {t('common.refresh')}
            </Button>
          ) : null
        }
      >
        <Tabs
          items={[
            {
              key: 'snapshots',
              label: t('app.kuaiiot.tab.snapshots'),
              children: (
                <Table
                  loading={dataLoading}
                  rowKey={(row) => `${row.tag_key}-${row.sampled_at}`}
                  pagination={false}
                  size="small"
                  dataSource={snapshots}
                  columns={[
                    { title: t('app.kuaiiot.field.tagKey'), dataIndex: 'tag_key' },
                    { title: t('app.kuaiiot.field.value'), render: (_, row) => formatTagValue(row) },
                    {
                      title: t('app.kuaiiot.field.lastSeen'),
                      dataIndex: 'sampled_at',
                      render: (value) => (value ? formatDateTimeBySiteSetting(value) : '-'),
                    },
                  ]}
                />
              ),
            },
            {
              key: 'history',
              label: t('app.kuaiiot.tab.historyTable'),
              children: !tsdbConfigured ? (
                <div>{t('app.kuaiiot.message.tsdbNotConfigured')}</div>
              ) : (
                <Table
                  loading={dataLoading}
                  rowKey={(row) => `${row.tag_key}-${row.sampled_at}`}
                  pagination={{ pageSize: 20 }}
                  size="small"
                  dataSource={history}
                  columns={[
                    { title: t('app.kuaiiot.field.tagKey'), dataIndex: 'tag_key' },
                    { title: t('app.kuaiiot.field.value'), render: (_, row) => formatTagValue(row) },
                    {
                      title: t('app.kuaiiot.field.lastSeen'),
                      dataIndex: 'sampled_at',
                      render: (value) => (value ? formatDateTimeBySiteSetting(value) : '-'),
                    },
                  ]}
                />
              ),
            },
            {
              key: 'commands',
              label: t('app.kuaiiot.tab.commands'),
              children: (
                <>
                  {perms.canUpdate ? (
                    <Form form={commandForm} layout="vertical" style={{ marginBottom: 16 }}>
                      <Form.Item name="function_key" label={t('app.kuaiiot.field.functionKey')} rules={[{ required: true }]}>
                        <Select
                          allowClear
                          options={functionOptions}
                          onChange={(value) => {
                            setSelectedFunctionKey(value);
                            commandForm.setFieldValue('params', {});
                          }}
                        />
                      </Form.Item>
                      {(selectedFunction?.params || []).map((param) => (
                        <Form.Item
                          key={param.key}
                          name={['params', param.key]}
                          label={param.name}
                          rules={[{ required: param.required !== false }]}
                        >
                          {param.value_type === 'boolean' ? (
                            <Select
                              options={[
                                { label: t('common.yes'), value: true },
                                { label: t('common.no'), value: false },
                              ]}
                            />
                          ) : param.value_type === 'number' ? (
                            <InputNumber style={{ width: '100%' }} />
                          ) : (
                            <Input />
                          )}
                        </Form.Item>
                      ))}
                      <Button type="primary" onClick={handleDispatchCommand} disabled={!functionOptions.length}>
                        {t('app.kuaiiot.action.dispatchCommand')}
                      </Button>
                    </Form>
                  ) : null}
                  <Table
                    loading={dataLoading}
                    rowKey="uuid"
                    size="small"
                    pagination={{ pageSize: 10 }}
                    dataSource={commands}
                    columns={[
                      { title: t('app.kuaiiot.field.functionKey'), dataIndex: 'function_key' },
                      {
                        title: t('app.kuaiiot.field.dispatchChannel'),
                        dataIndex: 'dispatch_channel',
                        render: (value) => translateDispatchChannel(t, value),
                      },
                      {
                        title: t('common.status'),
                        dataIndex: 'status',
                        render: (value) => translateCommandStatus(t, value),
                      },
                      {
                        title: t('common.createdAt'),
                        dataIndex: 'created_at',
                        render: (value) => (value ? formatDateTimeBySiteSetting(value) : '-'),
                      },
                    ]}
                  />
                </>
              ),
            },
            {
              key: 'messageLogs',
              label: t('app.kuaiiot.tab.messageLogs'),
              children: (
                <Table
                  loading={dataLoading}
                  rowKey="uuid"
                  size="small"
                  pagination={{ pageSize: 20 }}
                  dataSource={messageLogs}
                  columns={[
                    {
                      title: t('app.kuaiiot.field.direction'),
                      dataIndex: 'direction',
                      render: (value) => translateMessageDirection(t, value),
                    },
                    {
                      title: t('app.kuaiiot.field.msgType'),
                      dataIndex: 'msg_type',
                      render: (value) => translateMessageType(t, value),
                    },
                    {
                      title: t('app.kuaiiot.field.result'),
                      dataIndex: 'result',
                      render: (value) => translateMessageResult(t, value),
                    },
                    {
                      title: t('common.createdAt'),
                      dataIndex: 'created_at',
                      render: (value) => (value ? formatDateTimeBySiteSetting(value) : '-'),
                    },
                  ]}
                />
              ),
            },
            {
              key: 'trend',
              label: t('app.kuaiiot.field.trendChart'),
              children: !tsdbConfigured ? (
                <div>{t('app.kuaiiot.message.tsdbNotConfigured')}</div>
              ) : (
                <>
                  <Select
                    style={{ width: 240, marginBottom: 16 }}
                    value={trendTagKey}
                    onChange={handleTrendTagChange}
                    options={numberTags.map((item) => ({ label: item.tag_key, value: item.tag_key }))}
                  />
                  <Line data={trendChartData} xField="time" yField="value" height={280} autoFit />
                </>
              ),
            },
          ]}
        />
      </Drawer>

      <Drawer
        open={debugOpen}
        size={760}
        title={dataDevice ? `${dataDevice.name} ${t('app.kuaiiot.action.debugAccess')}` : t('app.kuaiiot.action.debugAccess')}
        onClose={() => setDebugOpen(false)}
      >
        <Typography.Title level={5}>{t('app.kuaiiot.field.accessGuide')}</Typography.Title>
        <Typography.Paragraph copyable={{ text: accessGuide }}>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{accessGuide}</pre>
        </Typography.Paragraph>
        <Typography.Title level={5}>{t('app.kuaiiot.field.ingestPayload')}</Typography.Title>
        <Input.TextArea rows={8} value={debugPayload} onChange={(e) => setDebugPayload(e.target.value)} />
        <Button type="primary" style={{ marginTop: 12 }} onClick={handleSimulateIngest}>
          {t('app.kuaiiot.action.simulateIngest')}
        </Button>
        {debugResponse ? (
          <pre style={{ marginTop: 12, whiteSpace: 'pre-wrap', fontSize: 12 }}>{debugResponse}</pre>
        ) : null}
        <Typography.Title level={5} style={{ marginTop: 24 }}>
          {t('app.kuaiiot.tab.snapshots')}
        </Typography.Title>
        <Table
          loading={dataLoading}
          rowKey={(row) => `${row.tag_key}-${row.sampled_at}`}
          pagination={false}
          size="small"
          dataSource={snapshots}
          columns={[
            { title: t('app.kuaiiot.field.tagKey'), dataIndex: 'tag_key' },
            { title: t('app.kuaiiot.field.value'), render: (_, row) => formatTagValue(row) },
            {
              title: t('app.kuaiiot.field.lastSeen'),
              dataIndex: 'sampled_at',
              render: (value) => (value ? formatDateTimeBySiteSetting(value) : '-'),
            },
          ]}
        />
      </Drawer>
    </>
  );
};

export default DevicesPage;
