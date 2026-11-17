/**
 * 成品入库空白建单（无来源生产工单/成品检验）。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { App, Button, Col, Form as AntForm, Input, Row, Space } from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
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
import { validateDualQuantityBeforeSave } from '../../../../../utils/materialDualQuantity';
import {
  fetchMaterialForUnitSelectCache,
  prefetchMaterialsForUnitSelect,
} from '../../../../../components/material-unit-select';
import type { Material } from '../../../../master-data/types/material';
import {
  normalizeFormListItems,
  resolveFormListFieldForSubmit,
} from '../../../../../utils/formListItems';
import {
  applyMaterialTrackingToFormRow,
  readMaterialTrackingFromPicker,
} from './inboundItemTracking';
import {
  filterWarehouseTrackingColumns,
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import {
  materialApi,
  materialBatchApi,
  materialSerialApi,
  MATERIAL_SERIAL_GENERATE_MAX_COUNT,
} from '../../../../master-data/services/material';
import { SerialNumbersImportTrigger } from '../../../../../components/serial-numbers-import';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import type { User } from '../../../../../services/user';
import { searchUserDisplay } from '../../../../../services/user';
import {
  displayItemsToUsers,
  normalizeUserDisplayName,
} from '../../../../../utils/userDisplay';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { CustomFieldsFormSection } from '../../../../../components/custom-fields';

const INBOUND_HOST_RESOURCE = 'kuaizhizao:inbound';
const FINISHED_GOODS_RECEIPT_CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_finished_goods_receipts';
const SEMI_FINISHED_GOODS_RECEIPT_CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_semi_finished_goods_receipts';

const defaultLineItem = {
  receipt_quantity: 1,
  warehouse_id: undefined as number | undefined,
  warehouse_name: undefined as string | undefined,
  location_id: undefined as number | undefined,
  location_code: undefined as string | undefined,
  batch_number: undefined as string | undefined,
  batch_managed: false,
  serial_managed: false,
  serial_numbers: undefined as string[] | undefined,
  aux_quantity: undefined,
  aux_unit: undefined,
  unit_conversion_rate: undefined,
};

export type ProductionReceiptBlankKind = 'finished_goods' | 'semi_finished_goods';

export type FinishedGoodsReceiptCreateModalProps = {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  /** 空白建单类型：成品或半成品（无来源工单） */
  receiptKind?: ProductionReceiptBlankKind;
  /** 有值时编辑已有成品/半成品入库单 */
  receiptId?: number | null;
};

