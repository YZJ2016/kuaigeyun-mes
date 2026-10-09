import type { ProColumns } from '@ant-design/pro-components';

type ColumnLayout = { key: string; width?: number; title?: string; fixed?: 'right' };

// Reference colgroup widths. Omitted widths consume the remaining table space.
const layouts = {
  rules: [
    { key: 'code', width: 140, title: '编码' }, { key: 'tag_key', width: 140, title: '点位 Key' },
    { key: 'name', title: '名称' }, { key: 'rule_type', width: 100, title: '规则类型' },
    { key: 'severity', width: 80, title: '严重级别' }, { key: 'device_id', width: 160, title: '设备' },
    { key: 'operator', width: 80, title: '比较符' }, { key: 'threshold', title: '阈值' }, { key: 'action', fixed: 'right' },
  ],
  records: [
    { key: 'tag_key', width: 140, title: '点位 Key' }, { key: 'severity', width: 80, title: '严重级别' },
    { key: 'device_id', width: 160 }, { key: 'message', title: '消息' },
    { key: 'status', width: 80, fixed: 'right' }, { key: 'action', fixed: 'right' },
  ],
  products: [{ key: 'code', width: 140 }, { key: 'name' }, { key: 'remark', width: 160 }, { key: 'tags' }, { key: 'action', fixed: 'right' }],
  devices: [
    { key: 'code', width: 140 }, { key: 'name' }, { key: 'last_seen_at', width: 176, title: '最后上报' },
    { key: 'product_id', width: 160, title: '产品模型' }, { key: 'group_id', width: 160, title: '设备分组' },
    { key: 'external_device_id', width: 140, title: '外部设备 ID' }, { key: 'equipment_uuid', width: 160 },
    { key: 'is_online', width: 80, title: '在线' }, { key: 'action', fixed: 'right' },
  ],
  tags: [
    { key: 'tag_key', width: 140 }, { key: 'name' }, { key: 'value_type', width: 100 },
    { key: 'map_target', width: 120 }, { key: 'unit', width: 72 }, { key: 'is_enabled', width: 80 },
    { key: 'device_id', width: 160, title: '设备' }, { key: 'fill_target', width: 140 }, { key: 'action', fixed: 'right' },
  ],
  connections: [
    { key: 'code', width: 140 }, { key: 'name' }, { key: 'connection_type', width: 100 },
    { key: 'health_status', width: 80 }, { key: 'is_enabled', width: 80 }, { key: 'action', fixed: 'right' },
  ],
  edge: [
    { key: 'code', width: 140 }, { key: 'name' }, { key: 'protocol', width: 100 },
    { key: 'agent_status', width: 100 }, { key: 'last_agent_heartbeat_at', width: 176 },
    { key: 'is_enabled', width: 80, title: '启用' }, { key: 'device_id', width: 160 },
    { key: 'config_version', width: 100, title: '配置版本' }, { key: 'buffer_pending_count', width: 100, title: '缓冲待传' },
    { key: 'action', fixed: 'right' },
  ],
} satisfies Record<string, ColumnLayout[]>;

export function alignIotTableColumns<T>(columns: ProColumns<T>[], page: keyof typeof layouts): ProColumns<T>[] {
  const keyOf = (column: ProColumns<T>) => String(column.key ?? column.dataIndex ?? '');
  const byKey = new Map(columns.map(column => [keyOf(column), column]));
  const layout: ColumnLayout[] = layouts[page];
  const visible = new Set(layout.map(column => column.key));
  const ordered = layout.flatMap(spec => {
    const column = byKey.get(spec.key);
    if (!column) return [];
    const operation = spec.key === 'action';
    return [{
      ...column,
      ...(spec.title ? { title: spec.title } : {}),
      ...(operation ? {} : {
        width: spec.width,
        minWidth: spec.width ?? 140,
        uniTableKeepWidth: spec.width != null,
        uniTableRemainderFlex: spec.width == null,
        uniTableEqualRemainder: spec.width == null,
        uniTablePrimaryFlex: spec.width == null,
        resizable: false,
        ...(spec.width !== 80 ? { uniTableMarkerBadgeColumn: false } : {}),
      }),
      fixed: spec.fixed,
      defaultShow: true,
    }];
  });
  // Keep advanced search and optional columns available without crowding the reference view.
  return [...ordered, ...columns.filter(column => !visible.has(keyOf(column))).map(column => ({ ...column, defaultShow: false, fixed: undefined }))];
}
