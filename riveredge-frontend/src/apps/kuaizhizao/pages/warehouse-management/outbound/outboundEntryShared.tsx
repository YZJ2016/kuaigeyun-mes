/**
 * 出库取单录入页 — 共享表单项与出库人选择
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Form } from 'antd';
import { useTranslation } from 'react-i18next';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import {
  getDepartmentTree,
  type DepartmentTreeItem,
} from '../../../../../services/department';
import {
  InboundEntryAttachmentsSection,
  InboundEntryReceiverField,
  InboundEntryRemarksSection,
  ReadOnlyFormValue,
  mapWarehouseSelectOptions,
  readOnlyFieldProps,
  useInboundReceiverSelect,
  type WarehouseSelectOption,
} from '../inbound/inboundEntryShared';
import type { Material } from '../../../../master-data/types/material';

function flattenDepartmentTree(items: DepartmentTreeItem[]): DepartmentTreeItem[] {
  const out: DepartmentTreeItem[] = [];
  const walk = (nodes: DepartmentTreeItem[]) => {
    for (const node of nodes) {
      out.push(node);
      if (node.children?.length) walk(node.children);
    }
  };
  walk(items);
  return out;
}

export type OutboundPickDepartmentOption = {
  value: number;
  label: string;
  code?: string;
};

export function useOutboundPickDepartmentSelect(enabled = true) {
  const [options, setOptions] = useState<OutboundPickDepartmentOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [departmentId, setDepartmentId] = useState<number | undefined>();
  const [departmentCode, setDepartmentCode] = useState<string | undefined>();
  const [departmentName, setDepartmentName] = useState<string | undefined>();

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const deptRes = await getDepartmentTree({ is_active: true });
        if (!cancelled) {
          setOptions(
            flattenDepartmentTree(deptRes.items || []).map((d) => ({
              value: d.id,
              label: d.code ? `${d.code} - ${d.name}` : d.name,
              code: d.code,
            })),
          );
        }
      } catch {
        if (!cancelled) setOptions([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  const restoreFromDetail = useCallback(
    (detail: {
      pick_department_id?: unknown;
      pick_department_code?: unknown;
      pick_department_name?: unknown;
    }) => {
      const id = Number(detail.pick_department_id);
      setDepartmentId(id > 0 ? id : undefined);
      const code = String(detail.pick_department_code ?? '').trim();
      setDepartmentCode(code || undefined);
      const name = String(detail.pick_department_name ?? '').trim();
      setDepartmentName(name || undefined);
    },
    [],
  );

  const handleDepartmentChange = useCallback(
    (val: number | undefined) => {
      setDepartmentId(val);
      const row = options.find((d) => d.value === val);
      setDepartmentCode(row?.code);
      const label = row?.label ?? '';
      setDepartmentName(
        label.includes(' - ') ? label.split(' - ').slice(1).join(' - ').trim() : label || undefined,
      );
    },
    [options],
  );

  const toPayload = useCallback(
    () => ({
      pick_department_id: departmentId,
      pick_department_code: departmentCode,
      pick_department_name: departmentName,
    }),
    [departmentCode, departmentId, departmentName],
  );

  return {
    options,
    loading,
    departmentId,
    handleDepartmentChange,
    restoreFromDetail,
    toPayload,
  };
}

type OutboundEntryPickDepartmentFieldProps = {
  hook: ReturnType<typeof useOutboundPickDepartmentSelect>;
};

export function OutboundEntryPickDepartmentField({ hook }: OutboundEntryPickDepartmentFieldProps) {
  const { t } = useTranslation();
  const { options, loading, departmentId, handleDepartmentChange } = hook;
  return (
    <Form.Item
      label={t('app.kuaizhizao.warehouseOutbound.field.pickDepartment')}
      required
    >
      <UniDropdown
        placeholder={t('app.kuaizhizao.warehouseOutbound.field.pickDepartmentPlaceholder')}
        showSearch
        allowClear={false}
        loading={loading}
        style={{ width: '100%' }}
        options={options}
        value={departmentId}
        onChange={(val) => handleDepartmentChange(val != null ? Number(val) : undefined)}
      />
    </Form.Item>
  );
}

export {
  readOnlyFieldProps,
  ReadOnlyFormValue,
  mapWarehouseSelectOptions,
  type WarehouseSelectOption,
  useInboundReceiverSelect as useOutboundOperatorSelect,
  InboundEntryAttachmentsSection as OutboundEntryAttachmentsSection,
};

type OutboundEntryOperatorFieldProps = {
  label?: string;
  hook: ReturnType<typeof useInboundReceiverSelect>;
};

export function OutboundEntryOperatorField({ label, hook }: OutboundEntryOperatorFieldProps) {
  const { t } = useTranslation();
  return <InboundEntryReceiverField label={label ?? t('app.kuaizhizao.warehouseOutbound.field.operator')} hook={hook} />;
}

type OutboundEntryRemarksSectionProps = {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  placeholder?: string;
};

export function OutboundEntryRemarksSection({
  value,
  onChange,
  label,
  placeholder,
}: OutboundEntryRemarksSectionProps) {
  const { t } = useTranslation();
  return (
    <InboundEntryRemarksSection
      value={value}
      onChange={onChange}
      label={label ?? t('app.kuaizhizao.warehouseOutbound.field.remarks')}
      placeholder={placeholder ?? t('app.kuaizhizao.warehouseOutbound.field.remarksPlaceholder')}
    />
  );
}

/** 物料主数据默认出库仓（领料/出库取单共用） */
export function resolvePrimaryDefaultWarehouse(
  material: Material,
): { id: number; name: string } | null {
  const wh = material.defaultWarehouse ?? material.default_warehouse;
  if (wh && typeof wh === 'object' && 'id' in wh && wh.id) {
    return { id: Number(wh.id), name: String((wh as { name?: string }).name ?? '') };
  }
  return null;
}
