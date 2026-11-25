/**
 * 成品入库空白建单（无来源生产工单/成品检验）。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { App, Button, Col, Form as AntForm, Input, Row, Select, Space } from 'antd';
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
} from '../../../../../components/uni-wh-dropdown';
import { getPopupContainerInModal } from '../../../../../utils/modalEventIsolation';
import { warehouseApi } from '../../../services/production';
import type { WorkOrderFinishedGoodsPullLine } from '../../../services/warehouse-execution';
import { resolveKuaizhizaoDocumentAction } from '../../../constants/documentActionRegistry';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import {
  UniPullQueryModal,
  PULL_SOURCE_REFERENCE,
  isPullOpenLineSelectable,
  isPullWorkOrderFgLineSelectable,
  isPullableScope,
  loadPullSourceReferenceOptions,
  renderPullCapabilityTag,
  toUniPullQueryHttpParams,
  useUniPullQuery,
  buildPullQueryMaterialIdentityColumn,
  buildDefaultPullOpenLineQtyColumns,
} from '../../../../../components/uni-pull-query';
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
  enrichInboundFormItemsTracking,
  readMaterialTrackingFromPicker,
} from './inboundItemTracking';
import {
  resolveDocumentLineMaterialModel,
  resolveDocumentLineMaterialSpec,
} from './inboundPoReceiptEntryUtils';
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

type PullWorkOrderCandidate = WorkOrderFinishedGoodsPullLine;

const defaultLineItem = {
  receipt_quantity: 1,
  work_order_id: undefined as number | undefined,
  work_order_code: undefined as string | undefined,
  work_order_quantity: undefined as number | undefined,
  received_quantity: undefined as number | undefined,
  warehouse_id: undefined as number | undefined,
  warehouse_name: undefined as string | undefined,
  location_id: undefined as number | undefined,
  location_code: undefined as string | undefined,
  batch_number: undefined as string | undefined,
  batch_managed: false,
  serial_managed: false,
  serial_numbers: undefined as string[] | undefined,
  material_spec: undefined as string | undefined,
  material_model: undefined as string | undefined,
  material_uuid: undefined as string | undefined,
  batch_rule_id: undefined as number | undefined,
  default_batch_rule_id: undefined as number | undefined,
  default_serial_rule_id: undefined as number | undefined,
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
        <AntForm.Item name={[index, 'location_id']} noStyle>
          <UniWhLocationDropdown
            warehouseId={warehouseId > 0 ? warehouseId : undefined}
            materialId={materialId > 0 ? materialId : undefined}
            hostResource={INBOUND_HOST_RESOURCE}
            showStock={false}
            allowClear
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
  const pullSourceWorkOrderIdRef = useRef<number | undefined>(undefined);
  const [pullSourceWorkOrderId, setPullSourceWorkOrderId] = useState<number | undefined>();
  const [pullSourceWorkOrderOptions, setPullSourceWorkOrderOptions] = useState<
    Array<{ value: number; label: string }>
  >([]);
  const pullFromWorkOrderAction = resolveKuaizhizaoDocumentAction(t, 'inbound.pull_from_work_order');
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
    // 入库批号/序列号为新录入（非在库批），换仓只清库位；勿清空用户已填跟踪号
    formRef.current?.setFieldValue(['items', index, 'location_id'], undefined);
    formRef.current?.setFieldValue(['items', index, 'location_code'], '');
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
      } else {
        const id = Number(material.id);
        if (id > 0) {
          const resolved = await fetchMaterialForUnitSelectCache(id);
          const meta = resolved
            ? readMaterialTrackingFromPicker(resolved as unknown as Record<string, unknown>)
            : null;
          if (meta) {
            applyMaterialTrackingToFormRow(
              (name, value) => formRef.current!.setFieldValue(name, value),
              'items',
              index,
              meta,
            );
            batchManaged = meta.batchManaged;
          }
        }
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

  // 新建时 currentUser 晚到则补填；仅当入库人 id 与姓名皆空时回填，禁止把当前用户 id 贴到单据残留姓名上
  useEffect(() => {
    if (!open) return;
    if (defaultPerson.id == null && !defaultPerson.name) return;
    const rid = formRef.current?.getFieldValue('receiver_id');
    const rname = String(formRef.current?.getFieldValue('receiver_name') ?? '').trim();
    if ((rid != null && rid !== '') || rname) return;
    formRef.current?.setFieldsValue({
      receiver_id: defaultPerson.id,
      receiver_name: defaultPerson.name,
    });
  }, [open, editingId, defaultPerson]);

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
                material_model: line.material_model != null ? String(line.material_model) : undefined,
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
        const detailReceiverId = positiveId(detail.receiver_id);
        const detailReceiverName = String(detail.receiver_name ?? '').trim();
        const receiverEmpty = detailReceiverId == null && !detailReceiverName;
        formRef.current?.setFieldsValue({
          receiver_id: receiverEmpty ? defaultPerson.id : detailReceiverId,
          receiver_name: receiverEmpty ? defaultPerson.name : detailReceiverName,
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
    defaultPerson,
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
        title: t('app.kuaizhizao.warehouseInbound.col.workOrderCode'),
        dataIndex: 'work_order_code',
        width: 168,
        ellipsis: true,
      },
      buildPullQueryMaterialIdentityColumn<PullWorkOrderCandidate>(t),
      ...pullOpenQtyTripleColumns,
      {
        title: t('app.kuaizhizao.warehouseInbound.pull.gateStatus'),
        key: 'convert_status',
        width: 100,
        align: 'center' as const,
        render: (_: unknown, record: PullWorkOrderCandidate) =>
          renderPullCapabilityTag(
            isPullWorkOrderFgLineSelectable(record),
            t('app.kuaizhizao.warehouseInbound.pull.canCreate'),
            t('app.kuaizhizao.purchaseRequisition.pull.cannotCreate'),
          ),
      },
    ],
    [pullOpenQtyTripleColumns, t],
  );

  const applyWorkOrderPreviewToForm = useCallback(
    async (workOrderIds: number[]) => {
      const res = await warehouseApi.finishedGoodsReceipt.previewBlankFromWorkOrders(workOrderIds);
      if (res.message) {
        messageApi.info(res.message);
      }
      const previewItems = res.items ?? [];
      if (!previewItems.length) {
        messageApi.warning(t('app.kuaizhizao.warehouseInbound.msg.workOrderLinesLoadEmpty'));
        return;
      }
      let newLines = await Promise.all(
        previewItems.map(async (row) => {
          const materialId = Number(row.material_id);
          const material =
            materialId > 0 ? await fetchMaterialForUnitSelectCache(materialId) : null;
          const qty = Number(row.receipt_quantity) || 0;
          const line: Record<string, unknown> = {
            ...defaultLineItem,
            work_order_id: row.work_order_id,
            work_order_code: row.work_order_code,
            work_order_quantity: Number(row.work_order_quantity) || 0,
            received_quantity: Number(row.received_quantity) || 0,
            material_id: materialId,
            material_code: row.material_code,
            material_name: row.material_name,
            material_spec: resolveDocumentLineMaterialSpec(
              row as unknown as Record<string, unknown>,
              material ?? undefined,
            ),
            material_model: resolveDocumentLineMaterialModel(
              row as unknown as Record<string, unknown>,
              material ?? undefined,
            ),
            material_unit:
              String(row.material_unit ?? '').trim() ||
              (material ? resolveMaterialScenarioUnit(material, 'production') : '个'),
            receipt_quantity: qty > 0 ? qty : 0,
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
      newLines = (await enrichInboundFormItemsTracking(
        newLines as Record<string, unknown>[],
      )) as typeof newLines;
      const current = normalizeFormListItems<Record<string, unknown>>(
        formRef.current?.getFieldValue('items'),
      );
      const merged = [
        ...current.filter((it) => Number(it.material_id) > 0),
        ...newLines.filter(
          (nl) =>
            !current.some(
              (c) =>
                Number(c.work_order_id) === Number(nl.work_order_id) &&
                Number(c.material_id) === Number(nl.material_id),
            ),
        ),
      ];
      formRef.current?.setFieldsValue({ items: merged.length ? merged : newLines });
      const rows = normalizeFormListItems<Record<string, unknown>>(
        formRef.current?.getFieldValue('items'),
      );
      await Promise.all(
        rows.map(async (_row, index) => {
          const materialId = Number(rows[index]?.material_id);
          if (!(materialId > 0)) return;
          const material = await fetchMaterialForUnitSelectCache(materialId);
          if (material) await syncLineMaterialTracking(index, material);
        }),
      );
      messageApi.success(t('app.kuaizhizao.warehouseInbound.msg.workOrderLinesLoaded'));
    },
    [messageApi, syncLineMaterialTracking, t, trackingFlags],
  );

  const handleGenerateBatch = useCallback(
    async (index: number) => {
      if (!trackingFlags.batchManagement) return;
      const materialId = Number(formRef.current?.getFieldValue(['items', index, 'material_id']));
      const batchManaged = !!formRef.current?.getFieldValue(['items', index, 'batch_managed']);
      let uuid = String(formRef.current?.getFieldValue(['items', index, 'material_uuid']) ?? '').trim();
      if (!uuid && materialId > 0) {
        const m = await fetchMaterialForUnitSelectCache(materialId);
        if (m?.uuid) {
          uuid = String(m.uuid).trim();
          formRef.current?.setFieldValue(['items', index, 'material_uuid'], uuid);
          const meta = readMaterialTrackingFromPicker(m as unknown as Record<string, unknown>);
          if (meta) {
            applyMaterialTrackingToFormRow(
              (name, value) => formRef.current!.setFieldValue(name, value),
              'items',
              index,
              meta,
            );
          }
        }
      }
      if (!uuid || !batchManaged) {
        messageApi.warning(t('app.kuaizhizao.warehouseOtherInbound.msg.selectMaterialFirst'));
        return;
      }
      const batchRuleId = formRef.current?.getFieldValue(['items', index, 'batch_rule_id']);
      const defaultBatchRuleId = formRef.current?.getFieldValue(['items', index, 'default_batch_rule_id']);
      setGeneratingBatchIdx(index);
      try {
        const res = await materialBatchApi.generate(uuid, {
          ruleId: batchRuleId ?? defaultBatchRuleId,
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
        hostResource: INBOUND_HOST_RESOURCE,
      })
        .then(setPullSourceWorkOrderOptions)
        .catch((error: unknown) => {
          messageApi.error(
            getApiErrorMessage(error, t('app.kuaizhizao.warehouseInbound.pull.workOrder.loadSourceFailed')),
          );
          setPullSourceWorkOrderOptions([]);
        });
    },
    loadData: async (params) => {
      const { scope } = params;
      try {
        const listRes = await warehouseApi.finishedGoodsReceipt.listWorkOrderPullLines({
          ...toUniPullQueryHttpParams(params),
          work_order_id: pullSourceWorkOrderIdRef.current,
          pullable_only: isPullableScope(scope),
        });
        return { data: listRes?.data ?? [], total: listRes?.total ?? 0 };
      } catch (error: unknown) {
        messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.warehouseInbound.pull.workOrder.loadFailed')));
        return { data: [], total: 0 };
      }
    },
    isRowDisabled: (record) => !isPullWorkOrderFgLineSelectable(record),
    onConfirm: async (_keys, rows) => {
      const selectedRows = rows.filter((row) => isPullWorkOrderFgLineSelectable(row));
      if (!selectedRows.length) {
        messageApi.warning(t('app.kuaizhizao.warehouseInbound.pull.workOrder.selectLinesFirst'));
        return;
      }
      const workOrderIds = [
        ...new Set(
          selectedRows
            .map((row) => Number(row.work_order_id))
            .filter((id) => Number.isFinite(id) && id > 0),
        ),
      ];
      if (!workOrderIds.length) {
        messageApi.warning(t('app.kuaizhizao.warehouseInbound.msg.selectWorkOrderFirst'));
        return;
      }
      try {
        await applyWorkOrderPreviewToForm(workOrderIds);
        pullFromWorkOrderQuery.closeModal();
      } catch (error: unknown) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.warehouseInbound.pull.workOrder.previewFailed')),
        );
      }
    },
  });

  const formItemColumns = useMemo(() => {
    const woCols =
      receiptKind === 'finished_goods'
        ? [
            {
              title: t('app.kuaizhizao.warehouseInbound.col.workOrderCode'),
              dataIndex: 'work_order_code',
              width: 110,
              ellipsis: true,
              render: (_: unknown, __: unknown, index: number) => (
                <>
                  <AntForm.Item name={[index, 'work_order_id']} hidden>
                    <Input />
                  </AntForm.Item>
                  <AntForm.Item name={[index, 'work_order_code']} noStyle>
                    <Input readOnly variant="borderless" placeholder="—" />
                  </AntForm.Item>
                </>
              ),
            },
            {
              title: t('app.kuaizhizao.warehouseInbound.col.workOrderQty'),
              dataIndex: 'work_order_quantity',
              width: 96,
              align: 'right' as const,
              render: (_: unknown, __: unknown, index: number) => (
                <AntForm.Item name={[index, 'work_order_quantity']} noStyle>
                  <Input readOnly variant="borderless" />
                </AntForm.Item>
              ),
            },
            {
              title: t('app.kuaizhizao.warehouseInbound.col.receivedQty'),
              dataIndex: 'received_quantity',
              width: 96,
              align: 'right' as const,
              render: (_: unknown, __: unknown, index: number) => (
                <AntForm.Item name={[index, 'received_quantity']} noStyle>
                  <Input readOnly variant="borderless" />
                </AntForm.Item>
              ),
            },
          ]
        : [];
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
            <AntForm.Item name={[index, 'material_model']} hidden>
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
            <AntForm.Item name={[index, 'batch_rule_id']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'default_batch_rule_id']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'default_serial_rule_id']} hidden>
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
                // 换物料时清空跟踪号（与库位一并重置）
                formRef.current?.setFieldValue(['items', index, 'batch_number'], undefined);
                formRef.current?.setFieldValue(['items', index, 'serial_numbers'], undefined);
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
      ...woCols,
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
            shouldUpdate={(prev, curr) =>
              prev?.items?.[index]?.batch_managed !== curr?.items?.[index]?.batch_managed
            }
          >
            {({ getFieldValue }) => {
              const row = getFieldValue('items')?.[index];
              if (!isMaterialBatchEntryEnabled(trackingFlags, row?.batch_managed)) return <span>—</span>;
              return (
                <Space size={2}>
                  <AntForm.Item name={[index, 'batch_number']} noStyle>
                    <Input
                      size={DOCUMENT_DETAIL_CONTROL_SIZE}
                      style={{ width: 96 }}
                      placeholder={t('app.kuaizhizao.warehouseInbound.field.batchNoPlaceholder')}
                    />
                  </AntForm.Item>
                  <Button
                    type="link"
                    size="small"
                    icon={<ThunderboltOutlined />}
                    loading={generatingBatchIdx === index}
                    onClick={() => void handleGenerateBatch(index)}
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
              shouldUpdate={(prev, curr) => {
                const p = prev?.items?.[index];
                const c = curr?.items?.[index];
                return (
                  p?.serial_managed !== c?.serial_managed ||
                  p?.receipt_quantity !== c?.receipt_quantity ||
                  p?.serial_numbers !== c?.serial_numbers ||
                  p?.material_code !== c?.material_code ||
                  p?.material_name !== c?.material_name
                );
              }}
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
                      let uuid = String(getFieldValue(['items', index, 'material_uuid']) ?? '').trim();
                      const materialId = Number(getFieldValue(['items', index, 'material_id']));
                      if (!uuid && materialId > 0) {
                        const m = await fetchMaterialForUnitSelectCache(materialId);
                        if (m?.uuid) {
                          uuid = String(m.uuid).trim();
                          formRef.current?.setFieldValue(['items', index, 'material_uuid'], uuid);
                          const meta = readMaterialTrackingFromPicker(m as unknown as Record<string, unknown>);
                          if (meta) {
                            applyMaterialTrackingToFormRow(
                              (name, value) => formRef.current!.setFieldValue(name, value),
                              'items',
                              index,
                              meta,
                            );
                          }
                        }
                      }
                      if (!uuid) {
                        messageApi.warning(t('app.kuaizhizao.warehouseOtherInbound.msg.selectMaterialFirst'));
                        return [];
                      }
                      if (!(expected > 0)) return [];
                      const serialRuleId =
                        getFieldValue(['items', index, 'default_serial_rule_id']) ??
                        getFieldValue(['items', index, 'serial_rule_id']);
                      const count = Math.min(expected, MATERIAL_SERIAL_GENERATE_MAX_COUNT);
                      setGeneratingSerialIdx(index);
                      try {
                        const res = await materialSerialApi.generate(uuid, count, {
                          ruleId:
                            serialRuleId != null && Number(serialRuleId) > 0
                              ? Number(serialRuleId)
                              : undefined,
                        });
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
    handleGenerateBatch,
    messageApi,
    quantityDecimals,
    syncLineMaterialTracking,
    t,
    trackingFlags,
    receiptKind,
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
      // 库位可空：保存后由后端 `_resolve_line_location_*` / ensure 整仓解析
      const material = await fetchMaterialForUnitSelectCache(Number(it.material_id));
      const batchManaged =
        it.batch_managed != null
          ? !!it.batch_managed
          : !!(material as Material | null)?.batchManaged;
      if (isMaterialBatchEntryEnabled(trackingFlags, batchManaged) && !String(it.batch_number ?? '').trim()) {
        const msg = t('app.kuaizhizao.warehouseInbound.msg.batchRequiredForSave', {
          material: materialLabel,
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
          const msg = t('app.kuaizhizao.warehouseInbound.msg.serialCountMismatch', {
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
          material_model: it.material_model != null ? String(it.material_model) : undefined,
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
          work_order_id:
            it.work_order_id != null && Number(it.work_order_id) > 0
              ? Number(it.work_order_id)
              : undefined,
          work_order_code: it.work_order_code ? String(it.work_order_code) : undefined,
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
    <>
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
            {receiptKind === 'finished_goods' && !editingId ? (
              <Button type="default" onClick={() => pullFromWorkOrderQuery.openModal()}>
                {t('app.kuaizhizao.warehouseInbound.action.loadLinesFromWorkOrder')}
              </Button>
            ) : null}
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
      <UniPullQueryModal<PullWorkOrderCandidate>
        title={pullFromWorkOrderAction.label}
        pullQuery={pullFromWorkOrderQuery.pullQuery}
        open={pullFromWorkOrderQuery.open}
        onCancel={pullFromWorkOrderQuery.closeModal}
        onOk={pullFromWorkOrderQuery.handleConfirm}
        rowKey="id"
        columns={workOrderPullColumns}
        dataSource={pullFromWorkOrderQuery.dataSource}
        loading={pullFromWorkOrderQuery.loading}
        confirmLoading={pullFromWorkOrderQuery.confirmLoading}
        selectionType={pullFromWorkOrderQuery.selectionType}
        selectedRowKeys={pullFromWorkOrderQuery.selectedRowKeys}
        selectedRows={pullFromWorkOrderQuery.selectedRows}
        onSelectedRowKeysChange={pullFromWorkOrderQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullFromWorkOrderQuery.isRowDisabled}
        searchDraft={pullFromWorkOrderQuery.searchDraft}
        onSearchDraftChange={pullFromWorkOrderQuery.setSearchDraft}
        onSearchApply={pullFromWorkOrderQuery.handleSearchApply}
        onSearchClear={pullFromWorkOrderQuery.handleSearchClear}
        appliedKeyword={pullFromWorkOrderQuery.appliedKeyword}
        searchPlaceholder={t('app.kuaizhizao.warehouseInbound.pull.workOrder.searchPlaceholder')}
        filterExtra={
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder={t('app.kuaizhizao.warehouseInbound.pull.workOrder.sourceDocPlaceholder')}
            style={{ width: 220, flexShrink: 0 }}
            value={pullSourceWorkOrderId}
            options={pullSourceWorkOrderOptions}
            onChange={(value) => {
              const nextId = Number(value);
              const next = Number.isFinite(nextId) && nextId > 0 ? nextId : undefined;
              pullSourceWorkOrderIdRef.current = next;
              setPullSourceWorkOrderId(next);
              pullFromWorkOrderQuery.handleSearchApply(pullFromWorkOrderQuery.appliedKeyword);
            }}
          />
        }
        getRowLabel={(row) => [row.work_order_code, row.material_code].filter(Boolean).join(' ')}
        page={pullFromWorkOrderQuery.page}
        pageSize={pullFromWorkOrderQuery.pageSize}
        total={pullFromWorkOrderQuery.total}
        onPageChange={pullFromWorkOrderQuery.handlePageChange}
        scopeOptions={pullFromWorkOrderQuery.scopeOptions}
        scope={pullFromWorkOrderQuery.scope}
        onScopeChange={pullFromWorkOrderQuery.handleScopeChange}
        okText={t('app.kuaizhizao.warehouseInbound.pull.workOrder.ok')}
      />
    </>
  );
};

export default FinishedGoodsReceiptCreateModal;
