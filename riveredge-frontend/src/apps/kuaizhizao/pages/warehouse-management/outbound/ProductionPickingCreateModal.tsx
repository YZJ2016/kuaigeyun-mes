/**
 * 生产领料空白建单 / 编辑（与新建同一 FormModal，确认领料前可改）。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { App, Button, Col, Form as AntForm, Input, Row, Space, Typography } from 'antd';
import {
  ProFormDatePicker,
  ProFormItem,
  ProFormTextArea,
  type ProFormInstance,
} from '@ant-design/pro-components';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { FormModalTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import CodeField from '../../../../../components/code-field';
import { UniTableDetail } from '../../../../../components/uni-table-detail';
import {
  DOCUMENT_DETAIL_COL_WIDTH,
  DOCUMENT_DETAIL_CONTROL_SIZE,
  DOCUMENT_DETAIL_NUM_COL,
  DOCUMENT_DETAIL_TABLE_PROPS,
  DOCUMENT_DETAIL_TEXT_COL,
  DocumentDetailTableStyles,
} from '../../../components/document-detail-table/documentDetailTable';
import { UniMaterialSelect } from '../../../../../components/uni-material-select';
import {
  UniWhDropdown,
  UniWhLocationDropdown,
  useWarehouseHasLocations,
  lineLocationSelectionRequired,
} from '../../../../../components/uni-wh-dropdown';
import { getPopupContainerInModal } from '../../../../../utils/modalEventIsolation';
import { warehouseApi } from '../../../services/production';
import { useNumericPrecisionPlaces } from '../../../../../hooks/useNumericPrecision';
import { toApiBusinessDocumentDateTime } from '../../../../../utils/formDate';
import {
  buildDocumentDetailSpecModelFormColumns,
  withMaterialLineFillMapping,
} from '../../sales-management/shared/materialLineFormDetail';
import { resolveMaterialScenarioUnit } from '../../../../../utils/materialScenarioUnit';
import { buildDocumentLineDualQuantityPairColumns } from '../../../../../components/quantity-with-unit';
import {
  resolveAuxUnitForScenario,
  syncDualQuantitiesFixed,
  validateDualQuantityBeforeSave,
} from '../../../../../utils/materialDualQuantity';
import {
  fetchMaterialForUnitSelectCache,
  prefetchMaterialsForUnitSelect,
} from '../../../../../components/material-unit-select';
import type { Material } from '../../../../master-data/types/material';
import { normalizeFormListItems } from '../../../../../utils/formListItems';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import type { User } from '../../../../../services/user';
import { searchUserDisplay } from '../../../../../services/user';
import {
  displayItemsToUsers,
  formatUserDisplayLabel,
  normalizeUserDisplayName,
} from '../../../../../utils/userDisplay';
import {
  getDepartmentTree,
  type DepartmentTreeItem,
} from '../../../../../services/department';
import { materialApi } from '../../../../master-data/services/material';

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
import { SerialNumbersImportTrigger } from '../../../../../components/serial-numbers-import';
import {
  applyMaterialTrackingToFormRow,
  readMaterialTrackingFromPicker,
} from '../inbound/inboundItemTracking';
import {
  filterWarehouseTrackingColumns,
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  isOutboundConfirmBatchLineEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import {
  loadAvailableQtyByMaterialId,
  loadBatchOptionsByMaterialId,
  resolveOutboundConfirmBatchValue,
  type InventoryPickOption,
} from './outboundConfirmInventoryOptions';
import { fetchBatchMaterialInventory } from '../../../../../components/uni-material-batch-picker/utils';
import { formatQuantity } from '../../../../../utils/format';
import OutboundBatchAllocationField from './OutboundBatchAllocationField';
import {
  allocateBatchQuantitiesFifo,
  coerceBatchAllocationsDraft,
  isValidOutboundBatchAllocations,
  type OutboundBatchAllocation,
} from './outboundBatchAllocation';
import { isOutboundEditable, outboundDocumentCode } from './outboundHubTypes';
import type { OutboundHubOrder } from './outboundHubTypes';
import { resolvePrimaryDefaultWarehouse } from './outboundEntryShared';

const OUTBOUND_HOST_RESOURCE = 'kuaizhizao:outbound';

/** 明细物料+仓库指纹：触发按行仓库存重拉 */
function productionPickingLineStockFingerprint(items: unknown): string {
  if (!Array.isArray(items)) return '';
  return [
    ...new Set(
      items
        .map((raw) => {
          const it = raw as { material_id?: unknown; warehouse_id?: unknown };
          const mid = Number(it?.material_id);
          const wh = Number(it?.warehouse_id);
          if (!(mid > 0)) return '';
          return wh > 0 ? `${mid}:${wh}` : `${mid}:`;
        })
        .filter(Boolean),
    ),
  ]
    .sort()
    .join(',');
}

const defaultLineItem = {
  id: undefined as number | undefined,
  required_quantity: 1,
  warehouse_id: undefined as number | undefined,
  warehouse_name: undefined as string | undefined,
  location_id: undefined as number | undefined,
  location_code: undefined as string | undefined,
  batch_number: undefined as string | undefined,
  batch_allocations: [] as OutboundBatchAllocation[],
  batch_managed: false,
  serial_managed: false,
  serial_numbers: undefined as string[] | undefined,
};

function lineBatchAllocations(
  row: Record<string, unknown>,
  qty: number,
): OutboundBatchAllocation[] {
  return (
    coerceBatchAllocationsDraft(row.batch_allocations, qty) ??
    coerceBatchAllocationsDraft(row.batch_number, qty) ??
    []
  ).filter((a) => String(a.batchNo).trim() && Number(a.quantity) > 0);
}

function syncLineBatchFields(
  setFieldValue: (name: (string | number)[], value: unknown) => void,
  index: number,
  allocs: OutboundBatchAllocation[],
) {
  setFieldValue(['items', index, 'batch_allocations'], allocs);
  setFieldValue(
    ['items', index, 'batch_number'],
    allocs.length === 1 ? allocs[0].batchNo : undefined,
  );
}

function batchOptionsCacheKey(materialId: number, warehouseId: number): string {
  return `${materialId}:${warehouseId}`;
}

function productionPickingCreateBatchLineEnabled(
  trackingFlags: ReturnType<typeof useWarehouseTrackingFlags>,
  batchManaged?: boolean | null,
): boolean {
  return isOutboundConfirmBatchLineEnabled('production_picking', trackingFlags, batchManaged);
}

export type ProductionPickingCreateModalProps = {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  /** 有值则为编辑，表单布局与新建一致 */
  editingId?: number | null;
};

