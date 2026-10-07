/**
 * 实体选择器：页面表单用可搜索下拉代替手输数字 ID 或 UUID。
 * 选项 label 统一为“名称 (编码)”。
 */

import React, { useEffect, useState } from 'react';
import { Select, type SelectProps } from 'antd';
import { equipmentApi } from '../../kuaizhizao/services/equipment';
import {
  listConnections,
  listDeviceGroups,
  listDevices,
  listProducts,
} from '../services/kuaiiot';

type Option = { label: string; value: string | number };

type EntitySelectProps = Omit<SelectProps, 'options' | 'loading'>;

function useOptions(loader: () => Promise<Option[]>) {
  const [options, setOptions] = useState<Option[]>([]);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loader()
      .then((rows) => {
        if (!cancelled) setOptions(rows);
      })
      .catch(() => {
        if (!cancelled) setOptions([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // loader 由各 Select 的模块级函数提供，保持稳定引用。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return { options, loading };
}

function OptionsSelect(props: EntitySelectProps & { loader: () => Promise<Option[]> }) {
  const { loader, ...rest } = props;
  const { options, loading } = useOptions(loader);
  return (
    <Select
      allowClear
      showSearch
      optionFilterProp="label"
      loading={loading}
      options={options}
      {...rest}
    />
  );
}

async function deviceOptions(): Promise<Option[]> {
  const rows = await listDevices();
  return (rows || []).map((row) => ({ value: row.id, label: `${row.name} (${row.code})` }));
}

export function DeviceSelect(props: EntitySelectProps) {
  return <OptionsSelect placeholder="选择 IoT 设备" loader={deviceOptions} {...props} />;
}

async function connectionOptions(): Promise<Option[]> {
  const rows = await listConnections();
  return (rows || []).map((row) => ({ value: row.id, label: `${row.name} (${row.code})` }));
}

export function ConnectionSelect(props: EntitySelectProps) {
  return <OptionsSelect placeholder="选择数采连接" loader={connectionOptions} {...props} />;
}

async function productOptions(): Promise<Option[]> {
  const rows = await listProducts();
  return (rows || []).map((row) => ({ value: row.id, label: `${row.name} (${row.code})` }));
}

export function ProductSelect(props: EntitySelectProps) {
  return <OptionsSelect placeholder="选择产品物模型" loader={productOptions} {...props} />;
}

async function deviceGroupOptions(): Promise<Option[]> {
  const rows = await listDeviceGroups();
  return (rows || []).map((row) => ({ value: row.id, label: `${row.name} (${row.code})` }));
}

export function DeviceGroupSelect(props: EntitySelectProps) {
  return <OptionsSelect placeholder="选择设备分组" loader={deviceGroupOptions} {...props} />;
}

async function equipmentOptions(): Promise<Option[]> {
  const res = await equipmentApi.list({ is_active: true, limit: 500 });
  const items: Array<{ uuid: string; name: string; code: string }> = res?.items ?? [];
  return items.map((row) => ({ value: row.uuid, label: `${row.name} (${row.code})` }));
}

/** 值是星制造设备 equipment.uuid，不是数字 ID。 */
export function EquipmentSelect(props: EntitySelectProps) {
  return <OptionsSelect placeholder="选择星制造设备" loader={equipmentOptions} {...props} />;
}
