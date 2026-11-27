/**
 * 采购单据表头「部门」选择（与杂项凭证 / 其他出库同一套部门树扁平选项）。
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Form } from 'antd';
import { ProFormSelect, type ProFormSelectProps } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { getDepartmentTree } from '../../../../../services/department';
import {
  flattenDepartmentTreeOptions,
  type DepartmentPickerOption,
} from '../../../../master-data/utils/flattenDepartmentTreeOptions';

export type PurchaseDepartmentOption = Pick<DepartmentPickerOption, 'label' | 'value' | 'uuid'>;

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
            uuid: d.uuid,
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

/** 按申请人所在部门 uuid 映射采购表头 department_id/name（选项未就绪时返回空）。 */
export function resolvePurchaseDepartmentFromApplicant(
  departmentUuid: string | null | undefined,
  options: PurchaseDepartmentOption[],
): { department_id?: number; department_name?: string } {
  const uuid = String(departmentUuid ?? '').trim();
  if (!uuid || !options.length) {
    return { department_id: undefined, department_name: undefined };
  }
  const hit = options.find((o) => o.uuid === uuid);
  if (!hit) {
    return { department_id: undefined, department_name: undefined };
  }
  return { department_id: hit.value, department_name: hit.label };
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
  required?: boolean;
  /** 覆盖默认 common.required 文案 */
  requiredMessage?: string;
  options: PurchaseDepartmentOption[];
  loading?: boolean;
  colProps?: ProFormSelectProps['colProps'];
};

/** 表头部门下拉；外层自行包 Col。 */
export const PurchaseDepartmentFormField: React.FC<PurchaseDepartmentFormFieldProps> = ({
  name = 'department_id',
  disabled,
  required = false,
  requiredMessage,
  options,
  loading,
  colProps,
}) => {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const watchedDeptId = Form.useWatch(name, form);
  const watchedDeptName = Form.useWatch('department_name', form);
  const mergedOptions = useMemo(() => {
    const id = Number(watchedDeptId);
    if (!Number.isFinite(id) || id <= 0) return options;
    if (options.some((o) => Number(o.value) === id)) return options;
    const fallbackLabel = String(watchedDeptName ?? '').trim();
    if (!fallbackLabel) return options;
    return [{ value: id, label: fallbackLabel, uuid: '' }, ...options];
  }, [options, watchedDeptId, watchedDeptName]);
  const departmentRequiredMsg =
    requiredMessage ?? t('app.kuaizhizao.purchaseOrder.form.departmentRequired', '请选择部门');

  return (
    <ProFormSelect
      name={name}
      label={t('app.kuaizhizao.purchase.field.department')}
      colProps={colProps}
      options={mergedOptions}
      disabled={disabled}
      rules={required ? [{ required: true, message: departmentRequiredMsg }] : undefined}
      fieldProps={{
        showSearch: true,
        optionFilterProp: 'label',
        allowClear: !required,
        loading,
      }}
    />
  );
};

export default PurchaseDepartmentFormField;
