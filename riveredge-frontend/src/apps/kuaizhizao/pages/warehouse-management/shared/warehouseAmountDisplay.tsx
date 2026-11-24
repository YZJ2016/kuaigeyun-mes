/**
 * 仓储 hub 列表/明细「显示金额」开关（默认关闭，偏好写入 localStorage）
 * 金额列须走 AmountDisplay，与角色「字段权限」一致。
 */
import React, { useCallback, useState } from 'react';
import type { ProColumns } from '@ant-design/pro-components';
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { AmountDisplay, PartyNameDisplay } from '../../../../../components/permission';
import { UniTableToolbarSwitch } from '../../../../../components/uni-table/UniTableToolbarSwitch';
import { formatAmount, formatCurrencyAmount, formatCurrencyPrice, formatPrice } from '../../../../../utils/format';

const STORAGE_KEY = 'kuaizhizao.warehouse-hub.showAmount';

export const KUAIZHIZAO_OUTBOUND_FIELD_RESOURCE = 'kuaizhizao:outbound';
export const KUAIZHIZAO_INBOUND_FIELD_RESOURCE = 'kuaizhizao:inbound';

export function formatWarehouseAmount(val: unknown, kind: 'price' | 'amount' = 'amount'): string {
  return kind === 'price' ? formatPrice(val) : formatAmount(val);
}

/** 只读场景无 resource 时仍按原样格式化（非权限字段展示） */
export function renderWarehouseAmountCell(val: unknown, kind: 'price' | 'amount' = 'amount'): string {
  const formatted = kind === 'price' ? formatCurrencyPrice(val) : formatCurrencyAmount(val);
  return formatted === '—' ? '-' : formatted;
}

export function renderWarehousePartyNameDisplay(
  val: unknown,
  fieldResource: string,
  fieldName: 'customer_name' | 'supplier_name',
): React.ReactNode {
  return (
    <PartyNameDisplay
      resource={fieldResource}
      fieldName={fieldName}
      value={val == null ? '' : String(val)}
    />
  );
}

export type WarehousePartyNameRecord = {
  customer_name?: string | null;
  supplier_name?: string | null;
};

/** 仓储 hub 列表叠列主行：客户/供应商名称走字段权限（与出库管理一致） */
export function resolveWarehouseHubStackedPartyPrimary(
  fieldResource: string,
  record: WarehousePartyNameRecord,
): { primary: string; primaryContent: React.ReactNode } | null {
  if (record.customer_name) {
    const value = String(record.customer_name);
    return {
      primary: value,
      primaryContent: renderWarehousePartyNameDisplay(value, fieldResource, 'customer_name'),
    };
  }
  if (record.supplier_name) {
    const value = String(record.supplier_name);
    return {
      primary: value,
      primaryContent: renderWarehousePartyNameDisplay(value, fieldResource, 'supplier_name'),
    };
  }
  return null;
}

export const KUAIZHIZAO_DELIVERY_NOTICE_FIELD_RESOURCE = 'kuaizhizao:delivery-notice';
export const KUAIZHIZAO_CUSTOMER_MATERIAL_REGISTRATION_FIELD_RESOURCE =
  'kuaizhizao:warehouse-management-customer-material-registration';

export function renderWarehouseAmountDisplay(
  val: unknown,
  kind: 'price' | 'amount',
  fieldResource: string,
  fieldName: 'unit_price' | 'total_amount' | 'amount' = kind === 'price' ? 'unit_price' : 'total_amount',
): React.ReactNode {
  const num = val == null || val === '' ? null : Number(val);
  if (num == null || !Number.isFinite(num)) {
    return '-';
  }
  return (
    <AmountDisplay
      resource={fieldResource}
      fieldName={fieldName}
      value={num}
    />
  );
}

export function useWarehouseShowAmount(): [boolean, (next: boolean) => void] {
  const [showAmount, setShowAmount] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === '1';
    } catch {
      return false;
    }
  });

  const setShowAmountPersist = useCallback((next: boolean) => {
    setShowAmount(next);
    try {
      localStorage.setItem(STORAGE_KEY, next ? '1' : '0');
    } catch {
      /* ignore quota / private mode */
    }
  }, []);

  return [showAmount, setShowAmountPersist];
}

export function WarehouseShowAmountSwitch({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  const { t } = useTranslation();
  return (
    <UniTableToolbarSwitch
      checked={checked}
      onChange={onChange}
      label={t('app.kuaizhizao.warehouseCommon.showAmount')}
    />
  );
}

export function buildWarehouseTotalAmountListColumn<T extends Record<string, unknown>>(
  t: TFunction,
  showAmount: boolean,
  fieldResource: string,
): ProColumns<T>[] {
  if (!showAmount) return [];
  return [
    {
      title: t('app.kuaizhizao.warehouseCommon.colAmount'),
      dataIndex: 'total_amount',
      width: 110,
      align: 'right',
      sorter: true,
      render: (_dom, record) =>
        renderWarehouseAmountDisplay(record.total_amount, 'amount', fieldResource, 'total_amount'),
    },
  ];
}

type LineAmountCol = ColumnsType[number];

export function buildWarehouseLineUnitPriceColumn(
  t: TFunction,
  showAmount: boolean,
  fieldResource: string,
): LineAmountCol[] {
  if (!showAmount) return [];
  return [
    {
      title: t('app.kuaizhizao.warehouseCommon.colUnitPrice'),
      dataIndex: 'unit_price',
      width: 90,
      align: 'right' as const,
      render: (val: unknown) => renderWarehouseAmountDisplay(val, 'price', fieldResource, 'unit_price'),
    },
  ];
}

export function buildWarehouseLineAmountColumn(
  t: TFunction,
  showAmount: boolean,
  fieldResource: string,
): LineAmountCol[] {
  if (!showAmount) return [];
  return [
    {
      title: t('app.kuaizhizao.warehouseCommon.colAmount'),
      dataIndex: 'total_amount',
      width: 100,
      align: 'right' as const,
      render: (val: unknown) => renderWarehouseAmountDisplay(val, 'amount', fieldResource, 'total_amount'),
    },
  ];
}

export function appendWarehouseLineAmountColumns<T extends LineAmountCol>(
  columns: T[],
  t: TFunction,
  showAmount: boolean,
  fieldResource: string,
  insertBeforeIndex?: number,
): T[] {
  if (!showAmount) return columns;
  const amountCols = [
    ...buildWarehouseLineUnitPriceColumn(t, true, fieldResource),
    ...buildWarehouseLineAmountColumn(t, true, fieldResource),
  ] as T[];
  if (insertBeforeIndex == null || insertBeforeIndex < 0 || insertBeforeIndex >= columns.length) {
    return [...columns, ...amountCols];
  }
  return [...columns.slice(0, insertBeforeIndex), ...amountCols, ...columns.slice(insertBeforeIndex)];
}