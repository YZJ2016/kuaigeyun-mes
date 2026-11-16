/**
 * 统一库位下拉：按仓库加载库区库位 + 独立仓位；可选按物料展示库位库存。
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Select } from 'antd';
import { ProFormSelect } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { formatQuantity } from '../../utils/format';
import { fetchStorageLocationsForWarehouse } from '../../apps/kuaizhizao/pages/warehouse-management/inbound/inboundPoReceiptEntryUtils';
import {
  loadAvailableQtyByMaterialLocation,
  type LocationStockMaps,
} from '../../apps/kuaizhizao/pages/warehouse-management/outbound/outboundConfirmInventoryOptions';
import type {
  UniWhLocationChangePayload,
  UniWhLocationDropdownProps,
  UniWhLocationOption,
} from './types';

type LocBase = { value: number; label: string; code: string };

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
  const [baseOptions, setBaseOptions] = useState<LocBase[]>([]);
  const [loading, setLoading] = useState(false);
  const [stockMaps, setStockMaps] = useState<LocationStockMaps>({ byId: {}, byCode: {} });
  const [stockStatus, setStockStatus] = useState<'idle' | 'loading' | 'ready'>('idle');

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
    } catch {
      setBaseOptions([]);
    } finally {
      setLoading(false);
    }
  }, []);

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

  const options: UniWhLocationOption[] = useMemo(() => {
    const showQty = stockEnabled && stockStatus === 'ready';
    const enriched = baseOptions.map((row) => {
      const qtyFromId = Number(stockMaps.byId[row.value] ?? 0);
      const qtyFromCode = Number(stockMaps.byCode[String(row.code || '').trim()] ?? 0);
      const qty = qtyFromId > 0 ? qtyFromId : qtyFromCode;
      const base = String(row.label || row.code || row.value).trim();
      const labelText = showQty
        ? t('components.uniWhDropdown.locationWithStock', {
            location: base,
            qty: formatQuantity(qty),
          })
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
