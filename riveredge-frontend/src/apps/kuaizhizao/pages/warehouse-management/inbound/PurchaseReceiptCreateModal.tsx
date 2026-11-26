/**
 * 采购入库新建/编辑独立页（UniTab DocumentFormPageLayout）。
 * 表头：供应商、采购员、验收人、付款方式、币别等；税率在明细行。
 * 金蝶 billtype_number 仅走仓储业务配置 / 接口样例，不进本表单。
 * 采购员工号由选人自动写入 buyer_operator_number（隐藏字段），不再单独填写。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { App, Button, Col, Form as AntForm, Input, InputNumber, Row, Select, Space, Spin, Tooltip, Typography } from 'antd';
import {
  ProForm,
  ProFormDatePicker,
  ProFormDependency,
  ProFormItem,
  ProFormText,
  ProFormTextArea,
  type ProFormInstance,
} from '@ant-design/pro-components';
import { ArrowLeftOutlined, PlusOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import dayjs from 'dayjs';
import {
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  DetailDrawerSection,
  DocumentFormPageHeaderActions,
  DocumentFormPageLayout,
} from '../../../../../components/layout-templates';
import { useLeaveFormTab } from '../../../../../components/uni-tabs/navigateClosingTab';
import { setCustomPageTitle, removeCustomPageTitle } from '../../../../../utils/customPageTitle';
import { useSubmitShortcut } from '../../../../../hooks/useSubmitShortcut';
import { useDocumentFormCommitAndSubmitReview } from '../../../../../hooks/useDocumentFormCommitAndSubmitReview';
import { purchaseReceiptEditPath, resolveInboundListPath } from './inboundPaths';
import { UniTableDetail } from '../../../../../components/uni-table-detail';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import {
  mapAttachmentsToUploadList,
  normalizeDocumentAttachments,
} from '../../../utils/documentAttachments';
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
  resolveDocumentLineMaterialModel,
  resolveDocumentLineMaterialSpec,
  getOutstandingPoItems,
  normalizePurchaseOrderDetail,
  resolvePurchaseOrderPaymentForReceipt,
  resolvePurchaseReceiptLineWarehouse,
} from './inboundPoReceiptEntryUtils';
import { resolvePrimaryDefaultWarehouseFromMaterial } from '../../../../master-data/utils/materialDefaultWarehouse';
import type { PurchaseReceiptPoComposePayload } from './inboundPullEntryTypes';
import { buildDocumentLineDualQuantityPairColumns } from '../../../../../components/quantity-with-unit';
import {
  documentLineDualQuantityForPush,
  validateDualQuantityBeforeSave,
} from '../../../../../utils/materialDualQuantity';
import {
  fetchMaterialForUnitSelectCache,
  prefetchMaterialsForUnitSelect,
} from '../../../../../components/material-unit-select';
import {
  materialApi,
  materialBatchApi,
  materialSerialApi,
  MATERIAL_SERIAL_GENERATE_MAX_COUNT,
} from '../../../../master-data/services/material';
import { SerialNumbersImportTrigger } from '../../../../../components/serial-numbers-import';
import type { Material } from '../../../../master-data/types/material';
import {
  applyPurchaseDocumentLineMaterialPricing,
  repriceUnlockedPurchaseDocumentLineIfNeeded,
} from '../../../../master-data/utils/resolve-partner-material-price';
import {
  normalizeFormListItems,
  resolveFormListFieldForSubmit,
} from '../../../../../utils/formListItems';
import {
  applyMaterialTrackingToFormRow,
  readMaterialTrackingFromPicker,
} from './inboundItemTracking';
import { useQuery } from '@tanstack/react-query';
import { getBusinessConfig } from '../../../../../services/businessConfig';
import {
  applySupplierLedgerRecognition,
  resolveOrgPayableDefaultFromBusinessConfig,
  resolveSupplierFormFieldValues,
} from '../../purchase-management/shared/applySupplierFormFields';
import {
  partnerPaymentMethodSelectOptions,
} from '../../../../master-data/utils/partner-static-labels';
import { isPartnerEmployeeAdvancePaymentMethod } from '../../../../master-data/utils/paymentMethodMix';
import { resolvePartnerAdvancePayeeName } from '../../../components/PartnerPaymentAdvancePayeeField';
import { PaymentMethodWithMixFormItems } from '../../../components/PaymentMethodWithMixFormItems';
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
  formatUserDisplayLabel,
  normalizeUserDisplayName,
} from '../../../../../utils/userDisplay';
import { getPopupContainerInModal } from '../../../../../utils/modalEventIsolation';
import {
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import PriceTypeSwitch, { type PriceTypeValue } from '../../../../../components/price-type-switch/PriceTypeSwitch';
import {
  deferConvertLineItemsByPriceType,
} from '../../../../../utils/priceTypeSwitch';
import {
  DEFAULT_PURCHASE_PRICE_TYPE,
  normalizePurchasePriceType,
  purchaseFormPriceType,
} from '../../purchase-management/shared/purchasePriceType';

const shouldUpdatePurchaseReceiptAmounts = (
  prev: Record<string, unknown> | undefined,
  curr: Record<string, unknown> | undefined,
) => prev?.items !== curr?.items || prev?.price_type !== curr?.price_type;

function resolvePurchaseReceiptFormPriceType(
  poCtx: PurchaseReceiptPoSettlementCtx | null,
  formPriceType: unknown,
): PriceTypeValue {
  return purchaseFormPriceType(poCtx?.priceType ?? formPriceType);
}

function mapPurchaseReceiptDetailLineToForm(
  line: Record<string, unknown>,
  headerTax: unknown,
  headerPriceType: unknown,
): Record<string, unknown> {
  const lineTaxPct = resolveReceiptLineTaxPercent(line.tax_rate, headerTax);
  const pt = normalizePurchasePriceType(headerPriceType);
  const formUnit = readPurchaseReceiptFormUnitPrice(line);
  const displayRaw = line.display_unit_price ?? line.displayUnitPrice;
  const hasStoredDisplay =
    displayRaw != null && displayRaw !== '' && Number(displayRaw) > 0;
  const serials = Array.isArray(line.serial_numbers)
    ? line.serial_numbers.map((item) => String(item))
    : [];
  const receiptQty = Number(line.receipt_quantity) || 0;
  return {
    material_id: positiveId(line.material_id) ?? undefined,
    material_code: String(line.material_code ?? ''),
    material_name: String(line.material_name ?? ''),
    material_spec: resolveDocumentLineMaterialSpec(line),
    material_model: resolveDocumentLineMaterialModel(line),
    material_unit: String(line.material_unit ?? line.unit ?? ''),
    receipt_quantity: receiptQty,
    tax_rate: lineTaxPct,
    unit_price: formUnit,
    display_unit_price: hasStoredDisplay
      ? Number(displayRaw)
      : pt === 'tax_inclusive' && formUnit > 0
        ? formUnit
        : undefined,
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
    serial_numbers: serials.length ? serials : undefined,
    unqualified_quantity: Number(line.unqualified_quantity) || 0,
    quality_status: String(line.quality_status || '合格'),
    line_status: String(line.status ?? line.line_status ?? '待入库'),
    attachments: line.attachments,
  };
}

const INBOUND_HOST_RESOURCE = 'kuaizhizao:inbound';

const PURCHASE_RECEIPT_ORDER_TYPE_FALLBACK: Pick<DictionaryItem, 'value' | 'label' | 'is_system_managed' | 'sort_order'>[] = [
  { value: '标准采购', label: '标准采购', is_system_managed: true, sort_order: 0 },
  { value: '资产采购', label: '资产采购', is_system_managed: true, sort_order: 1 },
  { value: '服务采购', label: '服务采购', is_system_managed: true, sort_order: 2 },
];

const defaultLineItem = {
  receipt_quantity: 1,
  unit_price: 0,
  tax_rate: 13,
  warehouse_id: undefined as number | undefined,
  warehouse_name: undefined as string | undefined,
  location_id: undefined as number | undefined,
  location_code: undefined as string | undefined,
  batch_number: undefined as string | undefined,
  batch_managed: false,
  serial_managed: false,
  serial_numbers: undefined as string[] | undefined,
  material_uuid: undefined as string | undefined,
  batch_rule_id: undefined as number | undefined,
  default_batch_rule_id: undefined as number | undefined,
  aux_quantity: undefined,
  aux_unit: undefined,
  unit_conversion_rate: undefined,
};

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
function normalizeReceiptPayModeForForm(raw: unknown): string | undefined {
  const s = String(raw ?? '').trim();
  if (!s) return undefined;
  const upper = s.toUpperCase();
  if (upper === 'CASH') return 'cash';
  if (upper === 'CREDIT') return 'CREDIT';
  return s;
}

export type PurchaseReceiptCreateModalProps = Record<string, never>;

function positiveId(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function purchaseReceiptFormPriceType(taxRatePercent: number): 'tax_inclusive' | 'tax_exclusive' {
  return taxRatePercent > 0 ? 'tax_inclusive' : 'tax_exclusive';
}

function resolveReceiptLineTaxPercent(
  lineTax: unknown,
  headerTax: unknown,
  fallback = 13,
): number {
  if (lineTax != null && lineTax !== '' && Number.isFinite(Number(lineTax))) {
    return purchaseOrderTaxRateToPercent(lineTax);
  }
  if (headerTax != null && headerTax !== '' && Number.isFinite(Number(headerTax))) {
    return purchaseOrderTaxRateToPercent(headerTax);
  }
  return fallback;
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
  operatorNumberField,
}: {
  name: string;
  nameField: string;
  label: string;
  placeholder: string;
  required?: boolean;
  userList: User[];
  loading: boolean;
  operatorNumberField?: string;
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
          onChange={(val, opt: { label?: React.ReactNode } | undefined) => {
            const patch: Record<string, unknown> = {
              [nameField]: typeof opt?.label === 'string' ? opt.label : undefined,
            };
            if (operatorNumberField) {
              const uid = val != null && val !== '' && Number.isFinite(Number(val)) ? Number(val) : NaN;
              const picked = Number.isFinite(uid) ? userList.find((u) => Number(u.id) === uid) : undefined;
              // 换人必须同步工号；无工号则清空，禁止沿用上一任隐藏字段
              patch[operatorNumberField] = picked?.employee_number?.trim() || undefined;
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

export const PurchaseReceiptCreateModal: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi, modal: modalApi } = App.useApp();
  const location = useLocation();
  const navigate = useNavigate();
  const params = useParams<{ id?: string }>();
  const listPath = resolveInboundListPath(location.pathname);
  const leaveFormPage = useLeaveFormTab(listPath);

  const { runAfterPersist: runPurchaseReceiptSaveAndAudit, initiatorModal: purchaseReceiptInitiatorModal } =
    useDocumentFormCommitAndSubmitReview({
      entityType: 'purchase_receipt',
      entityLabel: t('app.kuaizhizao.warehouseInbound.purchaseReceiptEntity'),
      commit: (id) => warehouseApi.purchaseReceipt.commit(id),
    });
  const isCreatePage = /\/inbound\/new$/.test(location.pathname);
  const editRouteId = (() => {
    const fromParams = Number(params.id);
    if (Number.isFinite(fromParams) && fromParams > 0) return fromParams;
    const m = location.pathname.match(/\/inbound\/(\d+)\/edit$/);
    return m ? Number(m[1]) : null;
  })();
  const editingId =
    !isCreatePage && editRouteId != null && Number.isFinite(editRouteId) && editRouteId > 0
      ? editRouteId
      : null;
  const copySourceId = (() => {
    if (!isCreatePage) return null;
    const raw = new URLSearchParams(location.search).get('copyFrom');
    const n = Number(raw);
    return Number.isFinite(n) && n > 0 ? n : null;
  })();
  const poCompose =
    isCreatePage && location.state && typeof location.state === 'object'
      ? ((location.state as { purchaseReceiptPoCompose?: PurchaseReceiptPoComposePayload })
          .purchaseReceiptPoCompose ?? null)
      : null;
  const formRef = useRef<ProFormInstance>();
  const commitAfterSaveRef = useRef(false);
  const [documentStatus, setDocumentStatus] = useState('待入库');
  const [reviewStatus, setReviewStatus] = useState('草稿');
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
  const [generatingSerialIdx, setGeneratingSerialIdx] = useState<number | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [formLoading, setFormLoading] = useState(false);
  const [linkedPoId, setLinkedPoId] = useState<number | null>(null);
  const [poSettlementCtx, setPoSettlementCtx] = useState<PurchaseReceiptPoSettlementCtx | null>(
    null,
  );
  /** 仅编辑历史「赊购 CREDIT」时追加选项，新建不再提供赊购 */
  const [includeLegacyCreditOption, setIncludeLegacyCreditOption] = useState(false);
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
        formRef.current?.setFieldsValue({ price_type: priceType });
      } catch {
        if (!cancelled) setPoSettlementCtx(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [linkedPoId]);

  const sourceLinkRef = useRef<{ purchase_order_id: number | null; purchase_order_code: string }>({
    purchase_order_id: null,
    purchase_order_code: '',
  });
  const leaveFormPageRef = useRef(leaveFormPage);
  leaveFormPageRef.current = leaveFormPage;
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
    setIncludeLegacyCreditOption(false);
    formRef.current?.resetFields();
    formRef.current?.setFieldsValue({
      items: [{ ...defaultLineItem }],
      receipt_time: dayjs(),
      pay_mode: undefined,
      price_type: 'tax_inclusive',
      currency: 'CNY',
      buyer_id: defaultPerson.id,
      buyer_name: defaultPerson.name,
      receiver_id: defaultPerson.id,
      receiver_name: defaultPerson.name,
      payable_recognition: orgPayableDefault,
    });
  }, [defaultPerson, orgPayableDefault]);

  useEffect(() => {
    if (editingId) return;
    const rid = formRef.current?.getFieldValue('receiver_id');
    if (rid != null && rid !== '') return;
    if (defaultPerson.id == null && !defaultPerson.name) return;
    formRef.current?.setFieldsValue({
      receiver_id: defaultPerson.id,
      receiver_name: defaultPerson.name,
    });
  }, [editingId, defaultPerson]);

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
        formRef.current.setFieldValue(['items', index, 'serial_managed'], false);
        formRef.current.setFieldValue(['items', index, 'material_uuid'], undefined);
        formRef.current.setFieldValue(['items', index, 'serial_numbers'], undefined);
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
          /* 使用列表/选择器字段 */
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
      formRef.current.setFieldValue(
        ['items', index, 'material_spec'],
        String(material.specification ?? '').trim() || undefined,
      );
      formRef.current.setFieldValue(
        ['items', index, 'material_model'],
        String(material.model ?? '').trim() || undefined,
      );
      const existingWh = Number(formRef.current.getFieldValue(['items', index, 'warehouse_id']));
      if (!(existingWh > 0)) {
        let matForWh: Material | undefined = material;
        const mid = Number(material.id);
        if (mid > 0 && !resolvePrimaryDefaultWarehouseFromMaterial(material)) {
          try {
            const full = await fetchMaterialForUnitSelectCache(mid);
            if (full) matForWh = full;
          } catch {
            /* 列表快照无 defaults 时尝试完整档案 */
          }
        }
        const primaryWh = resolvePrimaryDefaultWarehouseFromMaterial(matForWh);
        if (primaryWh) {
          formRef.current.setFieldValue(['items', index, 'warehouse_id'], primaryWh.id);
          formRef.current.setFieldValue(['items', index, 'warehouse_name'], primaryWh.name);
        }
      }
    },
    [trackingFlags],
  );

  useEffect(() => {
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
          const orderIds = (
            poCompose.purchaseOrderIds?.length
              ? [...poCompose.purchaseOrderIds]
              : [poCompose.purchaseOrderId]
          )
            .map((id) => Number(id))
            .filter((id) => id > 0);
          const ordersNormalized = await Promise.all(
            orderIds.map(async (oid) =>
              normalizePurchaseOrderDetail(await getPurchaseOrder(String(oid))),
            ),
          );
          if (cancelled || !ordersNormalized.length) return;

          const primary = ordersNormalized[0];
          const materialIdSet = new Set<number>();
          for (const order of ordersNormalized) {
            for (const it of order.items || []) {
              const mid = Number(it.material_id);
              if (mid > 0) materialIdSet.add(mid);
            }
          }
          const materialById = await prefetchMaterialsForUnitSelect([...materialIdSet]);
          if (cancelled) return;

          type ComposeLine = { order: (typeof ordersNormalized)[0]; item: NonNullable<(typeof ordersNormalized)[0]['items']>[0] };
          const composeLines: ComposeLine[] = [];
          for (const order of ordersNormalized) {
            const orderWithMaterials = {
              ...order,
              items: enrichPurchaseOrderItemsMaterial(order.items || [], materialById),
            };
            const outstanding = getOutstandingPoItems(orderWithMaterials);
            for (const it of outstanding) {
              if (it.id != null && (poCompose.quantities[it.id] ?? 0) > 0) {
                composeLines.push({ order: orderWithMaterials, item: it });
              }
            }
          }

          const poCodes = ordersNormalized
            .map((o) => String(o.order_code ?? '').trim())
            .filter(Boolean);
          // 备注可展示多单号；头字段 purchase_order_code 仅存主单号（max 50，与后端/下推一致）
          const poCodeLabel = poCodes.join('、');
          const primaryPoCode = String(primary.order_code ?? '').trim();
          sourceLinkRef.current = {
            purchase_order_id: poCompose.purchaseOrderId,
            purchase_order_code: primaryPoCode,
          };
          if (orderIds.length > 1) {
            setLinkedPoId(null);
          } else {
            setLinkedPoId(poCompose.purchaseOrderId);
          }
          const headerTaxPct = purchaseOrderTaxRateToPercent(primary.tax_rate ?? 13);
          const formItems: typeof defaultLineItem[] = [];
          for (const { order: orderWithMaterials, item: it } of composeLines) {
            const lineId = it.id!;
            const serialList = poCompose.lineSerials[lineId] ?? [];
            const orderHeaderTax = purchaseOrderTaxRateToPercent(orderWithMaterials.tax_rate ?? 13);
            const lineTaxPct = resolveReceiptLineTaxPercent(
              (it as { tax_rate?: number }).tax_rate,
              orderHeaderTax,
            );
            const pushQty = Number(poCompose.quantities[lineId]) || 0;
            const poPriceType = (() => {
              const raw = String(
                (orderWithMaterials as { price_type?: string; priceType?: string }).price_type ??
                  (orderWithMaterials as { priceType?: string }).priceType ??
                  '',
              ).trim();
              return raw === 'tax_inclusive' || raw === 'tax_exclusive'
                ? raw
                : purchaseReceiptFormPriceType(orderHeaderTax);
            })();
            // 分批第二次取单：副数量以取单 remaining_aux 为准，禁止仅按整单 ordered 比例重算
            const handoffAuxRaw = poCompose.auxQuantities?.[lineId];
            const dualFromOrdered = documentLineDualQuantityForPush(
              it as unknown as Record<string, unknown>,
              {
                sourcePrimaryQty: Number(it.ordered_quantity) || 0,
                pushPrimaryQty: pushQty,
              },
            );
            const dual =
              handoffAuxRaw != null && Number.isFinite(Number(handoffAuxRaw))
                ? {
                    ...dualFromOrdered,
                    aux_quantity: Number(handoffAuxRaw),
                  }
                : dualFromOrdered;
            let material = it.material_id
              ? materialById.get(String(it.material_id))
              : undefined;
            if (
              material &&
              !resolvePrimaryDefaultWarehouseFromMaterial(material) &&
              !(Number(poCompose.lineWh[lineId]) > 0) &&
              !(Number((it as { warehouse_id?: number }).warehouse_id) > 0)
            ) {
              try {
                const full = await fetchMaterialForUnitSelectCache(Number(it.material_id));
                if (full) material = full;
              } catch {
                /* ignore */
              }
            }
            const headerWh = Number(
              (orderWithMaterials as { warehouse_id?: number }).warehouse_id ?? 0,
            );
            const lineWh = resolvePurchaseReceiptLineWarehouse(it, material, {
              explicitWarehouseId: poCompose.lineWh[lineId],
              headerWarehouseId: headerWh > 0 ? headerWh : undefined,
            });
            formItems.push({
              purchase_order_item_id: lineId,
              material_id: it.material_id,
              material_code: String(it.material_code ?? ''),
              material_name: String(it.material_name ?? ''),
              material_spec: resolveDocumentLineMaterialSpec(
                it as unknown as Record<string, unknown>,
                material,
              ),
              material_model: resolveDocumentLineMaterialModel(
                it as unknown as Record<string, unknown>,
                material,
              ),
              material_unit: String(it.material_unit ?? ''),
              receipt_quantity: pushQty,
              tax_rate: lineTaxPct,
              unit_price: readPurchaseOrderEnteredUnitPrice(it, poPriceType) ?? undefined,
              warehouse_id: lineWh.warehouse_id,
              warehouse_name: String(lineWh.warehouse_name ?? it.warehouse_name ?? ''),
              location_id: poCompose.lineLoc[lineId],
              location_code: poCompose.lineLocCode[lineId] ?? '',
              batch_number: poCompose.batchNumbers[lineId],
              aux_quantity: dual.aux_quantity,
              aux_unit: dual.aux_unit,
              unit_conversion_rate: dual.unit_conversion_rate,
              serial_numbers_json: serialList.length ? JSON.stringify(serialList) : '',
              unqualified_quantity: 0,
              quality_status: '合格',
              line_status: '待入库',
            });
          }
          const notesText =
            String(poCompose.notes ?? '').trim() ||
            (poCodeLabel
              ? t('app.kuaizhizao.warehouseInbound.poCompose.defaultNotes', { code: poCodeLabel })
              : '');
          const poPayment = resolvePurchaseOrderPaymentForReceipt(primary);
          const poPayMode = normalizeReceiptPayModeForForm(
            poPayment.pay_mode ?? primary.payment_method_code,
          );
          const poPayableRecognition = String(
            primary.payable_recognition ??
              (primary as { payableRecognition?: string }).payableRecognition ??
              orgPayableDefault,
          );
          setIncludeLegacyCreditOption(poPayMode === 'CREDIT');
          if (orderIds.length > 1) {
            const poiById: PurchaseReceiptPoSettlementCtx['poiById'] = {};
            for (const { item } of composeLines) {
              const poiId = Number(item.id);
              if (poiId > 0) {
                poiById[poiId] = item as PurchaseReceiptPoSettlementCtx['poiById'][number];
              }
            }
            const primaryPriceType = (() => {
              const raw = String(
                (primary as { price_type?: string; priceType?: string }).price_type ??
                  (primary as { priceType?: string }).priceType ??
                  '',
              ).trim();
              return raw === 'tax_inclusive' || raw === 'tax_exclusive'
                ? raw
                : purchaseReceiptFormPriceType(headerTaxPct);
            })();
            setPoSettlementCtx({
              priceType: primaryPriceType,
              headerTaxRate: primary.tax_rate,
              poiById,
            });
          }
          formRef.current?.setFieldsValue({
            order_type: String(primary.order_type ?? '标准采购').trim() || '标准采购',
            supplier_id: positiveId(primary.supplier_id) ?? undefined,
            supplier_name: String(primary.supplier_name ?? ''),
            payable_recognition: poPayableRecognition,
            buyer_id: positiveId(primary.buyer_id) ?? undefined,
            buyer_name: String(primary.buyer_name ?? ''),
            department_id: positiveId(primary.department_id) ?? undefined,
            department_name: String(primary.department_name ?? ''),
            receiver_id: poCompose.receiverId ?? defaultPerson.id,
            receiver_name: String(poCompose.receiverName ?? '').trim() || defaultPerson.name,
            receipt_time: poCompose.receiptTimeIso ? dayjs(poCompose.receiptTimeIso) : dayjs(),
            delivery_note: poCompose.deliveryNote ?? '',
            pay_mode: poPayMode,
            payment_wire_percent: poPayment.payment_wire_percent,
            payment_acceptance_percent: poPayment.payment_acceptance_percent,
            advance_payee_id: poPayment.advance_payee_id,
            advance_payee_name: poPayment.advance_payee_name,
            price_type: purchaseReceiptFormPriceType(headerTaxPct),
            currency: String(primary.currency ?? 'CNY').trim() || 'CNY',
            notes: notesText,
            attachments: [],
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
          leaveFormPageRef.current();
        } finally {
          if (!cancelled) setFormLoading(false);
        }
      })();
      return () => {
        cancelled = true;
      };
    }

    if (!editingId && copySourceId) {
      setFormLoading(true);
      void (async () => {
        try {
          const detail = (await warehouseApi.purchaseReceipt.get(String(copySourceId))) as Record<
            string,
            unknown
          >;
          if (cancelled) return;
          sourceLinkRef.current = { purchase_order_id: null, purchase_order_code: '' };
          setLinkedPoId(null);
          setDocumentStatus('待入库');
          setReviewStatus('草稿');
          const rawItems = Array.isArray(detail.items) ? detail.items : [];
          const headerPriceType = normalizePurchasePriceType(
            (detail as { price_type?: string }).price_type
              ?? (detail as { priceType?: string }).priceType,
          );
          const items = rawItems.length
            ? rawItems.map((row) => ({
                ...mapPurchaseReceiptDetailLineToForm(
                  row as Record<string, unknown>,
                  detail.tax_rate,
                  headerPriceType,
                ),
                line_status: '待入库',
              }))
            : [{ ...defaultLineItem }];
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
            receiver_id: positiveId(detail.receiver_id) ?? defaultPerson.id,
            receiver_name: String(detail.receiver_name ?? '').trim() || defaultPerson.name,
            receipt_time: dayjs(),
            delivery_note: String(detail.delivery_note ?? ''),
            pay_mode: formPayMode,
            advance_payee_id: (detail as { advance_payee_id?: number }).advance_payee_id ?? undefined,
            advance_payee_name: (detail as { advance_payee_name?: string }).advance_payee_name ?? undefined,
            price_type: headerPriceType,
            currency: String(detail.currency ?? 'CNY'),
            notes: String(detail.notes ?? ''),
            attachments: mapAttachmentsToUploadList(
              (detail as { attachments?: Parameters<typeof mapAttachmentsToUploadList>[0] }).attachments,
            ),
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
          leaveFormPageRef.current();
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
      setDocumentStatus('待入库');
      setReviewStatus('草稿');
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
        setDocumentStatus(String(detail.status || '待入库'));
        setReviewStatus(String(detail.review_status || '草稿'));
        const poId = positiveId(detail.purchase_order_id);
        sourceLinkRef.current = {
          purchase_order_id: poId,
          purchase_order_code: String(detail.purchase_order_code ?? '').trim(),
        };
        setLinkedPoId(poId);
        const rawItems = Array.isArray(detail.items) ? detail.items : [];
        const headerPriceType = normalizePurchasePriceType(
          (detail as { price_type?: string }).price_type
            ?? (detail as { priceType?: string }).priceType,
        );
        const items = rawItems.length
          ? rawItems.map((row) =>
              mapPurchaseReceiptDetailLineToForm(
                row as Record<string, unknown>,
                detail.tax_rate,
                headerPriceType,
              ),
            )
          : [{ ...defaultLineItem }];
        const receiptTimeRaw = detail.receipt_time;
        let formPayMode = normalizeReceiptPayModeForForm(detail.pay_mode);
        let paymentFromPo: ReturnType<typeof resolvePurchaseOrderPaymentForReceipt> = {};
        if (!formPayMode && poId) {
          try {
            const poRaw = await getPurchaseOrder(String(poId));
            const po = normalizePurchaseOrderDetail(poRaw);
            paymentFromPo = resolvePurchaseOrderPaymentForReceipt(po);
            formPayMode = normalizeReceiptPayModeForForm(paymentFromPo.pay_mode);
          } catch {
            /* 关联订单付款方式补全失败不挡编辑 */
          }
        }
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
          receiver_id: positiveId(detail.receiver_id) ?? defaultPerson.id,
          receiver_name: String(detail.receiver_name ?? '').trim() || defaultPerson.name,
          receipt_time: receiptTimeRaw ? dayjs(String(receiptTimeRaw)) : dayjs(),
          delivery_note: String(detail.delivery_note ?? ''),
          pay_mode: formPayMode,
          payment_wire_percent:
            (detail as { payment_wire_percent?: number }).payment_wire_percent ??
            paymentFromPo.payment_wire_percent,
          payment_acceptance_percent:
            (detail as { payment_acceptance_percent?: number }).payment_acceptance_percent ??
            paymentFromPo.payment_acceptance_percent,
          advance_payee_id:
            (detail as { advance_payee_id?: number }).advance_payee_id ??
            paymentFromPo.advance_payee_id,
          advance_payee_name:
            (detail as { advance_payee_name?: string }).advance_payee_name ??
            paymentFromPo.advance_payee_name,
          price_type: headerPriceType,
          currency: String(detail.currency ?? 'CNY'),
          notes: String(detail.notes ?? ''),
          attachments: mapAttachmentsToUploadList(
            (detail as { attachments?: Parameters<typeof mapAttachmentsToUploadList>[0] }).attachments,
          ),
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
        leaveFormPageRef.current();
      } finally {
        if (!cancelled) setFormLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [
    copySourceId,
    defaultPerson,
    editingId,
    messageApi,
    orgPayableDefault,
    poCompose,
    priceDecimals,
    resetForm,
    syncLineMaterialTracking,
    t,
  ]);

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
            <AntForm.Item name={[index, 'purchase_order_item_id']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'receipt_notice_item_id']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'serial_numbers_json']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'serial_managed']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'unqualified_quantity']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'quality_status']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'line_status']} hidden>
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
                const primaryWh = resolvePrimaryDefaultWarehouseFromMaterial(mat);
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
      ...buildDocumentLineDualQuantityPairColumns({
        t,
        getForm: () => formRef.current,
        quantityField: 'receipt_quantity',
        unitField: 'material_unit',
        scenario: 'purchase',
        quantityPrecision: quantityDecimals,
        width: 168,
        columnSpread: DOCUMENT_DETAIL_NUM_COL,
        onAfterQuantityChange: (index) => {
          const supplierId = Number(formRef.current?.getFieldValue('supplier_id'));
          void repriceUnlockedPurchaseDocumentLineIfNeeded(formRef.current, index, {
            asOfField: 'receipt_time',
            unitPriceField: 'unit_price',
            trigger: 'quantity',
            supplierId: Number.isFinite(supplierId) && supplierId > 0 ? supplierId : undefined,
          });
        },
      }),
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
        title: t('app.kuaizhizao.warehouseInbound.col.serialNo'),
        dataIndex: 'serial_numbers',
        width: 160,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <>
            <AntForm.Item name={[index, 'serial_numbers']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item
              noStyle
              shouldUpdate={(prev, curr) => prev?.items?.[index] !== curr?.items?.[index]}
            >
              {({ getFieldValue }) => {
                const row = getFieldValue('items')?.[index];
                if (!isMaterialSerialEntryEnabled(trackingFlags, row?.serial_managed)) {
                  return <span>—</span>;
                }
                const qty = Number(row?.receipt_quantity ?? 0);
                const expected = qty > 0 ? Math.floor(qty) : 0;
                const sn = getFieldValue(['items', index, 'serial_numbers']);
                const serials = Array.isArray(sn)
                  ? sn.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
                  : parseSerialNumbers(sn) ?? [];
                return (
                  <SerialNumbersImportTrigger
                    serials={serials}
                    expectedCount={expected > 0 ? expected : undefined}
                    materialLabel={row?.material_code || row?.material_name}
                    generateLoading={generatingSerialIdx === index}
                    onSerialsChange={(next) =>
                      formRef.current?.setFieldValue(['items', index, 'serial_numbers'], next)
                    }
                    onGenerate={async () => {
                      const uuid = getFieldValue(['items', index, 'material_uuid']);
                      if (!uuid || !(expected > 0)) return [];
                      const count = Math.min(expected, MATERIAL_SERIAL_GENERATE_MAX_COUNT);
                      setGeneratingSerialIdx(index);
                      try {
                        const res = await materialSerialApi.generate(String(uuid), count, {});
                        formRef.current?.setFieldValue(
                          ['items', index, 'serial_numbers'],
                          res.serial_nos,
                        );
                        messageApi.success(
                          t('app.kuaizhizao.warehouseInbound.msg.serialGenerated', {
                            count: res.count,
                          }),
                        );
                        return res.serial_nos;
                      } catch (e: unknown) {
                        messageApi.error(
                          (e as Error)?.message ||
                            t('app.kuaizhizao.warehouseInbound.msg.serialGenerateFailed'),
                        );
                        return [];
                      } finally {
                        setGeneratingSerialIdx(null);
                      }
                    }}
                  />
                );
              }}
            </AntForm.Item>
          </>
        ),
      },
      {
        title: showTaxColumns
          ? t('app.kuaizhizao.purchaseOrder.col.taxUnitPrice')
          : t('app.kuaizhizao.purchaseOrder.col.unitPrice'),
        dataIndex: 'unit_price',
        width: DOCUMENT_DETAIL_COL_WIDTH.unitPrice + 28,
        ...DOCUMENT_DETAIL_NUM_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item name={[index, 'unit_price']} noStyle>
            <InputNumber
              size={DOCUMENT_DETAIL_CONTROL_SIZE}
              style={{ width: '100%' }}
              min={0}
              precision={priceDecimals}
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
                <AntForm.Item noStyle shouldUpdate={shouldUpdatePurchaseReceiptAmounts}>
                  {({ getFieldValue }) => {
                    const row = normalizeFormListItems<Record<string, unknown>>(
                      getFieldValue('items'),
                    )[index];
                    const taxPct = purchaseOrderTaxRateToPercent(row?.tax_rate ?? 13);
                    const priceType = resolvePurchaseReceiptFormPriceType(
                      poSettlementCtx,
                      getFieldValue('price_type'),
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
                <AntForm.Item noStyle shouldUpdate={shouldUpdatePurchaseReceiptAmounts}>
                  {({ getFieldValue }) => {
                    const row = normalizeFormListItems<Record<string, unknown>>(
                      getFieldValue('items'),
                    )[index];
                    const taxPct = purchaseOrderTaxRateToPercent(row?.tax_rate ?? 13);
                    const priceType = resolvePurchaseReceiptFormPriceType(
                      poSettlementCtx,
                      getFieldValue('price_type'),
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
                <AntForm.Item noStyle shouldUpdate={shouldUpdatePurchaseReceiptAmounts}>
                  {({ getFieldValue }) => {
                    const row = normalizeFormListItems<Record<string, unknown>>(
                      getFieldValue('items'),
                    )[index];
                    const taxPct = purchaseOrderTaxRateToPercent(row?.tax_rate ?? 13);
                    const priceType = resolvePurchaseReceiptFormPriceType(
                      poSettlementCtx,
                      getFieldValue('price_type'),
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
                <AntForm.Item noStyle shouldUpdate={shouldUpdatePurchaseReceiptAmounts}>
                  {({ getFieldValue }) => {
                    const row = normalizeFormListItems<Record<string, unknown>>(
                      getFieldValue('items'),
                    )[index];
                    const taxPct = purchaseOrderTaxRateToPercent(row?.tax_rate ?? 13);
                    const priceType = resolvePurchaseReceiptFormPriceType(
                      poSettlementCtx,
                      getFieldValue('price_type'),
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
      clearLineWarehouseDependents,
      generatingBatchIdx,
      generatingSerialIdx,
      handleGenerateBatch,
      messageApi,
      quantityDecimals,
      priceDecimals,
      amountDecimals,
      poSettlementCtx,
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
    const itemsRaw = resolveFormListFieldForSubmit(formRef, values, 'items');
    const items = normalizeFormListItems<Record<string, unknown>>(itemsRaw);
    const validItems = items.filter(
      (it) => it.material_id && (Number(it.receipt_quantity) || 0) > 0,
    );
    if (!validItems.length) {
      const msg = t('app.kuaizhizao.warehouseInbound.msg.needValidPurchaseLine');
      messageApi.error(msg);
      throw new Error(msg);
    }
    const zeroTaxLines = validItems.filter((item) => {
      const raw = item.tax_rate;
      return raw != null && raw !== '' && Number(raw) === 0;
    });
    if (zeroTaxLines.length > 0) {
      const confirmed = await new Promise<boolean>((resolve) => {
        modalApi.confirm({
          title: t('app.kuaizhizao.warehouseInbound.confirmZeroTaxRateTitle'),
          content: t('app.kuaizhizao.warehouseInbound.confirmZeroTaxRateContent', {
            count: zeroTaxLines.length,
          }),
          okText: t('app.kuaizhizao.warehouseInbound.confirmZeroTaxRateOk'),
          cancelText: t('app.kuaizhizao.warehouseInbound.confirmZeroTaxRateCancel'),
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
        });
      });
      if (!confirmed) return;
    }

    const supplierId = Number(values.supplier_id) || 0;
    if (supplierId <= 0) {
      const msg = t('app.kuaizhizao.warehouseInbound.selectSupplierRequired');
      messageApi.error(msg);
      throw new Error(msg);
    }

    await prefetchMaterialsForUnitSelect(
      validItems.map((it) => Number(it.material_id) || 0),
    );

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
      if (
        !servicePurchase &&
        isMaterialBatchEntryEnabled(trackingFlags, Boolean(it.batch_managed)) &&
        !String(it.batch_number ?? '').trim()
      ) {
        const msg = t('app.kuaizhizao.warehouseOutbound.confirm.batchRequired', {
          material: materialLabel,
          batches: '—',
        });
        messageApi.error(msg);
        throw new Error(msg);
      }
      const material = await fetchMaterialForUnitSelectCache(Number(it.material_id));
      const serialManaged =
        it.serial_managed != null
          ? !!it.serial_managed
          : !!(material as Material | null)?.serialManaged;
      if (!servicePurchase && isMaterialSerialEntryEnabled(trackingFlags, serialManaged)) {
        const serials = Array.isArray(it.serial_numbers)
          ? it.serial_numbers.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
          : parseSerialNumbers(it.serial_numbers_json) ?? [];
        const qty = Math.floor(Number(it.receipt_quantity) || 0);
        if (serials.length !== qty) {
          const msg = t('app.kuaizhizao.warehouseOutbound.entry.serialCountMismatch', {
            material: materialLabel,
            required: qty,
            actual: serials.length,
          });
          messageApi.error(msg);
          throw new Error(msg);
        }
      }
      const dualErr = validateDualQuantityBeforeSave({
        material: material as Material | null,
        scenario: 'purchase',
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
        const msg = `${materialLabel}：${dualErr}`;
        messageApi.error(msg);
        throw new Error(msg);
      }
    }

    const headerWhId = Number(validItems[0]?.warehouse_id) || 0;
    const headerWhName = String(validItems[0]?.warehouse_name ?? '').trim();

    const fromPoCompose = !editingId && poCompose?.purchaseOrderId;
    const linkedPoId = fromPoCompose
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
        purchase_order_id: linkedPoId,
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
        advance_payee_id: (() => {
          const mode = String(values.pay_mode ?? '').trim();
          if (!isPartnerEmployeeAdvancePaymentMethod(mode)) return undefined;
          const id = Number(values.advance_payee_id);
          if (!Number.isFinite(id) || id <= 0) {
            const msg = t('app.kuaicaiwu.payment.advancePayeeRequired');
            messageApi.error(msg);
            throw new Error(msg);
          }
          return id;
        })(),
        advance_payee_name: (() => {
          const mode = String(values.pay_mode ?? '').trim();
          if (!isPartnerEmployeeAdvancePaymentMethod(mode)) return undefined;
          const id = Number(values.advance_payee_id);
          const name =
            resolvePartnerAdvancePayeeName(
              id,
              users.map((u) => ({
                label: String(u.full_name || u.username || '').trim(),
                value: u.id,
              })),
            ) || String(values.advance_payee_name ?? '').trim();
          if (!name) {
            const msg = t('app.kuaicaiwu.payment.advancePayeeRequired');
            messageApi.error(msg);
            throw new Error(msg);
          }
          return name;
        })(),
        tax_rate: (() => {
          const first = validItems[0];
          const pct = purchaseOrderTaxRateToPercent(first?.tax_rate ?? 13);
          return pct;
        })(),
        currency: String(values.currency ?? 'CNY').trim() || 'CNY',
        receiver_id: values.receiver_id != null ? Number(values.receiver_id) : undefined,
        receiver_name: String(values.receiver_name ?? '').trim() || undefined,
        warehouse_id: headerWhId > 0 ? headerWhId : null,
        warehouse_name: headerWhId > 0 ? headerWhName || null : null,
        receipt_time: toApiBusinessDocumentDateTime(values.receipt_time),
        delivery_note: String(values.delivery_note ?? '').trim() || undefined,
        notes: String(values.notes ?? '').trim() || undefined,
        attachments: normalizeDocumentAttachments(
          values.attachments as Parameters<typeof normalizeDocumentAttachments>[0],
        ),
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
              display_unit_price:
                it.display_unit_price != null && Number(it.display_unit_price) > 0
                  ? Number(it.display_unit_price)
                  : priceType === 'tax_inclusive' && price > 0
                    ? price
                    : undefined,
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
          const serials = Array.isArray(it.serial_numbers)
            ? it.serial_numbers.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
            : parseSerialNumbers(it.serial_numbers_json);
          return {
            purchase_order_item_id: positiveId(it.purchase_order_item_id),
            receipt_notice_item_id: positiveId(it.receipt_notice_item_id),
            material_id: Number(it.material_id),
            material_code: String(it.material_code ?? ''),
            material_name: String(it.material_name ?? ''),
            material_spec: it.material_spec != null ? String(it.material_spec) : undefined,
            material_model: it.material_model != null ? String(it.material_model).trim() || undefined : undefined,
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
    const shouldCommit = commitAfterSaveRef.current;
    commitAfterSaveRef.current = false;
    try {
      let savedId = editingId;
      if (editingId) {
        await warehouseApi.purchaseReceipt.update(String(editingId), payload);
        if (!shouldCommit) messageApi.success(t('common.updateSuccess'));
      } else if (fromPoCompose && poCompose) {
        const created = (await warehouseApi.purchaseReceipt.create({ ...payload, status: '草稿' })) as {
          id?: number;
        };
        savedId = created?.id ?? null;
        if (!shouldCommit) messageApi.success(t('common.createSuccess'));
      } else {
        const created = (await warehouseApi.purchaseReceipt.create(payload)) as { id?: number };
        savedId = created?.id ?? null;
        if (!shouldCommit) messageApi.success(t('common.createSuccess'));
      }
      if (shouldCommit) {
        if (savedId == null) {
          messageApi.error(t('common.operationFailed'));
          return;
        }
        try {
          const { completed } = await runPurchaseReceiptSaveAndAudit(savedId);
          if (!completed) {
            if (!editingId && savedId != null) {
              navigate(purchaseReceiptEditPath(savedId, listPath), { replace: true });
            }
            return;
          }
        } catch (error: unknown) {
          if (!editingId && savedId != null) {
            navigate(purchaseReceiptEditPath(savedId, listPath), { replace: true });
          }
          const err = error as { message?: string };
          messageApi.error(err?.message || t('common.operationFailed'));
          return;
        }
      }
      leaveFormPage();
    } catch (error: unknown) {
      const err = error as { message?: string };
      if (err?.message !== t('app.kuaizhizao.warehouseInbound.msg.needValidPurchaseLine')) {
        messageApi.error(
          err?.message || (editingId ? t('common.updateFailed') : t('common.createFailed')),
        );
      }
      throw error;
    }
  };

  const purchaseReceiptFormCanCommit = (() => {
    const status = documentStatus.trim();
    const review = reviewStatus.trim();
    const editableBusiness = ['', '草稿', 'draft', 'DRAFT', '待入库'].includes(status);
    const editableReview = ['', '草稿', 'draft', 'DRAFT', '已驳回', '审核驳回', 'rejected'].includes(review);
    return editableBusiness && editableReview;
  })();

  const pageTitle = editingId
    ? t('app.kuaizhizao.warehouseInbound.editPurchaseReceiptModal')
    : poCompose
      ? t('app.kuaizhizao.warehouseInbound.composePurchaseReceiptModal')
      : t('app.kuaizhizao.warehouseInbound.createPurchaseReceiptModal');

  useEffect(() => {
    const sp = new URLSearchParams(location.search || '');
    sp.delete('_refresh');
    const cleanSearch = sp.toString();
    const tabKey = location.pathname + (cleanSearch ? `?${cleanSearch}` : '');
    setCustomPageTitle(location.pathname, pageTitle);
    setCustomPageTitle(tabKey, pageTitle);
    window.dispatchEvent(
      new CustomEvent('riveredge:update-tab-title', {
        detail: { key: tabKey, path: location.pathname, title: pageTitle },
      }),
    );
    return () => {
      removeCustomPageTitle(location.pathname);
      removeCustomPageTitle(tabKey);
    };
  }, [location.pathname, location.search, pageTitle]);

  const triggerSave = useCallback(() => {
    commitAfterSaveRef.current = false;
    void formRef.current?.submit?.();
  }, []);

  const triggerCommit = useCallback(() => {
    commitAfterSaveRef.current = true;
    void formRef.current?.submit?.();
  }, []);

  useSubmitShortcut(() => {
    if (purchaseReceiptFormCanCommit) triggerSave();
  }, true);

  return (
    <>
    <DocumentFormPageLayout
      header={
        <>
          <Space align="center" size={8}>
            <Button
              type="text"
              icon={<ArrowLeftOutlined />}
              aria-label={t('common.back')}
              onClick={() => {
                commitAfterSaveRef.current = false;
                leaveFormPage();
              }}
            />
            <Typography.Title level={4} style={DOCUMENT_DETAIL_PAGE_TITLE_STYLE}>
              {pageTitle}
            </Typography.Title>
          </Space>
          <DocumentFormPageHeaderActions
            onCancel={() => {
              commitAfterSaveRef.current = false;
              leaveFormPage();
            }}
            onSaveDraft={triggerSave}
            onPrimarySubmit={triggerSave}
            isCreatePage={isCreatePage}
            canSubmitAfterSave={purchaseReceiptFormCanCommit}
            showSaveDraft={purchaseReceiptFormCanCommit}
            showCommitSubmit={purchaseReceiptFormCanCommit}
            onCommitSubmit={triggerCommit}
            primaryLoading={formLoading}
            saveDraftLoading={formLoading}
            commitSubmitLoading={formLoading}
          />
        </>
      }
    >
      <Spin spinning={formLoading}>
        <ProForm
          key={
            isCreatePage
              ? `purchase-receipt-create:${location.search}:${poCompose?.purchaseOrderId ?? ''}`
              : `purchase-receipt-edit:${editingId ?? ''}`
          }
          formRef={formRef}
          layout="vertical"
          submitter={false}
          scrollToFirstError
          onFinish={handleFinish}
          onFinishFailed={({ errorFields }) => {
            const first = errorFields?.[0];
            const errText = first?.errors?.filter(Boolean)[0];
            messageApi.error(errText || t('components.layoutTemplates.formModal.checkFormHint'));
          }}
          initialValues={{
            order_type: '标准采购',
            receipt_time: dayjs(),
            items: [{ ...defaultLineItem }],
            pay_mode: undefined,
            currency: 'CNY',
            buyer_id: defaultPerson.id,
            buyer_name: defaultPerson.name,
            receiver_id: defaultPerson.id,
            receiver_name: defaultPerson.name,
            price_type: DEFAULT_PURCHASE_PRICE_TYPE,
          }}
        >
      <ProFormText name="price_type" hidden />
      <DetailDrawerSection titleAccent title={t('app.uniDetail.sectionBasic')}>
        <div className="document-form-untitled-groups">
          <div className="document-form-untitled-group">
      {/* 一行 5 格：对齐采购订单；行1 身份/往来/人员/日期，行2 结算/组织/验收 */}
      <Row gutter={16} wrap={false}>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormItem
            name="order_type"
            label={t('app.kuaizhizao.purchaseReceipt.field.orderType')}
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
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
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
                  formRef.current?.setFieldsValue({
                    supplier_id: undefined,
                    supplier_name: '',
                    pay_mode: undefined,
                  });
                  applySupplierLedgerRecognition(formRef, null, orgPayableDefault);
                  setIncludeLegacyCreditOption(false);
                  return;
                }
                applySupplierLedgerRecognition(
                  formRef,
                  supplier as Record<string, unknown>,
                  orgPayableDefault,
                );
                const resolved = resolveSupplierFormFieldValues(
                  supplier as Record<string, unknown>,
                  [],
                  orgPayableDefault,
                );
                setIncludeLegacyCreditOption(false);
                const linkedPo =
                  linkedPoId != null && linkedPoId > 0
                    ? linkedPoId
                    : sourceLinkRef.current.purchase_order_id;
                const inheritPayFromPo =
                  Boolean(poCompose?.purchaseOrderId) ||
                  (linkedPo != null && Number(linkedPo) > 0);
                formRef.current?.setFieldsValue({
                  supplier_id: supplier.id,
                  supplier_name: supplier.name ?? '',
                  ...(inheritPayFromPo
                    ? {}
                    : {
                        pay_mode: resolved.payment_method_code,
                        ...(resolved.currency != null ? { currency: resolved.currency } : {}),
                      }),
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
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <UserPickField
            name="buyer_id"
            nameField="buyer_name"
            label={t('app.kuaizhizao.warehouseInbound.field.buyer')}
            placeholder={t('app.kuaizhizao.warehouseInbound.field.buyerPlaceholder')}
            userList={users}
            loading={usersLoading}
            operatorNumberField="buyer_operator_number"
          />
          <ProFormText name="buyer_operator_number" hidden />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormDatePicker
            name="receipt_time"
            label={t('app.kuaizhizao.warehouseInbound.field.receiptDate')}
            rules={[{ required: true, message: t('app.kuaizhizao.warehouseInbound.field.receiptDateRequired') }]}
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
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormText
            name="delivery_note"
            label={t('app.kuaizhizao.warehouseInbound.field.deliveryNote')}
            placeholder={t('app.kuaizhizao.warehouseInbound.field.deliveryNotePlaceholder')}
          />
        </Col>
      </Row>
      <Row gutter={16} wrap={false}>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormItem
            name="payable_recognition"
            label={t('field.document.ledgerRecognition')}
            initialValue={orgPayableDefault}
            rules={[{ required: true, message: t('field.document.ledgerRecognitionRequired') }]}
          >
            <UniDropdown options={payableLedgerRecognitionOptions} style={{ width: '100%' }} />
          </ProFormItem>
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <PaymentMethodWithMixFormItems
            formRef={formRef}
            options={payModeOptions}
            methodLabel={t('app.kuaizhizao.warehouseInbound.field.payMode')}
            methodPlaceholder={t('app.kuaizhizao.purchaseOrder.selectPaymentMethod')}
            methodField="pay_mode"
          />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormText
            name="currency"
            label={t('app.kuaizhizao.warehouseInbound.field.currency')}
            initialValue="CNY"
            rules={[{ required: true, message: t('app.kuaizhizao.warehouseInbound.field.currencyRequired') }]}
          />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <PurchaseDepartmentFormField
            options={departmentOptions}
            loading={departmentOptionsLoading}
          />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
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
      </Row>
          </div>
        </div>
      </DetailDrawerSection>

      <DetailDrawerSection titleAccent title={t('app.uniDetail.sectionLines')}>
        <AntForm.Item
          noStyle
          shouldUpdate={(prev, curr) => prev?.price_type !== curr?.price_type}
        >
          {({ getFieldValue }) => {
            const priceType = resolvePurchaseReceiptFormPriceType(
              poSettlementCtx,
              getFieldValue('price_type'),
            );
            const showTaxColumns = priceType === 'tax_inclusive';
            return (
              <>
                <DocumentDetailTableStyles />
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
              </>
            );
          }}
        </AntForm.Item>

        <AntForm.Item
          noStyle
          shouldUpdate={shouldUpdatePurchaseReceiptAmounts}
        >
          {({ getFieldValue }) => (
            <DocumentAmountSummary
              variant="purchase"
              getFieldValue={getFieldValue}
              quantityField="receipt_quantity"
              priceType={resolvePurchaseReceiptFormPriceType(
                poSettlementCtx,
                getFieldValue('price_type'),
              )}
              goodsTotalsFn={(formItems) =>
                computePurchaseReceiptFormGoodsTotals(
                  formItems,
                  getFieldValue('tax_rate'),
                  resolvePurchaseReceiptFormPriceType(
                    poSettlementCtx,
                    getFieldValue('price_type'),
                  ),
                  poSettlementCtx,
                )
              }
              style={{ marginBottom: 16 }}
            />
          )}
        </AntForm.Item>

        <ProFormTextArea
          name="notes"
          label={t('common.remark')}
          placeholder={t('app.kuaizhizao.warehouseInbound.field.inboundRemarksPlaceholder')}
          fieldProps={{ rows: 3 }}
        />
      </DetailDrawerSection>

      <DetailDrawerSection titleAccent title={t('app.uniDetail.sectionAttachments')} marginBottom={0}>
        <DocumentAttachmentsField
          category="purchase_receipt_attachments"
          label={false}
        />
      </DetailDrawerSection>
        </ProForm>
      </Spin>
    </DocumentFormPageLayout>
    {purchaseReceiptInitiatorModal}
    </>
  );
};

export default PurchaseReceiptCreateModal;
