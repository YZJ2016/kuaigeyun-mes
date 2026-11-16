/**
 * 销售出库空白建单（无来源销售订单/发货通知）。
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
  Select,
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
import { useQuery } from '@tanstack/react-query';
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
  buildDocumentDetailSpecModelFormColumns,
  withMaterialLineFillMapping,
} from '../../sales-management/shared/materialLineFormDetail';
import { resolveMaterialScenarioUnit } from '../../../../../utils/materialScenarioUnit';
import { DocumentLineDualQuantityFormCell } from '../../../../../components/quantity-with-unit/documentLineDualQuantityColumn';
import { validateDualQuantityBeforeSave } from '../../../../../utils/materialDualQuantity';
import { fetchMaterialForUnitSelectCache } from '../../../../../components/material-unit-select';
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
  isMaterialBatchEntryEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import {
  loadBatchOptionsByMaterialId,
  type InventoryPickOption,
} from './outboundConfirmInventoryOptions';
import SplitByWarehouseModal, {
  type SplitByWarehouseAllocation,
} from './SplitByWarehouseModal';

const OUTBOUND_HOST_RESOURCE = 'kuaizhizao:outbound';

const defaultLineItem = {
  delivery_quantity: 1,
  unit_price: 0,
  warehouse_id: undefined as number | undefined,
  warehouse_name: undefined as string | undefined,
  location_id: undefined as number | undefined,
  location_code: undefined as string | undefined,
  batch_number: undefined as string | undefined,
  batch_managed: false,
  aux_quantity: undefined,
  aux_unit: undefined,
  unit_conversion_rate: undefined,
};

function batchOptionsCacheKey(materialId: number, warehouseId: number): string {
  return `${materialId}:${warehouseId}`;
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
  ensureBatchOptions: (materialId: number, warehouseId: number) => Promise<void>;
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
              if (mid > 0 && isMaterialBatchEntryEnabled(trackingFlags, batchManaged)) {
                void ensureBatchOptions(mid, whId);
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
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>();
  const currentUser = useCurrentUser();
  const quantityDecimals = useNumericPrecisionPlaces('quantity');
  const trackingFlags = useWarehouseTrackingFlags();
  const [users, setUsers] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [batchOptionsByKey, setBatchOptionsByKey] = useState<Record<string, InventoryPickOption[]>>(
    {},
  );
  const [batchOptionsLoadingKey, setBatchOptionsLoadingKey] = useState<string | null>(null);
  const [splitLineIndex, setSplitLineIndex] = useState<number | null>(null);

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

  const ensureBatchOptions = useCallback(
    async (materialId: number, warehouseId: number) => {
      const mid = Number(materialId);
      const whId = Number(warehouseId);
      if (!(mid > 0) || !(whId > 0)) return;
      const key = batchOptionsCacheKey(mid, whId);
      setBatchOptionsLoadingKey(key);
      try {
        const map = await loadBatchOptionsByMaterialId([mid], whId, batchOptionLabel);
        setBatchOptionsByKey((prev) => {
          if (prev[key]) return prev;
          return { ...prev, [key]: map[mid] ?? [] };
        });
      } finally {
        setBatchOptionsLoadingKey((cur) => (cur === key ? null : cur));
      }
    },
    [batchOptionLabel],
  );

  const clearLineWarehouseDependents = useCallback((index: number) => {
    formRef.current?.setFieldValue(['items', index, 'location_id'], undefined);
    formRef.current?.setFieldValue(['items', index, 'location_code'], '');
    formRef.current?.setFieldValue(['items', index, 'batch_number'], undefined);
  }, []);

  const resetForm = useCallback(() => {
    formRef.current?.resetFields();
    formRef.current?.setFieldsValue({
      items: [{ ...defaultLineItem }],
      delivery_time: dayjs(),
      currency_code: 'CNY',
      exchange_rate: 1,
      deliverer_id: defaultPerson.id,
      deliverer_name: defaultPerson.name,
      revenue_recognition: orgRevenueRecognitionDefault,
    });
    setBatchOptionsByKey({});
    setBatchOptionsLoadingKey(null);
    setSplitLineIndex(null);
  }, [defaultPerson, orgRevenueRecognitionDefault]);

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
    return () => {
      cancelled = true;
    };
  }, [open, resetForm]);

  const formItemColumns = useMemo(
    () => [
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
                const primaryWh = resolvePrimaryDefaultWarehouse(mat);
                if (primaryWh) {
                  formRef.current?.setFieldValue(['items', index, 'warehouse_id'], primaryWh.id);
                  formRef.current?.setFieldValue(['items', index, 'warehouse_name'], primaryWh.name);
                  if (isMaterialBatchEntryEnabled(trackingFlags, !!mat.batchManaged)) {
                    void ensureBatchOptions(Number(mat.id), primaryWh.id);
                  }
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
      {
        title: t('common.quantity'),
        dataIndex: 'delivery_quantity',
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
                  quantityField="delivery_quantity"
                  unitField="material_unit"
                  scenario="sales"
                  quantityPrecision={quantityDecimals}
                  materialId={materialId}
                  inlineUnitWithQuantity
                  onAfterQuantityChange={() => {
                    void repriceUnlockedSalesDocumentLineIfNeeded(formRef.current, index, {
                      asOfField: 'delivery_time',
                    });
                  }}
                />
              );
            }}
          </AntForm.Item>
        ),
      },
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
        dataIndex: 'batch_number',
        width: 180,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item
            noStyle
            shouldUpdate={(prev, curr) =>
              prev?.items?.[index]?.material_id !== curr?.items?.[index]?.material_id ||
              prev?.items?.[index]?.warehouse_id !== curr?.items?.[index]?.warehouse_id ||
              prev?.items?.[index]?.batch_managed !== curr?.items?.[index]?.batch_managed ||
              prev?.items?.[index]?.batch_number !== curr?.items?.[index]?.batch_number
            }
          >
            {({ getFieldValue }) => {
              const materialId = Number(getFieldValue(['items', index, 'material_id']) || 0);
              const whId = Number(getFieldValue(['items', index, 'warehouse_id']) || 0);
              const batchManaged = !!getFieldValue(['items', index, 'batch_managed']);
              if (!isMaterialBatchEntryEnabled(trackingFlags, batchManaged)) {
                return <span>—</span>;
              }
              const key =
                materialId > 0 && whId > 0 ? batchOptionsCacheKey(materialId, whId) : '';
              const opts = key ? batchOptionsByKey[key] ?? [] : [];
              const loading = !!key && batchOptionsLoadingKey === key;
              return (
                <AntForm.Item name={[index, 'batch_number']} noStyle>
                  <Select
                    size={DOCUMENT_DETAIL_CONTROL_SIZE}
                    style={{ width: '100%' }}
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    options={opts}
                    loading={loading}
                    disabled={!(whId > 0) || !(materialId > 0)}
                    placeholder={
                      whId > 0
                        ? t('app.kuaizhizao.warehouseCommon.selectBatchPlaceholder')
                        : t('app.kuaizhizao.warehouseOutbound.field.selectWarehouseFirst')
                    }
                    getPopupContainer={getPopupContainerInModal}
                    onOpenChange={(openSel) => {
                      if (openSel && materialId > 0 && whId > 0 && !batchOptionsByKey[key]?.length) {
                        void ensureBatchOptions(materialId, whId);
                      }
                    }}
                  />
                </AntForm.Item>
              );
            }}
          </AntForm.Item>
        ),
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.splitByWarehouse.actionCol'),
        width: 96,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item
            noStyle
            shouldUpdate={(prev, curr) =>
              prev?.items?.[index]?.material_id !== curr?.items?.[index]?.material_id ||
              prev?.items?.[index]?.delivery_quantity !== curr?.items?.[index]?.delivery_quantity
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
                  title={t('app.kuaizhizao.warehouseOutbound.splitByWarehouse.disabledHint')}
                >
                  <span>{btn}</span>
                </Tooltip>
              );
            }}
          </AntForm.Item>
        ),
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.field.unitPrice'),
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
      buildDocumentLineAttachmentsFormColumn(
        t,
        DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY.salesDelivery,
      ),
    ],
    [
      batchOptionsByKey,
      batchOptionsLoadingKey,
      clearLineWarehouseDependents,
      ensureBatchOptions,
      quantityDecimals,
      t,
      trackingFlags,
    ],
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

  const handleFinish = async (values: Record<string, unknown>) => {
    const items = (values.items as Record<string, unknown>[]) ?? [];
    const validItems = items.filter(
      (it) => it.material_id && (Number(it.delivery_quantity) || 0) > 0,
    );
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
      if (
        isMaterialBatchEntryEnabled(trackingFlags, batchManaged) &&
        !String(it.batch_number ?? '').trim()
      ) {
        throw new Error(
          `${materialLabel}：${t('app.kuaizhizao.warehouseCommon.batchRequiredOutbound')}`,
        );
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

    try {
      await warehouseApi.salesDelivery.create({
        sales_order_id: null,
        sales_order_code: '',
        customer_id: customerId,
        customer_name: String(values.customer_name ?? '').trim(),
        revenue_recognition: values.revenue_recognition,
        // 表头仓仅列表汇总：取首行；真源在明细行
        warehouse_id: headerWhId,
        warehouse_name: headerWhName,
        delivery_time:
          values.delivery_time &&
          typeof (values.delivery_time as { format?: unknown }).format === 'function'
            ? toApiBusinessDocumentDateTime(values.delivery_time as dayjs.Dayjs)
            : undefined,
        deliverer_id: values.deliverer_id != null ? Number(values.deliverer_id) : undefined,
        deliverer_name: String(values.deliverer_name ?? '').trim() || undefined,
        currency_code: String(values.currency_code ?? 'CNY').trim() || 'CNY',
        exchange_rate: values.exchange_rate != null ? Number(values.exchange_rate) : 1,
        notes: String(values.notes ?? '').trim() || undefined,
        items: validItems.map((it) => {
          const qty = Number(it.delivery_quantity) || 0;
          const price = Number(it.unit_price) || 0;
          const lineWhId = Number(it.warehouse_id) || 0;
          return {
            sales_order_item_id: null,
            material_id: Number(it.material_id),
            material_code: String(it.material_code ?? ''),
            material_name: String(it.material_name ?? ''),
            material_spec: it.material_spec != null ? String(it.material_spec) : undefined,
            material_unit: String(it.material_unit ?? ''),
            aux_quantity: it.aux_quantity != null ? Number(it.aux_quantity) : undefined,
            aux_unit: it.aux_unit != null ? String(it.aux_unit) : undefined,
            unit_conversion_rate:
              it.unit_conversion_rate != null ? Number(it.unit_conversion_rate) : undefined,
            delivery_quantity: qty,
            unit_price: price,
            total_amount: Number((qty * price).toFixed(2)),
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
            batch_number: String(it.batch_number ?? '').trim() || undefined,
            attachments: normalizeDocumentAttachments(it.attachments as any),
          };
        }),
      });
      messageApi.success(t('common.createSuccess'));
      onClose();
      onSuccess?.();
    } catch (error: unknown) {
      const err = error as { message?: string };
      if (err?.message !== t(needValidLineKey)) {
        messageApi.error(err?.message || t('common.createFailed'));
      }
      throw error;
    }
  };

  return (
    <>
    <FormModalTemplate
      title={t('app.kuaizhizao.warehouseOutbound.createSalesDeliveryModal')}
      open={open}
      onClose={onClose}
      formRef={formRef}
      onFinish={handleFinish}
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
        <Col span={12}>
          <UserPickField
            name="deliverer_id"
            nameField="deliverer_name"
            label={t('app.kuaizhizao.warehouseOutbound.field.operator')}
            placeholder={t('app.kuaizhizao.warehouseOutbound.field.operator')}
            userList={users}
            loading={usersLoading}
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

      <DocumentDetailTableStyles />
      <UniTableDetail
        name="items"
        title={t('app.kuaizhizao.warehouseOutbound.createLinesTitle')}
        required
        requiredMessage={t(needValidLineKey)}
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
        columns={formItemColumns}
        disabledAdd
        initialValue={{ ...defaultLineItem }}
        tableProps={DOCUMENT_DETAIL_TABLE_PROPS}
      />

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
    {splitLineContext ? (
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
