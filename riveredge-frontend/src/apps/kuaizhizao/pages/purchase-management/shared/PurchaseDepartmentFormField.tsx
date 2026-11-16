/**
 * 采购单据表头「部门」选择（与杂项凭证 / 其他出库同一套部门树扁平选项）。
 */
import React, { useEffect, useState } from 'react';
import { ProFormSelect } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { getDepartmentTree } from '../../../../../services/department';
import {
  flattenDepartmentTreeOptions,
  type DepartmentPickerOption,
} from '../../../../master-data/utils/flattenDepartmentTreeOptions';

export type PurchaseDepartmentOption = Pick<DepartmentPickerOption, 'label' | 'value'>;

export function usePurchaseDepartmentOptions(): {
  options: PurchaseDepartmentOption[];
  loading: boolean;
  resolveName: (departmentId: number | null | undefined) => string | undefined;
} {
  const [options, setOptions] = useState<PurchaseDepartmentOption[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void getDepartmentTree({ is_active: true })
      .then((res) => {
        if (cancelled) return;
        setOptions(
          flattenDepartmentTreeOptions(res?.items ?? []).map((d) => ({
            label: d.label,
            value: d.value,
          })),
        );
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
  }, []);

  const resolveName = (departmentId: number | null | undefined) => {
    if (departmentId == null || !Number.isFinite(Number(departmentId))) return undefined;
    const hit = options.find((o) => Number(o.value) === Number(departmentId));
    const label = String(hit?.label ?? '').trim();
    return label || undefined;
  };

  return { options, loading, resolveName };
}

export function resolvePurchaseDepartmentPayload(
  departmentId: unknown,
  resolveName: (id: number | null | undefined) => string | undefined,
  fallbackName?: string | null,
): { department_id?: number; department_name?: string } {
  if (departmentId == null || departmentId === '') {
    return { department_id: undefined, department_name: undefined };
  }
  const id = Number(departmentId);
  if (!Number.isFinite(id) || id <= 0) {
    return { department_id: undefined, department_name: undefined };
  }
  const name = resolveName(id) ?? (String(fallbackName ?? '').trim() || undefined);
  return { department_id: id, department_name: name };
}

type PurchaseDepartmentFormFieldProps = {
  name?: string;
  disabled?: boolean;
  options: PurchaseDepartmentOption[];
  loading?: boolean;
};

/** 表头部门下拉；外层自行包 Col。 */
export const PurchaseDepartmentFormField: React.FC<PurchaseDepartmentFormFieldProps> = ({
  name = 'department_id',
  disabled,
  options,
  loading,
}) => {
  const { t } = useTranslation();

  return (
    <ProFormSelect
      name={name}
      label={t('app.kuaizhizao.purchase.field.department')}
      options={options}
      disabled={disabled}
      fieldProps={{
        showSearch: true,
        optionFilterProp: 'label',
        allowClear: true,
        loading,
      }}
    />
  );
};

export default PurchaseDepartmentFormField;
