/**
 * 采购入库空白建单（无来源采购订单/通知/检验）。
 * 表头补齐金蝶外推常用字段：供应商、采购员、验收人、付款方式、税率、币别。
 * 采购员工号由选人自动写入 buyer_operator_number（隐藏字段），不再单独填写。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { App, Button, Col, Form as AntForm, Input, InputNumber, Row, Space, Tooltip } from 'antd';
import {
  ProFormDatePicker,
  ProFormItem,
  ProFormText,
  ProFormTextArea,
  type ProFormInstance,
} from '@ant-design/pro-components';
import { PlusOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { FormModalTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import { UniTableDetail } from '../../../../../components/uni-table-detail';
import { normalizeDocumentAttachments } from '../../../utils/documentAttachments';
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
import { SupplierSelectDropdown } from '../../../../master-data/components/SupplierSelectDropdown';
import { warehouseApi } from '../../../services/production';
import { useNumericPrecisionPlaces } from '../../../../../hooks/useNumericPrecision';
import { toApiBusinessDocumentDateTime } from '../../../../../utils/formDate';
import {
  buildDocumentDetailSpecModelFormColumns,
  withMaterialLineFillMapping,
} from '../../sales-management/shared/materialLineFormDetail';
import { resolveMaterialScenarioUnit } from '../../../../../utils/materialScenarioUnit';
import { DocumentAmountSummary } from '../../../components/document-amount-summary/DocumentAmountSummary';
import {
  computePurchaseReceiptFormGoodsTotals,
  computePurchaseReceiptFormLineAmounts,
  purchaseOrderFormLineToStored,
  purchaseOrderTaxRateToPercent,
  readPurchaseOrderEnteredUnitPrice,
  type PurchaseReceiptPoSettlementCtx,
} from '../../purchase-management/shared/purchaseOrderAmounts';
import { readPurchaseReceiptFormUnitPrice } from '../shared/purchaseReceiptWarehouseAmounts';
import { getPurchaseOrder } from '../../../services/purchase';
import {
  enrichPurchaseOrderItemsMaterial,
  getOutstandingPoItems,
  normalizePurchaseOrderDetail,
} from './inboundPoReceiptEntryUtils';
import type { PurchaseReceiptPoComposePayload } from './inboundPullEntryTypes';
import { DocumentLineUnitSelect } from '../../../../../components/quantity-with-unit';
import { DocumentLineDualQuantityFormCell } from '../../../../../components/quantity-with-unit/documentLineDualQuantityColumn';
import {
  documentLineDualQuantityForPush,
  validateDualQuantityBeforeSave,
} from '../../../../../utils/materialDualQuantity';
import {
  fetchMaterialForUnitSelectCache,
  prefetchMaterialsForUnitSelect,
} from '../../../../../components/material-unit-select';
import { materialApi, materialBatchApi } from '../../../../master-data/services/material';
import type { Material } from '../../../../master-data/types/material';
import {
  applyPurchaseDocumentLineMaterialPricing,
  repriceUnlockedPurchaseDocumentLineIfNeeded,
} from '../../../../master-data/utils/resolve-partner-material-price';
import { partnerPaymentMethodSelectOptions } from '../../../../master-data/utils/partner-static-labels';
import { normalizeFormListItems } from '../../../../../utils/formListItems';
import {
  applyMaterialTrackingToFormRow,
  readMaterialTrackingFromPicker,
} from './inboundItemTracking';
import { useQuery } from '@tanstack/react-query';
import { getBusinessConfig } from '../../../../../services/businessConfig';
import {
  applySupplierLedgerRecognition,
  resolveOrgPayableDefaultFromBusinessConfig,
} from '../../purchase-management/shared/applySupplierFormFields';
import {
  PurchaseDepartmentFormField,
  resolvePurchaseDepartmentPayload,
  usePurchaseDepartmentOptions,
} from '../../purchase-management/shared/PurchaseDepartmentFormField';
import {
  buildPayableLedgerRecognitionOptions,
} from '../../../../../utils/documentLedgerRecognition';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import { getDataDictionaryByCode, getDictionaryItemList, type DictionaryItem } from '../../../../../services/dataDictionary';
import { mapSystemDictionaryItemOptions } from '../../../../../utils/systemDictionaryI18n';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import type { User } from '../../../../../services/user';
import { searchUserDisplay } from '../../../../../services/user';
import {
  displayItemsToUsers,
  normalizeUserDisplayName,
} from '../../../../../utils/userDisplay';
import { getPopupContainerInModal } from '../../../../../utils/modalEventIsolation';
import {
  isMaterialBatchEntryEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import PriceTypeSwitch, { type PriceTypeValue } from '../../../../../components/price-type-switch/PriceTypeSwitch';
import {
  deferConvertLineItemsByPriceType,
} from '../../../../../utils/priceTypeSwitch';
import {
  DEFAULT_PURCHASE_PRICE_TYPE,
  purchaseFormPriceType,
} from '../../purchase-management/shared/purchasePriceType';

const INBOUND_HOST_RESOURCE = 'kuaizhizao:inbound';

const PURCHASE_RECEIPT_ORDER_TYPE_FALLBACK: Pick<DictionaryItem, 'value' | 'label' | 'is_system_managed' | 'sort_order'>[] = [
  { value: '标准采购', label: '标准采购', is_system_managed: true, sort_order: 0 },
  { value: '资产采购', label: '资产采购', is_system_managed: true, sort_order: 1 },
  { value: '服务采购', label: '服务采购', is_system_managed: true, sort_order: 2 },
];

const defaultLineItem = {
  receipt_quantity: 1,
  unit_price: 0,
  warehouse_id: undefined as number | undefined,
  warehouse_name: undefined as string | undefined,
  location_id: undefined as number | undefined,
  location_code: undefined as string | undefined,
  batch_number: undefined as string | undefined,
  batch_managed: false,
  material_uuid: undefined as string | undefined,
  batch_rule_id: undefined as number | undefined,
  default_batch_rule_id: undefined as number | undefined,
  aux_quantity: undefined,
  aux_unit: undefined,
  unit_conversion_rate: undefined,
};

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

function PurchaseReceiptCreateLocationCell({
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
            hostResource={INBOUND_HOST_RESOURCE}
            showStock={false}
            allowClear={false}
            size={DOCUMENT_DETAIL_CONTROL_SIZE}
            getPopupContainer={getPopupContainerInModal}
            disabled={!(warehouseId > 0) || hasLocations === undefined}
            placeholder={
              warehouseId > 0
                ? t('app.kuaizhizao.warehouseInbound.col.location')
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

function PurchaseReceiptCreateWarehouseCell({
  index,
  clearLineWarehouseDependents,
  formRef,
  t,
}: {
  index: number;
  clearLineWarehouseDependents: (index: number) => void;
  formRef: React.MutableRefObject<ProFormInstance | undefined>;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  const materialId = Number(AntForm.useWatch(['items', index, 'material_id']) || 0);
  const servicePurchase = String(AntForm.useWatch('order_type') ?? '').trim() === '服务采购';
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
        rules={
          servicePurchase
            ? []
            : [
                {
                  required: true,
                  message: t('app.kuaizhizao.warehouseInbound.selectWarehouse'),
                },
              ]
        }
        noStyle
      >
        <UniWhDropdown
          size={DOCUMENT_DETAIL_CONTROL_SIZE}
          hostResource={INBOUND_HOST_RESOURCE}
          materialId={materialId > 0 ? materialId : undefined}
          showStock={materialId > 0}
          sortByStock={materialId > 0}
          allowClear={servicePurchase}
          placeholder={t('app.kuaizhizao.warehouseInbound.selectWarehouse')}
          getPopupContainer={getPopupContainerInModal}
          onChange={(_value, wh) => {
            clearLineWarehouseDependents(index);
            formRef.current?.setFieldValue(['items', index, 'warehouse_name'], wh?.name ?? '');
          }}
        />
      </AntForm.Item>
    </div>
  );
}

/** 历史金蝶 CREDIT/CASH → 表单码；客商码原样 */
const TAX_RATE_PERCENT_ADDON_STYLE: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '0 8px',
  color: 'var(--ant-color-text-secondary)',
  background: 'var(--ant-color-fill-alter)',
  border: '1px solid var(--ant-color-border)',
  borderLeft: 0,
  borderRadius: '0 var(--ant-border-radius) var(--ant-border-radius) 0',
  fontSize: 'inherit',
};

