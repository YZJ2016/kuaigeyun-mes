/**
 * 销售出库空白建单 / 编辑（与新建同一 FormModal，确认出库前可改）。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  App,
  Button,
  Col,
  Form as AntForm,
  Input,
  InputNumber,
  Row,
  Space,
  Tooltip,
} from 'antd';
import {
  ProFormDatePicker,
  ProFormItem,
  ProFormText,
  ProFormTextArea,
  type ProFormInstance,
} from '@ant-design/pro-components';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import {
  normalizeDocumentFormPriceType,
  recalcDocumentStoredLineAmount,
} from '../../../utils/documentLineAmounts';
import { formatCurrencyAmount } from '../../../../../utils/format';
import { resolveSalesWarehouseLineAmounts } from '../../sales-management/shared/salesDocumentAmounts';
import { DEFAULT_SALES_PRICE_TYPE, salesFormPriceType } from '../../sales-management/shared/salesPriceType';
import PriceTypeSwitch, { type PriceTypeValue } from '../../../../../components/price-type-switch/PriceTypeSwitch';
import { deferConvertLineItemsByPriceType } from '../../../../../utils/priceTypeSwitch';
import { useQuery } from '@tanstack/react-query';
import { FormModalTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import { UniTableDetail } from '../../../../../components/uni-table-detail';
import {
  mapAttachmentsToUploadList,
  normalizeDocumentAttachments,
} from '../../../utils/documentAttachments';
import { isOutboundEditable, outboundDocumentCode } from './outboundHubTypes';
import type { OutboundHubOrder } from './outboundHubTypes';
import {
  buildDocumentLineAttachmentsFormColumn,
  DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY,
} from '../../../components/documentLineAttachmentsColumns';
import {
  DOCUMENT_DETAIL_COL_WIDTH,
  DOCUMENT_DETAIL_CONTROL_SIZE,
  DOCUMENT_DETAIL_NUM_COL,
  DOCUMENT_DETAIL_TABLE_PROPS,
  DOCUMENT_DETAIL_TEXT_COL,
  DocumentDetailTableStyles,
  TaxRateBatchColumnTitle,
  TaxRateDetailCell,
} from '../../../components/document-detail-table/documentDetailTable';
import { UniMaterialSelect } from '../../../../../components/uni-material-select';
import {
  UniWhDropdown,
  UniWhLocationDropdown,
  useWarehouseHasLocations,
  lineLocationSelectionRequired,
} from '../../../../../components/uni-wh-dropdown';
import { CustomerSelectDropdown } from '../../../../master-data/components/CustomerSelectDropdown';
import { warehouseApi } from '../../../services/production';
import { useNumericPrecisionPlaces } from '../../../../../hooks/useNumericPrecision';
import { toApiBusinessDocumentDateTime } from '../../../../../utils/formDate';
import {
  buildDocumentDetailPartnerMaterialFormColumns,
  buildDocumentDetailSpecModelFormColumns,
  withMaterialLineFillMapping,
} from '../../sales-management/shared/materialLineFormDetail';
import { resolveMaterialScenarioUnit } from '../../../../../utils/materialScenarioUnit';
import { buildDocumentLineDualQuantityPairColumns } from '../../../../../components/quantity-with-unit';
import { validateDualQuantityBeforeSave } from '../../../../../utils/materialDualQuantity';
import {
  fetchMaterialForUnitSelectCache,
  prefetchMaterialsForUnitSelect,
} from '../../../../../components/material-unit-select';
import type { Material } from '../../../../master-data/types/material';
import {
  applySalesDocumentLineMaterialPricing,
  repriceUnlockedSalesDocumentLineIfNeeded,
} from '../../../../master-data/utils/resolve-partner-material-price';
import { normalizeFormListItems } from '../../../../../utils/formListItems';
import { getBusinessConfig } from '../../../../../services/businessConfig';
import { applyCustomerFormFields } from '../../sales-management/shared/applyCustomerFormFields';
import {
  buildRevenueLedgerRecognitionOptions,
  orgFinanceRevenueDefault,
} from '../../../../../utils/documentLedgerRecognition';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import type { User } from '../../../../../services/user';
import { searchUserDisplay } from '../../../../../services/user';
import {
  displayItemsToUsers,
  normalizeUserDisplayName,
} from '../../../../../utils/userDisplay';
import { getPopupContainerInModal } from '../../../../../utils/modalEventIsolation';
import {
  filterWarehouseTrackingColumns,
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  isOutboundConfirmBatchLineEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import {
  loadBatchOptionsByMaterialId,
  loadInStockSerialOptions,
  resolveOutboundConfirmBatchValue,
  type InventoryPickOption,
} from './outboundConfirmInventoryOptions';
import OutboundBatchAllocationField from './OutboundBatchAllocationField';
import OutboundSerialPickerField from './OutboundSerialPickerField';
import {
  allocateBatchQuantitiesFifo,
  coerceBatchAllocationsDraft,
  isValidOutboundBatchAllocations,
  type OutboundBatchAllocation,
} from './outboundBatchAllocation';
import SplitByWarehouseModal, {
  type SplitByWarehouseAllocation,
} from './SplitByWarehouseModal';

const OUTBOUND_HOST_RESOURCE = 'kuaizhizao:outbound';

const defaultLineItem = {
  id: undefined as number | undefined,
  delivery_quantity: 1,
  unit_price: 0,
  tax_rate: 0,
  partner_material_code: '',
  partner_material_name: '',
  warehouse_id: undefined as number | undefined,
  warehouse_name: undefined as string | undefined,
  location_id: undefined as number | undefined,
  location_code: undefined as string | undefined,
  batch_number: undefined as string | undefined,
  batch_allocations: [] as OutboundBatchAllocation[],
  batch_managed: false,
  serial_managed: false,
  material_uuid: undefined as string | undefined,
  serial_numbers: undefined as string[] | undefined,
  aux_quantity: undefined,
  aux_unit: undefined,
  unit_conversion_rate: undefined,
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

function salesDeliveryCreateBatchLineEnabled(
  trackingFlags: ReturnType<typeof useWarehouseTrackingFlags>,
  batchManaged?: boolean | null,
): boolean {
  return isOutboundConfirmBatchLineEnabled('sales_delivery', trackingFlags, batchManaged);
}

/** 物料默认仓库列表按 priority 取首个有效仓 */
function resolvePrimaryDefaultWarehouse(
  material: Material | null | undefined,
): { id: number; name: string } | null {
  const defWhs = material?.defaults?.defaultWarehouses;
  if (!defWhs?.length) return null;
  const sorted = [...defWhs].sort((a, b) => (a.priority ?? 999) - (b.priority ?? 999));
  const first = sorted[0];
  const id = Number(first?.warehouseId ?? 0);
  if (!(id > 0)) return null;
  return { id, name: String(first?.warehouseName ?? '').trim() };
}

