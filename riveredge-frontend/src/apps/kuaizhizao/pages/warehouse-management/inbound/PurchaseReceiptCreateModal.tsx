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
import { DocumentLineDualQuantityFormCell } from '../../../../../components/quantity-with-unit/documentLineDualQuantityColumn';
import { validateDualQuantityBeforeSave } from '../../../../../utils/materialDualQuantity';
import { fetchMaterialForUnitSelectCache } from '../../../../../components/material-unit-select';
import { materialApi, materialBatchApi } from '../../../../master-data/services/material';
import type { Material } from '../../../../master-data/types/material';
import {
  applyPurchaseDocumentLineMaterialPricing,
  repriceUnlockedPurchaseDocumentLineIfNeeded,
} from '../../../../master-data/utils/resolve-partner-material-price';
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

const INBOUND_HOST_RESOURCE = 'kuaizhizao:inbound';

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
            message: t('app.kuaizhizao.warehouseInbound.selectWarehouse'),
          },
        ]}
        noStyle
      >
        <UniWhDropdown
          size={DOCUMENT_DETAIL_CONTROL_SIZE}
          hostResource={INBOUND_HOST_RESOURCE}
          materialId={materialId > 0 ? materialId : undefined}
          showStock={materialId > 0}
          sortByStock={materialId > 0}
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

const PAY_MODE_OPTIONS = [
  { value: 'CREDIT', labelKey: 'app.kuaizhizao.warehouseInbound.payMode.credit' },
  { value: 'CASH', labelKey: 'app.kuaizhizao.warehouseInbound.payMode.cash' },
] as const;

export type PurchaseReceiptCreateModalProps = {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
};

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
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>();
  const currentUser = useCurrentUser();
  const {
    options: departmentOptions,
    loading: departmentOptionsLoading,
    resolveName: resolveDepartmentName,
  } = usePurchaseDepartmentOptions();
  const quantityDecimals = useNumericPrecisionPlaces('quantity');
  const trackingFlags = useWarehouseTrackingFlags();
  const [generatingBatchIdx, setGeneratingBatchIdx] = useState<number | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
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
  const payModeOptions = useMemo(
    () => PAY_MODE_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) })),
    [t],
  );

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
      pay_mode: 'CREDIT',
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
        title: t('app.kuaizhizao.purchaseReturn.unitPrice'),
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
        DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY.purchaseReceipt,
      ),
    ],
    [
      clearLineWarehouseDependents,
      generatingBatchIdx,
      handleGenerateBatch,
      quantityDecimals,
      syncLineMaterialTracking,
      t,
      trackingFlags,
    ],
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

    for (const it of validItems) {
      const materialLabel =
        String(it.material_name || it.material_code || it.material_id || '').trim() || '-';
      const lineWhId = Number(it.warehouse_id) || 0;
      if (!(lineWhId > 0)) {
        const msg = t('app.kuaizhizao.warehouseInbound.msg.selectWarehouseForMaterial', {
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
        const msg = t('app.kuaizhizao.warehouseInbound.msg.selectLocationForMaterial', {
          material: materialLabel,
        });
        messageApi.error(msg);
        throw new Error(msg);
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

    try {
      await warehouseApi.purchaseReceipt.create({
        purchase_order_id: null,
        purchase_order_code: '',
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
        pay_mode: String(values.pay_mode ?? 'CREDIT').trim() || 'CREDIT',
        tax_rate: values.tax_rate != null ? Number(values.tax_rate) : 13,
        currency: String(values.currency ?? 'CNY').trim() || 'CNY',
        receiver_id: values.receiver_id != null ? Number(values.receiver_id) : undefined,
        receiver_name: String(values.receiver_name ?? '').trim() || undefined,
        warehouse_id: headerWhId,
        warehouse_name: headerWhName,
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
          const lineWhId = Number(it.warehouse_id) || 0;
          return {
            purchase_order_item_id: null,
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
            unit_price: price,
            total_amount: Number((qty * price).toFixed(2)),
            qualified_quantity: qty,
            unqualified_quantity: 0,
            quality_status: '合格',
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
      if (err?.message !== t('app.kuaizhizao.warehouseInbound.msg.needValidPurchaseLine')) {
        messageApi.error(err?.message || t('common.createFailed'));
      }
      throw error;
    }
  };

  return (
    <FormModalTemplate
      title={t('app.kuaizhizao.warehouseInbound.createPurchaseReceiptModal')}
      open={open}
      onClose={onClose}
      formRef={formRef}
      onFinish={handleFinish}
      width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
      grid={false}
      initialValues={{
        receipt_time: dayjs(),
        items: [{ ...defaultLineItem }],
        pay_mode: 'CREDIT',
        tax_rate: 13,
        currency: 'CNY',
      }}
    >
      <Row gutter={16}>
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
            initialValue="CREDIT"
            rules={[{ required: true, message: t('app.kuaizhizao.warehouseInbound.field.payModeRequired') }]}
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
            <InputNumber min={0} max={100} precision={2} addonAfter="%" style={{ width: '100%' }} />
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
      <UniTableDetail
        name="items"
        title={t('app.kuaizhizao.warehouseInbound.createLinesTitle')}
        required
        requiredMessage={t('app.kuaizhizao.warehouseInbound.msg.needValidPurchaseLine')}
        headerExtra={(
          <Space size={8}>
            <Button
              type="default"
              icon={<PlusOutlined />}
              onClick={() => {
                const next = [...(formRef.current?.getFieldValue('items') ?? []), { ...defaultLineItem }];
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
            placeholder={t('app.kuaizhizao.warehouseInbound.field.inboundRemarksPlaceholder')}
            fieldProps={{ rows: 3 }}
          />
        </Col>
      </Row>
    </FormModalTemplate>
  );
};

export default PurchaseReceiptCreateModal;