/** Form.Item 子组件须接收 value/onChange；不可直接用 Space.Compact 包裹 InputNumber */
function TaxRatePercentInput({
  value,
  onChange,
}: {
  value?: number | null;
  onChange?: (value: number | null) => void;
}) {
  return (
    <Space.Compact style={{ width: '100%' }}>
      <InputNumber
        value={value}
        onChange={onChange}
        min={0}
        max={100}
        precision={2}
        style={{ width: '100%' }}
      />
      <span style={TAX_RATE_PERCENT_ADDON_STYLE}>%</span>
    </Space.Compact>
  );
}

function normalizeReceiptPayModeForForm(raw: unknown): string | undefined {
  const s = String(raw ?? '').trim();
  if (!s) return undefined;
  const upper = s.toUpperCase();
  if (upper === 'CASH') return 'cash';
  if (upper === 'CREDIT') return 'CREDIT';
  return s;
}

export type PurchaseReceiptCreateModalProps = {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  /** 有值时用同一套新建表单编辑已有采购入库单 */
  receiptId?: number | null;
  /** 采购订单取单后尚未下推：打开新建弹窗预填，保存时才建单 */
  poCompose?: PurchaseReceiptPoComposePayload | null;
};
function positiveId(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function purchaseReceiptFormPriceType(taxRatePercent: number): 'tax_inclusive' | 'tax_exclusive' {
  return taxRatePercent > 0 ? 'tax_inclusive' : 'tax_exclusive';
}


function parseSerialNumbers(raw: unknown): string[] | undefined {
  if (Array.isArray(raw)) {
    const list = raw.map((item) => String(item).trim()).filter(Boolean);
    return list.length ? list : undefined;
  }
  const text = String(raw ?? '').trim();
  if (!text) return undefined;
  try {
    const parsed = JSON.parse(text) as unknown;
    if (Array.isArray(parsed)) {
      const list = parsed.map((item) => String(item).trim()).filter(Boolean);
      return list.length ? list : undefined;
    }
  } catch {
    return [text];
  }
  return undefined;
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

export const PurchaseReceiptCreateModal: React.FC<PurchaseReceiptCreateModalProps> = ({
  open,
  onClose,
  onSuccess,
  receiptId = null,
  poCompose = null,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const editingId = open && receiptId != null && Number(receiptId) > 0 ? Number(receiptId) : null;
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const formRef = useRef<ProFormInstance>();
  const [formLoading, setFormLoading] = useState(false);
  const sourceLinkRef = useRef<{ purchase_order_id: number | null; purchase_order_code: string }>({
    purchase_order_id: null,
    purchase_order_code: '',
  });
  /** 仅编辑历史「赊购 CREDIT」时追加选项，新建不再提供赊购 */
  const [includeLegacyCreditOption, setIncludeLegacyCreditOption] = useState(false);
  const currentUser = useCurrentUser();
  const {
    options: departmentOptions,
    loading: departmentOptionsLoading,
    resolveName: resolveDepartmentName,
  } = usePurchaseDepartmentOptions();
  const quantityDecimals = useNumericPrecisionPlaces('quantity');
  const priceDecimals = useNumericPrecisionPlaces('price');
  const amountDecimals = useNumericPrecisionPlaces('amount');
  const trackingFlags = useWarehouseTrackingFlags();
  const [generatingBatchIdx, setGeneratingBatchIdx] = useState<number | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [orderTypeOptions, setOrderTypeOptions] = useState<Array<{ label: string; value: string }>>(() =>
    mapSystemDictionaryItemOptions('ORDER_TYPE', PURCHASE_RECEIPT_ORDER_TYPE_FALLBACK as DictionaryItem[], t),
  );
  const [orderTypeLoading, setOrderTypeLoading] = useState(false);
  useEffect(() => {
    const loadOrderType = async () => {
      setOrderTypeLoading(true);
      try {
        const dict = await getDataDictionaryByCode('ORDER_TYPE');
        const items = await getDictionaryItemList(dict.uuid, true);
        const sorted = [...items].sort((a, b) => a.sort_order - b.sort_order);
        setOrderTypeOptions(mapSystemDictionaryItemOptions('ORDER_TYPE', sorted, t));
      } catch {
        setOrderTypeOptions(
          mapSystemDictionaryItemOptions('ORDER_TYPE', PURCHASE_RECEIPT_ORDER_TYPE_FALLBACK as DictionaryItem[], t),
        );
        messageApi.info(t('app.kuaizhizao.purchaseOrder.orderTypeFallback'));
      } finally {
        setOrderTypeLoading(false);
      }
    };
    void loadOrderType();
  }, [messageApi, t]);
  const [linkedPoId, setLinkedPoId] = useState<number | null>(null);
  const [poSettlementCtx, setPoSettlementCtx] = useState<PurchaseReceiptPoSettlementCtx | null>(
    null,
  );

  useEffect(() => {
    if (linkedPoId == null || linkedPoId <= 0) {
      setPoSettlementCtx(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const raw = await getPurchaseOrder(String(linkedPoId));
        const order = normalizePurchaseOrderDetail(
          await enrichPurchaseOrderItemsMaterial(raw as Parameters<typeof enrichPurchaseOrderItemsMaterial>[0]),
        );
        if (cancelled) return;
        const headerTaxPct = purchaseOrderTaxRateToPercent(order.tax_rate ?? 13);
        const rawPriceType = String(
          (order as { price_type?: string; priceType?: string }).price_type ??
            (order as { priceType?: string }).priceType ??
            '',
        ).trim();
        const priceType =
          rawPriceType === 'tax_inclusive' || rawPriceType === 'tax_exclusive'
            ? rawPriceType
            : purchaseReceiptFormPriceType(headerTaxPct);
        const items = Array.isArray(order.items) ? order.items : [];
        const poiById: PurchaseReceiptPoSettlementCtx['poiById'] = {};
        for (const it of items) {
          const id = Number((it as { id?: number }).id);
          if (id > 0) {
            poiById[id] = it as PurchaseReceiptPoSettlementCtx['poiById'][number];
          }
        }
        setPoSettlementCtx({
          priceType,
          headerTaxRate: order.tax_rate,
          poiById,
        });
      } catch {
        if (!cancelled) setPoSettlementCtx(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [linkedPoId]);

  const { data: businessConfig } = useQuery({
    queryKey: ['businessConfigFinanceRecognition'],
    queryFn: getBusinessConfig,
    staleTime: 60_000,
  });
  const payableLedgerRecognitionOptions = useMemo(
    () => buildPayableLedgerRecognitionOptions(t),
    [t],
  );
  const orgPayableDefault = useMemo(
    () => resolveOrgPayableDefaultFromBusinessConfig(businessConfig),
    [businessConfig],
  );
  const payModeOptions = useMemo(() => {
    const base = partnerPaymentMethodSelectOptions(t);
    if (!includeLegacyCreditOption) return base;
    if (base.some((o) => o.value === 'CREDIT')) return base;
    return [
      ...base,
      {
        value: 'CREDIT',
        label: t('app.kuaizhizao.warehouseInbound.payMode.credit'),
      },
    ];
  }, [t, includeLegacyCreditOption]);

  const defaultPerson = useMemo(() => {
    if (!currentUser) return { id: undefined as number | undefined, name: '' };
    const id = currentUser.id != null && currentUser.id > 0 ? Number(currentUser.id) : undefined;
    const name = String(currentUser.full_name || currentUser.username || '').trim();
    return { id, name };
  }, [currentUser]);

  const resetForm = useCallback(() => {
    formRef.current?.resetFields();
    formRef.current?.setFieldsValue({
      items: [{ ...defaultLineItem }],
      receipt_time: dayjs(),
      pay_mode: undefined,
      tax_rate: 13,
      currency: 'CNY',
      buyer_id: defaultPerson.id,
      buyer_name: defaultPerson.name,
      receiver_id: defaultPerson.id,
      receiver_name: defaultPerson.name,
      payable_recognition: orgPayableDefault,
    });
  }, [defaultPerson, orgPayableDefault]);

  const clearLineWarehouseDependents = useCallback((index: number) => {
    formRef.current?.setFieldValue(['items', index, 'location_id'], undefined);
    formRef.current?.setFieldValue(['items', index, 'location_code'], '');
    formRef.current?.setFieldValue(['items', index, 'batch_number'], undefined);
  }, []);

  const handleGenerateBatch = useCallback(
    async (index: number) => {
      if (!trackingFlags.batchManagement) return;
      const items = (formRef.current?.getFieldValue('items') ?? []) as Array<{
        material_uuid?: string;
        batch_managed?: boolean;
        batch_rule_id?: number;
        default_batch_rule_id?: number;
      }>;
      const row = items[index];
      if (!row?.material_uuid || !row?.batch_managed) {
        messageApi.warning(t('app.kuaizhizao.warehouseOtherInbound.msg.selectMaterialFirst'));
        return;
      }
      setGeneratingBatchIdx(index);
      try {
        const res = await materialBatchApi.generate(row.material_uuid, {
          ruleId: row.batch_rule_id ?? row.default_batch_rule_id,
        });
        formRef.current?.setFieldValue(['items', index, 'batch_number'], res.batch_no);
        messageApi.success(t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerated'));
      } catch (error: unknown) {
        const err = error as { message?: string };
        messageApi.error(err?.message || t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerateFailed'));
      } finally {
        setGeneratingBatchIdx(null);
      }
    },
    [messageApi, t, trackingFlags.batchManagement],
  );

  const syncLineMaterialTracking = useCallback(
    async (index: number, material: Material | undefined) => {
      if (!formRef.current) return;
      if (!material) {
        formRef.current.setFieldValue(['items', index, 'batch_managed'], false);
        formRef.current.setFieldValue(['items', index, 'material_uuid'], undefined);
        return;
      }
      let batchManaged = !!(material.batchManaged ?? (material as { batch_managed?: boolean }).batch_managed);
      const fromPicker = readMaterialTrackingFromPicker(material as unknown as Record<string, unknown>);
      if (fromPicker) {
        applyMaterialTrackingToFormRow(
          (name, value) => formRef.current!.setFieldValue(name, value),
          'items',
          index,
          fromPicker,
        );
        batchManaged = fromPicker.batchManaged;
      }
      if (material.uuid) {
        try {
          const full = await materialApi.get(material.uuid);
          batchManaged = !!full.batchManaged;
          const meta = readMaterialTrackingFromPicker(full as unknown as Record<string, unknown>);
          if (meta) {
            applyMaterialTrackingToFormRow(
              (name, value) => formRef.current!.setFieldValue(name, value),
              'items',
              index,
              meta,
            );
            batchManaged = meta.batchManaged;
          }
        } catch {
          /* 使用列表/选择器字段 */
        }
      }
      formRef.current.setFieldValue(
        ['items', index, 'batch_managed'],
        isMaterialBatchEntryEnabled(trackingFlags, batchManaged),
      );
    },
    [trackingFlags],
  );

  useEffect(() => {
    if (!open) return;
    resetForm();
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

    if (!editingId && poCompose?.purchaseOrderId) {
      setFormLoading(true);
      void (async () => {
        try {
          const orderRaw = await getPurchaseOrder(String(poCompose.purchaseOrderId));
          if (cancelled) return;
          const order = normalizePurchaseOrderDetail(orderRaw);
          const materialById = await prefetchMaterialsForUnitSelect(
            (order.items || []).map((it) => it.material_id),
          );
          if (cancelled) return;
          const orderWithMaterials = {
            ...order,
            items: enrichPurchaseOrderItemsMaterial(order.items || [], materialById),
          };
          const outstanding = getOutstandingPoItems(orderWithMaterials);
          const poCode = String(order.order_code ?? '').trim();
          sourceLinkRef.current = {
            purchase_order_id: poCompose.purchaseOrderId,
            purchase_order_code: poCode,
          };
          setLinkedPoId(poCompose.purchaseOrderId);
          const headerTaxPct = purchaseOrderTaxRateToPercent(orderWithMaterials.tax_rate ?? 13);
          const poPriceType = (() => {
            const raw = String(
              (orderWithMaterials as { price_type?: string; priceType?: string }).price_type ??
                (orderWithMaterials as { priceType?: string }).priceType ??
                '',
            ).trim();
            return raw === 'tax_inclusive' || raw === 'tax_exclusive'
              ? raw
              : purchaseReceiptFormPriceType(headerTaxPct);
          })();
          const formItems = outstanding
            .filter((it) => it.id != null && (poCompose.quantities[it.id] ?? 0) > 0)
            .map((it) => {
              const lineId = it.id!;
              const serialList = poCompose.lineSerials[lineId] ?? [];
              const lineTaxPct = (() => {
                const fromLine = purchaseOrderTaxRateToPercent(
                  (it as { tax_rate?: number }).tax_rate,
                );
                return fromLine > 0 ? fromLine : headerTaxPct;
              })();
              const pushQty = Number(poCompose.quantities[lineId]) || 0;
              const dual = documentLineDualQuantityForPush(it as unknown as Record<string, unknown>, {
                sourcePrimaryQty: Number(it.ordered_quantity) || 0,
                pushPrimaryQty: pushQty,
              });
              return {
                purchase_order_item_id: lineId,
                material_id: it.material_id,
                material_code: String(it.material_code ?? ''),
                material_name: String(it.material_name ?? ''),
                material_spec: it.material_spec != null ? String(it.material_spec) : undefined,
                material_unit: String(it.material_unit ?? ''),
                receipt_quantity: pushQty,
                tax_rate: lineTaxPct,
                unit_price: readPurchaseOrderEnteredUnitPrice(it, poPriceType) ?? undefined,
                aux_quantity: dual.aux_quantity,
                aux_unit: dual.aux_unit,
                unit_conversion_rate: dual.unit_conversion_rate,
                warehouse_id: poCompose.lineWh[lineId],
                warehouse_name: String(it.warehouse_name ?? ''),
                location_id: poCompose.lineLoc[lineId],
                location_code: poCompose.lineLocCode[lineId] ?? '',
                batch_number: poCompose.batchNumbers[lineId],
                serial_numbers_json: serialList.length ? JSON.stringify(serialList) : '',
                unqualified_quantity: 0,
                quality_status: '合格',
                line_status: '待入库',
              };
            });
          const taxPct = purchaseOrderTaxRateToPercent(orderWithMaterials.tax_rate ?? 13);
          const notesText =
            String(poCompose.notes ?? '').trim() ||
            (poCode
              ? t('app.kuaizhizao.warehouseInbound.poCompose.defaultNotes', { code: poCode })
              : '');
          const poPayMode = normalizeReceiptPayModeForForm(orderWithMaterials.payment_method_code);
          const poPayableRecognition = String(
            orderWithMaterials.payable_recognition ??
              (orderWithMaterials as { payableRecognition?: string }).payableRecognition ??
              orgPayableDefault,
          );
          setIncludeLegacyCreditOption(poPayMode === 'CREDIT');
          formRef.current?.setFieldsValue({
            order_type: String(orderWithMaterials.order_type ?? '标准采购').trim() || '标准采购',
            supplier_id: positiveId(orderWithMaterials.supplier_id) ?? undefined,
            supplier_name: String(orderWithMaterials.supplier_name ?? ''),
            payable_recognition: poPayableRecognition,
            buyer_id: positiveId(orderWithMaterials.buyer_id) ?? undefined,
            buyer_name: String(orderWithMaterials.buyer_name ?? ''),
            department_id: positiveId(orderWithMaterials.department_id) ?? undefined,
            department_name: String(orderWithMaterials.department_name ?? ''),
            receiver_id: poCompose.receiverId,
            receiver_name: poCompose.receiverName ?? '',
            receipt_time: poCompose.receiptTimeIso ? dayjs(poCompose.receiptTimeIso) : dayjs(),
            delivery_note: poCompose.deliveryNote ?? '',
            pay_mode: poPayMode,
            price_type: poPriceType,
            tax_rate: taxPct,
            currency: String(orderWithMaterials.currency ?? 'CNY').trim() || 'CNY',
            notes: notesText,
            items: formItems.length ? formItems : [{ ...defaultLineItem }],
          });
          await Promise.all(
            formItems.map(async (row, index) => {
              const materialId = Number(row.material_id);
              if (!(materialId > 0)) return;
              const material = await fetchMaterialForUnitSelectCache(materialId);
              if (cancelled || !material) return;
              await syncLineMaterialTracking(index, material);
            }),
          );
        } catch (error: unknown) {
          if (cancelled) return;
          const err = error as { message?: string };
          messageApi.error(err?.message || t('app.kuaizhizao.warehouseInbound.entry.purchase.loadFailed'));
          onCloseRef.current();
        } finally {
          if (!cancelled) setFormLoading(false);
        }
      })();
      return () => {
        cancelled = true;
      };
    }

    if (!editingId) {
      sourceLinkRef.current = { purchase_order_id: null, purchase_order_code: '' };
      setLinkedPoId(null);
      resetForm();
      return () => {
        cancelled = true;
      };
    }

    setFormLoading(true);
    void (async () => {
      try {
        const detail = (await warehouseApi.purchaseReceipt.get(String(editingId))) as Record<
          string,
          unknown
        >;
        if (cancelled) return;
        const poId = positiveId(detail.purchase_order_id);
        sourceLinkRef.current = {
          purchase_order_id: poId,
          purchase_order_code: String(detail.purchase_order_code ?? '').trim(),
        };
        setLinkedPoId(poId);
        const rawItems = Array.isArray(detail.items) ? detail.items : [];
        const items = rawItems.length
          ? rawItems.map((row) => {
              const line = row as Record<string, unknown>;
              const serials = Array.isArray(line.serial_numbers)
                ? line.serial_numbers.map((item) => String(item))
                : [];
              return {
                material_id: positiveId(line.material_id) ?? undefined,
                material_code: String(line.material_code ?? ''),
                material_name: String(line.material_name ?? ''),
                material_spec: line.material_spec != null ? String(line.material_spec) : undefined,
                material_model: line.material_model != null ? String(line.material_model) : undefined,
                material_unit: String(line.material_unit ?? line.unit ?? ''),
                receipt_quantity: Number(line.receipt_quantity) || 0,
                unit_price: readPurchaseReceiptFormUnitPrice(line),
                warehouse_id: positiveId(line.warehouse_id) ?? undefined,
                warehouse_name: String(line.warehouse_name ?? ''),
                location_id: positiveId(line.location_id) ?? undefined,
                location_code: line.location_code != null ? String(line.location_code) : '',
                batch_number: line.batch_number != null ? String(line.batch_number) : undefined,
                aux_quantity: line.aux_quantity != null ? Number(line.aux_quantity) : undefined,
                aux_unit: line.aux_unit != null ? String(line.aux_unit) : undefined,
                unit_conversion_rate:
                  line.unit_conversion_rate != null ? Number(line.unit_conversion_rate) : undefined,
                purchase_order_item_id: positiveId(line.purchase_order_item_id) ?? undefined,
                receipt_notice_item_id: positiveId(line.receipt_notice_item_id) ?? undefined,
                serial_numbers_json: serials.length ? JSON.stringify(serials) : '',
                unqualified_quantity: Number(line.unqualified_quantity) || 0,
                quality_status: String(line.quality_status || '合格'),
                line_status: String(line.status || '待入库'),
                attachments: line.attachments,
              };
            })
          : [{ ...defaultLineItem }];
        const receiptTimeRaw = detail.receipt_time;
        const formPayMode = normalizeReceiptPayModeForForm(detail.pay_mode);
        setIncludeLegacyCreditOption(formPayMode === 'CREDIT');
        formRef.current?.setFieldsValue({
          order_type: String(detail.order_type ?? '标准采购').trim() || '标准采购',
          supplier_id: positiveId(detail.supplier_id) ?? undefined,
          supplier_name: String(detail.supplier_name ?? ''),
          payable_recognition: String(
            (detail.payable_recognition as string | undefined)
              ?? (detail.payableRecognition as string | undefined)
              ?? orgPayableDefault,
          ),
          buyer_id: positiveId(detail.buyer_id) ?? undefined,
          buyer_name: String(detail.buyer_name ?? ''),
          buyer_operator_number: String(detail.buyer_operator_number ?? ''),
          department_id: positiveId(detail.department_id) ?? undefined,
          department_name: String(detail.department_name ?? ''),
          receiver_id: positiveId(detail.receiver_id) ?? undefined,
          receiver_name: String(detail.receiver_name ?? ''),
          receipt_time: receiptTimeRaw ? dayjs(String(receiptTimeRaw)) : dayjs(),
          delivery_note: String(detail.delivery_note ?? ''),
          pay_mode: formPayMode,
          price_type: purchaseReceiptFormPriceType(
            purchaseOrderTaxRateToPercent(detail.tax_rate ?? 13),
          ),
          billtype_number: String(detail.billtype_number ?? 'im_PurInBill_STD_BT_S'),
          tax_rate: detail.tax_rate != null ? Number(detail.tax_rate) : 13,
          currency: String(detail.currency ?? 'CNY'),
          notes: String(detail.notes ?? ''),
          items,
        });
        await Promise.all(
          items.map(async (row, index) => {
            const materialId = Number(row.material_id);
            if (!(materialId > 0)) return;
            const material = await fetchMaterialForUnitSelectCache(materialId);
            if (cancelled || !material) return;
            await syncLineMaterialTracking(index, material);
          }),
        );
      } catch (error: unknown) {
        if (cancelled) return;
        const err = error as { message?: string };
        messageApi.error(err?.message || t('app.kuaizhizao.warehouseInbound.msg.loadDetailFailed'));
        onCloseRef.current();
      } finally {
        if (!cancelled) setFormLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [editingId, messageApi, open, orgPayableDefault, poCompose, resetForm, syncLineMaterialTracking, t]);

  const buildFormItemColumns = useCallback(
    (showTaxColumns: boolean) => [
      {
        title: t('app.kuaizhizao.shipmentNotice.import.materialName'),
        dataIndex: 'material_id',
        width: DOCUMENT_DETAIL_COL_WIDTH.material,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <div className="uni-detail-material-cell">
            <AntForm.Item name={[index, 'material_code']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'material_name']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item
              noStyle
              shouldUpdate={(prev, curr) => prev?.order_type !== curr?.order_type}
            >
              {({ getFieldValue }) => (
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
              sourceType={
                String(getFieldValue('order_type') ?? '').trim() === '服务采购' ? 'Service' : undefined
              }
              onChange={(_v, material) => {
                clearLineWarehouseDependents(index);
                if (!material) {
                  formRef.current?.setFieldValue(['items', index, 'warehouse_id'], undefined);
                  formRef.current?.setFieldValue(['items', index, 'warehouse_name'], '');
                  void syncLineMaterialTracking(index, undefined);
                  return;
                }
                const mat = material as Material;
                formRef.current?.setFieldValue(
                  ['items', index, 'material_unit'],
                  resolveMaterialScenarioUnit(mat, 'purchase'),
                );
                void syncLineMaterialTracking(index, mat);
                const primaryWh = resolvePrimaryDefaultWarehouse(mat);
                if (primaryWh) {
                  formRef.current?.setFieldValue(['items', index, 'warehouse_id'], primaryWh.id);
                  formRef.current?.setFieldValue(['items', index, 'warehouse_name'], primaryWh.name);
                }
                const supplierId = Number(formRef.current?.getFieldValue('supplier_id'));
                void applyPurchaseDocumentLineMaterialPricing(formRef.current, index, mat, {
                  asOfField: 'receipt_time',
                  unitPriceField: 'unit_price',
                  supplierId: Number.isFinite(supplierId) && supplierId > 0 ? supplierId : undefined,
                });
              }}
            />
              )}
            </AntForm.Item>
          </div>
        ),
      },
      ...buildDocumentDetailSpecModelFormColumns(t),
      {
        title: t('common.quantity'),
        dataIndex: 'receipt_quantity',
        width: DOCUMENT_DETAIL_COL_WIDTH.quantity + 80,
        ...DOCUMENT_DETAIL_NUM_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item
            noStyle
            shouldUpdate={(prev, curr) =>
              prev?.items?.[index]?.material_id !== curr?.items?.[index]?.material_id
            }
          >
            {({ getFieldValue }) => {
              const materialId = getFieldValue(['items', index, 'material_id']);
              if (!formRef.current) return null;
              return (
                <DocumentLineDualQuantityFormCell
                  form={formRef.current}
                  listName="items"
                  rowIndex={index}
                  quantityField="receipt_quantity"
                  unitField="material_unit"
                  scenario="purchase"
                  quantityPrecision={quantityDecimals}
                  materialId={materialId}
                  inlineUnitWithQuantity
                  onAfterQuantityChange={() => {
                    const supplierId = Number(formRef.current?.getFieldValue('supplier_id'));
                    void repriceUnlockedPurchaseDocumentLineIfNeeded(formRef.current, index, {
                      asOfField: 'receipt_time',
                      unitPriceField: 'unit_price',
                      supplierId: Number.isFinite(supplierId) && supplierId > 0 ? supplierId : undefined,
                    });
                  }}
                />
              );
            }}
          </AntForm.Item>
        ),
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.warehouse'),
        dataIndex: 'warehouse_id',
        width: 220,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <PurchaseReceiptCreateWarehouseCell
            index={index}
            clearLineWarehouseDependents={clearLineWarehouseDependents}
            formRef={formRef}
            t={t}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.location'),
        dataIndex: 'location_id',
        width: 180,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <PurchaseReceiptCreateLocationCell index={index} formRef={formRef} t={t} />
        ),
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.batchNo'),
        dataIndex: 'batch_number',
        width: 188,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item
            noStyle
            shouldUpdate={(prev, curr) =>
              prev?.items?.[index]?.material_id !== curr?.items?.[index]?.material_id ||
              prev?.items?.[index]?.batch_managed !== curr?.items?.[index]?.batch_managed
            }
          >
            {({ getFieldValue }) => {
              const batchManaged = !!getFieldValue(['items', index, 'batch_managed']);
              if (!isMaterialBatchEntryEnabled(trackingFlags, batchManaged)) {
                return <span>—</span>;
              }
              return (
                <Space size={4} align="center">
                  <AntForm.Item name={[index, 'batch_number']} noStyle>
                    <Input
                      size={DOCUMENT_DETAIL_CONTROL_SIZE}
                      placeholder={t('app.kuaizhizao.warehouseInbound.field.optional')}
                      allowClear
                      style={{ width: 128 }}
                    />
                  </AntForm.Item>
                  <Tooltip title={t('app.kuaizhizao.warehouseInbound.action.generateBatchNo')}>
                    <Button
                      type="text"
                      size="small"
                      icon={<ThunderboltOutlined />}
                      loading={generatingBatchIdx === index}
                      aria-label={t('app.kuaizhizao.warehouseInbound.action.generateBatchNo')}
                      onClick={() => void handleGenerateBatch(index)}
                      style={{ padding: 0, height: 'auto', color: 'var(--ant-color-text-tertiary)' }}
                    />
                  </Tooltip>
                </Space>
              );
            }}
          </AntForm.Item>
        ),
      },
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
            {
              title: t('app.kuaizhizao.purchaseOrder.col.exclAmount'),
              width: DOCUMENT_DETAIL_COL_WIDTH.exclAmount,
              ...DOCUMENT_DETAIL_NUM_COL,
              render: (_: unknown, __: unknown, index: number) => (
                <AntForm.Item noStyle shouldUpdate={(prev, curr) => prev?.items !== curr?.items}>
                  {({ getFieldValue }) => {
                    const row = normalizeFormListItems<Record<string, unknown>>(
                      getFieldValue('items'),
                    )[index];
                    const taxPct = purchaseOrderTaxRateToPercent(row?.tax_rate ?? 13);
                    const priceType = purchaseFormPriceType(
                      poSettlementCtx?.priceType ?? getFieldValue('price_type'),
                    );
                    const line = computePurchaseReceiptFormLineAmounts(
                      row as Parameters<typeof computePurchaseReceiptFormLineAmounts>[0],
                      getFieldValue('tax_rate') ?? taxPct,
                      priceType,
                      poSettlementCtx,
                    );
                    return <span>¥{line.excl.toFixed(amountDecimals)}</span>;
                  }}
                </AntForm.Item>
              ),
            },
            {
              title: t('app.kuaizhizao.purchaseOrder.col.taxAmount'),
              width: DOCUMENT_DETAIL_COL_WIDTH.taxAmount,
              ...DOCUMENT_DETAIL_NUM_COL,
              render: (_: unknown, __: unknown, index: number) => (
                <AntForm.Item noStyle shouldUpdate={(prev, curr) => prev?.items !== curr?.items}>
                  {({ getFieldValue }) => {
                    const row = normalizeFormListItems<Record<string, unknown>>(
                      getFieldValue('items'),
                    )[index];
                    const taxPct = purchaseOrderTaxRateToPercent(row?.tax_rate ?? 13);
                    const priceType = purchaseFormPriceType(
                      poSettlementCtx?.priceType ?? getFieldValue('price_type'),
                    );
                    const line = computePurchaseReceiptFormLineAmounts(
                      row as Parameters<typeof computePurchaseReceiptFormLineAmounts>[0],
                      getFieldValue('tax_rate') ?? taxPct,
                      priceType,
                      poSettlementCtx,
                    );
                    return <span>¥{line.tax.toFixed(amountDecimals)}</span>;
                  }}
                </AntForm.Item>
              ),
            },
            {
              title: t('app.kuaizhizao.purchaseOrder.col.inclTotal'),
              width: DOCUMENT_DETAIL_COL_WIDTH.lineAmount,
              ...DOCUMENT_DETAIL_NUM_COL,
              render: (_: unknown, __: unknown, index: number) => (
                <AntForm.Item noStyle shouldUpdate={(prev, curr) => prev?.items !== curr?.items}>
                  {({ getFieldValue }) => {
                    const row = normalizeFormListItems<Record<string, unknown>>(
                      getFieldValue('items'),
                    )[index];
                    const taxPct = purchaseOrderTaxRateToPercent(row?.tax_rate ?? 13);
                    const priceType = purchaseFormPriceType(
                      poSettlementCtx?.priceType ?? getFieldValue('price_type'),
                    );
                    const line = computePurchaseReceiptFormLineAmounts(
                      row as Parameters<typeof computePurchaseReceiptFormLineAmounts>[0],
                      getFieldValue('tax_rate') ?? taxPct,
                      priceType,
                      poSettlementCtx,
                    );
                    return <span>¥{line.incl.toFixed(amountDecimals)}</span>;
                  }}
                </AntForm.Item>
              ),
            },
          ]
        : [
            {
              title: t('app.kuaizhizao.purchaseOrder.col.totalPrice'),
              width: DOCUMENT_DETAIL_COL_WIDTH.lineAmount,
              ...DOCUMENT_DETAIL_NUM_COL,
              render: (_: unknown, __: unknown, index: number) => (
                <AntForm.Item noStyle shouldUpdate={(prev, curr) => prev?.items !== curr?.items}>
                  {({ getFieldValue }) => {
                    const row = normalizeFormListItems<Record<string, unknown>>(
                      getFieldValue('items'),
                    )[index];
                    const taxPct = purchaseOrderTaxRateToPercent(row?.tax_rate ?? 13);
                    const priceType = purchaseFormPriceType(
                      poSettlementCtx?.priceType ?? getFieldValue('price_type'),
                    );
                    const line = computePurchaseReceiptFormLineAmounts(
                      row as Parameters<typeof computePurchaseReceiptFormLineAmounts>[0],
                      getFieldValue('tax_rate') ?? taxPct,
                      priceType,
                      poSettlementCtx,
                    );
                    return <span>¥{line.excl.toFixed(amountDecimals)}</span>;
                  }}
                </AntForm.Item>
              ),
            },
          ]),
      buildDocumentLineAttachmentsFormColumn(
        t,
        DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY.purchaseReceipt,
      ),
    ],
    [
      amountDecimals,
      clearLineWarehouseDependents,
      generatingBatchIdx,
      handleGenerateBatch,
      poSettlementCtx,
      priceDecimals,
      quantityDecimals,
      syncLineMaterialTracking,
      t,
      trackingFlags,
    ],
  );

  const handlePurchaseReceiptPriceTypeChange = useCallback(
    (nextChecked: boolean) => {
      if (poSettlementCtx?.priceType) return;
      const nextType: PriceTypeValue = nextChecked ? 'tax_inclusive' : 'tax_exclusive';
      const fromType = purchaseFormPriceType(formRef.current?.getFieldValue('price_type'));
      deferConvertLineItemsByPriceType(formRef.current, fromType, nextType, {
        quantityField: 'receipt_quantity',
        priceDecimals,
      });
    },
    [poSettlementCtx?.priceType, priceDecimals],
  );

  const handleFinish = async (values: Record<string, unknown>) => {
    const items = (values.items as Record<string, unknown>[]) ?? [];
    const validItems = items.filter(
      (it) => it.material_id && (Number(it.receipt_quantity) || 0) > 0,
    );
    if (!validItems.length) {
      const msg = t('app.kuaizhizao.warehouseInbound.msg.needValidPurchaseLine');
      messageApi.error(msg);
      throw new Error(msg);
    }

    const supplierId = Number(values.supplier_id) || 0;
    if (supplierId <= 0) {
      const msg = t('app.kuaizhizao.warehouseInbound.selectSupplierRequired');
      messageApi.error(msg);
      throw new Error(msg);
    }

    const servicePurchase = String(values.order_type ?? '').trim() === '服务采购';

    for (const it of validItems) {
      const materialLabel =
        String(it.material_name || it.material_code || it.material_id || '').trim() || '-';
      const lineWhId = Number(it.warehouse_id) || 0;
      if (!servicePurchase && !(lineWhId > 0)) {
        const msg = t('app.kuaizhizao.warehouseInbound.msg.selectWarehouseForMaterial', {
          material: materialLabel,
        });
        messageApi.error(msg);
        throw new Error(msg);
      }
      if (!servicePurchase) {
        const needLoc = await lineLocationSelectionRequired(
          lineWhId,
          it.location_id,
          it.location_code,
        );
        if (needLoc) {
          const msg = t('app.kuaizhizao.warehouseInbound.msg.selectLocationForMaterial', {
            material: materialLabel,
          });
          messageApi.error(msg);
          throw new Error(msg);
        }
      }
      const material = await fetchMaterialForUnitSelectCache(Number(it.material_id));
      const dualErr = validateDualQuantityBeforeSave({
        material: material as Material | null,
        value: {
          quantity: Number(it.receipt_quantity),
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

    const fromPoCompose = !editingId && poCompose?.purchaseOrderId;
    const submitLinkedPoId = fromPoCompose
      ? poCompose.purchaseOrderId
      : editingId
        ? sourceLinkRef.current.purchase_order_id
        : null;
    const linkedPoCode = fromPoCompose
      ? sourceLinkRef.current.purchase_order_code
      : editingId
        ? sourceLinkRef.current.purchase_order_code
        : '';

    const payload = {
        purchase_order_id: submitLinkedPoId,
        purchase_order_code: linkedPoCode,
        order_type: String(values.order_type ?? '标准采购').trim() || '标准采购',
        supplier_id: supplierId,
        supplier_name: String(values.supplier_name ?? '').trim(),
        buyer_id: values.buyer_id != null ? Number(values.buyer_id) : undefined,
        buyer_name: String(values.buyer_name ?? '').trim() || undefined,
        buyer_operator_number: String(values.buyer_operator_number ?? '').trim() || undefined,
        ...resolvePurchaseDepartmentPayload(
          values.department_id,
          resolveDepartmentName,
          values.department_name,
        ),
        pay_mode: String(values.pay_mode ?? '').trim() || undefined,
        tax_rate: values.tax_rate != null ? Number(values.tax_rate) : 13,
        currency: String(values.currency ?? 'CNY').trim() || 'CNY',
        receiver_id: values.receiver_id != null ? Number(values.receiver_id) : undefined,
        receiver_name: String(values.receiver_name ?? '').trim() || undefined,
        warehouse_id: headerWhId > 0 ? headerWhId : null,
        warehouse_name: headerWhId > 0 ? headerWhName || null : null,
        receipt_time:
          values.receipt_time && typeof (values.receipt_time as { format?: unknown }).format === 'function'
            ? toApiBusinessDocumentDateTime(values.receipt_time as dayjs.Dayjs)
            : undefined,
        delivery_note: String(values.delivery_note ?? '').trim() || undefined,
        notes: String(values.notes ?? '').trim() || undefined,
        payable_recognition: values.payable_recognition,
        items: validItems.map((it) => {
          const qty = Number(it.receipt_quantity) || 0;
          const price = Number(it.unit_price) || 0;
          const taxPct = purchaseOrderTaxRateToPercent(it.tax_rate ?? 13);
          const priceType = purchaseFormPriceType(
            poSettlementCtx?.priceType ?? values.price_type,
          );
          const poiId = positiveId(it.purchase_order_item_id);
          const receiptAmounts = computePurchaseReceiptFormLineAmounts(
            {
              receipt_quantity: qty,
              unit_price: price,
              tax_rate: taxPct,
              purchase_order_item_id: poiId ?? undefined,
            },
            values.tax_rate,
            priceType,
            poSettlementCtx,
          );
          const storedLine = purchaseOrderFormLineToStored(
            price,
            qty,
            taxPct,
            priceType,
            priceDecimals,
          );
          const lineWhId = Number(it.warehouse_id) || 0;
          const unqualified = Number(it.unqualified_quantity) || 0;
          const serials = parseSerialNumbers(it.serial_numbers_json);
          return {
            purchase_order_item_id: positiveId(it.purchase_order_item_id),
            receipt_notice_item_id: positiveId(it.receipt_notice_item_id),
            material_id: Number(it.material_id),
            material_code: String(it.material_code ?? ''),
            material_name: String(it.material_name ?? ''),
            material_spec: it.material_spec != null ? String(it.material_spec) : undefined,
            material_unit: String(it.material_unit ?? ''),
            aux_quantity: it.aux_quantity != null ? Number(it.aux_quantity) : undefined,
            aux_unit: it.aux_unit != null ? String(it.aux_unit) : undefined,
            unit_conversion_rate:
              it.unit_conversion_rate != null ? Number(it.unit_conversion_rate) : undefined,
            receipt_quantity: qty,
            unit_price: storedLine.unit_price,
            display_unit_price: storedLine.display_unit_price,
            total_amount: poiId ? receiptAmounts.excl : storedLine.excl,
            tax_rate: taxPct,
            qualified_quantity: Math.max(qty - unqualified, 0),
            unqualified_quantity: unqualified,
            quality_status: String(it.quality_status || '合格'),
            status: String(it.line_status || '待入库'),
            serial_numbers: serials,
            warehouse_id: lineWhId > 0 ? lineWhId : null,
            warehouse_name: lineWhId > 0 ? String(it.warehouse_name ?? '').trim() || undefined : null,
            location_id:
              it.location_id != null && Number(it.location_id) > 0
                ? Number(it.location_id)
                : undefined,
            location_code:
              it.location_code != null && String(it.location_code).trim()
                ? String(it.location_code).trim()
                : undefined,
            batch_number: String(it.batch_number ?? '').trim() || undefined,
            attachments: normalizeDocumentAttachments(it.attachments as any),
          };
        }),
    };
    try {
      if (editingId) {
        await warehouseApi.purchaseReceipt.update(String(editingId), payload);
        messageApi.success(t('common.updateSuccess'));
      } else if (fromPoCompose && poCompose) {
        await warehouseApi.purchaseReceipt.create({ ...payload, status: '草稿' });
        messageApi.success(t('common.createSuccess'));
      } else {
        await warehouseApi.purchaseReceipt.create(payload);
        messageApi.success(t('common.createSuccess'));
      }
      onClose();
      onSuccess?.();
    } catch (error: unknown) {
      const err = error as { message?: string };
      if (err?.message !== t('app.kuaizhizao.warehouseInbound.msg.needValidPurchaseLine')) {
        messageApi.error(err?.message || t('common.createFailed'));
      }
      throw error;
    }
  };

  return (
    <FormModalTemplate
      title={
        editingId
          ? t('app.kuaizhizao.warehouseInbound.editPurchaseReceiptModal')
          : poCompose
            ? t('app.kuaizhizao.warehouseInbound.composePurchaseReceiptModal')
            : t('app.kuaizhizao.warehouseInbound.createPurchaseReceiptModal')
      }
      open={open}
      onClose={onClose}
      formRef={formRef}
      onFinish={handleFinish}
      width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
      grid={false}
      initialValues={{
        receipt_time: dayjs(),
        items: [{ ...defaultLineItem }],
        price_type: DEFAULT_PURCHASE_PRICE_TYPE,
        tax_rate: 13,
        currency: 'CNY',
      }}
    >
      <ProFormText name="price_type" hidden />
      <Row gutter={16}>
        <Col span={6}>
          <ProFormItem
            name="order_type"
            label={t('app.kuaizhizao.purchaseReceipt.field.orderType')}
            initialValue="标准采购"
            rules={[
              {
                required: true,
                message: t('app.kuaizhizao.purchaseReceipt.orderTypeRequired'),
              },
            ]}
          >
            <UniDropdown
              options={orderTypeOptions}
              loading={orderTypeLoading}
              disabled={linkedPoId != null && linkedPoId > 0}
              placeholder={t('app.kuaizhizao.purchaseOrder.form.orderTypePlaceholder')}
              getPopupContainer={getPopupContainerInModal}
            />
          </ProFormItem>
        </Col>
        <Col span={6}>
          <ProFormItem
            name="supplier_id"
            label={t('app.kuaizhizao.warehouseInbound.field.supplier')}
            rules={[
              { required: true, message: t('app.kuaizhizao.warehouseInbound.selectSupplierRequired') },
            ]}
          >
            <SupplierSelectDropdown
              hostResource={INBOUND_HOST_RESOURCE}
              style={{ width: '100%' }}
              allowClear
              placeholder={t('app.kuaizhizao.warehouseInbound.selectSupplierRequired')}
              onSupplierPick={(supplier) => {
                if (!supplier) {
                  formRef.current?.setFieldsValue({ supplier_id: undefined, supplier_name: '' });
                  applySupplierLedgerRecognition(formRef, null, orgPayableDefault);
                  return;
                }
                applySupplierLedgerRecognition(
                  formRef,
                  supplier as Record<string, unknown>,
                  orgPayableDefault,
                );
                formRef.current?.setFieldsValue({
                  supplier_id: supplier.id,
                  supplier_name: supplier.name ?? '',
                });
                const sid = Number(supplier.id);
                const lineItems = normalizeFormListItems<Record<string, unknown>>(
                  formRef.current?.getFieldValue('items'),
                );
                lineItems.forEach((_, idx) => {
                  void repriceUnlockedPurchaseDocumentLineIfNeeded(formRef.current, idx, {
                    asOfField: 'receipt_time',
                    supplierId: Number.isFinite(sid) && sid > 0 ? sid : undefined,
                  });
                });
              }}
              onChange={(val) => {
                if (val == null || val === '') {
                  formRef.current?.setFieldsValue({ supplier_id: undefined, supplier_name: '' });
                }
              }}
            />
          </ProFormItem>
          <ProFormText name="supplier_name" hidden />
        </Col>
        <Col span={6}>
          <ProFormItem
            name="payable_recognition"
            label={t('field.document.ledgerRecognition')}
            initialValue={orgPayableDefault}
            rules={[{ required: true, message: t('field.document.ledgerRecognitionRequired') }]}
          >
            <UniDropdown options={payableLedgerRecognitionOptions} style={{ width: '100%' }} />
          </ProFormItem>
        </Col>
        <Col span={6}>
          <UserPickField
            name="buyer_id"
            nameField="buyer_name"
            label={t('app.kuaizhizao.warehouseInbound.field.buyer')}
            placeholder={t('app.kuaizhizao.warehouseInbound.field.buyerPlaceholder')}
            userList={users}
            loading={usersLoading}
          />
          <ProFormText name="buyer_operator_number" hidden />
        </Col>
        <Col span={6}>
          <PurchaseDepartmentFormField
            options={departmentOptions}
            loading={departmentOptionsLoading}
          />
        </Col>
        <Col span={6}>
          <UserPickField
            name="receiver_id"
            nameField="receiver_name"
            label={t('app.kuaizhizao.warehouseInbound.field.acceptor')}
            placeholder={t('app.kuaizhizao.warehouseInbound.field.acceptorPlaceholder')}
            required
            userList={users}
            loading={usersLoading}
          />
        </Col>
        <Col span={6}>
          <ProFormDatePicker
            name="receipt_time"
            label={t('app.kuaizhizao.warehouseInbound.field.receiptDate')}
            fieldProps={{
              style: { width: '100%' },
              onChange: () => {
                const lineItems = normalizeFormListItems<Record<string, unknown>>(
                  formRef.current?.getFieldValue('items'),
                );
                const supplierId = Number(formRef.current?.getFieldValue('supplier_id'));
                lineItems.forEach((_, idx) => {
                  void repriceUnlockedPurchaseDocumentLineIfNeeded(formRef.current, idx, {
                    asOfField: 'receipt_time',
                    supplierId: Number.isFinite(supplierId) && supplierId > 0 ? supplierId : undefined,
                  });
                });
              },
            }}
          />
        </Col>
        <Col span={6}>
          <ProFormText
            name="delivery_note"
            label={t('app.kuaizhizao.warehouseInbound.field.deliveryNote')}
            placeholder={t('app.kuaizhizao.warehouseInbound.field.deliveryNotePlaceholder')}
          />
        </Col>
        <Col span={6}>
          <ProFormItem
            name="pay_mode"
            label={t('app.kuaizhizao.warehouseInbound.field.payMode')}
          >
            <UniDropdown options={payModeOptions} style={{ width: '100%' }} />
          </ProFormItem>
        </Col>
        <Col span={6}>
          <ProFormItem
            name="tax_rate"
            label={t('app.kuaizhizao.warehouseInbound.field.taxRate')}
            rules={[{ required: true, message: t('app.kuaizhizao.warehouseInbound.field.taxRateRequired') }]}
          >
            <TaxRatePercentInput />
          </ProFormItem>
        </Col>
        <Col span={6}>
          <ProFormText
            name="currency"
            label={t('app.kuaizhizao.warehouseInbound.field.currency')}
            initialValue="CNY"
            rules={[{ required: true, message: t('app.kuaizhizao.warehouseInbound.field.currencyRequired') }]}
          />
        </Col>
      </Row>

      <DocumentDetailTableStyles />
      <AntForm.Item
        noStyle
        shouldUpdate={(prev, curr) => prev?.price_type !== curr?.price_type}
      >
        {({ getFieldValue }) => {
          const priceType = purchaseFormPriceType(
            poSettlementCtx?.priceType ?? getFieldValue('price_type'),
          );
          const showTaxColumns = priceType === 'tax_inclusive';
          return (
            <UniTableDetail
              name="items"
              title={t('app.kuaizhizao.warehouseInbound.createLinesTitle')}
              required
              requiredMessage={t('app.kuaizhizao.warehouseInbound.msg.needValidPurchaseLine')}
              leftExtra={(
                <PriceTypeSwitch
                  disabled={!!poSettlementCtx?.priceType}
                  checked={priceType === 'tax_inclusive'}
                  checkedChildren={t('app.kuaizhizao.purchaseOrder.form.taxIncl')}
                  unCheckedChildren={t('app.kuaizhizao.purchaseOrder.form.taxExcl')}
                  onChange={handlePurchaseReceiptPriceTypeChange}
                />
              )}
              headerExtra={(
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
              )}
              columns={buildFormItemColumns(showTaxColumns)}
              disabledAdd
              initialValue={{ ...defaultLineItem }}
              tableProps={DOCUMENT_DETAIL_TABLE_PROPS}
            />
          );
        }}
      </AntForm.Item>

      <AntForm.Item
        noStyle
        shouldUpdate={(prev, curr) => prev?.items !== curr?.items}
      >
        {({ getFieldValue }) => (
          <DocumentAmountSummary
            variant="purchase"
            getFieldValue={getFieldValue}
            quantityField="receipt_quantity"
            priceType={
              poSettlementCtx?.priceType ??
              String(getFieldValue('price_type') ?? 'tax_inclusive')
            }
            goodsTotalsFn={(formItems) =>
              computePurchaseReceiptFormGoodsTotals(
                formItems,
                getFieldValue('tax_rate'),
                poSettlementCtx?.priceType ??
                  String(getFieldValue('price_type') ?? 'tax_inclusive'),
                poSettlementCtx,
              )
            }
            style={{ marginBottom: 16 }}
          />
        )}
      </AntForm.Item>

      <Row gutter={16}>
        <Col span={24}>
          <ProFormTextArea
            name="notes"
            label={t('common.remark')}
            placeholder={t('app.kuaizhizao.warehouseInbound.field.inboundRemarksPlaceholder')}
            fieldProps={{ rows: 3 }}
          />
        </Col>
      </Row>
    </FormModalTemplate>  );
};

export default PurchaseReceiptCreateModal;
