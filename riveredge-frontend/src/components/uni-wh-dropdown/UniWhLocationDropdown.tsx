/**
 * 统一库位下拉：按仓库加载库区库位 + 独立仓位；可选按物料展示库位库存。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { App, Select } from 'antd';
import { ProFormSelect } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { formatQuantity } from '../../utils/format';
import { fetchStorageLocationsForWarehouse } from '../../apps/kuaizhizao/pages/warehouse-management/inbound/inboundPoReceiptEntryUtils';
import {
  loadAvailableQtyByMaterialLocation,
  resolveLocationOptionStockQty,
  type LocationStockMaps,
} from '../../apps/kuaizhizao/pages/warehouse-management/outbound/outboundConfirmInventoryOptions';
import type {
  UniWhLocationChangePayload,
  UniWhLocationDropdownProps,
  UniWhLocationOption,
} from './types';

type LocBase = { value: number; label: string; code: string };

function errorDetail(err: unknown): string {
  const e = err as { response?: { data?: { detail?: unknown; message?: string } }; message?: string };
  const detail = e?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (detail && typeof detail === 'object' && 'message' in (detail as object)) {
    const msg = (detail as { message?: unknown }).message;
    if (typeof msg === 'string' && msg.trim()) return msg;
  }
  const nested = e?.response?.data?.message;
  if (typeof nested === 'string' && nested.trim()) return nested;
  return e?.message || '';
}

export const UniWhLocationDropdown: React.FC<UniWhLocationDropdownProps> = ({
  name,
  value,
  onChange,
  warehouseId,
  materialId,
  showStock,
  sortByStock,
  disabled = false,
  size,
  placeholder,
  className,
  style,
  getPopupContainer,
  allowClear = true,
  ...restProForm
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [baseOptions, setBaseOptions] = useState<LocBase[]>([]);
  const [loading, setLoading] = useState(false);
  const [stockMaps, setStockMaps] = useState<LocationStockMaps>({ byId: {}, byCode: {} });
  const [stockStatus, setStockStatus] = useState<'idle' | 'loading' | 'ready'>('idle');
  /** 同一仓库仅自动带入一次，避免 ProForm/无 value 路径重复触发 onChange */
  const autoFilledForWhRef = useRef<number | null>(null);
  const prevWhForAutoRef = useRef(0);

  const whId = Number(warehouseId ?? 0);
  const mid = Number(materialId ?? 0);
  const canSelect = whId > 0;
  const stockEnabled = showStock ?? mid > 0;
  const sortEnabled = sortByStock ?? stockEnabled;

  const loadLocations = useCallback(async (id: number) => {
    if (!(id > 0)) {
      setBaseOptions([]);
      return;
    }
    setLoading(true);
    try {
      const opts = await fetchStorageLocationsForWarehouse(id);
      setBaseOptions(opts);
    } catch (err) {
      console.error('Failed to load storage locations:', err);
      setBaseOptions([]);
      const detail = errorDetail(err);
      message.error(
        detail
          || t('components.uniWhDropdown.loadLocationFailed', {
            defaultValue: '库位加载失败，请确认有仓库/库位读取权限',
          }),
      );
    } finally {
      setLoading(false);
    }
  }, [message, t]);

  const refreshStock = useCallback(async () => {
    if (!stockEnabled || !(mid > 0) || !(whId > 0)) {
      setStockMaps({ byId: {}, byCode: {} });
      setStockStatus('idle');
      return;
    }
    setStockStatus('loading');
    try {
      const maps = await loadAvailableQtyByMaterialLocation(mid, whId);
      setStockMaps(maps);
      setStockStatus('ready');
    } catch (err) {
      console.error('Failed to load location stock:', err);
      setStockMaps({ byId: {}, byCode: {} });
      setStockStatus('ready');
    }
  }, [mid, stockEnabled, whId]);

  useEffect(() => {
    void loadLocations(whId);
  }, [loadLocations, whId]);

  useEffect(() => {
    void refreshStock();
  }, [refreshStock]);

  // 仓下仅 1 个库位时自动带入，避免批量领料等明细逐行手点。
  useEffect(() => {
    if (prevWhForAutoRef.current !== whId) {
      prevWhForAutoRef.current = whId;
      autoFilledForWhRef.current = null;
    }
    if (!(whId > 0)) return;
    if (loading || baseOptions.length !== 1) return;
    const only = baseOptions[0];
    const onlyId = Number(only?.value ?? 0);
    if (!(onlyId > 0)) return;
    const current =
      value == null || value === ''
        ? NaN
        : Number(value);
    if (Number.isFinite(current) && current > 0) {
      autoFilledForWhRef.current = whId;
      return;
    }
    if (autoFilledForWhRef.current === whId) return;
    autoFilledForWhRef.current = whId;
    const payload: UniWhLocationChangePayload = {
      id: onlyId,
      code: String(only.code || '').trim(),
      label: String(only.label || only.code || onlyId),
    };
    onChange?.(onlyId, payload);
  }, [baseOptions, loading, onChange, value, whId]);

  const options: UniWhLocationOption[] = useMemo(() => {
    const showQty = stockEnabled && stockStatus === 'ready';
    const enriched = baseOptions.map((row) => {
      const base = String(row.label || row.code || row.value).trim();
      const qty = showQty
        ? resolveLocationOptionStockQty(
            stockMaps,
            { value: row.value, code: row.code, label: base },
            baseOptions.length,
          )
        : 0;
      const labelText = showQty
        ? qty > 0
          ? t('components.uniWhDropdown.locationWithStock', {
              location: base,
              qty: formatQuantity(qty),
            })
          : t('components.uniWhDropdown.locationWithStockEmpty', { location: base })
        : base;
      return {
        value: row.value,
        label: labelText,
        code: row.code,
        stockQty: qty,
      };
    });
    if (!sortEnabled || !showQty) return enriched;
    return [...enriched].sort((a, b) => {
      const aq = Number(a.stockQty ?? 0);
      const bq = Number(b.stockQty ?? 0);
      const aHas = aq > 0 ? 1 : 0;
      const bHas = bq > 0 ? 1 : 0;
      if (aHas !== bHas) return bHas - aHas;
      if (aq !== bq) return bq - aq;
      return String(a.code || a.label).localeCompare(String(b.code || b.label), 'zh');
    });
  }, [baseOptions, sortEnabled, stockEnabled, stockMaps, stockStatus, t]);

  const emitChange = useCallback(
    (raw: unknown) => {
      const nextId =
        raw == null || raw === ''
          ? undefined
          : Number.isFinite(Number(raw))
            ? Number(raw)
            : undefined;
      const opt = nextId != null ? options.find((o) => o.value === nextId) : undefined;
      const payload: UniWhLocationChangePayload | undefined = opt
        ? { id: opt.value, code: opt.code, label: opt.label }
        : undefined;
      onChange?.(nextId, payload);
    },
    [onChange, options],
  );

  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (!open || !canSelect) return;
      if (!baseOptions.length) {
        void loadLocations(whId);
      }
      if (stockEnabled && mid > 0) {
        void refreshStock();
      }
    },
    [baseOptions.length, canSelect, loadLocations, mid, refreshStock, stockEnabled, whId],
  );

  const resolvedPlaceholder = !canSelect
    ? t('components.uniWhDropdown.selectWarehouseFirst')
    : (placeholder ?? t('components.uniWhDropdown.selectLocation'));

  const commonSelectProps = {
    showSearch: true as const,
    allowClear,
    disabled: disabled || !canSelect,
    size,
    className,
    style: { width: '100%', ...style },
    placeholder: resolvedPlaceholder,
    options,
    loading: loading || (stockEnabled && stockStatus === 'loading'),
    optionFilterProp: 'label' as const,
    getPopupContainer,
    onOpenChange: handleOpenChange,
  };

  if (name != null) {
    return (
      <ProFormSelect
        name={name}
        label=""
        options={options}
        fieldProps={{
          ...commonSelectProps,
          onChange: emitChange,
        }}
        {...restProForm}
      />
    );
  }

  return (
    <Select
      {...commonSelectProps}
      value={value}
      onChange={emitChange}
    />
  );
};

export default UniWhLocationDropdown;