function positiveId(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function UserPickField({
  name,
  nameField,
  label,
  placeholder,
  userList,
  loading,
}: {
  name: string;
  nameField: string;
  label: string;
  placeholder: string;
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

function FinishedGoodsReceiptCreateWarehouseCell({
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

function FinishedGoodsReceiptCreateLocationCell({
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

function resolvePrimaryDefaultWarehouse(material: Material): { id: number; name: string } | null {
  const wh = material.defaultWarehouse ?? material.default_warehouse;
  if (wh && typeof wh === 'object' && 'id' in wh && wh.id) {
    return { id: Number(wh.id), name: String((wh as { name?: string }).name ?? '') };
  }
  return null;
}

export const FinishedGoodsReceiptCreateModal: React.FC<FinishedGoodsReceiptCreateModalProps> = ({
  open,
  onClose,
  onSuccess,
  receiptKind = 'finished_goods',
  receiptId = null,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>();
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const currentUser = useCurrentUser();
  const quantityDecimals = useNumericPrecisionPlaces('quantity');
  const trackingFlags = useWarehouseTrackingFlags();
  const [users, setUsers] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [formLoading, setFormLoading] = useState(false);
  const editingId = open && receiptId != null && Number(receiptId) > 0 ? Number(receiptId) : null;

  const {
    customFields: finishedFormCustomFields,
    customFieldValues: finishedFormCustomFieldValues,
    loadFieldValues: loadFinishedFormFieldValues,
    extractFormValues: extractFinishedFormValues,
    saveCustomFieldValues: saveFinishedCustomFieldValues,
    resetFieldValues: resetFinishedFormFieldValues,
  } = useCustomFields({
    tableName: FINISHED_GOODS_RECEIPT_CUSTOM_FIELD_TABLE,
    loadWhenOpen: true,
    open: open && receiptKind === 'finished_goods',
  });

  const {
    customFields: semiFormCustomFields,
    customFieldValues: semiFormCustomFieldValues,
    loadFieldValues: loadSemiFormFieldValues,
    extractFormValues: extractSemiFormValues,
    saveCustomFieldValues: saveSemiCustomFieldValues,
    resetFieldValues: resetSemiFormFieldValues,
  } = useCustomFields({
    tableName: SEMI_FINISHED_GOODS_RECEIPT_CUSTOM_FIELD_TABLE,
    loadWhenOpen: true,
    open: open && receiptKind === 'semi_finished_goods',
  });

  const activeFormCustomFields =
    receiptKind === 'semi_finished_goods' ? semiFormCustomFields : finishedFormCustomFields;
  const activeFormCustomFieldValues =
    receiptKind === 'semi_finished_goods' ? semiFormCustomFieldValues : finishedFormCustomFieldValues;
  const extractActiveFormValues =
    receiptKind === 'semi_finished_goods' ? extractSemiFormValues : extractFinishedFormValues;
  const saveActiveCustomFieldValues =
    receiptKind === 'semi_finished_goods' ? saveSemiCustomFieldValues : saveFinishedCustomFieldValues;
  const resetActiveFormFieldValues =
    receiptKind === 'semi_finished_goods' ? resetSemiFormFieldValues : resetFinishedFormFieldValues;
  const loadActiveFormFieldValues =
    receiptKind === 'semi_finished_goods' ? loadSemiFormFieldValues : loadFinishedFormFieldValues;

  const defaultPerson = useMemo(() => {
    if (!currentUser) return { id: undefined as number | undefined, name: '' };
    const id = currentUser.id != null && currentUser.id > 0 ? Number(currentUser.id) : undefined;
    const name = String(currentUser.full_name || currentUser.username || '').trim();
    return { id, name };
  }, [currentUser]);

  const clearLineWarehouseDependents = useCallback((index: number) => {
    formRef.current?.setFieldValue(['items', index, 'location_id'], undefined);
    formRef.current?.setFieldValue(['items', index, 'location_code'], '');
    formRef.current?.setFieldValue(['items', index, 'batch_number'], undefined);
    formRef.current?.setFieldValue(['items', index, 'serial_numbers'], undefined);
  }, []);

  const syncLineMaterialTracking = useCallback(
    async (index: number, material: Material | undefined) => {
      if (!formRef.current) return;
      if (!material) {
        formRef.current.setFieldValue(['items', index, 'batch_managed'], false);
        formRef.current.setFieldValue(['items', index, 'serial_managed'], false);
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
          /* use picker fields */
        }
      }
      let serialManaged = !!(material.serialManaged ?? (material as { serial_managed?: boolean }).serial_managed);
      if (fromPicker) serialManaged = fromPicker.serialManaged;
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

  const resetForm = useCallback(() => {
    formRef.current?.resetFields();
    resetActiveFormFieldValues();
    formRef.current?.setFieldsValue({
      items: [{ ...defaultLineItem }],
      receipt_time: dayjs(),
      receiver_id: defaultPerson.id,
      receiver_name: defaultPerson.name,
    });
  }, [defaultPerson, resetActiveFormFieldValues]);

  useEffect(() => {
    if (!open) {
      setFormLoading(false);
      return;
    }
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

    if (!editingId) {
      resetForm();
      return () => {
        cancelled = true;
      };
    }

    setFormLoading(true);
    void (async () => {
      try {
        const detail = (
          receiptKind === 'semi_finished_goods'
            ? await warehouseApi.semiFinishedGoodsReceipt.get(String(editingId))
            : await warehouseApi.finishedGoodsReceipt.get(String(editingId))
        ) as Record<string, unknown>;
        if (cancelled) return;
        const headerWhId = positiveId(detail.warehouse_id) ?? undefined;
        const headerWhName = String(detail.warehouse_name ?? '').trim();
        const rawItems = Array.isArray(detail.items) ? detail.items : [];
        const items = rawItems.length
          ? rawItems.map((row) => {
              const line = row as Record<string, unknown>;
              const serials = Array.isArray(line.serial_numbers)
                ? line.serial_numbers.map((item) => String(item ?? '').trim()).filter(Boolean)
                : [];
              return {
                ...defaultLineItem,
                material_id: positiveId(line.material_id) ?? undefined,
                material_code: String(line.material_code ?? ''),
                material_name: String(line.material_name ?? ''),
                material_spec: line.material_spec != null ? String(line.material_spec) : undefined,
                material_unit: String(line.material_unit ?? ''),
                receipt_quantity: Number(line.receipt_quantity) || 0,
                warehouse_id: positiveId(line.warehouse_id) ?? headerWhId ?? undefined,
                warehouse_name: String(line.warehouse_name ?? headerWhName),
                location_id: positiveId(line.location_id) ?? undefined,
                location_code: line.location_code != null ? String(line.location_code) : '',
                batch_number: line.batch_number != null ? String(line.batch_number) : undefined,
                serial_numbers: serials.length ? serials : undefined,
                aux_quantity: line.aux_quantity != null ? Number(line.aux_quantity) : undefined,
                aux_unit: line.aux_unit != null ? String(line.aux_unit) : undefined,
                unit_conversion_rate:
                  line.unit_conversion_rate != null ? Number(line.unit_conversion_rate) : undefined,
              };
            })
          : [{ ...defaultLineItem, warehouse_id: headerWhId, warehouse_name: headerWhName }];
        const receiptTimeRaw = detail.receipt_time;
        formRef.current?.setFieldsValue({
          receiver_id: positiveId(detail.receiver_id) ?? undefined,
          receiver_name: String(detail.receiver_name ?? ''),
          receipt_time: receiptTimeRaw ? dayjs(String(receiptTimeRaw)) : dayjs(),
          notes: String(detail.notes ?? ''),
          items,
        });
        const fieldFormValues = await loadActiveFormFieldValues(editingId);
        if (cancelled) return;
        if (fieldFormValues) {
          formRef.current?.setFieldsValue(fieldFormValues);
        }
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
  }, [
    editingId,
    loadActiveFormFieldValues,
    messageApi,
    open,
    receiptKind,
    resetForm,
    syncLineMaterialTracking,
    t,
  ]);

  const [generatingBatchIdx, setGeneratingBatchIdx] = useState<number | null>(null);
  const [generatingSerialIdx, setGeneratingSerialIdx] = useState<number | null>(null);

  const formItemColumns = useMemo(() => {
    const cols = [
      {
        title: t('common.material'),
        dataIndex: 'material_id',
        width: DOCUMENT_DETAIL_COL_WIDTH.material,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <div>
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
            <AntForm.Item name={[index, 'material_uuid']} hidden>
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
                  void syncLineMaterialTracking(index, undefined);
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
                }
              }}
            />
          </div>
        ),
      },
      ...buildDocumentDetailSpecModelFormColumns(t),
      ...buildDocumentLineDualQuantityPairColumns({
        t,
        getForm: () => formRef.current,
        quantityField: 'receipt_quantity',
        unitField: 'material_unit',
        scenario: 'production',
        quantityPrecision: quantityDecimals,
        columnSpread: DOCUMENT_DETAIL_NUM_COL,
        inlineUnitWithQuantity: true,
      }),
      {
        title: t('app.kuaizhizao.warehouseInbound.col.warehouse'),
        dataIndex: 'warehouse_id',
        width: 220,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <FinishedGoodsReceiptCreateWarehouseCell
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
          <FinishedGoodsReceiptCreateLocationCell index={index} formRef={formRef} t={t} />
        ),
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.batchNo'),
        dataIndex: 'batch_number',
        width: 140,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item
            noStyle
            shouldUpdate={(prev, curr) => prev?.items?.[index] !== curr?.items?.[index]}
          >
            {({ getFieldValue }) => {
              const row = getFieldValue('items')?.[index];
              if (!isMaterialBatchEntryEnabled(trackingFlags, row?.batch_managed)) return <span>—</span>;
              return (
                <Space size={2}>
                  <AntForm.Item name={[index, 'batch_number']} noStyle>
                    <Input size={DOCUMENT_DETAIL_CONTROL_SIZE} style={{ width: 96 }} />
                  </AntForm.Item>
                  <Button
                    type="link"
                    size="small"
                    icon={<ThunderboltOutlined />}
                    loading={generatingBatchIdx === index}
                    onClick={() => {
                      const uuid = getFieldValue(['items', index, 'material_uuid']);
                      if (!uuid) return;
                      setGeneratingBatchIdx(index);
                      void materialBatchApi
                        .generate(String(uuid), {})
                        .then((res) => {
                          formRef.current?.setFieldValue(['items', index, 'batch_number'], res.batch_no);
                          messageApi.success(t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerated'));
                        })
                        .catch((e: Error) => {
                          messageApi.error(
                            e?.message || t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerateFailed'),
                          );
                        })
                        .finally(() => setGeneratingBatchIdx(null));
                    }}
                  />
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
                return (
                  <SerialNumbersImportTrigger
                    serials={Array.isArray(sn) ? sn : []}
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
    ];
    return filterWarehouseTrackingColumns(cols, trackingFlags);
  }, [
    clearLineWarehouseDependents,
    generatingBatchIdx,
    generatingSerialIdx,
    messageApi,
    quantityDecimals,
    syncLineMaterialTracking,
    t,
    trackingFlags,
  ]);

  const handleFinish = async (values: Record<string, unknown>) => {
    const { standardValues, customData } = extractActiveFormValues(values);
    const itemsRaw = resolveFormListFieldForSubmit(formRef, standardValues, 'items');
    const items = normalizeFormListItems<Record<string, unknown>>(itemsRaw);
    const validItems = items.filter(
      (it) => it.material_id && (Number(it.receipt_quantity) || 0) > 0,
    );
    if (!validItems.length) {
      const msg = t('app.kuaizhizao.warehouseInbound.msg.needValidFinishedGoodsLine');
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
      const batchManaged =
        it.batch_managed != null
          ? !!it.batch_managed
          : !!(material as Material | null)?.batchManaged;
      if (isMaterialBatchEntryEnabled(trackingFlags, batchManaged) && !String(it.batch_number ?? '').trim()) {
        const msg = t('app.kuaizhizao.warehouseOutbound.confirm.batchRequired', {
          material: materialLabel,
          batches: '—',
        });
        messageApi.error(msg);
        throw new Error(msg);
      }
      const serialManaged =
        it.serial_managed != null
          ? !!it.serial_managed
          : !!(material as Material | null)?.serialManaged;
      if (isMaterialSerialEntryEnabled(trackingFlags, serialManaged)) {
        const serials = Array.isArray(it.serial_numbers)
          ? it.serial_numbers.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
          : [];
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
    const totalQty = validItems.reduce((sum, it) => sum + (Number(it.receipt_quantity) || 0), 0);

    const payload = {
      warehouse_id: headerWhId,
      warehouse_name: headerWhName,
      status: '待入库',
      total_quantity: totalQty,
      receiver_id: standardValues.receiver_id != null ? Number(standardValues.receiver_id) : undefined,
      receiver_name: String(standardValues.receiver_name ?? '').trim() || undefined,
      receipt_time:
        standardValues.receipt_time
        && typeof (standardValues.receipt_time as { format?: unknown }).format === 'function'
          ? toApiBusinessDocumentDateTime(standardValues.receipt_time as dayjs.Dayjs)
          : undefined,
      notes: String(standardValues.notes ?? '').trim() || undefined,
      items: validItems.map((it) => {
        const qty = Number(it.receipt_quantity) || 0;
        const lineWhId = Number(it.warehouse_id) || headerWhId;
        return {
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
          qualified_quantity: qty,
          unqualified_quantity: 0,
          quality_status: '合格',
          status: '待入库',
          warehouse_id: lineWhId,
          warehouse_name: String(it.warehouse_name ?? headerWhName).trim() || undefined,
          location_id: it.location_id != null ? Number(it.location_id) : undefined,
          location_code: it.location_code != null ? String(it.location_code) : undefined,
          batch_number: it.batch_number != null ? String(it.batch_number) : undefined,
          serial_numbers: Array.isArray(it.serial_numbers)
            ? it.serial_numbers.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
            : undefined,
        };
      }),
    };

    try {
      let recordId = editingId ?? 0;
      if (receiptKind === 'semi_finished_goods') {
        if (editingId) {
          await warehouseApi.semiFinishedGoodsReceipt.update(String(editingId), payload);
          messageApi.success(t('common.updateSuccess'));
        } else {
          const created = await warehouseApi.semiFinishedGoodsReceipt.create(payload);
          recordId = Number((created as { id?: number })?.id ?? 0);
          messageApi.success(t('app.kuaizhizao.warehouseInbound.msg.semiFinishedGoodsBlankCreated'));
        }
      } else if (editingId) {
        await warehouseApi.finishedGoodsReceipt.update(String(editingId), payload);
        messageApi.success(t('common.updateSuccess'));
      } else {
        const created = await warehouseApi.finishedGoodsReceipt.create(payload);
        recordId = Number((created as { id?: number })?.id ?? 0);
        messageApi.success(t('app.kuaizhizao.warehouseInbound.msg.finishedGoodsBlankCreated'));
      }
      if (recordId > 0) {
        await saveActiveCustomFieldValues(recordId, customData);
      }
      resetActiveFormFieldValues();
      onSuccess?.();
      onClose();
    } catch (error: unknown) {
      const err = error as { message?: string };
      const needMsg = t('app.kuaizhizao.warehouseInbound.msg.needValidFinishedGoodsLine');
      if (err?.message !== needMsg) {
        messageApi.error(
          err?.message || (editingId ? t('common.updateFailed') : t('common.createFailed')),
        );
      }
      throw error;
    }
  };

  const modalTitle = editingId
    ? receiptKind === 'semi_finished_goods'
      ? t('app.kuaizhizao.warehouseInbound.editSemiFinishedGoodsReceiptModal')
      : t('app.kuaizhizao.warehouseInbound.editFinishedGoodsReceiptModal')
    : receiptKind === 'semi_finished_goods'
      ? t('app.kuaizhizao.warehouseInbound.createSemiFinishedGoodsReceiptModal')
      : t('app.kuaizhizao.warehouseInbound.createFinishedGoodsReceiptModal');

  return (
    <FormModalTemplate
      open={open}
      title={modalTitle}
      width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
      grid={false}
      formRef={formRef}
      loading={formLoading}
      isEdit={editingId != null}
      onOpenChange={(visible) => {
        if (!visible) {
          resetActiveFormFieldValues();
          onClose();
        }
      }}
      onFinish={handleFinish}
      destroyOnHidden
    >
      <DocumentDetailTableStyles />
      <Row gutter={16}>
        <Col span={12}>
          <UserPickField
            name="receiver_id"
            nameField="receiver_name"
            label={t('app.kuaizhizao.warehouseInbound.field.receiver')}
            placeholder={t('app.kuaizhizao.warehouseInbound.field.receiver')}
            userList={users}
            loading={usersLoading}
          />
        </Col>
        <Col span={12}>
          <ProFormDatePicker
            name="receipt_time"
            label={t('app.kuaizhizao.warehouseInbound.field.receiptDate')}
            rules={[
              {
                required: true,
                message: t('app.kuaizhizao.warehouseInbound.msg.selectDocumentDateRequired'),
              },
            ]}
            fieldProps={{ style: { width: '100%' } }}
          />
        </Col>
        <CustomFieldsFormSection
          customFields={activeFormCustomFields}
          customFieldValues={activeFormCustomFieldValues}
          gridColumns={2}
          embedInParentRow
        />
      </Row>

      <UniTableDetail
        name="items"
        title={t('app.kuaizhizao.warehouseInbound.createLinesTitle')}
        required
        requiredMessage={t('app.kuaizhizao.warehouseInbound.msg.needValidFinishedGoodsLine')}
        headerExtra={
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
        }
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
            fieldProps={{ rows: 3 }}
          />
        </Col>
      </Row>
    </FormModalTemplate>
  );
};

export default FinishedGoodsReceiptCreateModal;
