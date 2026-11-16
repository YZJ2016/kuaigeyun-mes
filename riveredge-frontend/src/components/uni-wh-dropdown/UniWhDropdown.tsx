/**
 * 统一仓库下拉：reference-display 选仓；传入 materialId 后展示各仓可出库库存。
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { App, Select } from 'antd';
import { ProFormSelect } from '@ant-design/pro-components';
import { useDebounceFn } from 'ahooks';
import { useTranslation } from 'react-i18next';
import {
  ReferenceDisplayAccessError,
  searchReferenceDisplay,
  type ReferenceDisplayItem,
} from '../../utils/referenceDisplay';
import { formatQuantity } from '../../utils/format';
import { loadAvailableQtyByMaterialWarehouse } from '../../apps/kuaizhizao/pages/warehouse-management/outbound/outboundConfirmInventoryOptions';
import type { UniWhDropdownProps, UniWhWarehouseChangePayload, UniWhWarehouseOption } from './types';

const WAREHOUSE_REFERENCE_RESOURCE = 'master-data:warehouse:warehouse';

type WarehouseRow = {
  id: number;
  uuid: string;
  code: string;
  name: string;
};

function mapWarehouseDisplayItem(item: ReferenceDisplayItem): WarehouseRow {
  return {
    id: Number(item.id),
    uuid: String(item.uuid ?? ''),
    code: String(item.code ?? ''),
    name: String(item.name ?? ''),
  };
}

function warehouseBaseLabel(row: WarehouseRow): string {
  return `${row.code} ${row.name}`.trim() || String(row.id);
}

export const UniWhDropdown: React.FC<UniWhDropdownProps> = ({
  name,
  value,
  onChange,
  materialId,
  showStock,
  sortByStock,
  hostResource,
  activeOnly = true,
  disabled = false,
  size,
  placeholder,
  className,
  style,
  getPopupContainer,
  required = false,
  label = '',
  allowClear = false,
  ...restProForm
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();

  const [data, setData] = useState<WarehouseRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [stockByWh, setStockByWh] = useState<Record<number, number>>({});
  const [stockStatus, setStockStatus] = useState<'idle' | 'loading' | 'ready'>('idle');

  const mid = Number(materialId ?? 0);
  const stockEnabled = showStock ?? mid > 0;
  const sortEnabled = sortByStock ?? stockEnabled;

  const fetchWarehouses = useCallback(
    async (searchText: string = '') => {
      setLoading(true);
      try {
        const response = await searchReferenceDisplay({
          resource: WAREHOUSE_REFERENCE_RESOURCE,
          hostResource,
          keyword: searchText.trim() || undefined,
          isActive: activeOnly ? true : undefined,
          pageSize: 200,
        });
        setData((response.items || []).map(mapWarehouseDisplayItem));
      } catch (error) {
        console.error('Failed to fetch warehouses:', error);
        if (error instanceof ReferenceDisplayAccessError) {
          message.error(error.message);
        } else {
          message.error(t('components.uniWhDropdown.loadWarehouseFailed'));
        }
      } finally {
        setLoading(false);
      }
    },
    [activeOnly, hostResource, message, t],
  );

  const refreshStock = useCallback(async () => {
    if (!stockEnabled || !(mid > 0)) {
      setStockByWh({});
      setStockStatus('idle');
      return;
    }
    setStockStatus('loading');
    try {
      const map = await loadAvailableQtyByMaterialWarehouse([mid]);
      setStockByWh(map[mid] ?? {});
      // 失败也不回到 idle：无数据按 0 展示，避免「像没接入」
      setStockStatus('ready');
    } catch (err) {
      console.error('Failed to load warehouse stock:', err);
      setStockByWh({});
      setStockStatus('ready');
    }
  }, [mid, stockEnabled]);

  const { run: debounceFetch } = useDebounceFn(
    (kw: string) => {
      void fetchWarehouses(kw);
    },
    { wait: 300 },
  );

  useEffect(() => {
    void fetchWarehouses();
  }, [fetchWarehouses]);

  useEffect(() => {
    void refreshStock();
  }, [refreshStock]);

  const options: UniWhWarehouseOption[] = useMemo(() => {
    const showQty = stockEnabled && stockStatus === 'ready';
    const enriched = data.map((row) => {
      const qty = Number(stockByWh[row.id] ?? 0);
      const base = warehouseBaseLabel(row);
      const labelText = showQty
        ? t('components.uniWhDropdown.warehouseWithStock', {
            warehouse: base,
            qty: formatQuantity(qty),
          })
        : base;
      return {
        value: row.id,
        label: labelText,
        name: row.name,
        code: row.code,
        stockQty: qty,
      };
    });
    // 有物料库存口径时：有货仓优先，再按库存降序，最后按名称
    if (!sortEnabled || !(stockEnabled && stockStatus === 'ready')) return enriched;
    return [...enriched].sort((a, b) => {
      const aq = Number(a.stockQty ?? 0);
      const bq = Number(b.stockQty ?? 0);
      const aHas = aq > 0 ? 1 : 0;
      const bHas = bq > 0 ? 1 : 0;
      if (aHas !== bHas) return bHas - aHas;
      if (aq !== bq) return bq - aq;
      return String(a.name || a.label).localeCompare(String(b.name || b.label), 'zh');
    });
  }, [data, sortEnabled, stockByWh, stockEnabled, stockStatus, t]);

  const emitChange = useCallback(
    (raw: unknown) => {
      const nextId =
        raw == null || raw === ''
          ? undefined
          : Number.isFinite(Number(raw))
            ? Number(raw)
            : undefined;
      const row = nextId != null ? data.find((w) => Number(w.id) === nextId) : undefined;
      const opt = nextId != null ? options.find((o) => o.value === nextId) : undefined;
      const payload: UniWhWarehouseChangePayload | undefined = row
        ? {
            id: row.id,
            name: row.name,
            code: row.code,
            stockQty: opt?.stockQty,
          }
        : undefined;
      onChange?.(nextId, payload);
    },
    [data, onChange, options],
  );

  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (open) {
        if (stockEnabled && mid > 0) {
          void refreshStock();
        }
      }
    },
    [mid, refreshStock, stockEnabled],
  );

  const resolvedPlaceholder =
    placeholder ??
    (stockEnabled && !(mid > 0)
      ? t('components.uniWhDropdown.selectWarehouseNeedMaterial')
      : t('components.uniWhDropdown.selectWarehouse'));

  const commonSelectProps = {
    showSearch: true as const,
    allowClear,
    disabled,
    size,
    className,
    style: { width: '100%', ...style },
    placeholder: resolvedPlaceholder,
    options,
    loading: loading || (stockEnabled && stockStatus === 'loading'),
    filterOption: false as const,
    onSearch: debounceFetch,
    getPopupContainer,
    optionFilterProp: 'label' as const,
    onOpenChange: handleOpenChange,
  };

  if (name != null) {
    return (
      <ProFormSelect
        name={name}
        label={label}
        required={required}
        rules={
          required
            ? [
                {
                  required: true,
                  message: t('components.uniWhDropdown.selectWarehouse'),
                },
              ]
            : undefined
        }
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

export default UniWhDropdown;
