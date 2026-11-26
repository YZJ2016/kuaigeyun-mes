/**
 * 其他出库单管理页面
 *
 * 提供其他出库单的创建、查看、确认和管理功能（盘亏/样品/报废/其他）
 *
 * @author RiverEdge Team
 * @date 2026-02-19
 */

import React, { useRef, useState, useEffect, useCallback, useMemo } from 'react';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useToolbarSyncPushFlags } from '../../../../../hooks/useToolbarSyncPushFlags';
import { SyncPushHubButton } from '../../../../../components/sync-push-hub';
import OtherOutboundDocumentPushPanel from './OtherOutboundDocumentPushPanel';
import { readExternalWithdrawMessage } from '../shared/externalWithdrawMessage';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import {
  CustomFieldsFormSection,
  CustomFieldsDetailSection,
  hasCustomFieldsDetailContent,
} from '../../../../../components/custom-fields';
import { useNavigate } from 'react-router-dom';
import {
  ActionType,
  ProColumns,
  ProDescriptionsItemProps,
  ProFormDatePicker,
  ProFormItem,
  ProFormTextArea,
  type ProFormInstance,
} from '@ant-design/pro-components';
import { App, Button, Tag, Space, Modal, Table, Form as AntForm, Input, Row, Col, Select, Typography, Descriptions } from 'antd';
import { UniInputNumber } from '../../../../../components/uni-input-number/UniInputNumber';
import { CheckCircleOutlined, PlusOutlined, RollbackOutlined, ShoppingOutlined } from '@ant-design/icons';
import { UniCapabilityBatchButton } from '../../../../../components/uni-batch';
import { runOutboundHubConfirmFromRecord, formatOutboundConfirmError } from '../outbound/outboundHubRunConfirm';
import { isOutboundEditable } from '../outbound/outboundHubTypes';
import {
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import { buildDocumentDetailSerialReadonlyColumn } from '../../../components/documentDetailSerialNumberColumn';
import OutboundSerialPickerField from '../outbound/OutboundSerialPickerField';
import { materialApi } from '../../../../master-data/services/material';
import {
  loadBatchOptionsByMaterialId,
  loadInStockSerialOptions,
  type InventoryPickOption,
} from '../outbound/outboundConfirmInventoryOptions';
import OutboundBatchAllocationField from '../outbound/OutboundBatchAllocationField';
import {
  isValidOutboundBatchAllocations,
  lineBatchAllocationsFromRow,
  syncFormLineBatchFields,
} from '../outbound/outboundBatchAllocation';
import { getPopupContainerInModal } from '../../../../../utils/modalEventIsolation';
import { UniTable, type UniTableRequestMeta} from '../../../../../components/uni-table';
import { UniMaterialSelect } from '../../../../../components/uni-material-select';
import { UniMaterialBatchPicker } from '../../../../../components/uni-material-batch-picker';
import { fetchBatchMaterialInventory } from '../../../../../components/uni-material-batch-picker/utils';
import {
  buildDocumentLineAuxQuantityDetailColumn,
  buildDocumentLineDualQuantityPairColumns,
} from '../../../../../components/quantity-with-unit';
import {
  pickDocumentLineDualQuantityFields,
  validateDualQuantityBeforeSave,
} from '../../../../../utils/materialDualQuantity';
import { resolveMaterialScenarioUnit } from '../../../../../utils/materialScenarioUnit';
import type { Material } from '../../../../master-data/types/material';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import {
  UniWhDropdown,
  UniWhLocationDropdown,
  useWarehouseHasLocations,
  lineLocationSelectionRequired,
} from '../../../../../components/uni-wh-dropdown';
import { UniTableDetail } from '../../../../../components/uni-table-detail';
import {
  DocumentDetailTableStyles,
  DOCUMENT_DETAIL_COL_WIDTH,
  DOCUMENT_DETAIL_CONTROL_SIZE,
  DOCUMENT_DETAIL_NUM_COL,
  DOCUMENT_DETAIL_TABLE_PROPS,
  DOCUMENT_DETAIL_TEXT_COL,
} from '../../../components/document-detail-table/documentDetailTable';
import CodeField from '../../../../../components/code-field';
import { MaterialUnitLabel } from '../../../../../components/material-unit-label';
import { getDataDictionaryList, getDictionaryItemList } from '../../../../../services/dataDictionary';
import {   useDetailDrawerDescriptionItems, detailDrawerBasicColumn, DetailDrawerTemplate, DRAWER_CONFIG, FormModalTemplate, ListPageTemplate, MODAL_CONFIG, WAREHOUSE_DETAIL_TABLE_STYLES } from '../../../../../components/layout-templates';
import { warehouseApi } from '../../../services/production';
import { getOtherOutboundLifecycle } from '../../../utils/otherOutboundLifecycle';
import { computeSimpleDocumentLineTotal } from '../../../utils/documentLineAmounts';
import { UniLifecycle, UniLifecycleStepper } from '../../../../../components/uni-lifecycle';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import { useNumericPrecision } from '../../../../../hooks/useNumericPrecision';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import {
  buildDocumentDetailSpecModelFormColumns,
  withMaterialLineFillMapping,
} from '../../sales-management/shared/materialLineFormDetail';
import { normalizeDocumentAttachments } from '../../../utils/documentAttachments';
import { rowActionKind, rowActionLabelKeep } from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { renderWarehouseReasonTypeMarkerTag } from '../shared/warehouseMarkerTags';
import {
  OTHER_OUTBOUND_TYPE_ASSET,
  OTHER_OUTBOUND_TYPE_MATERIAL,
  renderOtherOutboundTypeMarkerTag,
  translateOtherOutboundTypeLabel,
} from './otherOutboundTypeLabels';
import { useNewShortcut } from '../../../../../hooks/useNewShortcut';
import { withSingleNewShortcutHint } from '../../../../../utils/globalNewShortcut';
import { useKuaizhizaoPrintModal } from '../../../hooks/useKuaizhizaoPrintModal';
import { formatBusinessDateOnly, formatDateTime, formatQuantity, todaySiteDateString } from '../../../../../utils/format';
import { fetchAllListItems } from '../../../../../utils/fetchAllListPages';
import {
  enrichStandaloneDocsWithDetail,
  exportWarehouseDocLinesXlsx,
  filterWarehouseFlatRowsByExportKeys,
  flattenStandaloneWarehouseDocsForExport,
  resolveWarehouseListExportHeaders,
} from '../shared/warehouseDocListExport';
import { formDateRangeFormItemProps, toApiDateString } from '../../../../../utils/formDate';
import { alignDescriptionColumns, alignProColumns } from '../../sales-management/shared/documentFieldAlignment';
import { WAREHOUSE_DOC_LIST_FIELD_RANK } from '../shared/warehouseDocListFieldRank';
import { buildDocumentAuditColumns } from '../../shared/documentAuditColumns';
import { createListAuditPhaseColumn } from '../../sales-management/shared/listAuditPhaseColumn';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../../utils/uniTableLayoutColumns';
import {
  DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
  renderDocumentLineMaterialsPreview,
} from '../../sales-management/shared/documentLineMaterialsPreview';
import {
  WAREHOUSE_DOC_PINNED_STATUS_FIELD,
  buildOtherOutboundStatusValueEnum,
  normalizeWarehouseListResponse,
  resolveWarehouseDocListParams,
} from '../../../utils/warehouseListCore';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { loadAvailableQtyByMaterialId } from '../outbound/outboundConfirmInventoryOptions';
import {
  mapOtherOutboundReasonTypeOptions,
  translateOtherOutboundReasonTypeLabel,
} from './otherOutboundReasonTypeLabels';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import { searchUserDisplay } from '../../../../../services/user';
import type { User } from '../../../../../services/user';
import {
  displayItemsToUsers,
  formatUserDisplayLabel,
  normalizeUserDisplayName,
} from '../../../../../utils/userDisplay';
import {
  getDepartmentTree,
  type DepartmentTreeItem,
} from '../../../../../services/department';
import { CustomerSelectDropdown } from '../../../../master-data/components/CustomerSelectDropdown';
import type { Customer } from '../../../../master-data/types/supply-chain';

const OTHER_OUTBOUND_HOST_RESOURCE = 'kuaizhizao:other-outbound';

/** 明细物料+仓库指纹：触发按行仓库存重拉 */
function otherOutboundStockFingerprint(items: unknown): string {
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

function resolvePrimaryDefaultWarehouse(material: Material): { id: number; name: string } | null {
  const wh = material.defaultWarehouse ?? (material as { default_warehouse?: { id?: number; name?: string } }).default_warehouse;
  if (wh && typeof wh === 'object' && 'id' in wh && wh.id) {
    return { id: Number(wh.id), name: String((wh as { name?: string }).name ?? '') };
  }
  return null;
}

function OtherOutboundCreateWarehouseCell({
  index,
  clearLineWarehouseDependents,
  ensureBatchOptions,
  formRef,
  t,
}: {
  index: number;
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
          hostResource={OTHER_OUTBOUND_HOST_RESOURCE}
          materialId={materialId > 0 ? materialId : undefined}
          showStock={materialId > 0}
          sortByStock={materialId > 0}
          placeholder={t('app.kuaizhizao.warehouseOutbound.msg.selectWarehouse')}
          getPopupContainer={getPopupContainerInModal}
          onChange={(_id, wh) => {
            clearLineWarehouseDependents(index);
            const whId = Number(wh?.id ?? _id ?? 0);
            formRef.current?.setFieldValue(['items', index, 'warehouse_name'], wh?.name ?? '');
            if (whId > 0) {
              const mid = Number(
                formRef.current?.getFieldValue(['items', index, 'material_id']) || 0,
              );
              const batchManaged = !!formRef.current?.getFieldValue([
                'items',
                index,
                'batch_managed',
              ]);
              if (mid > 0 && batchManaged) {
                void ensureBatchOptions(mid, whId);
              }
            }
          }}
        />
      </AntForm.Item>
    </div>
  );
}

function OtherOutboundCreateLocationCell({
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
            hostResource={OTHER_OUTBOUND_HOST_RESOURCE}
            showStock={materialId > 0}
            sortByStock={materialId > 0}
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

const REASON_TYPES_FALLBACK = [
  { value: '盘亏', label: '盘亏' },
  { value: '样品', label: '样品' },
  { value: '报废', label: '报废' },
  { value: '其他', label: '其他' },
];

interface OtherOutbound {
  id?: number;
  tenant_id?: number;
  outbound_code?: string;
  outbound_type?: string;
  reason_type?: string;
  reason_desc?: string;
  warehouse_id?: number;
  warehouse_name?: string;
  status?: string;
  deliverer_id?: number;
  deliverer_name?: string;
  delivery_time?: string;
  total_quantity?: number;
  total_items?: number;
  total_amount?: number;
  /** 列表「明细」列预览（仅 material_name） */
  items?: { material_name?: string }[];
  notes?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: any;
}

interface OtherOutboundDetail extends OtherOutbound {
  items?: OtherOutboundItem[];
}

interface OtherOutboundItem {
  id?: number;
  material_id?: number;
  material_code?: string;
  material_name?: string;
  material_spec?: string;
  material_unit?: string;
  warehouse_id?: number;
  warehouse_name?: string;
  location_id?: number;
  location_code?: string;
  outbound_quantity?: number;
  unit_price?: number;
  total_amount?: number;
  batch_number?: string;
  notes?: string;
}

const OTHER_OUTBOUND_CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_other_outbounds';

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

const OTHER_OUTBOUND_PICKER_USER_PAGE_SIZE = 50;

function OtherOutboundUserPickField({
  name,
  nameField,
  label,
  placeholder,
  required,
  operatorNumberField,
  departmentOptions,
}: {
  name: string;
  nameField: string;
  label: string;
  placeholder: string;
  required?: boolean;
  operatorNumberField?: string;
  departmentOptions?: Array<{ value: number; label: string; code?: string }>;
}) {
  const form = AntForm.useFormInstance();
  const pickedId = AntForm.useWatch(name, form);
  const pickedName = AntForm.useWatch(nameField, form);
  const [userList, setUserList] = useState<User[]>([]);
  const [userSearchLoading, setUserSearchLoading] = useState(false);

  const loadPickerUsers = useCallback(async (keyword = '') => {
    setUserSearchLoading(true);
    try {
      const res = await searchUserDisplay({
        page: 1,
        page_size: OTHER_OUTBOUND_PICKER_USER_PAGE_SIZE,
        is_active: true,
        keyword: keyword.trim() || undefined,
      });
      setUserList(displayItemsToUsers(res.items || []));
    } catch {
      setUserList([]);
    } finally {
      setUserSearchLoading(false);
    }
  }, []);

  const pickerSearchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const debouncedLoadPickerUsers = useCallback((keyword: string) => {
    if (pickerSearchTimerRef.current) {
      clearTimeout(pickerSearchTimerRef.current);
    }
    pickerSearchTimerRef.current = setTimeout(() => {
      pickerSearchTimerRef.current = null;
      void loadPickerUsers(keyword);
    }, 300);
  }, [loadPickerUsers]);

  useEffect(
    () => () => {
      if (pickerSearchTimerRef.current) {
        clearTimeout(pickerSearchTimerRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    void loadPickerUsers('');
  }, [loadPickerUsers]);

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
      const labelText = normalizeUserDisplayName(pickedName) || String(bid);
      return [{ value: bid, label: labelText }, ...base];
    }
    return base;
  }, [pickedId, pickedName, userList]);

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
          filterOption={false}
          allowClear={!required}
          loading={userSearchLoading}
          style={{ width: '100%' }}
          options={options}
          onOpenChange={(open) => {
            if (open) void loadPickerUsers('');
          }}
          onSearch={debouncedLoadPickerUsers}
          onChange={(val, opt: { label?: React.ReactNode } | undefined) => {
            const patch: Record<string, unknown> = {
              [nameField]: typeof opt?.label === 'string' ? opt.label : undefined,
            };
            const uid =
              val != null && val !== '' && Number.isFinite(Number(val)) ? Number(val) : NaN;
            const picked = Number.isFinite(uid) ? userList.find((u) => Number(u.id) === uid) : undefined;
            if (operatorNumberField) {
              const emp = picked?.employee_number?.trim();
              patch[operatorNumberField] = emp || undefined;
            }
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

const OtherOutboundPage: React.FC = () => {
  const { t } = useTranslation();
  const otherOutboundAuditColumn = useMemo(
    () => createListAuditPhaseColumn<Record<string, unknown>>({ t }),
    [t],
  );
  const currentUser = useCurrentUser();
  const { quantity: quantityDecimals, price: priceDecimals } = useNumericPrecision();
  const { openPrint, PrintModal } = useKuaizhizaoPrintModal();
  const navigate = useNavigate();
  const { message: messageApi } = App.useApp();
  const actionRef = useRef<ActionType>(null);

  const invalidateMenuBadgeCounts = useInvalidateMenuBadgeCounts();
  const outboundPerms = useResourcePermissions('kuaizhizao:other-outbound');
  const toolbarSyncPush = useToolbarSyncPushFlags('kuaizhizao:other-outbound');
  const canConfirmOutbound = outboundPerms.canAction?.('execute') ?? false;
  const canRevokeOutbound = outboundPerms.canAction?.('revoke') ?? false;
  const canDeleteOutbound = outboundPerms.canDelete ?? false;
  const canUpdateOutbound = outboundPerms.canUpdate ?? false;
  const [editingOutboundId, setEditingOutboundId] = useState<number | null>(null);
  const [editingOutboundCode, setEditingOutboundCode] = useState<string>('');
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [outboundDetail, setOutboundDetail] = useState<OtherOutboundDetail | null>(null);

  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [materialPickerOpen, setMaterialPickerOpen] = useState(false);
  const formRef = useRef<any>(null);
  /** 编辑灌数时的行 id 快照；Form.List 未注册字段会在改库位等操作后从 onFinish values 丢失 */
  const editLineIdsRef = useRef<number[]>([]);

  const {
    customFields: otherOutboundFormCustomFields,
    customFieldValues: otherOutboundFormCustomFieldValues,
    extractFormValues: extractOtherOutboundFormValues,
    saveCustomFieldValues: saveOtherOutboundCustomFieldValues,
    resetFieldValues: resetOtherOutboundFormFieldValues,
    loadFieldValues: loadOtherOutboundFormFieldValues,
  } = useCustomFields({
    tableName: OTHER_OUTBOUND_CUSTOM_FIELD_TABLE,
    loadWhenOpen: true,
    open: createModalVisible,
  });

  const {
    customFields: otherOutboundListCustomFields,
    generateCustomFieldColumns: generateOtherOutboundCustomFieldColumns,
    enrichRecordsWithCustomFields: enrichOtherOutboundRecordsWithCustomFields,
    customFieldValues: otherOutboundDetailCustomFieldValues,
    loadFieldValuesForDetail: loadOtherOutboundFieldValuesForDetail,
    resetDetailFieldValues: resetOtherOutboundDetailFieldValues,
  } = useCustomFieldsForList<OtherOutbound>({ tableName: OTHER_OUTBOUND_CUSTOM_FIELD_TABLE });
  const [reasonTypeOptions, setReasonTypeOptions] = useState<Array<{ label: string; value: string }>>([]);
  /** 按「物料:仓库」键的可出库库存（自购在库，与确认出库扣减口径一致） */
  const [stockByKey, setStockByKey] = useState<Record<string, number>>({});
  const [stockLoading, setStockLoading] = useState(false);
  const [lineStockKey, setLineStockKey] = useState('');
  const trackingFlags = useWarehouseTrackingFlags();
  const [serialOptionsByUuid, setSerialOptionsByUuid] = useState<Record<string, InventoryPickOption[]>>({});
  const [serialOptionsLoadingUuid, setSerialOptionsLoadingUuid] = useState<string | null>(null);
  const serialOptionsLoadingRef = useRef<Record<string, boolean>>({});
  const [batchOptionsByKey, setBatchOptionsByKey] = useState<Record<string, InventoryPickOption[]>>({});
  const [batchOptionsLoadingKey, setBatchOptionsLoadingKey] = useState<string | null>(null);
  const [departmentOptions, setDepartmentOptions] = useState<Array<{ value: number; label: string; code?: string }>>(
    [],
  );
  const [departmentsLoading, setDepartmentsLoading] = useState(false);
  useEffect(() => {
    if (!createModalVisible) return;
    let cancelled = false;
    (async () => {
      setDepartmentsLoading(true);
      try {
        const deptRes = await getDepartmentTree({ is_active: true });
        if (!cancelled) {
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
          setDepartmentOptions([]);
        }
      } finally {
        if (!cancelled) {
          setDepartmentsLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [createModalVisible]);

  useEffect(() => {
    if (!createModalVisible || !currentUser || editingOutboundId != null) return;
    const id =
      currentUser.id != null && Number(currentUser.id) > 0 ? Number(currentUser.id) : undefined;
    const name = String(currentUser.full_name || currentUser.username || '').trim();
    const emp = String(currentUser.employee_number ?? '').trim();
    formRef.current?.setFieldsValue({
      picker_id: id,
      picker_name: name,
      ...(emp ? { picker_operator_number: emp } : {}),
    });
  }, [createModalVisible, currentUser, editingOutboundId]);

  const defaultOutboundItem = {
    material_id: undefined,
    material_uuid: undefined as string | undefined,
    material_code: '',
    material_name: '',
    material_spec: '',
    material_model: '',
    material_unit: '',
    aux_quantity: undefined as number | undefined,
    aux_unit: undefined as string | undefined,
    unit_conversion_rate: undefined as number | undefined,
    warehouse_id: undefined as number | undefined,
    warehouse_name: undefined as string | undefined,
    location_id: undefined as number | undefined,
    location_code: undefined as string | undefined,
    batch_number: undefined as string | undefined,
    batch_allocations: [] as { batchNo: string; quantity: number }[],
    batch_managed: false,
    serial_managed: false,
    serial_numbers: undefined as string[] | undefined,
    batch_rule_id: undefined as string | undefined,
    default_batch_rule_id: undefined as string | undefined,
    outbound_quantity: 1,
    // 单价选填，不自动带物料采购价/成本
    unit_price: undefined as number | undefined,
  };
  const [reasonTypeLoading, setReasonTypeLoading] = useState(false);

  const syncLineStockKeyFromForm = useCallback(() => {
    setLineStockKey(otherOutboundStockFingerprint(formRef.current?.getFieldValue('items')));
  }, []);

  const clearLineWarehouseDependents = useCallback((index: number) => {
    formRef.current?.setFieldValue(['items', index, 'location_id'], undefined);
    formRef.current?.setFieldValue(['items', index, 'location_code'], undefined);
    formRef.current?.setFieldValue(['items', index, 'batch_number'], undefined);
    formRef.current?.setFieldValue(['items', index, 'batch_allocations'], []);
    formRef.current?.setFieldValue(['items', index, 'serial_numbers'], undefined);
    syncLineStockKeyFromForm();
  }, [syncLineStockKeyFromForm]);

  const ensureSerialOptions = useCallback(async (materialUuid: string, selected?: string[]) => {
    const uuid = String(materialUuid || '').trim();
    if (!uuid || serialOptionsLoadingRef.current[uuid]) return;
    if (serialOptionsByUuid[uuid]?.length) return;
    serialOptionsLoadingRef.current[uuid] = true;
    setSerialOptionsLoadingUuid(uuid);
    try {
      const opts = await loadInStockSerialOptions(uuid);
      setSerialOptionsByUuid((prev) => ({ ...prev, [uuid]: opts }));
    } catch {
      setSerialOptionsByUuid((prev) => ({ ...prev, [uuid]: [] }));
    } finally {
      serialOptionsLoadingRef.current[uuid] = false;
      setSerialOptionsLoadingUuid((cur) => (cur === uuid ? null : cur));
    }
  }, [serialOptionsByUuid]);

  const applyMaterialBatchFlags = useCallback(
    async (idx: number, material: Material | undefined) => {
      if (!material) return;
      const uuid = material.uuid;
      let batchManaged = material.batchManaged ?? false;
      let serialManaged = material.serialManaged ?? false;
      let defaultBatchRuleId = material.defaultBatchRuleId;
      if (uuid) {
        try {
          const full = await materialApi.get(uuid);
          batchManaged = full.batchManaged ?? false;
          serialManaged = full.serialManaged ?? false;
          defaultBatchRuleId = full.defaultBatchRuleId;
        } catch {
          // 使用列表返回的字段
        }
      }
      formRef.current?.setFieldValue(['items', idx, 'material_uuid'], uuid);
      formRef.current?.setFieldValue(
        ['items', idx, 'batch_managed'],
        isMaterialBatchEntryEnabled(trackingFlags, batchManaged),
      );
      formRef.current?.setFieldValue(
        ['items', idx, 'serial_managed'],
        isMaterialSerialEntryEnabled(trackingFlags, serialManaged),
      );
      formRef.current?.setFieldValue(['items', idx, 'default_batch_rule_id'], defaultBatchRuleId);
    },
    [trackingFlags],
  );

  const executeConfirmOutbound = useCallback(
    async (record: OtherOutbound) => {
      if (record.id == null) return;
      try {
        const confirmed = await runOutboundHubConfirmFromRecord({
          t,
          record: { id: record.id, outbound_type: 'other_outbound' },
          trackingFlags,
        });
        messageApi.success(t('app.kuaizhizao.warehouseOutbound.confirm.success'));
        if (confirmed.externalPushMessage) {
          messageApi.warning(confirmed.externalPushMessage);
        }
        invalidateMenuBadgeCounts();
        actionRef.current?.reload();
      } catch (error: unknown) {
        messageApi.error(formatOutboundConfirmError(error, t));
        throw error;
      }
    },
    [invalidateMenuBadgeCounts, messageApi, t, trackingFlags],
  );

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
      const key = `${mid}:${whId}`;
      setBatchOptionsLoadingKey(key);
      try {
        const map = await loadBatchOptionsByMaterialId([mid], whId, batchOptionLabel);
        setBatchOptionsByKey((prev) => ({ ...prev, [key]: map[mid] ?? [] }));
      } finally {
        setBatchOptionsLoadingKey((cur) => (cur === key ? null : cur));
      }
    },
    [batchOptionLabel],
  );

  useEffect(() => {
    if (!createModalVisible) {
      setStockByKey({});
      setStockLoading(false);
      setLineStockKey('');
      setBatchOptionsByKey({});
      setBatchOptionsLoadingKey(null);
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
  }, [createModalVisible, lineStockKey]);

  const fallbackReasonTypeOptions = useMemo(
    () => mapOtherOutboundReasonTypeOptions(REASON_TYPES_FALLBACK, t),
    [t],
  );

  useEffect(() => {
    setReasonTypeOptions(fallbackReasonTypeOptions);
  }, [fallbackReasonTypeOptions]);

  useEffect(() => {
    const loadReasonType = async () => {
      setReasonTypeLoading(true);
      try {
        const dictList = await getDataDictionaryList({
          code: 'OUTBOUND_REASON_TYPE',
          page: 1,
          page_size: 1,
        });
        const dict = dictList.items?.[0];
        if (!dict) {
          setReasonTypeOptions(fallbackReasonTypeOptions);
          return;
        }
        const items = await getDictionaryItemList(dict.uuid, true);
        const sorted = items.sort((a, b) => a.sort_order - b.sort_order).map((it) => ({ label: it.label, value: it.value }));
        setReasonTypeOptions(mapOtherOutboundReasonTypeOptions(sorted, t));
      } catch {
        setReasonTypeOptions(fallbackReasonTypeOptions);
      } finally {
        setReasonTypeLoading(false);
      }
    };
    loadReasonType();
  }, [fallbackReasonTypeOptions, t]);

  const otherOutboundCustomFieldColumns = generateOtherOutboundCustomFieldColumns();
  const otherOutboundStatusValueEnum = useMemo(() => buildOtherOutboundStatusValueEnum(t), [t]);

  const handleDetail = useCallback(
    async (record: OtherOutbound) => {
      setDetailDrawerVisible(true);
      setDetailLoading(true);
      setOutboundDetail(null);
      resetOtherOutboundDetailFieldValues();
      try {
        const detail = await warehouseApi.otherOutbound.get(record.id!.toString());
        setOutboundDetail(detail as OtherOutboundDetail);
        if (record.id != null) {
          await loadOtherOutboundFieldValuesForDetail(record.id);
        }
      } catch {
        messageApi.error(t('app.kuaizhizao.otherOutbound.msg.loadDetailFailed'));
        setDetailDrawerVisible(false);
      } finally {
        setDetailLoading(false);
      }
    },
    [
      loadOtherOutboundFieldValuesForDetail,
      messageApi,
      resetOtherOutboundDetailFieldValues,
      t,
    ],
  );

  const handleEdit = useCallback((record: OtherOutbound) => {
    if (record.id == null || !isOutboundEditable({ ...record, outbound_type: 'other_outbound' })) {
      return;
    }
    setEditingOutboundId(record.id);
    setEditingOutboundCode(String(record.outbound_code ?? '').trim());
    setCreateModalVisible(true);
  }, []);

  const columns: ProColumns<OtherOutbound>[] = useMemo(() => alignProColumns<OtherOutbound>([
    {
      title: t('common.updatedAt'),
      dataIndex: 'updated_at_range',
      valueType: 'dateRange',
      hideInTable: true,
      formItemProps: formDateRangeFormItemProps,
      search: { order: 10 } as ProColumns['search'],
    },
    {
      title: t('common.status'),
      dataIndex: 'status',
      valueType: 'select',
      valueEnum: otherOutboundStatusValueEnum,
      hideInTable: true,
      search: { order: 20 } as ProColumns['search'],
    },
    {
      title: t('app.kuaizhizao.otherOutbound.col.reasonType'),
      dataIndex: 'reason_type',
      valueType: 'select',
      fieldProps: { options: reasonTypeOptions, loading: reasonTypeLoading },
      hideInTable: true,
      search: { order: 30 } as ProColumns['search'],
    },
    {
      title: t('app.kuaizhizao.otherOutbound.col.deliveryTime'),
      dataIndex: 'doc_date_range',
      valueType: 'dateRange',
      hideInTable: true,
      formItemProps: formDateRangeFormItemProps,
      search: { order: 40 } as ProColumns['search'],
    },
    {
      title: t('app.kuaizhizao.otherOutbound.col.outboundCode'),
      dataIndex: 'outbound_code',
      width: 160,
      minWidth: 160,
      uniTableKeepWidth: true,
      resizable: false,
      ellipsis: true,
      fixed: 'left',
      sorter: true,
      search: { order: 50 } as ProColumns['search'],
      render: (_, r) => (
        <Typography.Text copyable={{ text: String(r.outbound_code ?? '') }} ellipsis>
          {r.outbound_code ?? '-'}
        </Typography.Text>
      ),
    },
    {
      title: t('app.kuaizhizao.warehouseReports.colWarehouse'),
      dataIndex: 'warehouse_name',
      width: 160,
      minWidth: 160,
      uniTableKeepWidth: true,
      resizable: false,
      ellipsis: true,
      sorter: true,
      hideInSearch: true,
      render: (_, r) =>
        r.warehouse_name != null && r.warehouse_name !== '' ? String(r.warehouse_name) : '-',
    },
    {
      title: t('app.kuaizhizao.otherOutbound.col.outboundType'),
      dataIndex: 'outbound_type',
      width: 108,
      minWidth: 108,
      uniTableKeepWidth: true,
      resizable: false,
      sorter: true,
      hideInSearch: true,
      render: (_, r) => renderOtherOutboundTypeMarkerTag(t, r.outbound_type),
    },
    {
      title: t('app.kuaizhizao.otherOutbound.col.reasonType'),
      dataIndex: 'reason_type',
      ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
      sorter: true,
      hideInSearch: true,
      render: (v) =>
        renderWarehouseReasonTypeMarkerTag(
          translateOtherOutboundReasonTypeLabel(t, v as string | undefined, reasonTypeOptions),
          v as string | undefined,
        ),
    },
    {
      title: t('app.kuaizhizao.common.colLineMaterials'),
      ...DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
      render: (_, r) => renderDocumentLineMaterialsPreview(r.items, t),
    },
    {
      title: t('app.kuaizhizao.warehouseCommon.colTotalQuantity'),
      dataIndex: 'total_quantity',
      width: 100,
      minWidth: 100,
      uniTableKeepWidth: true,
      resizable: false,
      sorter: true,
      hideInSearch: true,
      render: (_, r) => formatQuantity(r.total_quantity),
    },
    {
      title: t('app.kuaizhizao.otherOutbound.field.pickDate'),
      dataIndex: 'pick_date',
      width: 120,
      minWidth: 120,
      uniTableKeepWidth: true,
      resizable: false,
      sorter: true,
      hideInSearch: true,
      render: (_, r) => formatBusinessDateOnly(r.pick_date) || '—',
    },
    {
      title: t('app.kuaizhizao.otherOutbound.col.deliverer'),
      dataIndex: 'deliverer_name',
      width: 100,
      minWidth: 100,
      uniTableKeepWidth: true,
      resizable: false,
      ellipsis: true,
      sorter: true,
      hideInSearch: true,
      render: (_, r) =>
        r.deliverer_name != null && r.deliverer_name !== '' ? String(r.deliverer_name) : '-',
    },
    {
      title: t('app.kuaizhizao.otherOutbound.col.deliveryTime'),
      dataIndex: 'delivery_time',
      width: 132,
      minWidth: 132,
      uniTableKeepWidth: true,
      resizable: false,
      sorter: true,
      hideInSearch: true,
      render: (_, r) => (r.delivery_time ? formatDateTime(r.delivery_time) : '-'),
    },
    ...buildDocumentAuditColumns<Record<string, unknown>>(t),
    otherOutboundAuditColumn,
    {
      title: t('app.kuaizhizao.warehouseOutbound.col.lifecycle'),
      dataIndex: 'lifecycle_stage',
      fixed: 'right',
      hideInSearch: true,
      render: (_, record) => {
        const lifecycle = getOtherOutboundLifecycle(record as Record<string, unknown>, t);
        return (
          <UniLifecycle
            percent={lifecycle.percent}
            stageName={lifecycle.stageName}
            status={lifecycle.status}
            subStages={lifecycle.subStages}
            showLabel
            size="small"
            showCircleTooltip={false}
          />
        );
      },
    },
    ...otherOutboundCustomFieldColumns,
    {
      title: t('common.actions'),
      key: 'option',
      fixed: 'right',
      hideInSearch: true,
      render: (_, record) => {
        const actions: React.ReactNode[] = [
          <Button key="detail" {...rowActionKind('read')} onClick={() => handleDetail(record)} />,
        ];
        if (canUpdateOutbound && isOutboundEditable({ ...record, outbound_type: 'other_outbound' })) {
          actions.push(
            <Button
              key="edit"
              {...rowActionKind('update')}
              onClick={(e) => {
                e.stopPropagation();
                handleEdit(record);
              }}
            />,
          );
        }
        return <Space>{actions}</Space>;
      },
    },
  ], WAREHOUSE_DOC_LIST_FIELD_RANK), [
    t,
    otherOutboundAuditColumn,
    otherOutboundCustomFieldColumns,
    otherOutboundStatusValueEnum,
    reasonTypeOptions,
    reasonTypeLoading,
    canUpdateOutbound,
    handleDetail,
    handleEdit,
  ]);

  const executeWithdraw = async (record: OtherOutbound) => {
    try {
      const kingdeeWarn = readExternalWithdrawMessage(
        await warehouseApi.otherOutbound.withdraw(record.id!.toString()),
      );
      if (kingdeeWarn) {
        messageApi.warning(kingdeeWarn);
      }
      messageApi.success(t('app.kuaizhizao.otherOutbound.msg.withdrawSuccess'));
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error.message || t('app.kuaizhizao.otherOutbound.msg.withdrawFailed'));
    }
  };

  const handlePrint = (record: OtherOutbound) => {
    if (!record.id) return;
    openPrint({ documentType: 'other_outbound', documentId: record.id });
  };

  const executeDelete = async (record: OtherOutbound) => {
    try {
      await warehouseApi.otherOutbound.delete(record.id!.toString());
      messageApi.success(t('common.deleteSuccess'));
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error.message || t('common.deleteFailed'));
    }
  };

  const listRowsRef = useRef<Map<string, OtherOutbound>>(new Map());
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const isOtherOutboundDeletable = (record: OtherOutbound) => record.status === '待出库' && !!record.id;
  const isOtherOutboundPrintable = (record: OtherOutbound) =>
    record.status === '已出库' && !!record.id;

  const selectedOtherOutboundForBatch = useMemo(
    () =>
      selectedRowKeys
        .map((key) => listRowsRef.current.get(String(key)))
        .filter((row): row is OtherOutbound => row != null),
    [selectedRowKeys],
  );

  const selectedOtherOutboundCapabilityRows = useMemo(
    () =>
      selectedOtherOutboundForBatch.map((row) => ({
        ...row,
        capabilities: {
          confirm: { allowed: row.status === '待出库' },
          withdraw: { allowed: row.status === '已出库' },
        },
      })),
    [selectedOtherOutboundForBatch],
  );

  const reloadOtherOutboundAfterCapability = useCallback(() => {
    setSelectedRowKeys([]);
    invalidateMenuBadgeCounts();
    actionRef.current?.reload();
  }, [invalidateMenuBadgeCounts]);

  const selectedOtherOutboundIdsForDocumentPush = useMemo(
    () =>
      selectedOtherOutboundForBatch
        .filter((row) => Number(row.id) > 0)
        .map((row) => Number(row.id)),
    [selectedOtherOutboundForBatch],
  );

  const getOtherOutboundReconcileDocumentIds = useCallback(() => {
    if (selectedOtherOutboundIdsForDocumentPush.length) {
      return selectedOtherOutboundIdsForDocumentPush;
    }
    return [...listRowsRef.current.values()]
      .filter((row) => Number(row.id) > 0)
      .map((row) => Number(row.id));
  }, [selectedOtherOutboundIdsForDocumentPush]);

  const canToolbarPrint =
    selectedRowKeys.length === 1 &&
    !!selectedOtherOutboundForBatch[0] &&
    isOtherOutboundPrintable(selectedOtherOutboundForBatch[0]);

  const handleBatchDelete = async (keys: React.Key[]) => {
    const rows = keys
      .map((k) => listRowsRef.current.get(String(k)))
      .filter((r): r is OtherOutbound => !!r && isOtherOutboundDeletable(r));
    if (rows.length === 0) {
      messageApi.warning(t('app.kuaizhizao.warehouseCommon.batchDeleteNoneDeletable'));
      return;
    }
    try {
      for (const row of rows) {
        await warehouseApi.otherOutbound.delete(String(row.id));
      }
      messageApi.success(t('app.kuaizhizao.warehouseCommon.deleteSuccess', { count: rows.length }));
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error.message || t('app.kuaizhizao.warehouseCommon.batchDeleteFailed'));
    }
  };

  const appendOtherOutboundItemsFromMaterials = useCallback(
    (selected: Material[]) => {
      const current = formRef.current?.getFieldValue('items') ?? [];
      const newRows = selected.map((m) => {
        const primaryWh = resolvePrimaryDefaultWarehouse(m);
        return {
          ...defaultOutboundItem,
          material_id: m.id,
          material_code: m.mainCode ?? m.code ?? '',
          material_name: m.name ?? '',
          material_spec: m.specification ?? '',
          material_model: m.model ?? '',
          material_unit: resolveMaterialScenarioUnit(m, 'inventory'),
          warehouse_id: primaryWh?.id,
          warehouse_name: primaryWh?.name,
          batch_managed: isMaterialBatchEntryEnabled(trackingFlags, !!m.batchManaged),
        };
      });
      const nextItems = [...current, ...newRows];
      formRef.current?.setFieldsValue({ items: nextItems });
      setLineStockKey(otherOutboundStockFingerprint(nextItems));
      messageApi.success(t('app.kuaizhizao.common.materialBatchAdded', { count: selected.length }));
    },
    [messageApi, t, trackingFlags],
  );

  const formItemColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.warehouseOutbound.field.material'),
        dataIndex: 'material_id',
        width: DOCUMENT_DETAIL_COL_WIDTH.material,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <div className="uni-detail-material-cell">
            <AntForm.Item name={[index, 'id']} hidden preserve>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'material_code']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'material_name']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name={[index, 'batch_managed']} hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item noStyle shouldUpdate={(prev: any, curr: any) => prev?.items?.[index] !== curr?.items?.[index]}>
              {({ getFieldValue }: any) => {
                const row = getFieldValue('items')?.[index];
                const mid = row?.material_id ? Number(row.material_id) : null;
                const fallback =
                  mid && (row?.material_code || row?.material_name)
                    ? {
                        value: mid,
                        label:
                          `${row.material_code || ''} - ${row.material_name || ''}`.trim() ||
                          String(mid),
                      }
                    : undefined;
                return (
                  <UniMaterialSelect
                    name={[index, 'material_id']}
                    label=""
                    placeholder={t('app.kuaizhizao.warehouseOutbound.field.selectMaterial')}
                    required
                    size={DOCUMENT_DETAIL_CONTROL_SIZE}
                    listFieldKey={index}
                    listFieldName="items"
                    warehouseId={
                      Number(row?.warehouse_id) > 0 ? Number(row.warehouse_id) : undefined
                    }
                    fillMapping={withMaterialLineFillMapping({ material_unit: 'inventoryUnit' })}
                    onChange={async (_val, material) => {
                      clearLineWarehouseDependents(index);
                      formRef.current?.setFieldValue(['items', index, 'warehouse_id'], undefined);
                      formRef.current?.setFieldValue(['items', index, 'warehouse_name'], undefined);
                      if (material) {
                        formRef.current?.setFieldValue(
                          ['items', index, 'material_unit'],
                          resolveMaterialScenarioUnit(material, 'inventory'),
                        );
                        await applyMaterialBatchFlags(index, material);
                        const primaryWh = resolvePrimaryDefaultWarehouse(material);
                        if (primaryWh) {
                          formRef.current?.setFieldValue(
                            ['items', index, 'warehouse_id'],
                            primaryWh.id,
                          );
                          formRef.current?.setFieldValue(
                            ['items', index, 'warehouse_name'],
                            primaryWh.name,
                          );
                        }
                        const midNum = Number(_val ?? material.id ?? 0);
                        const whId = Number(
                          formRef.current?.getFieldValue(['items', index, 'warehouse_id']) || 0,
                        );
                        if (midNum > 0 && whId > 0) {
                          void ensureBatchOptions(midNum, whId);
                        }
                      }
                      syncLineStockKeyFromForm();
                    }}
                    fallbackOption={fallback}
                    formItemProps={{ style: { margin: 0 } }}
                    showQuickCreate
                    showAdvancedSearch
                  />
                );
              }}
            </AntForm.Item>
          </div>
        ),
      },
      ...buildDocumentDetailSpecModelFormColumns(t),
      ...buildDocumentLineDualQuantityPairColumns({
        t,
        getForm: () => formRef.current,
        quantityField: 'outbound_quantity',
        unitField: 'material_unit',
        scenario: 'inventory',
        quantityPrecision: quantityDecimals,
        columnSpread: DOCUMENT_DETAIL_NUM_COL,
        inlineUnitWithQuantity: true,
      }),
      {
        title: t('app.kuaizhizao.warehouseOutbound.field.warehouse'),
        dataIndex: 'warehouse_id',
        width: 220,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <OtherOutboundCreateWarehouseCell
            index={index}
            clearLineWarehouseDependents={clearLineWarehouseDependents}
            ensureBatchOptions={ensureBatchOptions}
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
              prev?.items?.[index]?.outbound_quantity !== curr?.items?.[index]?.outbound_quantity
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
              const qty = Number(getFieldValue(['items', index, 'outbound_quantity']) || 0);
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
          <OtherOutboundCreateLocationCell index={index} formRef={formRef} t={t} />
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
              prev?.items?.[index]?.outbound_quantity !==
                curr?.items?.[index]?.outbound_quantity ||
              prev?.items?.[index]?.batch_allocations !==
                curr?.items?.[index]?.batch_allocations ||
              prev?.items?.[index]?.batch_number !== curr?.items?.[index]?.batch_number
            }
          >
            {({ getFieldValue }) => {
              const row = getFieldValue('items')?.[index] as Record<string, unknown> | undefined;
              if (!row?.batch_managed) return '—';
              const materialId = Number(row?.material_id ?? 0);
              const whId = Number(row?.warehouse_id ?? 0);
              const key = materialId > 0 && whId > 0 ? `${materialId}:${whId}` : '';
              const opts = key ? batchOptionsByKey[key] ?? [] : [];
              const loading = !!key && batchOptionsLoadingKey === key;
              const qty = Number(row?.outbound_quantity ?? 0);
              const allocs = lineBatchAllocationsFromRow(row, qty);
              const materialLabel = [row?.material_code, row?.material_name]
                .filter(Boolean)
                .join(' - ');
              const disabled = !(whId > 0) || !(materialId > 0);
              return (
                <span
                  onClick={() => {
                    if (!disabled && materialId > 0 && whId > 0 && !batchOptionsByKey[key]?.length) {
                      void ensureBatchOptions(materialId, whId);
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
                      syncFormLineBatchFields(
                        (name, value) => formRef.current?.setFieldValue(name, value),
                        index,
                        next,
                      )
                    }
                    options={opts}
                    totalQuantity={qty}
                    loading={loading}
                    disabled={disabled}
                    materialLabel={String(materialLabel)}
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
              const qty = Number(row?.outbound_quantity ?? 0);
              const sn = getFieldValue(['items', index, 'serial_numbers']);
              const uuid = String(row?.material_uuid ?? '').trim();
              const serials = Array.isArray(sn)
                ? sn.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
                : [];
              return (
                <>
                  <AntForm.Item name={[index, 'serial_numbers']} hidden>
                    <Input />
                  </AntForm.Item>
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
                </>
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
          <AntForm.Item name={[index, 'unit_price']} style={{ margin: 0 }}>
            <UniInputNumber
              placeholder="0"
              min={0}
              precision={priceDecimals}
              style={{ width: '100%' }}
              size={DOCUMENT_DETAIL_CONTROL_SIZE}
            />
          </AntForm.Item>
        ),
      },
    ],
    [
      applyMaterialBatchFlags,
      batchOptionsByKey,
      batchOptionsLoadingKey,
      clearLineWarehouseDependents,
      ensureBatchOptions,
      priceDecimals,
      quantityDecimals,
      stockByKey,
      stockLoading,
      syncLineStockKeyFromForm,
      t,
      trackingFlags,
      ensureSerialOptions,
      serialOptionsByUuid,
      serialOptionsLoadingUuid,
    ],
  );

  /** 参考销售订单：先打开弹窗，再让 CodeField 自动生成编号 */
  const handleCreate = () => {
    setEditingOutboundId(null);
    setEditingOutboundCode('');
    editLineIdsRef.current = [];
    setCreateModalVisible(true);
    // FormModalTemplate 设置了 destroyOnHidden，ProForm 每次打开都是全新挂载，无需 setTimeout + resetFields
  };

  useEffect(() => {
    if (!createModalVisible || editingOutboundId == null) {
      return undefined;
    }
    let cancelled = false;
    void (async () => {
      try {
        const detail = (await warehouseApi.otherOutbound.get(String(editingOutboundId))) as OtherOutboundDetail;
        if (cancelled) return;
        const custom = await loadOtherOutboundFormFieldValues(editingOutboundId);
        const items = (detail.items ?? []).map((it) => ({
          id: it.id,
          material_id: it.material_id,
          material_code: it.material_code,
          material_name: it.material_name,
          material_spec: it.material_spec,
          material_unit: it.material_unit,
          outbound_quantity: it.outbound_quantity,
          aux_quantity: (it as { aux_quantity?: number }).aux_quantity,
          aux_unit: (it as { aux_unit?: string }).aux_unit,
          unit_conversion_rate: (it as { unit_conversion_rate?: number }).unit_conversion_rate,
          unit_price: it.unit_price,
          warehouse_id: it.warehouse_id,
          warehouse_name: it.warehouse_name,
          location_id: it.location_id,
          location_code: it.location_code,
          batch_number: it.batch_number,
          serial_numbers: Array.isArray((it as { serial_numbers?: unknown }).serial_numbers)
            ? ((it as { serial_numbers: string[] }).serial_numbers ?? [])
                .map((s) => String(s ?? '').trim())
                .filter(Boolean)
            : undefined,
          notes: it.notes,
        }));
        formRef.current?.setFieldsValue({
          outbound_code: detail.outbound_code,
          outbound_type: detail.outbound_type ? detail.outbound_type : undefined,
          reason_type: detail.reason_type,
          pick_date: detail.pick_date ? dayjs(String(detail.pick_date)) : dayjs(todaySiteDateString()),
          picker_id: detail.picker_id,
          picker_name: detail.picker_name,
          picker_operator_number: detail.picker_operator_number,
          pick_department_id: detail.pick_department_id,
          pick_department_code: detail.pick_department_code,
          pick_department_name: detail.pick_department_name,
          customer_id: detail.customer_id,
          customer_name: detail.customer_name,
          customer_number: detail.customer_number,
          notes: detail.notes,
          attachments: detail.attachments,
          items: items.length ? items : [{ ...defaultOutboundItem }],
          ...custom,
        });
        editLineIdsRef.current = items.map((row) => Number(row.id) || 0);
        setEditingOutboundCode(String(detail.outbound_code ?? '').trim());
        setLineStockKey(otherOutboundStockFingerprint(items));
        await Promise.all(
          items
            .filter((it) => Number(it.material_id) > 0 && Number(it.warehouse_id) > 0)
            .map((it) => ensureBatchOptions(Number(it.material_id), Number(it.warehouse_id))),
        );
        for (const [idx, it] of items.entries()) {
          const mid = Number(it.material_id);
          if (!(mid > 0)) continue;
          const uuid = String(formRef.current?.getFieldValue(['items', idx, 'material_uuid']) ?? '').trim();
          if (uuid) {
            const serials = Array.isArray(it.serial_numbers) ? it.serial_numbers : undefined;
            await ensureSerialOptions(uuid, serials);
          }
        }
      } catch {
        if (!cancelled) {
          messageApi.error(t('app.kuaizhizao.otherOutbound.msg.loadDetailFailed'));
          setCreateModalVisible(false);
          setEditingOutboundId(null);
          setEditingOutboundCode('');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    createModalVisible,
    editingOutboundId,
    ensureBatchOptions,
    ensureSerialOptions,
    loadOtherOutboundFormFieldValues,
    messageApi,
    t,
  ]);
  useNewShortcut(handleCreate);
  const createButtonLabel = useMemo(
    () => withSingleNewShortcutHint(t('app.kuaizhizao.otherOutbound.create')),
    [t],
  );

  const otherOutboundFormTitle = useMemo(() => {
    if (editingOutboundId != null) {
      const code = editingOutboundCode.trim();
      return code
        ? `${t('app.kuaizhizao.otherOutbound.editModal')} - ${code}`
        : t('app.kuaizhizao.otherOutbound.editModal');
    }
    return t('app.kuaizhizao.otherOutbound.createModal');
  }, [editingOutboundCode, editingOutboundId, t]);

  const resolveEditLineId = (row: Record<string, unknown>, lineIndex: number): number => {
    const fromRow = Number(row.id);
    if (fromRow > 0) return fromRow;
    const fromForm = Number(formRef.current?.getFieldValue(['items', lineIndex, 'id']));
    if (fromForm > 0) return fromForm;
    const fromSnapshot = editLineIdsRef.current[lineIndex];
    return fromSnapshot > 0 ? fromSnapshot : 0;
  };

  const handleCreateSubmit = async (values: any) => {
    const needValidLinesMsg = t('app.kuaizhizao.otherOutbound.msg.needValidLines');
    try {
      const rawItems = (values.items ?? []) as Record<string, unknown>[];
      const validItems = rawItems
        .map((it, index) => {
          if (!(it.material_id && (Number(it.outbound_quantity) || 0) > 0)) return null;
          if (editingOutboundId == null) return it;
          const lineId = resolveEditLineId(it, index);
          return lineId > 0 ? { ...it, id: lineId } : it;
        })
        .filter(Boolean) as Record<string, unknown>[];
      if (!validItems.length) {
        messageApi.error(needValidLinesMsg);
        throw new Error(needValidLinesMsg);
      }
      for (const it of validItems) {
        const material = it.material_code || it.material_name || '-';
        if (!(Number(it.warehouse_id) > 0)) {
          const msg = t('app.kuaizhizao.warehouseOutbound.msg.selectWarehouse');
          messageApi.error(msg);
          throw new Error(msg);
        }
        if (!String(it.location_code || '').trim()) {
          const msg = t('app.kuaizhizao.warehouseOutbound.msg.selectLocationForMaterial', {
            material,
          });
          messageApi.error(msg);
          throw new Error(msg);
        }
        const qty = Number(it.outbound_quantity) || 0;
        const allocs = lineBatchAllocationsFromRow(it as Record<string, unknown>, qty);
        if (it.batch_managed) {
          const materialId = Number(it.material_id) || 0;
          const whId = Number(it.warehouse_id) || 0;
          const key = materialId > 0 && whId > 0 ? `${materialId}:${whId}` : '';
          const opts = key ? batchOptionsByKey[key] ?? [] : [];
          if (!isValidOutboundBatchAllocations(allocs, opts, qty)) {
            const msg = t('app.kuaizhizao.warehouseOutbound.confirm.batchAllocationRequired', {
              material,
              qty,
              batches: opts.map((o) => o.value).join('、') || '—',
            });
            messageApi.error(msg);
            throw new Error(msg);
          }
        }
        const serialManaged = !!it.serial_managed;
        if (isMaterialSerialEntryEnabled(trackingFlags, serialManaged)) {
          const serials = Array.isArray(it.serial_numbers)
            ? it.serial_numbers.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
            : [];
          const required = Math.round(qty);
          if (serials.length !== required) {
            const msg = t('app.kuaizhizao.warehouseOutbound.entry.serialCountMismatch', {
              material,
              required,
              actual: serials.length,
            });
            messageApi.error(msg);
            throw new Error(msg);
          }
          if (allocs.length > 1) {
            const msg = t('app.kuaizhizao.warehouseOutbound.confirm.batchSerialMultiNotSupported', {
              material,
            });
            messageApi.error(msg);
            throw new Error(msg);
          }
        }
        const dualErr = validateDualQuantityBeforeSave({
          material: (it as { material?: Material }).material ?? null,
          value: {
            quantity: Number(it.outbound_quantity),
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
      const { standardValues, customData } = extractOtherOutboundFormValues(values);

      if (editingOutboundId != null) {
        const withoutId = validItems.filter((it: { id?: number }) => !(Number(it.id) > 0));
        if (withoutId.length > 0) {
          const msg = t('app.kuaizhizao.otherOutbound.msg.editKeepExistingLinesOnly');
          messageApi.error(msg);
          throw new Error(msg);
        }
        const updateItems = validItems.map((it: Record<string, unknown>) => {
          const rid = Number(it.id);
          const qty = Number(it.outbound_quantity) || 0;
          const allocs = lineBatchAllocationsFromRow(it, qty);
          const payload: Record<string, unknown> = {
            id: rid,
            outbound_quantity: qty,
            unit_price: Number(it.unit_price) || 0,
            location_id:
              it.location_id != null && Number(it.location_id) > 0 ? Number(it.location_id) : undefined,
            location_code: String(it.location_code ?? '').trim() || undefined,
            ...pickDocumentLineDualQuantityFields(it),
          };
          if (allocs.length > 1) {
            payload.batch_allocations = allocs.map((a) => ({
              batch_number: a.batchNo,
              quantity: a.quantity,
            }));
            payload.batch_number = allocs[0]?.batchNo;
          } else if (allocs.length === 1) {
            payload.batch_number = allocs[0].batchNo;
          } else {
            payload.batch_number = String(it.batch_number ?? '').trim() || undefined;
          }
          if (isMaterialSerialEntryEnabled(trackingFlags, !!it.serial_managed)) {
            const serials = Array.isArray(it.serial_numbers)
              ? it.serial_numbers.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
              : [];
            if (serials.length) {
              payload.serial_numbers = serials;
            }
          }
          return payload;
        });
        const updateOutboundType = String(values.outbound_type ?? '').trim();
        if (!updateOutboundType) {
          const msg = t('app.kuaizhizao.otherOutbound.field.outboundTypeRequired');
          messageApi.error(msg);
          throw new Error(msg);
        }
        await warehouseApi.otherOutbound.update(String(editingOutboundId), {
          outbound_type: updateOutboundType,
          reason_type: standardValues.reason_type,
          warehouse_id: headerWhId,
          warehouse_name: headerWhName,
          pick_department_id: values.pick_department_id ?? undefined,
          pick_department_code: values.pick_department_code || undefined,
          pick_department_name: values.pick_department_name || undefined,
          picker_id: values.picker_id ?? undefined,
          picker_name: values.picker_name || undefined,
          pick_date: toApiDateString(values.pick_date),
          picker_operator_number: String(values.picker_operator_number ?? '').trim() || undefined,
          customer_id: values.customer_id ?? undefined,
          customer_name: values.customer_name || undefined,
          customer_number: values.customer_number || undefined,
          notes: standardValues.notes,
          attachments: normalizeDocumentAttachments(standardValues.attachments),
          items: updateItems,
        });
        if (Object.keys(customData).length > 0) {
          await saveOtherOutboundCustomFieldValues(editingOutboundId, customData);
        }
        messageApi.success(t('common.updateSuccess'));
        resetOtherOutboundFormFieldValues();
        setCreateModalVisible(false);
        setEditingOutboundId(null);
        setEditingOutboundCode('');
        invalidateMenuBadgeCounts();
        actionRef.current?.reload();
        return;
      }

      const created = await warehouseApi.otherOutbound.create({
        outbound_code: standardValues.outbound_code,
        outbound_type: String(values.outbound_type ?? OTHER_OUTBOUND_TYPE_MATERIAL).trim(),
        reason_type: standardValues.reason_type,
        // 表头仓仅列表汇总：取首行；真源在明细行
        warehouse_id: headerWhId,
        warehouse_name: headerWhName,
        pick_department_id: values.pick_department_id ?? undefined,
        pick_department_code: values.pick_department_code || undefined,
        pick_department_name: values.pick_department_name || undefined,
        picker_id: values.picker_id ?? undefined,
        picker_name: values.picker_name || undefined,
        pick_date: toApiDateString(values.pick_date),
        picker_operator_number: String(values.picker_operator_number ?? '').trim() || undefined,
        customer_id: values.customer_id ?? undefined,
        customer_name: values.customer_name || undefined,
        customer_number: values.customer_number || undefined,
        notes: standardValues.notes,
        attachments: normalizeDocumentAttachments(standardValues.attachments),
        items: validItems.flatMap((it: any) => {
          const outboundQty = Number(it.outbound_quantity) || 0;
          const unitPrice = Number(it.unit_price) || 0;
          const lineWhId = Number(it.warehouse_id) || 0;
          const allocs = lineBatchAllocationsFromRow(it as Record<string, unknown>, outboundQty);
          const serials =
            isMaterialSerialEntryEnabled(trackingFlags, !!it.serial_managed) &&
            Array.isArray(it.serial_numbers)
              ? it.serial_numbers.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
              : undefined;
          const base = {
            material_id: it.material_id,
            material_code: it.material_code || undefined,
            material_name: it.material_name || undefined,
            material_spec: it.material_spec != null ? String(it.material_spec).trim() || undefined : undefined,
            material_unit: it.material_unit || '',
            ...pickDocumentLineDualQuantityFields(it as Record<string, unknown>),
            warehouse_id: lineWhId,
            warehouse_name: String(it.warehouse_name ?? '').trim() || undefined,
            location_id:
              it.location_id != null && Number(it.location_id) > 0
                ? Number(it.location_id)
                : undefined,
            location_code: it.location_code || undefined,
            unit_price: unitPrice,
            ...(serials?.length ? { serial_numbers: serials } : {}),
          };
          if (allocs.length > 1) {
            return allocs.map((a) => ({
              ...base,
              outbound_quantity: a.quantity,
              total_amount: computeSimpleDocumentLineTotal(a.quantity, unitPrice),
              batch_number: a.batchNo,
            }));
          }
          return [
            {
              ...base,
              outbound_quantity: outboundQty,
              total_amount: computeSimpleDocumentLineTotal(outboundQty, unitPrice),
              batch_number: allocs[0]?.batchNo || it.batch_number || undefined,
            },
          ];
        }),
      });
      const recordId = Number((created as { id?: number })?.id ?? 0);
      if (recordId > 0 && Object.keys(customData).length > 0) {
        await saveOtherOutboundCustomFieldValues(recordId, customData);
      }
      messageApi.success(t('common.createSuccess'));
      resetOtherOutboundFormFieldValues();
      setCreateModalVisible(false);
      invalidateMenuBadgeCounts();

      actionRef.current?.reload();
    } catch (error: any) {
      if (error.message !== needValidLinesMsg) messageApi.error(error.message || t('common.createFailed'));
      throw error;
    }
  };

  const detailColumns = useMemo(() => alignDescriptionColumns([
    { title: t('app.kuaizhizao.otherOutbound.col.outboundCode'), dataIndex: 'outbound_code' },
    {
      title: t('app.kuaizhizao.warehouse.field.kingdeeBillNo'),
      key: 'kingdee_bill_no',
      dataIndex: 'kingdee_bill_no',
      render: (_, record) => {
        const display = String(record.kingdee_bill_no || '').trim();
        return display || '—';
      },
    },
    {
      title: t('app.kuaizhizao.otherOutbound.col.outboundType'),
      dataIndex: 'outbound_type',
      render: (_, record) => translateOtherOutboundTypeLabel(t, record.outbound_type),
    },
    {
      title: t('app.kuaizhizao.otherOutbound.col.reasonType'),
      dataIndex: 'reason_type',
      render: (_, record) =>
        renderWarehouseReasonTypeMarkerTag(
          translateOtherOutboundReasonTypeLabel(t, record.reason_type, reasonTypeOptions),
          record.reason_type,
        ),
    },
    { title: t('app.kuaizhizao.otherOutbound.field.picker'), dataIndex: 'picker_name' },
    {
      title: t('app.kuaizhizao.otherOutbound.field.pickDate'),
      dataIndex: 'pick_date',
      render: (_, r) => formatBusinessDateOnly(r.pick_date) || '—',
    },
    {
      title: t('app.kuaizhizao.otherOutbound.field.pickDepartment'),
      dataIndex: 'pick_department_name',
      render: (_, r) =>
        r.pick_department_code
          ? `${r.pick_department_code} ${r.pick_department_name || ''}`.trim()
          : r.pick_department_name || '-',
    },
    { title: t('app.kuaizhizao.otherOutbound.field.customer'), dataIndex: 'customer_name' },
    { title: t('app.kuaizhizao.warehouseReports.colWarehouse'), dataIndex: 'warehouse_name' },
    {
      title: t('common.status'),
      dataIndex: 'status',
      render: (s) => {
        const map: Record<string, { text: string; color: string }> = {
          '待出库': { text: '待出库', color: 'default' },
          '已出库': { text: '已出库', color: 'success' },
          '已取消': { text: '已取消', color: 'error' },
        };
        const c = map[(s as any) || ''] || { text: (s as any) || '-', color: 'default' };
        return <Tag color={c.color}>{c.text}</Tag>;
      },
    },
    { title: t('app.kuaizhizao.otherOutbound.col.deliverer'), dataIndex: 'deliverer_name' },
    { title: t('app.kuaizhizao.otherOutbound.col.deliveryTime'), dataIndex: 'delivery_time', valueType: 'dateTime' },
  ]), [t, reasonTypeOptions]);

  const detailNotesColumn: ProDescriptionsItemProps<OtherOutboundDetail> = useMemo(() => ({
    title: t('common.remark'),
    dataIndex: 'notes',
    span: 3,
  }), [t]);

  const detailCollaboration = useMemo(() => {
    if (!outboundDetail) return undefined;
    const lifecycle = getOtherOutboundLifecycle(outboundDetail as unknown as Record<string, unknown>, t);
    const mainStages = lifecycle.mainStages ?? [];
    if (!mainStages.length) return undefined;
    return (
      <UniLifecycleStepper
        steps={mainStages}
        status={lifecycle.status}
        showLabels
        nextStepSuggestions={lifecycle.nextStepSuggestions}
      />
    );
  }, [outboundDetail, t]);

  const timeconfigBasicItems0 = useDetailDrawerDescriptionItems(
    [detailNotesColumn],
    outboundDetail,
    'other_outbound',
  );
  const timeconfigBasicItems1 = useDetailDrawerDescriptionItems(
    detailColumns,
    outboundDetail,
    'other_outbound',
  );

  const detailSupplementary = useMemo(() => {
    if (!outboundDetail) return undefined;
    const nodes: React.ReactNode[] = [];
    if (hasCustomFieldsDetailContent(otherOutboundListCustomFields, otherOutboundDetailCustomFieldValues)) {
      nodes.push(
        <CustomFieldsDetailSection
          key="custom-fields"
          customFields={otherOutboundListCustomFields}
          customFieldValues={otherOutboundDetailCustomFieldValues}
        />,
      );
    }
    if (outboundDetail.notes) {
      nodes.push(
        <Descriptions
          key="notes"
          column={detailDrawerBasicColumn(false)}
          size="small"
          style={nodes.length > 0 ? { marginTop: 16 } : undefined}
          items={timeconfigBasicItems0}
        />,
      );
    }
    if (nodes.length === 0) return undefined;
    return <>{nodes}</>;
  }, [detailNotesColumn, outboundDetail, otherOutboundDetailCustomFieldValues, otherOutboundListCustomFields, timeconfigBasicItems0]);

  return (
    <>
      <ListPageTemplate>
        <UniTable
          headerTitle={t('app.kuaizhizao.otherOutbound.title')}
        viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.otherOutbound)}
          columnPersistenceId="apps.kuaizhizao.pages.warehouse-management.other-outbound-width-v6"
          actionRef={actionRef}
          rowKey="id"
          columns={columns}
          showAdvancedSearch
          pinnedTabsField={WAREHOUSE_DOC_PINNED_STATUS_FIELD}
          skipFuzzyPinyinClientFilter
          showCreateButton
          createButtonText={createButtonLabel}
          onCreate={handleCreate}
          enableRowSelection
          onTableDataChange={(rows) => {
            const next = new Map<string, OtherOutbound>();
            for (const row of rows) {
              if (row.id != null) next.set(String(row.id), row);
            }
            listRowsRef.current = next;
          }}
          selectedRowKeys={selectedRowKeys}
          onRowSelectionChange={setSelectedRowKeys}
          showSyncButton={toolbarSyncPush.hubVisible && toolbarSyncPush.pushEnabled}
          onSync={() => undefined}
          syncToolbarExtra={
            toolbarSyncPush.hubVisible && toolbarSyncPush.pushEnabled
              ? () => (
                  <SyncPushHubButton
                    syncEnabled={false}
                    pushEnabled={toolbarSyncPush.pushEnabled}
                    historySourceType="other_outbound"
                    historyTargetProfiles={['kingdee_im_otheroutbill']}
                    getReconcileDocumentIds={getOtherOutboundReconcileDocumentIds}
                    size="medium"
                    renderPushPanel={({ active, close }) => (
                      <OtherOutboundDocumentPushPanel
                        embedded
                        open={active}
                        onClose={close}
                        outboundIds={selectedOtherOutboundIdsForDocumentPush}
                        onComplete={() => {
                          actionRef.current?.reload?.();
                          close();
                        }}
                      />
                    )}
                  />
                )
              : undefined
          }
          showDeleteButton
          deleteButtonText={t('common.delete')}
          toolBarActionsAfterBatch={[
            <UniCapabilityBatchButton
              key="other-outbound-confirm"
              selectedRowKeys={selectedRowKeys}
              selectedRecords={selectedOtherOutboundCapabilityRows}
              capabilityKey="confirm"
              permAllowed={canConfirmOutbound}
              onRun={async (id) => {
                const row = selectedOtherOutboundForBatch.find((r) => Number(r.id) === id);
                if (!row) {
                  throw new Error(t('app.kuaizhizao.warehouseOutbound.msg.noneConfirmable'));
                }
                await runOutboundHubConfirmFromRecord({
                  t,
                  record: { id: row.id, outbound_type: 'other_outbound' },
                  trackingFlags,
                });
              }}
              onSuccess={reloadOtherOutboundAfterCapability}
              requireConfirm
              labels={{
                single: t('app.kuaizhizao.warehouseOutbound.action.confirmOutbound'),
                batch: t('app.kuaizhizao.warehouseOutbound.action.confirmOutbound'),
                singleConfirmTitle: t('app.kuaizhizao.warehouseOutbound.action.confirmOutbound'),
              }}
              icon={<CheckCircleOutlined />}
              size="medium"
              color="green"
              variant="solid"
            />,
            <UniCapabilityBatchButton
              key="other-outbound-withdraw"
              selectedRowKeys={selectedRowKeys}
              selectedRecords={selectedOtherOutboundCapabilityRows}
              capabilityKey="withdraw"
              permAllowed={canRevokeOutbound}
              onRun={async (id) => {
                await warehouseApi.otherOutbound.withdraw(String(id));
              }}
              onSuccess={reloadOtherOutboundAfterCapability}
              requireConfirm
              labels={{
                single: t('app.kuaizhizao.warehouseOutbound.action.withdrawOutbound'),
                batch: t('app.kuaizhizao.warehouseOutbound.action.withdrawOutbound'),
                singleConfirmTitle: t('app.kuaizhizao.otherOutbound.msg.withdrawTitle'),
              }}
              icon={<RollbackOutlined />}
              size="medium"
              color="orange"
              variant="solid"
            />,
          ]}
          rowSelectionGetCheckboxProps={(record) => ({
            disabled: !isOtherOutboundDeletable(record) && !isOtherOutboundPrintable(record),
          })}
          onDelete={handleBatchDelete}
          deleteConfirmTitle={(count) =>
            t('app.kuaizhizao.warehouseCommon.batchDeleteConfirm', {
              count,
              noun: t('app.kuaizhizao.otherOutbound.title'),
            })
          }
          showExportButton
          onExport={async (type, keys, pageData) => {
            try {
              const loadAll = async () => {
                const listParams = resolveWarehouseDocListParams({}, undefined, {
                  docDateParamPrefix: 'delivery',
                });
                const rows = await fetchAllListItems((p) =>
                  warehouseApi.otherOutbound.list({ ...listParams, ...p }),
                );
                return enrichOtherOutboundRecordsWithCustomFields(rows);
              };
              const headers = await resolveWarehouseListExportHeaders(
                type,
                keys,
                pageData as OtherOutbound[] | undefined,
                listRowsRef.current,
                loadAll,
              );
              if (headers.length === 0) {
                messageApi.warning(t('common.exportNoData'));
                return;
              }
              const enriched = await enrichStandaloneDocsWithDetail(headers, (id) =>
                warehouseApi.otherOutbound.get(String(id)),
              );
              let flatRows = flattenStandaloneWarehouseDocsForExport(enriched, {
                docCodeField: 'outbound_code',
                docTypeLabel: t('app.kuaizhizao.warehouseOutbound.type.otherOutbound'),
                dateFields: ['delivery_time', 'pick_date'],
                operatorFields: ['deliverer_name', 'picker_name'],
              });
              if (type === 'selected' && keys?.length) {
                flatRows = filterWarehouseFlatRowsByExportKeys(flatRows, keys);
              }
              await exportWarehouseDocLinesXlsx(
                flatRows,
                `other-outbound-lines-${todaySiteDateString()}.xlsx`,
                {
                  t,
                  sheetName: t('app.kuaizhizao.otherOutbound.title'),
                  includeDocTypeColumn: false,
                  direction: 'standalone',
                },
              );
              messageApi.success(t('common.exportSuccess', { count: flatRows.length }));
            } catch (error: unknown) {
              messageApi.error((error as { message?: string })?.message || t('common.exportFailed'));
            }
          }}
          request={async (params, sort, _filter, searchFormValues, meta?: UniTableRequestMeta) => {
            try {
              const listParams = resolveWarehouseDocListParams(searchFormValues, sort, {
                docDateParamPrefix: 'delivery',
              });
              const response = await warehouseApi.otherOutbound.list({
                skip: ((params.current || 1) - 1) * (params.pageSize || 20),
                limit: params.pageSize || 20,
                ...listParams,
              });
              const { data: raw, total } = normalizeWarehouseListResponse(response);
              const data = meta?.purpose === 'prefetch'
                ? raw
                : await enrichOtherOutboundRecordsWithCustomFields(raw);
              return { data, success: true, total };
            } catch {
              messageApi.error(t('app.kuaizhizao.otherOutbound.msg.loadListFailed'));
              return { data: [], success: false, total: 0 };
            }
          }}
          showPrintButton
          printButtonDisabled={!canToolbarPrint}
          printButtonText={t('components.uniAction.print')}
          onPrint={() => {
            const row = selectedOtherOutboundForBatch[0];
            if (row) handlePrint(row);
          }}
        />
      </ListPageTemplate>

      <DetailDrawerTemplate
        title={`${t('app.kuaizhizao.otherOutbound.detailTitle')}${outboundDetail?.outbound_code ? ` - ${outboundDetail.outbound_code}` : ''}`}
        open={detailDrawerVisible}
        loading={detailLoading}
        onClose={() => {
          setDetailDrawerVisible(false);
          setOutboundDetail(null);
          resetOtherOutboundDetailFieldValues();
        }}
        size={DRAWER_CONFIG.HALF_WIDTH}
        basic={
          outboundDetail ? (
            <Descriptions column={detailDrawerBasicColumn(false)} size="small" items={timeconfigBasicItems1} />
          ) : undefined
        }
        collaboration={detailCollaboration}
        supplementary={detailSupplementary}
        linesTitle={t('app.kuaizhizao.warehouseOutbound.section.lines')}
        lines={
          outboundDetail?.items && outboundDetail.items.length > 0 ? (
            <>
              <style>{WAREHOUSE_DETAIL_TABLE_STYLES}</style>
              <Table
                className="warehouse-detail-table"
                size="small"
                rowKey="id"
                columns={[
                  { title: t('app.kuaizhizao.warehouseOutbound.col.materialCode'), dataIndex: 'material_code', width: 120 },
                  { title: t('app.kuaizhizao.warehouseOutbound.col.materialName'), dataIndex: 'material_name', width: 150 },
                  {
                    title: t('app.kuaizhizao.warehouseInbound.col.spec'),
                    dataIndex: 'material_spec',
                    width: 120,
                    ellipsis: true,
                    render: (v: unknown) => (v != null && String(v).trim() ? String(v) : '—'),
                  },
                  {
                    title: t('common.unit'),
                    dataIndex: 'material_unit',
                    width: 60,
                    render: (val) => <MaterialUnitLabel value={val} />,
                  },
                  {
                    title: t('app.kuaizhizao.warehouseReports.colWarehouse'),
                    dataIndex: 'warehouse_name',
                    width: 120,
                    ellipsis: true,
                  },
                  { title: t('app.kuaizhizao.warehouseOutbound.col.location'), dataIndex: 'location_code', width: 100 },
                  { title: t('app.kuaizhizao.warehouseOutbound.col.deliveryQty'), dataIndex: 'outbound_quantity', width: 100, align: 'right' },
                  buildDocumentLineAuxQuantityDetailColumn({ t, width: 120 }),
                  { title: t('app.kuaizhizao.warehouseOutbound.col.batchNo'), dataIndex: 'batch_number', width: 100 },
                  buildDocumentDetailSerialReadonlyColumn(t),
                  { title: t('common.remark'), dataIndex: 'notes' },
                ]}
                dataSource={outboundDetail.items}
                pagination={false}
              />
            </>
          ) : undefined
        }
      />

      <FormModalTemplate
        title={otherOutboundFormTitle}
        open={createModalVisible}
        isEdit={editingOutboundId != null}
        onClose={() => {
          setCreateModalVisible(false);
          setEditingOutboundId(null);
          setEditingOutboundCode('');
          resetOtherOutboundFormFieldValues();
        }}
        formRef={formRef}
        onFinish={handleCreateSubmit}
        width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
        initialValues={{
          outbound_type: OTHER_OUTBOUND_TYPE_MATERIAL,
          reason_type: '其他',
          pick_date: dayjs(todaySiteDateString()),
          items: [{ ...defaultOutboundItem }],
        }}
        grid={false}
        onValuesChange={(changed, all) => {
          if (changed.items !== undefined) {
            setLineStockKey(otherOutboundStockFingerprint(all?.items));
          }
        }}
      >
        <Row gutter={16}>
          <Col span={12}>
            <CodeField
              pageCode="kuaizhizao-warehouse-other-outbound"
              name="outbound_code"
              label={t('app.kuaizhizao.otherOutbound.col.outboundCode')}
              autoGenerateOnCreate={editingOutboundId == null}
              showGenerateButton={false}
              context={{}}
            />
          </Col>
          <Col span={12}>
            <ProFormItem
              name="outbound_type"
              label={t('app.kuaizhizao.otherOutbound.field.outboundType')}
              rules={[
                {
                  required: true,
                  message: t('app.kuaizhizao.otherOutbound.field.outboundTypeRequired'),
                },
              ]}
            >
              <UniDropdown
                style={{ width: '100%' }}
                allowClear={false}
                options={[
                  {
                    value: OTHER_OUTBOUND_TYPE_MATERIAL,
                    label: t('app.kuaizhizao.otherOutbound.outboundType.material'),
                  },
                  {
                    value: OTHER_OUTBOUND_TYPE_ASSET,
                    label: t('app.kuaizhizao.otherOutbound.outboundType.asset'),
                  },
                ]}
              />
            </ProFormItem>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <ProFormItem name="reason_type" label={t('app.kuaizhizao.otherOutbound.field.reasonType')} rules={[{ required: true }]}>
              <UniDropdown
                placeholder={t('app.kuaizhizao.otherOutbound.field.selectReasonType')}
                showSearch
                allowClear
                loading={reasonTypeLoading}
                style={{ width: '100%' }}
                options={reasonTypeOptions}
                quickCreate={{
                  label: t('app.kuaizhizao.otherOutbound.field.dataDictionary'),
                  onClick: () => navigate('/system/data-dictionaries?keyword=OUTBOUND_REASON_TYPE'),
                }}
              />
            </ProFormItem>
          </Col>
          <Col span={12}>
            <ProFormDatePicker
              name="pick_date"
              label={t('app.kuaizhizao.otherOutbound.field.pickDate')}
              rules={[
                {
                  required: true,
                  message: t('app.kuaizhizao.otherOutbound.field.pickDateRequired'),
                },
              ]}
              fieldProps={{ style: { width: '100%' } }}
            />
          </Col>
          <Col span={12}>
            <OtherOutboundUserPickField
              name="picker_id"
              nameField="picker_name"
              label={t('app.kuaizhizao.otherOutbound.field.picker')}
              placeholder={t('app.kuaizhizao.otherOutbound.field.pickerPlaceholder')}
              required
              operatorNumberField="picker_operator_number"
              departmentOptions={departmentOptions}
            />
          </Col>
          <Col span={12}>
            <ProFormItem
              name="pick_department_id"
              label={t('app.kuaizhizao.otherOutbound.field.pickDepartment')}
              rules={[
                {
                  validator: async (_, val) => {
                    const customerId = formRef.current?.getFieldValue('customer_id');
                    if (val != null && val !== '') return;
                    if (customerId != null && customerId !== '') return;
                    throw new Error(t('app.kuaizhizao.otherOutbound.msg.pickDeptOrCustomerRequired'));
                  },
                },
              ]}
            >
              <UniDropdown
                placeholder={t('app.kuaizhizao.otherOutbound.field.pickDepartmentPlaceholder')}
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
            <AntForm.Item name="picker_operator_number" hidden>
              <Input />
            </AntForm.Item>
          </Col>
          <Col span={12}>
            <ProFormItem name="customer_id" label={t('app.kuaizhizao.otherOutbound.field.customer')}>
              <CustomerSelectDropdown
                allowClear
                placeholder={t('app.kuaizhizao.otherOutbound.field.customerPlaceholder')}
                hostResource="kuaizhizao:other-outbound"
                onCustomerPick={(customer: Customer | null) => {
                  if (!customer) {
                    formRef.current?.setFieldsValue({
                      customer_name: undefined,
                      customer_number: undefined,
                    });
                    return;
                  }
                  const row = customer as Record<string, unknown>;
                  const code = String(row.code ?? row.customer_code ?? '').trim();
                  const name = String(row.name ?? row.customer_name ?? '').trim();
                  formRef.current?.setFieldsValue({
                    customer_name: name || undefined,
                    customer_number: code || undefined,
                  });
                }}
              />
            </ProFormItem>
            <AntForm.Item name="customer_name" hidden>
              <Input />
            </AntForm.Item>
            <AntForm.Item name="customer_number" hidden>
              <Input />
            </AntForm.Item>
          </Col>
          <CustomFieldsFormSection
            customFields={otherOutboundFormCustomFields}
            customFieldValues={otherOutboundFormCustomFieldValues}
            gridColumns={2}
            embedInParentRow
          />
        </Row>
        <DocumentDetailTableStyles />
        <UniTableDetail
          name="items"
          title={t('app.kuaizhizao.warehouseOutbound.createLinesTitle')}
          required
          requiredMessage={t('app.kuaizhizao.otherOutbound.msg.needValidLines')}
          headerExtra={
            editingOutboundId == null ? (
              <Space size={8}>
                <Button
                  type="default"
                  icon={<PlusOutlined />}
                  onClick={() => {
                    const next = [
                      ...(formRef.current?.getFieldValue('items') ?? []),
                      { ...defaultOutboundItem },
                    ];
                    formRef.current?.setFieldsValue({ items: next });
                  }}
                >
                  {t('common.addDetail')}
                </Button>
                <Button
                  type="default"
                  icon={<ShoppingOutlined />}
                  onClick={() => setMaterialPickerOpen(true)}
                >
                  {t('app.kuaizhizao.common.materialBatchSelect')}
                </Button>
              </Space>
            ) : undefined
          }
          columns={formItemColumns}
          disabledAdd
          initialValue={{ ...defaultOutboundItem }}
          tableProps={DOCUMENT_DETAIL_TABLE_PROPS}
        />

        <DocumentAttachmentsField category="other_outbound_attachments" />
        <ProFormTextArea name="notes" label={t('common.remark')} placeholder={t('app.kuaizhizao.warehouseOutbound.field.optional')} fieldProps={{ rows: 2 }} />
      </FormModalTemplate>

      <UniMaterialBatchPicker
        open={materialPickerOpen}
        onCancel={() => setMaterialPickerOpen(false)}
        onConfirm={appendOtherOutboundItemsFromMaterials}
      />

      {PrintModal}
    </>
  );
};

export default OtherOutboundPage;
