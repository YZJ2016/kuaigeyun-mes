import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AutoComplete, Button, Input, Space, Typography } from 'antd';
import { discoverExternalDevices, type ExternalDevicePage } from './api';

/** Form.Item 注入 value/onChange；切换连接后旧请求不能覆盖新连接候选。 */
export function ExternalDeviceInput({ connectionId, connectionType, value, onChange }: {
  connectionId?: number;
  connectionType?: string;
  value?: string;
  onChange?: (value: string) => void;
}) {
  const [items, setItems] = useState<ExternalDevicePage['items']>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const pageRef = useRef(0);
  const generation = useRef(0);
  const canDiscover = connectionType === 'thingsboard' || connectionType === 'jetlinks';
  const load = useCallback(async (page = 0) => {
    if (!connectionId || !canDiscover) return;
    const request = ++generation.current;
    setLoading(true);
    setError(false);
    try {
      const result = await discoverExternalDevices(connectionId, page);
      if (request !== generation.current) return;
      setItems(previous => Array.from(new Map([...(page ? previous : []), ...result.items].map(row => [row.external_device_id, row])).values()));
      setHasMore(result.has_more);
      pageRef.current = page;
    } catch {
      if (request === generation.current) setError(true);
    } finally {
      if (request === generation.current) setLoading(false);
    }
  }, [connectionId, canDiscover]);
  useEffect(() => {
    generation.current++;
    setItems([]);
    setHasMore(false);
    setLoading(false);
    setError(false);
    pageRef.current = 0;
    if (canDiscover) void load();
    return () => { generation.current++; };
  }, [load, canDiscover]);
  return <div>
    <AutoComplete
      value={value}
      onChange={onChange}
      options={items.map(row => ({ value: row.external_device_id, label: `${row.name} (${row.external_device_id})` }))}
      filterOption={(input, option) => String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
      placeholder={canDiscover ? '选择平台设备或输入设备标识' : '填写外部设备标识'}
      style={{ width: '100%' }}
    ><Input maxLength={100} /></AutoComplete>
    {canDiscover ? <Space wrap size={8} style={{ marginTop: 4 }}>
      <Button size="small" loading={loading} onClick={() => void load()}>刷新平台设备</Button>
      {hasMore ? <Button size="small" disabled={loading} onClick={() => void load(pageRef.current + 1)}>加载更多</Button> : null}
      {error ? <Typography.Text type="warning">平台设备读取失败，请检查连接或手动填写</Typography.Text> : null}
    </Space> : <Typography.Text type="secondary">HTTP / MQTT 连接使用手动填写的设备标识</Typography.Text>}
  </div>;
}