function UserPickField({
  name,
  nameField,
  label,
  placeholder,
  userList,
  loading,
  departmentOptions,
  required,
}: {
  name: string;
  nameField: string;
  label: string;
  placeholder: string;
  userList: User[];
  loading: boolean;
  departmentOptions?: Array<{ value: number; label: string; code?: string }>;
  required?: boolean;
}) {
  const { t } = useTranslation();
  const form = AntForm.useFormInstance();
  const pickedId = AntForm.useWatch(name, form);
  const pickedName = AntForm.useWatch(nameField, form);

  const options = useMemo(() => {
    const base = userList.map((u) => ({
      value: Number(u.id),
      label: formatUserDisplayLabel(u),
    }));
    const bid =
      pickedId != null && pickedId !== '' && Number.isFinite(Number(pickedId))
        ? Number(pickedId)
        : NaN;
    if (Number.isFinite(bid) && !base.some((o) => o.value === bid)) {
      const labelText =
        normalizeUserDisplayName(pickedName) ||
        t('app.kuaizhizao.quotation.userFallback', { id: bid });
      return [{ value: bid, label: labelText }, ...base];
    }
    return base;
  }, [userList, pickedId, pickedName, t]);

  return (
    <>
      <ProFormItem
        name={name}
        label={label}
        rules={
          required
            ? [
                {
                  required: true,
                  message: t('app.kuaizhizao.warehouseOutbound.msg.requesterRequired'),
                },
              ]
            : undefined
        }
        normalize={(v) =>
          v != null && v !== '' && Number.isFinite(Number(v)) ? Number(v) : undefined
        }
      >
        <UniDropdown
          placeholder={placeholder}
          showSearch
          allowClear
          loading={loading}
          style={{ width: '100%' }}
          options={options}
          onChange={(val, opt: { label?: React.ReactNode } | undefined) => {
            const patch: Record<string, unknown> = {
              [nameField]: typeof opt?.label === 'string' ? opt.label : undefined,
            };
            const uid =
              val != null && val !== '' && Number.isFinite(Number(val)) ? Number(val) : NaN;
            const picked = Number.isFinite(uid) ? userList.find((u) => Number(u.id) === uid) : undefined;
            if (departmentOptions?.length && picked?.department?.code) {
              const hasDept = form.getFieldValue('pick_department_id');
              if (hasDept == null || hasDept === '') {
                const row = departmentOptions.find((d) => d.code === picked.department?.code);
                if (row) {
                  patch.pick_department_id = row.value;
                  patch.pick_department_code = row.code;
                  patch.pick_department_name = row.label.includes(' - ')
                    ? row.label.split(' - ').slice(1).join(' - ').trim()
                    : row.label;
                }
              }
            }
            form.setFieldsValue(patch);
          }}
        />
      </ProFormItem>
      <AntForm.Item name={nameField} hidden>
        <Input />
      </AntForm.Item>
    </>
  );
}