export type SalesDeliveryCreateModalProps = {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  /** 有值则为编辑，表单布局与新建一致 */
  editingId?: number | null;
};

/** 库位：订阅物料+仓库，展示库位库存并有货优先；出入库库位必填 */
function SalesDeliveryCreateLocationCell({
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
            showStock={materialId > 0 && warehouseId > 0}
            sortByStock={materialId > 0 && warehouseId > 0}
            allowClear={false}
            size={DOCUMENT_DETAIL_CONTROL_SIZE}
            getPopupContainer={getPopupContainerInModal}
            disabled={!(warehouseId > 0) || hasLocations === undefined}
            onChange={(_value, loc) => {
              formRef.current?.setFieldValue(['items', index, 'location_code'], loc?.code ?? '');
            }}
          />
        </AntForm.Item>
      )}
    </>
  );
}

/** 用 useWatch 订阅物料，确保选料后仓下拉能带 materialId 拉库存 */
function SalesDeliveryCreateWarehouseCell({
  index,
  trackingFlags,
  clearLineWarehouseDependents,
  ensureBatchOptions,
  formRef,
  t,
}: {
  index: number;
  trackingFlags: ReturnType<typeof useWarehouseTrackingFlags>;
  clearLineWarehouseDependents: (index: number) => void;
  ensureBatchOptions: (materialId: number, warehouseId: number, lineIndex: number) => Promise<void>;
  formRef: React.MutableRefObject<ProFormInstance | undefined>;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  const materialId = Number(AntForm.useWatch(['items', index, 'material_id']) || 0);
  return (
    <div>
      <AntForm.Item name={[index, 'warehouse_name']} hidden>
        <Input />
      </AntForm.Item>
      <AntForm.Item name={[index, 'batch_managed']} hidden>
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
          onChange={(_value, wh) => {
            clearLineWarehouseDependents(index);
            const whId = Number(wh?.id ?? _value ?? 0);
            formRef.current?.setFieldValue(['items', index, 'warehouse_name'], wh?.name ?? '');
            if (whId > 0) {
              const mid = Number(
                formRef.current?.getFieldValue(['items', index, 'material_id']) ?? 0,
              );
              const batchManaged = !!formRef.current?.getFieldValue([
                'items',
                index,
                'batch_managed',
              ]);
              if (mid > 0 && salesDeliveryCreateBatchLineEnabled(trackingFlags, batchManaged)) {
                void ensureBatchOptions(mid, whId, index);
              }
            }
          }}
        />
      </AntForm.Item>
    </div>
  );
}

function UserPickField({
  name,
  nameField,
  label,
  placeholder,
  required,
  userList,
  loading,
}: {
  name: string;
  nameField: string;
  label: string;
  placeholder: string;
  required?: boolean;
  userList: User[];
  loading: boolean;
}) {
  const { t } = useTranslation();
  const form = AntForm.useFormInstance();
  const pickedId = AntForm.useWatch(name, form);
  const pickedName = AntForm.useWatch(nameField, form);

  const options = useMemo(() => {
    const base = userList.map((u) => ({
      value: Number(u.id),
      label: normalizeUserDisplayName(u.full_name || u.username),
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
        rules={required ? [{ required: true, message: placeholder }] : undefined}
        normalize={(v) =>
          v != null && v !== '' && Number.isFinite(Number(v)) ? Number(v) : undefined
        }
      >
        <UniDropdown
          placeholder={placeholder}
          showSearch
          allowClear={!required}
          loading={loading}
          style={{ width: '100%' }}
          options={options}
          onChange={(_val, opt: { label?: React.ReactNode } | undefined) => {
            form.setFieldsValue({
              [nameField]: typeof opt?.label === 'string' ? opt.label : undefined,
            });
          }}
        />
      </ProFormItem>
      <AntForm.Item name={nameField} hidden>
        <Input />
      </AntForm.Item>
    </>
  );
}

export const SalesDeliveryCreateModal: React.FC<SalesDeliveryCreateModalProps> = ({
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
  const priceDecimals = useNumericPrecisionPlaces('price');
  const trackingFlags = useWarehouseTrackingFlags();
  const isEdit = editingId != null && Number(editingId) > 0;
  const [formLoading, setFormLoading] = useState(false);
  const [editDocumentCode, setEditDocumentCode] = useState('');
  const [users, setUsers] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [batchOptionsByKey, setBatchOptionsByKey] = useState<Record<string, InventoryPickOption[]>>(
    {},
  );
  const [batchOptionsLoadingKey, setBatchOptionsLoadingKey] = useState<string | null>(null);
  const [serialOptionsByUuid, setSerialOptionsByUuid] = useState<
    Record<string, InventoryPickOption[]>
  >({});
  const [serialOptionsLoadingUuid, setSerialOptionsLoadingUuid] = useState<string | null>(null);
  const serialOptionsLoadingRef = useRef<Record<string, boolean>>({});
  const [splitLineIndex, setSplitLineIndex] = useState<number | null>(null);
  /** 编辑灌数时的明细行 id（提交时若 Form 未带回则按行序回填） */
  const editLineIdsRef = useRef<number[]>([]);

  const applySplitByWarehouse = useCallback(
    (lineIndex: number, allocations: SplitByWarehouseAllocation[]) => {
      const items = [...(formRef.current?.getFieldValue('items') ?? [])];
      const source = items[lineIndex] as Record<string, unknown> | undefined;
      if (!source) return;
      const newRows = allocations.map((a) => ({
        ...source,
        warehouse_id: a.warehouseId,
        warehouse_name: a.warehouseName,
        delivery_quantity: a.quantity,
        location_id: undefined,
        location_code: undefined,
        batch_number: undefined,
        batch_allocations: [],
        aux_quantity: undefined,
      }));
      items.splice(lineIndex, 1, ...newRows);
      formRef.current?.setFieldsValue({ items });
      messageApi.success(t('app.kuaizhizao.warehouseOutbound.splitByWarehouse.done'));
    },
    [messageApi, t],
  );
  const { data: businessConfig } = useQuery({
    queryKey: ['businessConfigFinanceRecognition'],
    queryFn: getBusinessConfig,
    staleTime: 60_000,
  });
  const revenueLedgerRecognitionOptions = useMemo(
    () => buildRevenueLedgerRecognitionOptions(t),
    [t],
  );
  const orgRevenueRecognitionDefault = useMemo(
    () => orgFinanceRevenueDefault(businessConfig),
    [businessConfig],
  );

  const currentUserId = currentUser?.id;
  const currentUserName = String(currentUser?.full_name || currentUser?.username || '').trim();
  const defaultPerson = useMemo(() => {
    const id =
      currentUserId != null && Number(currentUserId) > 0 ? Number(currentUserId) : undefined;
    return { id, name: currentUserName };
  }, [currentUserId, currentUserName]);

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
        formRef.current.getFieldValue(['items', lineIndex, 'delivery_quantity']) || 0,
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
        const next = allocateBatchQuantitiesFifo(
          qty,
          currentAllocs.map((a) => a.batchNo),
          opts,
          currentAllocs,
        );
        syncLineBatchFields(
          (name, value) => formRef.current?.setFieldValue(name, value),
          lineIndex,
          next,
        );
        return;
      }
      const picked = resolveOutboundConfirmBatchValue(undefined, opts);
      if (!picked) return;
      if (opts.length !== 1) {
        // 多批可选时仅在有明确 FIFO 建议批号时自动带出
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

  const clearLineWarehouseDependents = useCallback((index: number) => {
    formRef.current?.setFieldValue(['items', index, 'location_id'], undefined);
    formRef.current?.setFieldValue(['items', index, 'location_code'], '');
    formRef.current?.setFieldValue(['items', index, 'batch_number'], undefined);
    formRef.current?.setFieldValue(['items', index, 'batch_allocations'], []);
    formRef.current?.setFieldValue(['items', index, 'serial_numbers'], undefined);
  }, []);

  const ensureSerialOptions = useCallback(async (materialUuid: string, selected?: string[]) => {
    const uuid = String(materialUuid || '').trim();
    if (!uuid || serialOptionsLoadingRef.current[uuid]) return;
    if (serialOptionsByUuid[uuid]?.length) return;
    serialOptionsLoadingRef.current[uuid] = true;
    setSerialOptionsLoadingUuid(uuid);
    try {
      const opts = await loadInStockSerialOptions(uuid);
      const merged = [...opts];
      for (const sn of selected ?? []) {
        const s = String(sn ?? '').trim();
        if (s && !merged.some((o) => o.value === s)) {
          merged.push({ value: s, label: s });
        }
      }
      setSerialOptionsByUuid((prev) => ({ ...prev, [uuid]: merged }));
    } catch {
      const fallback = (selected ?? [])
        .map((sn) => String(sn ?? '').trim())
        .filter(Boolean)
        .map((sn) => ({ value: sn, label: sn }));
      setSerialOptionsByUuid((prev) => ({ ...prev, [uuid]: fallback }));
    } finally {
      serialOptionsLoadingRef.current[uuid] = false;
      setSerialOptionsLoadingUuid((cur) => (cur === uuid ? null : cur));
    }
  }, [serialOptionsByUuid]);

  const resetForm = useCallback(() => {
    formRef.current?.resetFields();
    formRef.current?.setFieldsValue({
      items: [{ ...defaultLineItem }],
      delivery_time: dayjs(),
      currency_code: 'CNY',
      exchange_rate: 1,
      price_type: DEFAULT_SALES_PRICE_TYPE,
      deliverer_id: defaultPerson.id,
      deliverer_name: defaultPerson.name,
      revenue_recognition: orgRevenueRecognitionDefault,
    });
    setBatchOptionsByKey({});
    setBatchOptionsLoadingKey(null);
    setSerialOptionsByUuid({});
    setSerialOptionsLoadingUuid(null);
    serialOptionsLoadingRef.current = {};
    setSplitLineIndex(null);
    setEditDocumentCode('');
    editLineIdsRef.current = [];
  }, [defaultPerson, orgRevenueRecognitionDefault]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      setUsersLoading(true);
      try {
        const res = await searchUserDisplay({ page_size: 100, is_active: true });
        if (!cancelled) setUsers(displayItemsToUsers(res.items || []));
      } catch {
        if (!cancelled) setUsers([]);
      } finally {
        if (!cancelled) setUsersLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  // 新建：仅在出库人仍空时补登录人，避免 currentUser 抖动把已选人冲掉
  useEffect(() => {
    if (!open || isEdit) return;
    const rid = formRef.current?.getFieldValue('deliverer_id');
    if (rid != null && rid !== '') return;
    if (defaultPerson.id == null && !defaultPerson.name) return;
    formRef.current?.setFieldsValue({
      deliverer_id: defaultPerson.id,
      deliverer_name: defaultPerson.name,
    });
  }, [open, isEdit, defaultPerson]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    const hydrateEdit = async () => {
      if (!isEdit || editingId == null) {
        resetForm();
        return;
      }
      setFormLoading(true);
      try {
        const detail = (await warehouseApi.salesDelivery.get(String(editingId))) as Record<
          string,
          unknown
        >;
        if (cancelled) return;
        const hubRow = { ...detail, outbound_type: 'sales_delivery' as const };
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
          const lineIdRaw = line.id ?? line.item_id ?? line.delivery_item_id;
          const lineId = Number(lineIdRaw);
          return {
            ...defaultLineItem,
            id: lineId > 0 ? lineId : undefined,
            sales_order_item_id:
              line.sales_order_item_id != null && Number(line.sales_order_item_id) > 0
                ? Number(line.sales_order_item_id)
                : null,
            material_id: Number(line.material_id) || undefined,
            material_code: String(line.material_code ?? ''),
            material_name: String(line.material_name ?? ''),
            material_spec: line.material_spec != null ? String(line.material_spec) : undefined,
            partner_material_code:
              line.partner_material_code != null ? String(line.partner_material_code) : '',
            partner_material_name:
              line.partner_material_name != null ? String(line.partner_material_name) : '',
            material_unit: String(line.material_unit ?? ''),
            delivery_quantity: Number(line.delivery_quantity) || 1,
            unit_price: Number(line.unit_price) || 0,
            tax_rate: Number(line.tax_rate) || 0,
            warehouse_id: Number(line.warehouse_id) > 0 ? Number(line.warehouse_id) : undefined,
            warehouse_name: String(line.warehouse_name ?? ''),
            location_id: Number(line.location_id) > 0 ? Number(line.location_id) : undefined,
            location_code: line.location_code != null ? String(line.location_code) : undefined,
            batch_number: line.batch_number != null ? String(line.batch_number) : undefined,
            batch_allocations:
              coerceBatchAllocationsDraft(
                line.batch_number,
                Number(line.delivery_quantity) || 0,
              ) ?? [],
            batch_managed: !!line.batch_managed,
            serial_managed: !!line.serial_managed,
            serial_numbers: serials,
            aux_quantity: line.aux_quantity != null ? Number(line.aux_quantity) : undefined,
            aux_unit: line.aux_unit != null ? String(line.aux_unit) : undefined,
            unit_conversion_rate:
              line.unit_conversion_rate != null ? Number(line.unit_conversion_rate) : undefined,
            attachments: mapAttachmentsToUploadList(
              line.attachments as Parameters<typeof mapAttachmentsToUploadList>[0],
            ),
          };
        });
        const deliveryTimeRaw = detail.delivery_time ?? detail.delivery_date;
        const detailDelivererId =
          Number(detail.deliverer_id) > 0 ? Number(detail.deliverer_id) : undefined;
        const detailDelivererName = String(detail.deliverer_name ?? '').trim();
        formRef.current?.setFieldsValue({
          customer_id: Number(detail.customer_id) > 0 ? Number(detail.customer_id) : undefined,
          customer_name: String(detail.customer_name ?? ''),
          customer_contact: detail.customer_contact != null ? String(detail.customer_contact) : undefined,
          customer_phone: detail.customer_phone != null ? String(detail.customer_phone) : undefined,
          shipping_address:
            detail.shipping_address != null ? String(detail.shipping_address) : undefined,
          revenue_recognition:
            detail.revenue_recognition ?? orgRevenueRecognitionDefault,
          deliverer_id: detailDelivererId ?? defaultPerson.id,
          deliverer_name: detailDelivererName || defaultPerson.name,
          delivery_time: deliveryTimeRaw ? dayjs(String(deliveryTimeRaw)) : dayjs(),
          price_type: String(detail.price_type ?? DEFAULT_SALES_PRICE_TYPE),
          currency_code: String(detail.currency_code ?? 'CNY').trim() || 'CNY',
          exchange_rate: Number(detail.exchange_rate) > 0 ? Number(detail.exchange_rate) : 1,
          notes: String(detail.notes ?? ''),
          items: items.length ? items : [{ ...defaultLineItem }],
        });
        editLineIdsRef.current = items.map((row) => Number(row.id) || 0);
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
              const uuid = String(material.uuid ?? '').trim();
              if (uuid) {
                formRef.current?.setFieldValue(['items', index, 'material_uuid'], uuid);
              }
              if (
                isMaterialSerialEntryEnabled(trackingFlags, !!material.serialManaged) &&
                uuid
              ) {
                await ensureSerialOptions(
                  uuid,
                  Array.isArray(row.serial_numbers) ? row.serial_numbers : undefined,
                );
              }
            }
            if (
              whId > 0 &&
              salesDeliveryCreateBatchLineEnabled(
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
    // 仅开窗 / 切换编辑单时灌数；勿把 defaultPerson/resetForm 放进依赖，否则会冲掉已选出库人
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional open-bound hydrate
  }, [open, isEdit, editingId]);

  const buildFormItemColumns = useCallback((showTaxColumns: boolean) => {
    const cols = [
      {
        title: '',
        dataIndex: 'id',
        width: 0,
        className: 'uni-detail-line-id-anchor',
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item name={[index, 'id']} hidden preserve>
            <InputNumber controls={false} style={{ display: 'none' }} />
          </AntForm.Item>
        ),
      },
      {
        title: t('app.kuaizhizao.shipmentNotice.import.materialName'),
        dataIndex: 'material_id',
        width: DOCUMENT_DETAIL_COL_WIDTH.material,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <div className="uni-detail-material-cell">
            {/* 注册明细快照字段，避免 fillMapping 写入后 onFinish 丢失导致列表「明细」空白 */}
            <AntForm.Item name={[index, 'material_code']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'material_name']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'material_uuid']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'serial_managed']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'serial_numbers']} hidden>
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
                if (!material) {
                  formRef.current?.setFieldValue(['items', index, 'warehouse_id'], undefined);
                  formRef.current?.setFieldValue(['items', index, 'warehouse_name'], '');
                  formRef.current?.setFieldValue(['items', index, 'batch_managed'], false);
                  formRef.current?.setFieldValue(['items', index, 'serial_managed'], false);
                  formRef.current?.setFieldValue(['items', index, 'material_uuid'], undefined);
                  return;
                }
                const mat = material as Material;
                formRef.current?.setFieldValue(
                  ['items', index, 'material_unit'],
                  resolveMaterialScenarioUnit(mat, 'sales'),
                );
                formRef.current?.setFieldValue(
                  ['items', index, 'batch_managed'],
                  !!mat.batchManaged,
                );
                formRef.current?.setFieldValue(
                  ['items', index, 'serial_managed'],
                  !!mat.serialManaged,
                );
                formRef.current?.setFieldValue(
                  ['items', index, 'material_uuid'],
                  String(mat.uuid ?? '').trim() || undefined,
                );
                formRef.current?.setFieldValue(['items', index, 'serial_numbers'], undefined);
                const primaryWh = resolvePrimaryDefaultWarehouse(mat);
                if (primaryWh) {
                  formRef.current?.setFieldValue(['items', index, 'warehouse_id'], primaryWh.id);
                  formRef.current?.setFieldValue(['items', index, 'warehouse_name'], primaryWh.name);
                  if (salesDeliveryCreateBatchLineEnabled(trackingFlags, !!mat.batchManaged)) {
                    void ensureBatchOptions(Number(mat.id), primaryWh.id, index);
                  }
                }
                const uuid = String(mat.uuid ?? '').trim();
                if (isMaterialSerialEntryEnabled(trackingFlags, !!mat.serialManaged) && uuid) {
                  void ensureSerialOptions(uuid);
                }
                void applySalesDocumentLineMaterialPricing(formRef.current, index, mat, {
                  asOfField: 'delivery_time',
                });
              }}
            />
          </div>
        ),
      },
      ...buildDocumentDetailSpecModelFormColumns(t),
      ...buildDocumentDetailPartnerMaterialFormColumns(t, 'customer'),
      ...buildDocumentLineDualQuantityPairColumns({
        t,
        getForm: () => formRef.current,
        quantityField: 'delivery_quantity',
        unitField: 'material_unit',
        scenario: 'sale',
        quantityPrecision: quantityDecimals,
        columnSpread: DOCUMENT_DETAIL_NUM_COL,
        inlineUnitWithQuantity: true,
        onAfterQuantityChange: (index) => {
          void repriceUnlockedSalesDocumentLineIfNeeded(formRef.current, index, {
            asOfField: 'delivery_time',
          });
          const qty = Number(
            formRef.current?.getFieldValue(['items', index, 'delivery_quantity']) || 0,
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
        title: t('app.kuaizhizao.warehouseOutbound.col.warehouseName'),
        dataIndex: 'warehouse_id',
        width: 220,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <SalesDeliveryCreateWarehouseCell
            index={index}
            trackingFlags={trackingFlags}
            clearLineWarehouseDependents={clearLineWarehouseDependents}
            ensureBatchOptions={ensureBatchOptions}
            formRef={formRef}
            t={t}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.location'),
        dataIndex: 'location_id',
        width: 180,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <SalesDeliveryCreateLocationCell index={index} formRef={formRef} t={t} />
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
              prev?.items?.[index]?.delivery_quantity !==
                curr?.items?.[index]?.delivery_quantity ||
              prev?.items?.[index]?.batch_allocations !==
                curr?.items?.[index]?.batch_allocations ||
              prev?.items?.[index]?.batch_number !== curr?.items?.[index]?.batch_number
            }
          >
            {({ getFieldValue }) => {
              const materialId = Number(getFieldValue(['items', index, 'material_id']) || 0);
              const whId = Number(getFieldValue(['items', index, 'warehouse_id']) || 0);
              const batchManaged = !!getFieldValue(['items', index, 'batch_managed']);
              if (!salesDeliveryCreateBatchLineEnabled(trackingFlags, batchManaged)) {
                return <span>—</span>;
              }
              const key =
                materialId > 0 && whId > 0 ? batchOptionsCacheKey(materialId, whId) : '';
              const opts = key ? batchOptionsByKey[key] ?? [] : [];
              const loading = !!key && batchOptionsLoadingKey === key;
              const qty = Number(getFieldValue(['items', index, 'delivery_quantity']) || 0);
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
              if (!isMaterialSerialEntryEnabled(trackingFlags, row?.serial_managed)) {
                return <span>—</span>;
              }
              const qty = Number(row?.delivery_quantity ?? 0);
              const sn = getFieldValue(['items', index, 'serial_numbers']);
              const uuid = String(row?.material_uuid ?? '').trim();
              const serials = Array.isArray(sn)
                ? sn.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
                : [];
              return (
                <OutboundSerialPickerField
                  value={serials}
                  onChange={(next) =>
                    formRef.current?.setFieldValue(['items', index, 'serial_numbers'], next)
                  }
                  options={uuid ? serialOptionsByUuid[uuid] ?? [] : []}
                  maxCount={qty > 0 ? Math.round(qty) : undefined}
                  loading={!!uuid && serialOptionsLoadingUuid === uuid}
                  onOpenPicker={() => {
                    if (uuid) void ensureSerialOptions(uuid, serials);
                  }}
                  materialLabel={String(row?.material_code || row?.material_name || '')}
                />
              );
            }}
          </AntForm.Item>
        ),
      },
      ...(isEdit
        ? []
        : [
            {
              title: t('app.kuaizhizao.warehouseOutbound.splitByWarehouse.actionCol'),
              width: 96,
              ...DOCUMENT_DETAIL_TEXT_COL,
              render: (_: unknown, __: unknown, index: number) => (
                <AntForm.Item
                  noStyle
                  shouldUpdate={(prev, curr) =>
                    prev?.items?.[index]?.material_id !== curr?.items?.[index]?.material_id ||
                    prev?.items?.[index]?.delivery_quantity !==
                      curr?.items?.[index]?.delivery_quantity
                  }
                >
                  {({ getFieldValue }) => {
                    const materialId = Number(getFieldValue(['items', index, 'material_id']) || 0);
                    const qty = Number(getFieldValue(['items', index, 'delivery_quantity']) || 0);
                    const canSplit = materialId > 0 && qty > 0;
                    const btn = (
                      <Button
                        type="link"
                        size="small"
                        disabled={!canSplit}
                        style={{ padding: 0 }}
                        onClick={() => setSplitLineIndex(index)}
                      >
                        {t('app.kuaizhizao.warehouseOutbound.splitByWarehouse.action')}
                      </Button>
                    );
                    if (canSplit) return btn;
                    return (
                      <Tooltip
                        title={t(
                          'app.kuaizhizao.warehouseOutbound.splitByWarehouse.disabledHint',
                        )}
                      >
                        <span>{btn}</span>
                      </Tooltip>
                    );
                  }}
                </AntForm.Item>
              ),
            },
          ]),
      {
        title: showTaxColumns
          ? t('app.kuaizhizao.purchaseOrder.col.taxUnitPrice')
          : t('app.kuaizhizao.purchaseOrder.col.unitPrice'),
        dataIndex: 'unit_price',
        width: DOCUMENT_DETAIL_COL_WIDTH.unitPrice,
        ...DOCUMENT_DETAIL_NUM_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item name={[index, 'unit_price']} noStyle>
            <InputNumber
              size={DOCUMENT_DETAIL_CONTROL_SIZE}
              style={{ width: '100%' }}
              min={0}
              prefix="¥"
            />
          </AntForm.Item>
        ),
      },
      ...(showTaxColumns
        ? [
            {
              title: (
                <TaxRateBatchColumnTitle
                  onBatch={(num) => {
                    const items = normalizeFormListItems<Record<string, unknown>>(
                      formRef.current?.getFieldValue('items'),
                    );
                    if (items.length === 0) return;
                    formRef.current?.setFieldsValue({
                      items: items.map((it) => ({ ...it, tax_rate: num })),
                    });
                  }}
                />
              ),
              dataIndex: 'tax_rate',
              width: DOCUMENT_DETAIL_COL_WIDTH.taxRate,
              ...DOCUMENT_DETAIL_NUM_COL,
              onCell: () => ({ className: 'quotation-tax-rate-col' }),
              render: (_: unknown, __: unknown, index: number) => (
                <TaxRateDetailCell index={index} />
              ),
            },
          ]
        : []),
      ...(showTaxColumns
        ? [
            {
              title: t('app.kuaizhizao.purchaseOrder.col.exclAmount'),
              width: DOCUMENT_DETAIL_COL_WIDTH.exclAmount,
              ...DOCUMENT_DETAIL_NUM_COL,
              render: (_: unknown, __: unknown, index: number) => (
                <AntForm.Item
                  noStyle
                  shouldUpdate={(prev, curr) =>
                    prev?.items !== curr?.items || prev?.price_type !== curr?.price_type
                  }
                >
                  {({ getFieldValue }) => {
                    const row = getFieldValue(['items', index]) ?? {};
                    const pt = normalizeDocumentFormPriceType(
                      getFieldValue('price_type'),
                      'sales',
                    );
                    const line = resolveSalesWarehouseLineAmounts(
                      {
                        delivery_quantity: row.delivery_quantity,
                        unit_price: row.unit_price,
                        tax_rate: row.tax_rate,
                        is_gift: row.is_gift,
                      },
                      pt,
                    );
                    return <span>{formatCurrencyAmount(line.excl)}</span>;
                  }}
                </AntForm.Item>
              ),
            },
            {
              title: t('app.kuaizhizao.purchaseOrder.col.taxAmount'),
              width: DOCUMENT_DETAIL_COL_WIDTH.taxAmount,
              ...DOCUMENT_DETAIL_NUM_COL,
              render: (_: unknown, __: unknown, index: number) => (
                <AntForm.Item
                  noStyle
                  shouldUpdate={(prev, curr) =>
                    prev?.items !== curr?.items || prev?.price_type !== curr?.price_type
                  }
                >
                  {({ getFieldValue }) => {
                    const row = getFieldValue(['items', index]) ?? {};
                    const pt = normalizeDocumentFormPriceType(
                      getFieldValue('price_type'),
                      'sales',
                    );
                    const line = resolveSalesWarehouseLineAmounts(
                      {
                        delivery_quantity: row.delivery_quantity,
                        unit_price: row.unit_price,
                        tax_rate: row.tax_rate,
                        is_gift: row.is_gift,
                      },
                      pt,
                    );
                    return <span>{formatCurrencyAmount(line.tax)}</span>;
                  }}
                </AntForm.Item>
              ),
            },
            {
              title: t('app.kuaizhizao.purchaseOrder.col.inclTotal'),
              width: DOCUMENT_DETAIL_COL_WIDTH.lineAmount,
              ...DOCUMENT_DETAIL_NUM_COL,
              render: (_: unknown, __: unknown, index: number) => (
                <AntForm.Item
                  noStyle
                  shouldUpdate={(prev, curr) =>
                    prev?.items !== curr?.items || prev?.price_type !== curr?.price_type
                  }
                >
                  {({ getFieldValue }) => {
                    const row = getFieldValue(['items', index]) ?? {};
                    const pt = normalizeDocumentFormPriceType(
                      getFieldValue('price_type'),
                      'sales',
                    );
                    const line = resolveSalesWarehouseLineAmounts(
                      {
                        delivery_quantity: row.delivery_quantity,
                        unit_price: row.unit_price,
                        tax_rate: row.tax_rate,
                        is_gift: row.is_gift,
                      },
                      pt,
                    );
                    return <span>{formatCurrencyAmount(line.incl)}</span>;
                  }}
                </AntForm.Item>
              ),
            },
          ]
        : [
            {
              title: t('app.kuaizhizao.warehouseCommon.colAmount'),
              dataIndex: 'total_amount',
              width: DOCUMENT_DETAIL_COL_WIDTH.unitPrice,
              ...DOCUMENT_DETAIL_NUM_COL,
              render: (_: unknown, __: unknown, index: number) => (
                <AntForm.Item
                  noStyle
                  shouldUpdate={(prev, curr) =>
                    prev?.items !== curr?.items || prev?.price_type !== curr?.price_type
                  }
                >
                  {({ getFieldValue }) => {
                    const row = getFieldValue(['items', index]) ?? {};
                    const pt = normalizeDocumentFormPriceType(
                      getFieldValue('price_type'),
                      'sales',
                    );
                    const line = resolveSalesWarehouseLineAmounts(
                      {
                        delivery_quantity: row.delivery_quantity,
                        unit_price: row.unit_price,
                        tax_rate: row.tax_rate,
                        is_gift: row.is_gift,
                      },
                      pt,
                    );
                    return <span>{formatCurrencyAmount(line.excl)}</span>;
                  }}
                </AntForm.Item>
              ),
            },
          ]),
      buildDocumentLineAttachmentsFormColumn(
        t,
        DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY.salesDelivery,
      ),
    ];
    return filterWarehouseTrackingColumns(cols, trackingFlags);
  }, [
    batchOptionsByKey,
    batchOptionsLoadingKey,
    clearLineWarehouseDependents,
    ensureBatchOptions,
    ensureSerialOptions,
    isEdit,
    quantityDecimals,
    serialOptionsByUuid,
    serialOptionsLoadingUuid,
    t,
    trackingFlags,
    priceDecimals,
  ]);

  const handleSalesDeliveryPriceTypeChange = useCallback(
    (nextChecked: boolean) => {
      const nextType: PriceTypeValue = nextChecked ? 'tax_inclusive' : 'tax_exclusive';
      const fromType = salesFormPriceType(formRef.current?.getFieldValue('price_type'));
      deferConvertLineItemsByPriceType(formRef.current, fromType, nextType, {
        quantityField: 'delivery_quantity',
        priceDecimals,
      });
    },
    [priceDecimals],
  );

  const splitLineContext = useMemo(() => {
    if (splitLineIndex == null) return null;
    const items = (formRef.current?.getFieldValue('items') ?? []) as Record<string, unknown>[];
    const line = items[splitLineIndex];
    if (!line) return null;
    const materialId = Number(line.material_id) || 0;
    const qty = Number(line.delivery_quantity) || 0;
    const materialLabel =
      String(line.material_name || line.material_code || materialId || '').trim() || '-';
    return { materialId, qty, materialLabel, lineIndex: splitLineIndex };
  }, [splitLineIndex]);

  const needValidLineKey = 'app.kuaizhizao.warehouseOutbound.msg.needValidSalesDeliveryLine';

  const resolveEditLineId = (row: Record<string, unknown>, lineIndex: number): number => {
    const fromRow = Number(row.id);
    if (fromRow > 0) return fromRow;
    const fromForm = Number(formRef.current?.getFieldValue(['items', lineIndex, 'id']));
    if (fromForm > 0) return fromForm;
    const fromSnapshot = editLineIdsRef.current[lineIndex];
    return fromSnapshot > 0 ? fromSnapshot : 0;
  };

  const handleFinish = async (values: Record<string, unknown>) => {
    const items = (values.items as Record<string, unknown>[]) ?? [];
    const validItems: Record<string, unknown>[] = [];
    items.forEach((it, index) => {
      if (!it.material_id || (Number(it.delivery_quantity) || 0) <= 0) return;
      const lineId = isEdit ? resolveEditLineId(it, index) : 0;
      validItems.push({
        ...it,
        ...(isEdit && lineId > 0 ? { id: lineId } : {}),
      });
    });
    if (!validItems.length) {
      const msg = t(needValidLineKey);
      messageApi.error(msg);
      throw new Error(msg);
    }

    const customerId = Number(values.customer_id) || 0;
    if (customerId <= 0) {
      const msg = t('app.kuaizhizao.warehouseOutbound.selectCustomerRequired');
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
        throw new Error(
          t('app.kuaizhizao.warehouseOutbound.msg.selectLineWarehouse', {
            material: materialLabel,
          }),
        );
      }
      const material = await fetchMaterialForUnitSelectCache(Number(it.material_id));
      const batchManaged =
        it.batch_managed != null
          ? !!it.batch_managed
          : !!(material as Material | null)?.batchManaged;
      const materialId = Number(it.material_id) || 0;
      const batchLine = salesDeliveryCreateBatchLineEnabled(trackingFlags, batchManaged);
      const batchStrict = isMaterialBatchEntryEnabled(trackingFlags, batchManaged);
      const batchKey =
        materialId > 0 && lineWhId > 0 ? batchOptionsCacheKey(materialId, lineWhId) : '';
      const batchOpts = batchKey ? batchOptionsByKey[batchKey] ?? [] : [];
      const batchRequired = batchStrict || batchOpts.length > 0;
      const qty = Number(it.delivery_quantity) || 0;
      const allocs = lineBatchAllocations(it, qty);
      if (batchLine && batchRequired) {
        if (!isValidOutboundBatchAllocations(allocs, batchOpts, qty)) {
          throw new Error(
            t('app.kuaizhizao.warehouseOutbound.confirm.batchAllocationRequired', {
              material: materialLabel,
              qty,
              batches: batchOpts.map((o) => o.value).join('、') || '—',
            }),
          );
        }
      }
      const serialManaged =
        it.serial_managed != null
          ? !!it.serial_managed
          : !!(material as Material | null)?.serialManaged;
      if (isMaterialSerialEntryEnabled(trackingFlags, serialManaged)) {
        const serials = Array.isArray(it.serial_numbers)
          ? it.serial_numbers.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
          : [];
        const required = Math.round(qty);
        if (serials.length !== required) {
          throw new Error(
            t('app.kuaizhizao.warehouseOutbound.entry.serialCountMismatch', {
              material: materialLabel,
              required,
              actual: serials.length,
            }),
          );
        }
        if (allocs.length > 1) {
          throw new Error(
            t('app.kuaizhizao.warehouseOutbound.confirm.batchSerialMultiNotSupported', {
              material: materialLabel,
            }),
          );
        }
      }
      const dualErr = validateDualQuantityBeforeSave({
        material: material as Material | null,
        value: {
          quantity: Number(it.delivery_quantity),
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

    const headerWhId = Number(validItems[0]?.warehouse_id) || 0;
    const headerWhName = String(validItems[0]?.warehouse_name ?? '').trim();
    const deliveryTime =
      values.delivery_time &&
      typeof (values.delivery_time as { format?: unknown }).format === 'function'
        ? toApiBusinessDocumentDateTime(values.delivery_time as dayjs.Dayjs)
        : undefined;

    try {
      if (isEdit && editingId != null) {
        const missingLineId = validItems.some((it) => !(Number(it.id) > 0));
        if (missingLineId) {
          const msg = t('app.kuaizhizao.warehouseOutbound.msg.noEditableLines');
          messageApi.error(msg);
          throw new Error(msg);
        }
        await warehouseApi.salesDelivery.update(String(editingId), {
          customer_id: customerId,
          customer_name: String(values.customer_name ?? '').trim(),
          shipping_address: String(values.shipping_address ?? '').trim() || undefined,
          warehouse_id: headerWhId,
          warehouse_name: headerWhName,
          delivery_time: deliveryTime,
          deliverer_id: values.deliverer_id != null ? Number(values.deliverer_id) : undefined,
          deliverer_name: String(values.deliverer_name ?? '').trim() || undefined,
          notes: String(values.notes ?? '').trim() || undefined,
          price_type: String(values.price_type ?? DEFAULT_SALES_PRICE_TYPE),
          items: validItems.map((it) => {
            const qty = Number(it.delivery_quantity) || 0;
            const lineWhId = Number(it.warehouse_id) || 0;
            const allocs = lineBatchAllocations(it, qty);
            const payload: Record<string, unknown> = {
              id: Number(it.id),
              delivery_quantity: qty,
              unit_price: Number(it.unit_price) || 0,
              tax_rate: Number(it.tax_rate) || 0,
              warehouse_id: lineWhId,
              warehouse_name: String(it.warehouse_name ?? '').trim() || undefined,
              location_id:
                it.location_id != null && Number(it.location_id) > 0
                  ? Number(it.location_id)
                  : null,
              location_code:
                it.location_code != null && String(it.location_code).trim()
                  ? String(it.location_code).trim()
                  : null,
              serial_numbers: Array.isArray(it.serial_numbers)
                ? it.serial_numbers.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
                : undefined,
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
        await warehouseApi.salesDelivery.create({
          sales_order_id: null,
          sales_order_code: '',
          customer_id: customerId,
          customer_name: String(values.customer_name ?? '').trim(),
          shipping_address: String(values.shipping_address ?? '').trim() || undefined,
          revenue_recognition: values.revenue_recognition,
          // 表头仓仅列表汇总：取首行；真源在明细行
          warehouse_id: headerWhId,
          warehouse_name: headerWhName,
          delivery_time: deliveryTime,
          deliverer_id: values.deliverer_id != null ? Number(values.deliverer_id) : undefined,
          deliverer_name: String(values.deliverer_name ?? '').trim() || undefined,
          currency_code: String(values.currency_code ?? 'CNY').trim() || 'CNY',
          exchange_rate: values.exchange_rate != null ? Number(values.exchange_rate) : 1,
          notes: String(values.notes ?? '').trim() || undefined,
          price_type: String(values.price_type ?? DEFAULT_SALES_PRICE_TYPE),
          items: validItems.flatMap((it) => {
            const qty = Number(it.delivery_quantity) || 0;
            const price = Number(it.unit_price) || 0;
            const taxRate = Number(it.tax_rate) || 0;
            const lineAmount = (lineQty: number) =>
              recalcDocumentStoredLineAmount(
                { qty: lineQty, unit_price: price, tax_rate: taxRate, is_gift: it.is_gift },
                String(values.price_type ?? DEFAULT_SALES_PRICE_TYPE),
              );
            const lineWhId = Number(it.warehouse_id) || 0;
            const allocs = lineBatchAllocations(it, qty);
            const base = {
              sales_order_item_id: null as null,
              material_id: Number(it.material_id),
              material_code: String(it.material_code ?? ''),
              material_name: String(it.material_name ?? ''),
              material_spec: it.material_spec != null ? String(it.material_spec) : undefined,
              material_unit: String(it.material_unit ?? ''),
              aux_quantity: it.aux_quantity != null ? Number(it.aux_quantity) : undefined,
              aux_unit: it.aux_unit != null ? String(it.aux_unit) : undefined,
              unit_conversion_rate:
                it.unit_conversion_rate != null ? Number(it.unit_conversion_rate) : undefined,
              unit_price: price,
              tax_rate: taxRate,
              warehouse_id: lineWhId,
              warehouse_name: String(it.warehouse_name ?? '').trim() || undefined,
              location_id:
                it.location_id != null && Number(it.location_id) > 0
                  ? Number(it.location_id)
                  : undefined,
              location_code:
                it.location_code != null && String(it.location_code).trim()
                  ? String(it.location_code).trim()
                  : undefined,
              serial_numbers: Array.isArray(it.serial_numbers)
                ? it.serial_numbers.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
                : undefined,
              attachments: normalizeDocumentAttachments(it.attachments as any),
            };
            // 新建接口无 batch_allocations：多批拆成多行
            if (allocs.length > 1) {
              return allocs.map((a) => ({
                ...base,
                delivery_quantity: a.quantity,
                total_amount: lineAmount(a.quantity),
                batch_number: a.batchNo,
              }));
            }
            const batchNo = allocs[0]?.batchNo || String(it.batch_number ?? '').trim() || undefined;
            return [
              {
                ...base,
                delivery_quantity: qty,
                total_amount: lineAmount(qty),
                batch_number: batchNo,
              },
            ];
          }),
        });
        messageApi.success(t('common.createSuccess'));
      }
      onClose();
      onSuccess?.();
    } catch (error: unknown) {
      const err = error as { message?: string };
      if (err?.message !== t(needValidLineKey)) {
        messageApi.error(
          err?.message || (isEdit ? t('common.updateFailed') : t('common.createFailed')),
        );
      }
      throw error;
    }
  };

  const modalTitle = useMemo(() => {
    if (!isEdit) return t('app.kuaizhizao.warehouseOutbound.createSalesDeliveryModal');
    const typeLabel = t('app.kuaizhizao.warehouseOutbound.entry.salesDelivery');
    return `${t('common.edit')} ${typeLabel}${editDocumentCode ? ` - ${editDocumentCode}` : ''}`;
  }, [editDocumentCode, isEdit, t]);

  return (
    <>
    <FormModalTemplate
      title={modalTitle}
      open={open}
      onClose={onClose}
      formRef={formRef}
      onFinish={handleFinish}
      isEdit={isEdit}
      loading={formLoading}
      width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
      grid={false}
      initialValues={{
        delivery_time: dayjs(),
        items: [{ ...defaultLineItem }],
        currency_code: 'CNY',
        exchange_rate: 1,
      }}
    >
      <Row gutter={16}>
        <Col span={12}>
          <ProFormItem
            name="customer_id"
            label={t('app.kuaizhizao.warehouseOutbound.field.customer')}
            rules={[
              {
                required: true,
                message: t('app.kuaizhizao.warehouseOutbound.selectCustomerRequired'),
              },
            ]}
          >
            <CustomerSelectDropdown
              hostResource={OUTBOUND_HOST_RESOURCE}
              style={{ width: '100%' }}
              allowClear
              placeholder={t('app.kuaizhizao.warehouseOutbound.selectCustomerRequired')}
              onCustomerPick={(customer) => {
                if (!customer) {
                  formRef.current?.setFieldsValue({ customer_id: undefined, customer_name: '' });
                  applyCustomerFormFields(formRef, null, {
                    orgRevenueRecognitionDefault,
                  });
                  return;
                }
                applyCustomerFormFields(formRef, customer as Record<string, unknown>, {
                  orgRevenueRecognitionDefault,
                });
                formRef.current?.setFieldsValue({
                  customer_id: customer.id,
                  customer_name: customer.name ?? '',
                });
                const items = normalizeFormListItems<Record<string, unknown>>(
                  formRef.current?.getFieldValue('items'),
                );
                items.forEach((_, idx) => {
                  void repriceUnlockedSalesDocumentLineIfNeeded(formRef.current, idx, {
                    asOfField: 'delivery_time',
                  });
                });
              }}
              onChange={(val) => {
                if (val == null || val === '') {
                  formRef.current?.setFieldsValue({ customer_id: undefined, customer_name: '' });
                }
              }}
            />
          </ProFormItem>
          <ProFormText name="customer_name" hidden />
        </Col>
        <Col span={12}>
          <ProFormItem
            name="revenue_recognition"
            label={t('field.document.ledgerRecognition')}
            initialValue={orgRevenueRecognitionDefault}
            rules={[{ required: true, message: t('field.document.ledgerRecognitionRequired') }]}
          >
            <UniDropdown options={revenueLedgerRecognitionOptions} style={{ width: '100%' }} />
          </ProFormItem>
        </Col>
        <Col span={8}>
          <ProFormText
            name="customer_contact"
            label={t('app.kuaizhizao.salesOrder.customerContact')}
            placeholder={t('field.customer.contactPersonPlaceholder')}
          />
        </Col>
        <Col span={8}>
          <ProFormText
            name="customer_phone"
            label={t('app.kuaizhizao.salesOrder.customerPhone')}
            placeholder={t('field.customer.phonePlaceholder')}
          />
        </Col>
        <Col span={8}>
          <UserPickField
            name="deliverer_id"
            nameField="deliverer_name"
            label={t('app.kuaizhizao.warehouseOutbound.field.operator')}
            placeholder={t('app.kuaizhizao.warehouseOutbound.field.operator')}
            userList={users}
            loading={usersLoading}
          />
        </Col>
        <Col span={24}>
          <ProFormText
            name="shipping_address"
            label={t('app.kuaizhizao.salesOrder.shippingAddress')}
            placeholder={t('app.kuaizhizao.quotation.form.shippingAddressPlaceholder')}
          />
        </Col>
        <Col span={12}>
          <ProFormDatePicker
            name="delivery_time"
            label={t('app.kuaizhizao.warehouseOutbound.field.documentDate')}
            fieldProps={{
              style: { width: '100%' },
              onChange: () => {
                const items = normalizeFormListItems<Record<string, unknown>>(
                  formRef.current?.getFieldValue('items'),
                );
                items.forEach((_, idx) => {
                  void repriceUnlockedSalesDocumentLineIfNeeded(formRef.current, idx, {
                    asOfField: 'delivery_time',
                  });
                });
              },
            }}
          />
        </Col>
        <Col span={12}>
          <ProFormText
            name="currency_code"
            label={t('app.kuaizhizao.warehouseInbound.field.currency')}
            initialValue="CNY"
            rules={[
              { required: true, message: t('app.kuaizhizao.warehouseInbound.field.currencyRequired') },
            ]}
          />
        </Col>
      </Row>

      <ProFormText name="price_type" hidden initialValue={DEFAULT_SALES_PRICE_TYPE} />
      <AntForm.Item noStyle shouldUpdate={(prev, curr) => prev?.price_type !== curr?.price_type}>
        {({ getFieldValue }) => {
          const priceType = salesFormPriceType(getFieldValue('price_type'));
          const showTaxColumns = priceType === 'tax_inclusive';
          return (
            <>
              <DocumentDetailTableStyles />
              <UniTableDetail
                name="items"
                title={t('app.kuaizhizao.warehouseOutbound.createLinesTitle')}
                required
                requiredMessage={t(needValidLineKey)}
                leftExtra={(
                  <PriceTypeSwitch
                    checked={priceType === 'tax_inclusive'}
                    onChange={handleSalesDeliveryPriceTypeChange}
                  />
                )}
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
                        }}
                      >
                        {t('common.addDetail')}
                      </Button>
                    </Space>
                  )
                }
                columns={buildFormItemColumns(showTaxColumns)}
                disabledAdd
                disabledRemove={isEdit}
                initialValue={{ ...defaultLineItem }}
                tableProps={DOCUMENT_DETAIL_TABLE_PROPS}
              />
            </>
          );
        }}
      </AntForm.Item>
      <Row gutter={16}>
        <Col span={24}>
          <ProFormTextArea
            name="notes"
            label={t('common.remark')}
            placeholder={t('app.kuaizhizao.warehouseOutbound.field.remarksPlaceholder')}
            fieldProps={{ rows: 3 }}
          />
        </Col>
      </Row>
    </FormModalTemplate>
    {!isEdit && splitLineContext ? (
      <SplitByWarehouseModal
        open
        onClose={() => setSplitLineIndex(null)}
        materialId={splitLineContext.materialId}
        materialLabel={splitLineContext.materialLabel}
        targetQuantity={splitLineContext.qty}
        hostResource={OUTBOUND_HOST_RESOURCE}
        quantityPrecision={quantityDecimals}
        onConfirm={(allocations) =>
          applySplitByWarehouse(splitLineContext.lineIndex, allocations)
        }
      />
    ) : null}
    </>
  );
};

export default SalesDeliveryCreateModal;