function ProductionPickingCreateWarehouseCell({
  index,
  trackingFlags,
  clearLineWarehouseDependents,
  ensureBatchOptions,
  syncLineStockKeyFromForm,
  formRef,
  t,
}: {
  index: number;
  trackingFlags: ReturnType<typeof useWarehouseTrackingFlags>;
  clearLineWarehouseDependents: (index: number) => void;
  ensureBatchOptions: (materialId: number, warehouseId: number, lineIndex: number) => Promise<void>;
  syncLineStockKeyFromForm: () => void;
  formRef: React.MutableRefObject<ProFormInstance | undefined>;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  const materialId = Number(AntForm.useWatch(['items', index, 'material_id']) || 0);
  return (
    <div>
      <AntForm.Item name={[index, 'warehouse_name']} hidden>
        <Input />
      </AntForm.Item>
      <AntForm.Item
        name={[index, 'warehouse_id']}
        rules={[
          {
            required: true,
            message: t('app.kuaizhizao.warehouseOutbound.msg.selectWarehouse'),
          },
        ]}
        noStyle
      >
        <UniWhDropdown
          size={DOCUMENT_DETAIL_CONTROL_SIZE}
          hostResource={OUTBOUND_HOST_RESOURCE}
          materialId={materialId > 0 ? materialId : undefined}
          showStock={materialId > 0}
          sortByStock={materialId > 0}
          placeholder={t('app.kuaizhizao.warehouseOutbound.msg.selectWarehouse')}
          getPopupContainer={getPopupContainerInModal}
          onChange={(_id, wh) => {
            clearLineWarehouseDependents(index);
            const whId = Number(wh?.id ?? _id ?? 0);
            formRef.current?.setFieldValue(['items', index, 'warehouse_name'], wh?.name ?? '');
            syncLineStockKeyFromForm();
            if (whId > 0) {
              const mid = Number(
                formRef.current?.getFieldValue(['items', index, 'material_id']) || 0,
              );
              const batchManaged = !!formRef.current?.getFieldValue([
                'items',
                index,
                'batch_managed',
              ]);
              if (
                mid > 0 &&
                productionPickingCreateBatchLineEnabled(trackingFlags, batchManaged)
              ) {
                void ensureBatchOptions(mid, whId, index);
              }
            }
          }}
        />
      </AntForm.Item>
    </div>
  );
}

function ProductionPickingCreateLocationCell({
  index,
  formRef,
  t,
}: {
  index: number;
  formRef: React.MutableRefObject<ProFormInstance | undefined>;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  const materialId = Number(AntForm.useWatch(['items', index, 'material_id']) || 0);
  const warehouseId = Number(AntForm.useWatch(['items', index, 'warehouse_id']) || 0);
  const hasLocations = useWarehouseHasLocations(warehouseId > 0 ? warehouseId : undefined);

  return (
    <>
      <AntForm.Item name={[index, 'location_code']} hidden>
        <Input />
      </AntForm.Item>
      {hasLocations === false ? (
        <>
          <AntForm.Item name={[index, 'location_id']} hidden>
            <Input />
          </AntForm.Item>
          <span className="uni-wh-whole-location-auto">
            {t('app.kuaizhizao.warehouseOutbound.pull.wholeLocationAuto')}
          </span>
        </>
      ) : (
        <AntForm.Item
          name={[index, 'location_id']}
          rules={[
            {
              validator: async (_, value) => {
                if (!(warehouseId > 0)) return;
                const code = formRef.current?.getFieldValue(['items', index, 'location_code']);
                const need = await lineLocationSelectionRequired(warehouseId, value, code);
                if (need) {
                  throw new Error(t('app.kuaizhizao.warehouseOutbound.msg.selectLocation'));
                }
              },
            },
          ]}
          noStyle
        >
          <UniWhLocationDropdown
            warehouseId={warehouseId > 0 ? warehouseId : undefined}
            materialId={materialId > 0 ? materialId : undefined}
            hostResource={OUTBOUND_HOST_RESOURCE}
            showStock={false}
            allowClear={false}
            size={DOCUMENT_DETAIL_CONTROL_SIZE}
            getPopupContainer={getPopupContainerInModal}
            disabled={!(warehouseId > 0) || hasLocations === undefined}
            placeholder={
              warehouseId > 0
                ? t('app.kuaizhizao.warehouseOutbound.col.location')
                : t('app.kuaizhizao.warehouseOutbound.field.selectWarehouseFirst')
            }
            onChange={(_value, loc) => {
              formRef.current?.setFieldValue(['items', index, 'location_code'], loc?.code ?? '');
            }}
          />
        </AntForm.Item>
      )}
    </>
  );
}

export const ProductionPickingCreateModal: React.FC<ProductionPickingCreateModalProps> = ({
  open,
  onClose,
  onSuccess,
  editingId = null,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>();
  const currentUser = useCurrentUser();
  const quantityDecimals = useNumericPrecisionPlaces('quantity');
  const trackingFlags = useWarehouseTrackingFlags();
  const isEdit = editingId != null && Number(editingId) > 0;
  const [formLoading, setFormLoading] = useState(false);
  const [editDocumentCode, setEditDocumentCode] = useState('');
  const [users, setUsers] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [departmentOptions, setDepartmentOptions] = useState<
    Array<{ value: number; label: string; code?: string }>
  >([]);
  const [departmentsLoading, setDepartmentsLoading] = useState(false);
  const [batchOptionsByKey, setBatchOptionsByKey] = useState<Record<string, InventoryPickOption[]>>({});
  const [batchOptionsLoadingKey, setBatchOptionsLoadingKey] = useState<string | null>(null);
  const [stockByKey, setStockByKey] = useState<Record<string, number>>({});
  const [stockLoading, setStockLoading] = useState(false);
  const [lineStockKey, setLineStockKey] = useState('');

  const syncLineStockKeyFromForm = useCallback(() => {
    setLineStockKey(productionPickingLineStockFingerprint(formRef.current?.getFieldValue('items')));
  }, []);

  const defaultPerson = useMemo(() => {
    if (!currentUser) return { id: undefined as number | undefined, name: '' };
    const id = currentUser.id != null && currentUser.id > 0 ? Number(currentUser.id) : undefined;
    const name = String(currentUser.full_name || currentUser.username || '').trim();
    return { id, name };
  }, [currentUser]);

  const batchOptionLabel = useCallback(
    (batch: string, qty: number, warehouseName?: string) =>
      warehouseName
        ? t('app.kuaizhizao.warehouseOutbound.confirm.batchAvailableWithWh', {
            batch,
            qty,
            warehouse: warehouseName,
          })
        : t('app.kuaizhizao.warehouseOutbound.confirm.batchAvailable', { batch, qty }),
    [t],
  );

  const applyFifoPreferredBatchToLine = useCallback(
    (lineIndex: number, opts: InventoryPickOption[]) => {
      if (!formRef.current || !opts.length) return;
      const qty = Number(
        formRef.current.getFieldValue(['items', lineIndex, 'required_quantity']) || 0,
      );
      const currentAllocs = lineBatchAllocations(
        {
          batch_allocations: formRef.current.getFieldValue([
            'items',
            lineIndex,
            'batch_allocations',
          ]),
          batch_number: formRef.current.getFieldValue(['items', lineIndex, 'batch_number']),
        },
        qty,
      );
      if (currentAllocs.length) {
        syncLineBatchFields(
          (name, value) => formRef.current?.setFieldValue(name, value),
          lineIndex,
          allocateBatchQuantitiesFifo(
            qty,
            currentAllocs.map((a) => a.batchNo),
            opts,
            currentAllocs,
          ),
        );
        return;
      }
      const picked = resolveOutboundConfirmBatchValue(undefined, opts);
      if (!picked) return;
      if (opts.length !== 1) {
        const preferred = opts.find((o) => o.fifoRecommended);
        if (!preferred || preferred.value !== picked) return;
      }
      syncLineBatchFields(
        (name, value) => formRef.current?.setFieldValue(name, value),
        lineIndex,
        allocateBatchQuantitiesFifo(qty, [picked], opts),
      );
    },
    [],
  );

  const ensureBatchOptions = useCallback(
    async (materialId: number, warehouseId: number, lineIndex: number) => {
      const mid = Number(materialId);
      const whId = Number(warehouseId);
      if (!(mid > 0) || !(whId > 0)) return;
      const key = batchOptionsCacheKey(mid, whId);
      setBatchOptionsLoadingKey(key);
      try {
        const map = await loadBatchOptionsByMaterialId([mid], whId, batchOptionLabel);
        const opts = map[mid] ?? [];
        setBatchOptionsByKey((prev) => ({ ...prev, [key]: opts }));
        applyFifoPreferredBatchToLine(lineIndex, opts);
      } finally {
        setBatchOptionsLoadingKey((cur) => (cur === key ? null : cur));
      }
    },
    [applyFifoPreferredBatchToLine, batchOptionLabel],
  );

  const syncLineMaterialTracking = useCallback(
    async (index: number, material: Material | undefined) => {
      if (!formRef.current) return;
      if (!material) {
        formRef.current.setFieldValue(['items', index, 'batch_managed'], false);
        formRef.current.setFieldValue(['items', index, 'serial_managed'], false);
        return;
      }
      let batchManaged = !!(material.batchManaged ?? (material as { batch_managed?: boolean }).batch_managed);
      let serialManaged = !!(material.serialManaged ?? (material as { serial_managed?: boolean }).serial_managed);
      const fromPicker = readMaterialTrackingFromPicker(material as unknown as Record<string, unknown>);
      if (fromPicker) {
        applyMaterialTrackingToFormRow(
          (name, value) => formRef.current!.setFieldValue(name, value),
          'items',
          index,
          fromPicker,
        );
        batchManaged = fromPicker.batchManaged;
        serialManaged = fromPicker.serialManaged;
      }
      if (material.uuid) {
        try {
          const full = await materialApi.get(material.uuid);
          batchManaged = !!full.batchManaged;
          serialManaged = !!full.serialManaged;
          const meta = readMaterialTrackingFromPicker(full as unknown as Record<string, unknown>);
          if (meta) {
            applyMaterialTrackingToFormRow(
              (name, value) => formRef.current!.setFieldValue(name, value),
              'items',
              index,
              meta,
            );
            batchManaged = meta.batchManaged;
            serialManaged = meta.serialManaged;
          }
        } catch {
          /* use picker fields */
        }
      }
      formRef.current.setFieldValue(
        ['items', index, 'batch_managed'],
        isMaterialBatchEntryEnabled(trackingFlags, batchManaged),
      );
      formRef.current.setFieldValue(
        ['items', index, 'serial_managed'],
        isMaterialSerialEntryEnabled(trackingFlags, serialManaged),
      );
    },
    [trackingFlags],
  );

  const clearLineWarehouseDependents = useCallback(
    (index: number) => {
      formRef.current?.setFieldValue(['items', index, 'location_id'], undefined);
      formRef.current?.setFieldValue(['items', index, 'location_code'], '');
      formRef.current?.setFieldValue(['items', index, 'batch_number'], undefined);
      formRef.current?.setFieldValue(['items', index, 'batch_allocations'], []);
      syncLineStockKeyFromForm();
    },
    [syncLineStockKeyFromForm],
  );

  useEffect(() => {
    if (!open) {
      setStockByKey({});
      setStockLoading(false);
      setLineStockKey('');
      return;
    }
    const pairs = lineStockKey
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .map((s) => {
        const [midRaw, whRaw] = s.split(':');
        return { mid: Number(midRaw), wh: Number(whRaw) };
      })
      .filter((p) => Number.isFinite(p.mid) && p.mid > 0);
    if (!pairs.length) {
      setStockByKey({});
      setStockLoading(false);
      return;
    }
    let cancelled = false;
    setStockLoading(true);
    void (async () => {
      const next: Record<string, number> = {};
      const withWh = new Map<number, number[]>();
      const noWh: number[] = [];
      for (const p of pairs) {
        if (p.wh > 0) {
          const list = withWh.get(p.wh) ?? [];
          list.push(p.mid);
          withWh.set(p.wh, list);
        } else {
          noWh.push(p.mid);
        }
      }
      try {
        for (const [whId, mids] of withWh) {
          const map = await loadAvailableQtyByMaterialId([...new Set(mids)], whId);
          for (const mid of mids) {
            next[`${mid}:${whId}`] = map[mid] ?? 0;
          }
        }
        if (noWh.length) {
          const map = await fetchBatchMaterialInventory([...new Set(noWh)]);
          for (const mid of noWh) {
            next[`${mid}:`] = map[mid] ?? 0;
          }
        }
        if (!cancelled) setStockByKey(next);
      } catch {
        if (!cancelled) setStockByKey({});
      } finally {
        if (!cancelled) setStockLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, lineStockKey]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setBatchOptionsByKey({});
    setBatchOptionsLoadingKey(null);
    (async () => {
      setUsersLoading(true);
      setDepartmentsLoading(true);
      try {
        const [userRes, deptRes] = await Promise.all([
          searchUserDisplay({ page_size: 100, is_active: true }),
          getDepartmentTree({ is_active: true }),
        ]);
        if (!cancelled) {
          setUsers(displayItemsToUsers(userRes.items || []));
          setDepartmentOptions(
            flattenDepartmentTree(deptRes.items || []).map((d) => ({
              value: d.id,
              label: d.code ? `${d.code} - ${d.name}` : d.name,
              code: d.code,
            })),
          );
        }
      } catch {
        if (!cancelled) {
          setUsers([]);
          setDepartmentOptions([]);
        }
      } finally {
        if (!cancelled) {
          setUsersLoading(false);
          setDepartmentsLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    const hydrateEdit = async () => {
      if (!isEdit || editingId == null) {
        setEditDocumentCode('');
        return;
      }
      setFormLoading(true);
      try {
        const detail = (await warehouseApi.productionPicking.get(String(editingId))) as Record<
          string,
          unknown
        >;
        if (cancelled) return;
        const hubRow = { ...detail, outbound_type: 'production_picking' as const };
        if (!isOutboundEditable(hubRow as OutboundHubOrder)) {
          messageApi.warning(t('app.kuaizhizao.warehouseOutbound.msg.pickingEditFailed'));
          onClose();
          return;
        }
        setEditDocumentCode(outboundDocumentCode(hubRow as OutboundHubOrder));
        const rawItems = Array.isArray(detail.items) ? detail.items : [];
        const items = rawItems.map((raw) => {
          const line = raw as Record<string, unknown>;
          const serials = Array.isArray(line.serial_numbers)
            ? line.serial_numbers.map((s) => String(s ?? '').trim()).filter(Boolean)
            : typeof line.serial_numbers === 'string' && String(line.serial_numbers).trim()
              ? String(line.serial_numbers)
                  .split(/[,，\s]+/)
                  .map((s) => s.trim())
                  .filter(Boolean)
              : undefined;
          return {
            ...defaultLineItem,
            id: Number(line.id) > 0 ? Number(line.id) : undefined,
            material_id: Number(line.material_id) || undefined,
            material_code: String(line.material_code ?? ''),
            material_name: String(line.material_name ?? ''),
            material_spec: line.material_spec != null ? String(line.material_spec) : undefined,
            material_model: line.material_model != null ? String(line.material_model) : undefined,
            material_unit: String(line.material_unit ?? ''),
            required_quantity: Number(line.required_quantity) || 1,
            warehouse_id: Number(line.warehouse_id) > 0 ? Number(line.warehouse_id) : undefined,
            warehouse_name: String(line.warehouse_name ?? ''),
            location_id: Number(line.location_id) > 0 ? Number(line.location_id) : undefined,
            location_code: line.location_code != null ? String(line.location_code) : undefined,
            batch_number: line.batch_number != null ? String(line.batch_number) : undefined,
            batch_allocations:
              coerceBatchAllocationsDraft(
                line.batch_number,
                Number(line.required_quantity) || 0,
              ) ?? [],
            batch_managed: !!line.batch_managed,
            serial_managed: !!line.serial_managed,
            serial_numbers: serials,
            aux_quantity: line.aux_quantity != null ? Number(line.aux_quantity) : undefined,
            aux_unit: line.aux_unit != null ? String(line.aux_unit) : undefined,
            unit_conversion_rate:
              line.unit_conversion_rate != null ? Number(line.unit_conversion_rate) : undefined,
          };
        });
        const pickingTimeRaw = detail.picking_time ?? detail.picking_date;
        formRef.current?.setFieldsValue({
          picking_code: String(detail.picking_code ?? ''),
          picker_id: Number(detail.picker_id) > 0 ? Number(detail.picker_id) : defaultPerson.id,
          picker_name: String(detail.picker_name ?? '').trim() || defaultPerson.name,
          picking_time: pickingTimeRaw ? dayjs(String(pickingTimeRaw)) : dayjs(),
          pick_department_id:
            Number(detail.pick_department_id) > 0 ? Number(detail.pick_department_id) : undefined,
          pick_department_code: String(detail.pick_department_code ?? '') || undefined,
          pick_department_name: String(detail.pick_department_name ?? '') || undefined,
          notes: String(detail.notes ?? ''),
          items: items.length ? items : [{ ...defaultLineItem }],
        });
        setLineStockKey(productionPickingLineStockFingerprint(items.length ? items : [{ ...defaultLineItem }]));
        setBatchOptionsByKey({});
        await Promise.all(
          items.map(async (row, index) => {
            const mid = Number(row.material_id);
            const whId = Number(row.warehouse_id);
            if (!(mid > 0)) return;
            const material = await fetchMaterialForUnitSelectCache(mid);
            if (cancelled) return;
            if (material) {
              formRef.current?.setFieldValue(
                ['items', index, 'batch_managed'],
                !!material.batchManaged,
              );
              formRef.current?.setFieldValue(
                ['items', index, 'serial_managed'],
                !!material.serialManaged,
              );
            }
            if (
              whId > 0 &&
              productionPickingCreateBatchLineEnabled(
                trackingFlags,
                material?.batchManaged ?? row.batch_managed,
              )
            ) {
              await ensureBatchOptions(mid, whId, index);
            }
          }),
        );
      } catch (e: unknown) {
        if (cancelled) return;
        const err = e as { message?: string };
        messageApi.error(
          err?.message || t('app.kuaizhizao.warehouseOutbound.msg.loadDetailFailed'),
        );
        onClose();
      } finally {
        if (!cancelled) setFormLoading(false);
      }
    };

    void hydrateEdit();
    return () => {
      cancelled = true;
    };
  }, [
    open,
    isEdit,
    editingId,
    defaultPerson,
    ensureBatchOptions,
    trackingFlags,
    messageApi,
    onClose,
    t,
  ]);

  const formItemColumns = useMemo(() => {
    const cols = [
      {
        title: t('common.material'),
        dataIndex: 'material_id',
        width: DOCUMENT_DETAIL_COL_WIDTH.material,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <div>
            <AntForm.Item name={[index, 'id']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'material_code']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'material_name']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'material_spec']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'batch_managed']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'serial_managed']} hidden>
              <Input />
            </AntForm.Item>
            <UniMaterialSelect
              name={[index, 'material_id']}
              label=""
              placeholder={t('common.selectMaterial')}
              required
              size={DOCUMENT_DETAIL_CONTROL_SIZE}
              listFieldKey={index}
              listFieldName="items"
              fillMapping={withMaterialLineFillMapping({ material_unit: 'baseUnit' })}
              showAdvancedSearch
              skipFuzzyPinyinClientFilter
              onChange={(_v, material) => {
                clearLineWarehouseDependents(index);
                formRef.current?.setFieldValue(['items', index, 'serial_numbers'], undefined);
                if (!material) {
                  void syncLineMaterialTracking(index, undefined);
                  syncLineStockKeyFromForm();
                  return;
                }
                const mat = material as Material;
                formRef.current?.setFieldValue(
                  ['items', index, 'material_unit'],
                  resolveMaterialScenarioUnit(mat, 'production'),
                );
                void syncLineMaterialTracking(index, mat);
                const primaryWh = resolvePrimaryDefaultWarehouse(mat);
                if (primaryWh) {
                  formRef.current?.setFieldValue(['items', index, 'warehouse_id'], primaryWh.id);
                  formRef.current?.setFieldValue(['items', index, 'warehouse_name'], primaryWh.name);
                  const batchManaged = !!(mat.batchManaged ?? (mat as { batch_managed?: boolean }).batch_managed);
                  if (productionPickingCreateBatchLineEnabled(trackingFlags, batchManaged)) {
                    void ensureBatchOptions(Number(mat.id), primaryWh.id, index);
                  }
                }
                syncLineStockKeyFromForm();
              }}
            />
          </div>
        ),
      },
      ...buildDocumentDetailSpecModelFormColumns(t),
      ...buildDocumentLineDualQuantityPairColumns({
        t,
        getForm: () => formRef.current,
        quantityField: 'required_quantity',
        unitField: 'material_unit',
        scenario: 'production',
        quantityPrecision: quantityDecimals,
        columnSpread: DOCUMENT_DETAIL_NUM_COL,
        inlineUnitWithQuantity: true,
        onAfterQuantityChange: (index) => {
          const qty = Number(
            formRef.current?.getFieldValue(['items', index, 'required_quantity']) || 0,
          );
          const materialId = Number(
            formRef.current?.getFieldValue(['items', index, 'material_id']) || 0,
          );
          const whId = Number(
            formRef.current?.getFieldValue(['items', index, 'warehouse_id']) || 0,
          );
          const key =
            materialId > 0 && whId > 0 ? batchOptionsCacheKey(materialId, whId) : '';
          const opts = key ? batchOptionsByKey[key] ?? [] : [];
          const current = lineBatchAllocations(
            {
              batch_allocations: formRef.current?.getFieldValue([
                'items',
                index,
                'batch_allocations',
              ]),
              batch_number: formRef.current?.getFieldValue(['items', index, 'batch_number']),
            },
            qty,
          );
          if (!current.length || !opts.length) return;
          syncLineBatchFields(
            (name, value) => formRef.current?.setFieldValue(name, value),
            index,
            allocateBatchQuantitiesFifo(
              qty,
              current.map((a) => a.batchNo),
              opts,
              current,
            ),
          );
        },
      }),
      {
        title: t('app.kuaizhizao.warehouseOutbound.field.warehouse'),
        dataIndex: 'warehouse_id',
        width: 220,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <ProductionPickingCreateWarehouseCell
            index={index}
            trackingFlags={trackingFlags}
            clearLineWarehouseDependents={clearLineWarehouseDependents}
            ensureBatchOptions={ensureBatchOptions}
            syncLineStockKeyFromForm={syncLineStockKeyFromForm}
            formRef={formRef}
            t={t}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.pull.colCurrentStock'),
        key: 'current_stock',
        width: 100,
        ...DOCUMENT_DETAIL_NUM_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item
            noStyle
            shouldUpdate={(prev, curr) =>
              prev?.items?.[index]?.material_id !== curr?.items?.[index]?.material_id ||
              prev?.items?.[index]?.warehouse_id !== curr?.items?.[index]?.warehouse_id ||
              prev?.items?.[index]?.required_quantity !== curr?.items?.[index]?.required_quantity
            }
          >
            {({ getFieldValue }) => {
              const mid = Number(getFieldValue(['items', index, 'material_id']) || 0);
              const whId = Number(getFieldValue(['items', index, 'warehouse_id']) || 0);
              if (!(mid > 0)) return '—';
              if (stockLoading) return '…';
              const key = whId > 0 ? `${mid}:${whId}` : `${mid}:`;
              const stock = stockByKey[key];
              if (stock == null) return '—';
              const qty = Number(getFieldValue(['items', index, 'required_quantity']) || 0);
              const insufficient = qty > 0 && stock < qty;
              return (
                <Typography.Text type={insufficient ? 'danger' : undefined}>
                  {formatQuantity(stock)}
                </Typography.Text>
              );
            }}
          </AntForm.Item>
        ),
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.location'),
        dataIndex: 'location_id',
        width: 180,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <ProductionPickingCreateLocationCell index={index} formRef={formRef} t={t} />
        ),
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.batchNo'),
        dataIndex: 'batch_allocations',
        width: 260,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item
            noStyle
            shouldUpdate={(prev, curr) =>
              prev?.items?.[index]?.material_id !== curr?.items?.[index]?.material_id ||
              prev?.items?.[index]?.warehouse_id !== curr?.items?.[index]?.warehouse_id ||
              prev?.items?.[index]?.batch_managed !== curr?.items?.[index]?.batch_managed ||
              prev?.items?.[index]?.required_quantity !==
                curr?.items?.[index]?.required_quantity ||
              prev?.items?.[index]?.batch_allocations !==
                curr?.items?.[index]?.batch_allocations ||
              prev?.items?.[index]?.batch_number !== curr?.items?.[index]?.batch_number
            }
          >
            {({ getFieldValue }) => {
              const materialId = Number(getFieldValue(['items', index, 'material_id']) || 0);
              const whId = Number(getFieldValue(['items', index, 'warehouse_id']) || 0);
              const batchManaged = !!getFieldValue(['items', index, 'batch_managed']);
              if (!productionPickingCreateBatchLineEnabled(trackingFlags, batchManaged)) {
                return <span>—</span>;
              }
              const key =
                materialId > 0 && whId > 0 ? batchOptionsCacheKey(materialId, whId) : '';
              const opts = key ? batchOptionsByKey[key] ?? [] : [];
              const loading = !!key && batchOptionsLoadingKey === key;
              const qty = Number(getFieldValue(['items', index, 'required_quantity']) || 0);
              const allocs = lineBatchAllocations(
                {
                  batch_allocations: getFieldValue(['items', index, 'batch_allocations']),
                  batch_number: getFieldValue(['items', index, 'batch_number']),
                },
                qty,
              );
              const materialLabel = [
                getFieldValue(['items', index, 'material_code']),
                getFieldValue(['items', index, 'material_name']),
              ]
                .filter(Boolean)
                .join(' - ');
              const disabled = !(whId > 0) || !(materialId > 0);
              return (
                <span
                  onClick={() => {
                    if (
                      !disabled &&
                      materialId > 0 &&
                      whId > 0 &&
                      !batchOptionsByKey[key]?.length
                    ) {
                      void ensureBatchOptions(materialId, whId, index);
                    }
                  }}
                >
                  <AntForm.Item name={[index, 'batch_allocations']} hidden>
                    <Input />
                  </AntForm.Item>
                  <AntForm.Item name={[index, 'batch_number']} hidden>
                    <Input />
                  </AntForm.Item>
                  <OutboundBatchAllocationField
                    value={allocs}
                    onChange={(next) =>
                      syncLineBatchFields(
                        (name, value) => formRef.current?.setFieldValue(name, value),
                        index,
                        next,
                      )
                    }
                    options={opts}
                    totalQuantity={qty}
                    loading={loading}
                    disabled={disabled}
                    materialLabel={materialLabel}
                  />
                </span>
              );
            }}
          </AntForm.Item>
        ),
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.serialNo'),
        dataIndex: 'serial_numbers',
        width: 160,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item
            noStyle
            shouldUpdate={(prev, curr) => prev?.items?.[index] !== curr?.items?.[index]}
          >
            {({ getFieldValue }) => {
              const row = getFieldValue('items')?.[index];
              if (!row?.serial_managed) return <span>—</span>;
              const qty = Number(row?.required_quantity ?? 0);
              const sn = getFieldValue(['items', index, 'serial_numbers']);
              return (
                <SerialNumbersImportTrigger
                  serials={Array.isArray(sn) ? sn : []}
                  expectedCount={qty > 0 ? qty : undefined}
                  materialLabel={row?.material_code || row?.material_name}
                  onSerialsChange={(next) =>
                    formRef.current?.setFieldValue(['items', index, 'serial_numbers'], next)
                  }
                />
              );
            }}
          </AntForm.Item>
        ),
      },
    ];
    return filterWarehouseTrackingColumns(cols, trackingFlags);
  }, [
    batchOptionsByKey,
    batchOptionsLoadingKey,
    clearLineWarehouseDependents,
    ensureBatchOptions,
    quantityDecimals,
    stockByKey,
    stockLoading,
    syncLineMaterialTracking,
    syncLineStockKeyFromForm,
    t,
    trackingFlags,
  ]);

  const handleFinish = async (values: Record<string, unknown>) => {
    const items = normalizeFormListItems<Record<string, unknown>>(values.items);
    const validItems = items.filter(
      (it) => it.material_id && (Number(it.required_quantity) || 0) > 0,
    );
    if (!validItems.length) {
      const msg = t('app.kuaizhizao.warehouseOutbound.msg.needValidProductionPickingLine');
      messageApi.error(msg);
      throw new Error(msg);
    }

    await prefetchMaterialsForUnitSelect(
      validItems.map((it) => Number(it.material_id) || 0),
    );

    for (const it of validItems) {
      const materialLabel =
        String(it.material_name || it.material_code || it.material_id || '').trim() || '-';
      const lineWhId = Number(it.warehouse_id) || 0;
      if (!(lineWhId > 0)) {
        const msg = t('app.kuaizhizao.warehouseOutbound.pull.selectWarehouseForMaterial', {
          material: materialLabel,
        });
        messageApi.error(msg);
        throw new Error(msg);
      }
      const needLoc = await lineLocationSelectionRequired(
        lineWhId,
        it.location_id,
        it.location_code,
      );
      if (needLoc) {
        const msg = t('app.kuaizhizao.warehouseOutbound.msg.selectLocationForMaterial', {
          material: materialLabel,
        });
        messageApi.error(msg);
        throw new Error(msg);
      }
      const material = await fetchMaterialForUnitSelectCache(Number(it.material_id));
      const batchManaged =
        it.batch_managed != null
          ? !!it.batch_managed
          : !!(material as Material | null)?.batchManaged;
      const serialManaged =
        it.serial_managed != null
          ? !!it.serial_managed
          : !!(material as Material | null)?.serialManaged;
      const materialId = Number(it.material_id) || 0;
      const batchLine = productionPickingCreateBatchLineEnabled(trackingFlags, batchManaged);
      const batchStrict = isMaterialBatchEntryEnabled(trackingFlags, batchManaged);
      const batchKey =
        materialId > 0 && lineWhId > 0 ? batchOptionsCacheKey(materialId, lineWhId) : '';
      const batchOpts = batchKey ? batchOptionsByKey[batchKey] ?? [] : [];
      const batchRequired = batchStrict || batchOpts.length > 0;
      const qty = Number(it.required_quantity) || 0;
      const allocs = lineBatchAllocations(it, qty);
      if (batchLine && batchRequired) {
        if (!isValidOutboundBatchAllocations(allocs, batchOpts, qty)) {
          const msg = t('app.kuaizhizao.warehouseOutbound.confirm.batchAllocationRequired', {
            material: materialLabel,
            qty,
            batches: batchOpts.map((o) => o.value).join('、') || '—',
          });
          messageApi.error(msg);
          throw new Error(msg);
        }
      }
      if (isMaterialSerialEntryEnabled(trackingFlags, serialManaged)) {
        const serials = Array.isArray(it.serial_numbers)
          ? it.serial_numbers.filter((s: unknown) => String(s ?? '').trim())
          : [];
        if (qty > 0 && serials.length !== qty) {
          const msg = t('app.kuaizhizao.warehouseOutbound.entry.serialCountMismatch', {
            material: materialLabel,
            required: qty,
            actual: serials.length,
          });
          messageApi.error(msg);
          throw new Error(msg);
        }
        if (allocs.length > 1) {
          const msg = t('app.kuaizhizao.warehouseOutbound.confirm.batchSerialMultiNotSupported', {
            material: materialLabel,
          });
          messageApi.error(msg);
          throw new Error(msg);
        }
      }
      const dualErr = validateDualQuantityBeforeSave({
        material: material as Material | null,
        value: {
          quantity: Number(it.required_quantity),
          material_unit: String(it.material_unit ?? ''),
          aux_quantity: it.aux_quantity != null ? Number(it.aux_quantity) : undefined,
          aux_unit: it.aux_unit != null ? String(it.aux_unit) : undefined,
          unit_conversion_rate:
            it.unit_conversion_rate != null ? Number(it.unit_conversion_rate) : undefined,
        },
      });
      if (dualErr) {
        messageApi.error(dualErr);
        throw new Error(dualErr);
      }
    }

    const pickingTime =
      values.picking_time && typeof (values.picking_time as { format?: unknown }).format === 'function'
        ? toApiBusinessDocumentDateTime(values.picking_time as dayjs.Dayjs)
        : undefined;

    try {
      if (isEdit && editingId != null) {
        const missingLineId = validItems.some((it) => !(Number(it.id) > 0));
        if (missingLineId) {
          const msg = t('app.kuaizhizao.warehouseOutbound.msg.noEditableLines');
          messageApi.error(msg);
          throw new Error(msg);
        }
        await warehouseApi.productionPicking.update(String(editingId), {
          notes: String(values.notes ?? '').trim() || undefined,
          picker_id: values.picker_id != null ? Number(values.picker_id) : undefined,
          picker_name: String(values.picker_name ?? '').trim() || undefined,
          picking_time: pickingTime,
          pick_department_id:
            values.pick_department_id != null ? Number(values.pick_department_id) : undefined,
          pick_department_code: String(values.pick_department_code ?? '').trim() || undefined,
          pick_department_name: String(values.pick_department_name ?? '').trim() || undefined,
          items: validItems.map((it) => {
            const qty = Number(it.required_quantity) || 0;
            const allocs = lineBatchAllocations(it, qty);
            const payload: Record<string, unknown> = {
              id: Number(it.id),
              required_quantity: qty,
              warehouse_id: Number(it.warehouse_id),
              warehouse_name: String(it.warehouse_name ?? '').trim(),
              aux_quantity: it.aux_quantity != null ? Number(it.aux_quantity) : undefined,
              aux_unit: it.aux_unit != null ? String(it.aux_unit) : undefined,
              unit_conversion_rate:
                it.unit_conversion_rate != null ? Number(it.unit_conversion_rate) : undefined,
            };
            if (allocs.length) {
              payload.batch_allocations = allocs.map((a) => ({
                batch_number: a.batchNo,
                quantity: a.quantity,
              }));
              if (allocs.length === 1) payload.batch_number = allocs[0].batchNo;
            } else {
              payload.batch_number = String(it.batch_number ?? '').trim() || undefined;
            }
            return payload;
          }),
        });
        messageApi.success(t('common.updateSuccess'));
      } else {
        await warehouseApi.productionPicking.create({
          status: '待领料',
          picking_code: String(values.picking_code ?? '').trim() || undefined,
          picker_id: values.picker_id != null ? Number(values.picker_id) : undefined,
          picker_name: String(values.picker_name ?? '').trim() || undefined,
          picking_time: pickingTime,
          pick_department_id:
            values.pick_department_id != null ? Number(values.pick_department_id) : undefined,
          pick_department_code: String(values.pick_department_code ?? '').trim() || undefined,
          pick_department_name: String(values.pick_department_name ?? '').trim() || undefined,
          notes: String(values.notes ?? '').trim() || undefined,
          items: validItems.flatMap((it) => {
            const qty = Number(it.required_quantity) || 0;
            const allocs = lineBatchAllocations(it, qty);
            const base = {
              material_id: Number(it.material_id),
              material_code: String(it.material_code ?? ''),
              material_name: String(it.material_name ?? ''),
              material_spec: it.material_spec != null ? String(it.material_spec) : undefined,
              material_model: it.material_model != null ? String(it.material_model) : undefined,
              material_unit: String(it.material_unit ?? ''),
              aux_quantity: it.aux_quantity != null ? Number(it.aux_quantity) : undefined,
              aux_unit: it.aux_unit != null ? String(it.aux_unit) : undefined,
              unit_conversion_rate:
                it.unit_conversion_rate != null ? Number(it.unit_conversion_rate) : undefined,
              warehouse_id: Number(it.warehouse_id),
              warehouse_name: String(it.warehouse_name ?? '').trim(),
              location_id: it.location_id != null ? Number(it.location_id) : undefined,
              location_code: it.location_code != null ? String(it.location_code) : undefined,
              serial_numbers: Array.isArray(it.serial_numbers)
                ? it.serial_numbers.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
                : undefined,
            };
            if (allocs.length > 1) {
              return allocs.map((a) => ({
                ...base,
                required_quantity: a.quantity,
                batch_number: a.batchNo,
              }));
            }
            return [
              {
                ...base,
                required_quantity: qty,
                batch_number:
                  allocs[0]?.batchNo || String(it.batch_number ?? '').trim() || undefined,
              },
            ];
          }),
        });
        messageApi.success(t('app.kuaizhizao.warehouseOutbound.msg.productionPickingBlankCreated'));
      }
      onSuccess?.();
      onClose();
    } catch (error: unknown) {
      const err = error as { message?: string };
      messageApi.error(
        err?.message || (isEdit ? t('common.updateFailed') : t('common.createFailed')),
      );
      throw error;
    }
  };

  const pullDocumentScopeOptions = useMemo(
    () => [
      { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
      { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
    ],
    [t],
  );

  const pullOpenQtyTripleColumns = useMemo(
    () =>
      buildDefaultPullOpenLineQtyColumns(t, {
        includeRemaining: true,
        widths: { suggested: 100, pushed: 100, remaining: 100 },
      }),
    [t],
  );

  const workOrderPullColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.workOrderCode'),
        dataIndex: 'work_order_code',
        width: 168,
        ellipsis: true,
      },
      buildPullQueryMaterialIdentityColumn<PullWorkOrderCandidate>(t),
      ...pullOpenQtyTripleColumns,
      {
        title: t('app.kuaizhizao.warehouseOutbound.pull.convertStatus'),
        key: 'convert_status',
        width: 100,
        align: 'center' as const,
        render: (_: unknown, record: PullWorkOrderCandidate) =>
          renderPullCapabilityTag(
            Number(record.remaining_quantity ?? 0) > 0,
            t('app.kuaizhizao.warehouseOutbound.pull.canCreate'),
            t('app.kuaizhizao.purchaseRequisition.pull.cannotCreate'),
          ),
      },
    ],
    [pullOpenQtyTripleColumns, t],
  );

  const applyWorkOrderPullLinesToForm = useCallback(
    async (rows: PullWorkOrderCandidate[]) => {
      const selectable = rows.filter((row) => isPullOpenLineSelectable(row));
      if (!selectable.length) {
        messageApi.warning(t('app.kuaizhizao.warehouseOutbound.pull.wo.selectLinesFirst'));
        return;
      }
      const newLines = await Promise.all(
        selectable.map(async (row) => {
          const materialId = Number(row.material_id);
          const qty = Number(row.remaining_quantity ?? 0);
          const material = materialId > 0 ? await fetchMaterialForUnitSelectCache(materialId) : null;
          const unit =
            String(row.unit ?? '').trim() ||
            (material ? resolveMaterialScenarioUnit(material, 'production') : '个');
          const woId = Number(row.work_order_id);
          const woCode = String(row.work_order_code ?? '').trim();
          const specFromRow =
            row.material_spec != null ? String(row.material_spec).trim() : '';
          const modelFromRow =
            row.material_model != null ? String(row.material_model).trim() : '';
          const specFromMat =
            material?.specification != null ? String(material.specification).trim() : '';
          const modelFromMat = material?.model != null ? String(material.model).trim() : '';
          let auxQuantity =
            row.remaining_aux_quantity != null ? Number(row.remaining_aux_quantity) : undefined;
          let auxUnit =
            row.aux_unit != null && String(row.aux_unit).trim()
              ? String(row.aux_unit).trim()
              : undefined;
          let unitConversionRate =
            row.unit_conversion_rate != null ? Number(row.unit_conversion_rate) : undefined;
          if ((auxQuantity == null || !(auxQuantity > 0)) && material && qty > 0) {
            const dual = syncDualQuantitiesFixed({
              material,
              scenario: 'production',
              changed: 'primary',
              value: {
                quantity: qty,
                material_unit: unit,
                aux_unit: auxUnit ?? resolveAuxUnitForScenario(material, 'production'),
                unit_conversion_rate: unitConversionRate,
              },
            });
            if (dual.aux_quantity != null && Number(dual.aux_quantity) > 0) {
              auxQuantity = Number(dual.aux_quantity);
            }
            if (dual.aux_unit) auxUnit = dual.aux_unit;
            if (dual.unit_conversion_rate != null) {
              unitConversionRate = Number(dual.unit_conversion_rate);
            }
          }
          const line: Record<string, unknown> = {
            ...defaultLineItem,
            material_id: materialId,
            material_code: String(row.material_code ?? ''),
            material_name: String(row.material_name ?? ''),
            material_spec: specFromMat || undefined,
            material_model: modelFromMat || undefined,
            material_unit: unit,
            work_order_id: woId > 0 ? woId : undefined,
            work_order_code: woCode || undefined,
            wo_bom_required: Number(row.suggested_quantity ?? 0),
            wo_bom_picked: Number(row.pushed_quantity ?? 0),
            required_quantity: qty > 0 ? qty : 0,
            aux_quantity: auxQuantity,
            aux_unit: auxUnit,
            unit_conversion_rate: unitConversionRate,
            batch_managed: material
              ? isMaterialBatchEntryEnabled(trackingFlags, material.batchManaged)
              : false,
            serial_managed: material
              ? isMaterialSerialEntryEnabled(trackingFlags, material.serialManaged)
              : false,
          };
          const primaryWh = material ? resolvePrimaryDefaultWarehouse(material) : null;
          if (primaryWh) {
            line.warehouse_id = primaryWh.id;
            line.warehouse_name = primaryWh.name;
          }
          return line;
        }),
      );

      const current = normalizeFormListItems<Record<string, unknown>>(
        formRef.current?.getFieldValue('items'),
      );
      const merged = [
        ...current.filter((it) => Number(it.material_id) > 0),
        ...newLines.filter(
          (nl) =>
            !current.some(
              (c) =>
                Number(c.material_id) === Number(nl.material_id) &&
                Number(c.work_order_id) === Number(nl.work_order_id),
            ),
        ),
      ];

      const woIds = [
        ...new Set(
          merged
            .map((it) => Number(it.work_order_id))
            .filter((id) => Number.isFinite(id) && id > 0),
        ),
      ];
      const headerWo =
        woIds.length === 1
          ? {
              work_order_id: woIds[0],
              work_order_code: String(
                merged.find((it) => Number(it.work_order_id) === woIds[0])?.work_order_code ?? '',
              ).trim(),
            }
          : { work_order_id: undefined, work_order_code: undefined };

      formRef.current?.setFieldsValue({
        ...headerWo,
        items: merged.length ? merged : newLines,
      });
      syncLineStockKeyFromForm();
      await prefetchMaterialsForUnitSelect(
        (merged.length ? merged : newLines).map((it) => Number(it.material_id)),
      );
      messageApi.success(t('app.kuaizhizao.warehouseOutbound.msg.workOrderLinesLoaded'));
    },
    [messageApi, syncLineStockKeyFromForm, t, trackingFlags],
  );

  const pullFromWorkOrderQuery = useUniPullQuery<PullWorkOrderCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullDocumentScopeOptions,
    defaultScope: 'pullable',
    onOpen: () => {
      pullSourceWorkOrderIdRef.current = undefined;
      setPullSourceWorkOrderId(undefined);
      void loadPullSourceReferenceOptions({
        resource: PULL_SOURCE_REFERENCE.workOrder,
        hostResource: OUTBOUND_HOST_RESOURCE,
      })
        .then(setPullSourceWorkOrderOptions)
        .catch((error: unknown) => {
          messageApi.error(
            getApiErrorMessage(error, t('app.kuaizhizao.warehouseOutbound.pull.wo.loadSourceFailed')),
          );
          setPullSourceWorkOrderOptions([]);
        });
    },
    loadData: async (params) => {
      const { scope } = params;
      try {
        const listRes = await warehouseApi.productionPicking.listWorkOrderPullLines({
          ...toUniPullQueryHttpParams(params),
          work_order_id: pullSourceWorkOrderIdRef.current,
          pullable_only: isPullableScope(scope),
        });
        return { data: listRes?.data ?? [], total: listRes?.total ?? 0 };
      } catch (error: unknown) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.warehouseOutbound.pull.loadWorkOrdersFailed')),
        );
        return { data: [], total: 0 };
      }
    },
    isRowDisabled: (record) => !isPullOpenLineSelectable(record),
    onConfirm: async (_keys, selectedRows) => {
      try {
        await applyWorkOrderPullLinesToForm(selectedRows);
        pullFromWorkOrderQuery.closeModal();
      } catch (error: unknown) {
        messageApi.error(getApiErrorMessage(error, t('common.loadFailed')));
      }
    },
  });

  const handleOpenLoadWorkOrder = useCallback(() => {
    if (isEdit) return;
    pullFromWorkOrderQuery.openModal();
  }, [isEdit, pullFromWorkOrderQuery]);

  const modalTitle = useMemo(() => {
    if (!isEdit) return t('app.kuaizhizao.warehouseOutbound.createProductionPickingModal');
    const typeLabel = t('app.kuaizhizao.warehouseOutbound.entry.productionPicking');
    return `${t('common.edit')} ${typeLabel}${editDocumentCode ? ` - ${editDocumentCode}` : ''}`;
  }, [editDocumentCode, isEdit, t]);

  return (
    <FormModalTemplate
      open={open}
      title={modalTitle}
      width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
      grid={false}
      formRef={formRef}
      onClose={onClose}
      onFinish={handleFinish}
      isEdit={isEdit}
      loading={formLoading}
      initialValues={{
        picking_time: dayjs(),
        picker_id: defaultPerson.id,
        picker_name: defaultPerson.name,
        items: [{ ...defaultLineItem }],
      }}
    >
      <DocumentDetailTableStyles />
      <Row gutter={16}>
        <Col span={12}>
          <CodeField
            pageCode="kuaizhizao-warehouse-inbound"
            name="picking_code"
            label={t('app.kuaizhizao.warehouseOutbound.field.documentNumber')}
            autoGenerateOnCreate={!isEdit}
            showGenerateButton={false}
            context={{}}
          />
        </Col>
        <Col span={12}>
          <ProFormDatePicker
            name="picking_time"
            label={t('app.kuaizhizao.warehouseOutbound.field.documentDate')}
            rules={[
              {
                required: true,
                message: t('app.kuaizhizao.warehouseOutbound.field.documentDateRequired'),
              },
            ]}
            fieldProps={{ style: { width: '100%' } }}
          />
        </Col>
        <Col span={12}>
          <UserPickField
            name="picker_id"
            nameField="picker_name"
            label={t('app.kuaizhizao.warehouseOutbound.field.requester')}
            placeholder={t('app.kuaizhizao.warehouseOutbound.field.requesterPlaceholder')}
            userList={users}
            loading={usersLoading}
            departmentOptions={departmentOptions}
            required
          />
        </Col>
        <Col span={12}>
          <ProFormItem
            name="pick_department_id"
            label={t('app.kuaizhizao.warehouseOutbound.field.pickDepartment')}
            rules={[
              {
                required: true,
                message: t('app.kuaizhizao.warehouseOutbound.msg.pickDepartmentRequired'),
              },
            ]}
          >
            <UniDropdown
              placeholder={t('app.kuaizhizao.warehouseOutbound.field.pickDepartmentPlaceholder')}
              showSearch
              allowClear
              loading={departmentsLoading}
              style={{ width: '100%' }}
              options={departmentOptions}
              onChange={(val, opt) => {
                const row = departmentOptions.find((d) => d.value === val);
                const label =
                  typeof opt === 'object' && opt && 'label' in opt && typeof opt.label === 'string'
                    ? opt.label
                    : row?.label;
                formRef.current?.setFieldsValue({
                  pick_department_code: row?.code ?? undefined,
                  pick_department_name: label?.includes(' - ')
                    ? label.split(' - ').slice(1).join(' - ').trim()
                    : label,
                });
              }}
            />
          </ProFormItem>
          <AntForm.Item name="pick_department_code" hidden>
            <Input />
          </AntForm.Item>
          <AntForm.Item name="pick_department_name" hidden>
            <Input />
          </AntForm.Item>
        </Col>
      </Row>

      <UniTableDetail
        name="items"
        title={t('app.kuaizhizao.warehouseOutbound.createLinesTitle')}
        required
        requiredMessage={t('app.kuaizhizao.warehouseOutbound.msg.needValidProductionPickingLine')}
        headerExtra={
          isEdit ? undefined : (
            <Space size={8}>
              <Button
                type="default"
                icon={<PlusOutlined />}
                onClick={() => {
                  const next = [
                    ...(formRef.current?.getFieldValue('items') ?? []),
                    { ...defaultLineItem },
                  ];
                  formRef.current?.setFieldsValue({ items: next });
                  syncLineStockKeyFromForm();
                }}
              >
                {t('common.addDetail')}
              </Button>
            </Space>
          )
        }
        columns={formItemColumns}
        disabledAdd
        disabledRemove={isEdit}
        initialValue={{ ...defaultLineItem }}
        tableProps={DOCUMENT_DETAIL_TABLE_PROPS}
      />

      <Row gutter={16}>
        <Col span={24}>
          <ProFormTextArea name="notes" label={t('common.remark')} fieldProps={{ rows: 3 }} />
        </Col>
      </Row>
    </FormModalTemplate>
  );
};

export default ProductionPickingCreateModal;
