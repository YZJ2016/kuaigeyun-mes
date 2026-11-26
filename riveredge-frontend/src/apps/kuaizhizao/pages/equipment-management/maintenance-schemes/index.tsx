import React, { useRef, useState, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ActionType,
  ProColumns,
  ProDescriptionsItemProps,
  ProFormDependency,
  ProFormDigit,
  ProFormSelect,
  ProFormSwitch,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { App, Form, Input, Row, Col } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { UniTable } from '../../../../../components/uni-table';
import { ListPageTemplate, FormModalTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import {
  FormListDetailTable,
  type FormListDetailTableHandle,
} from '../../../../../components/form-list-detail-table';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import CodeField from '../../../../../components/code-field';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useNewShortcut } from '../../../../../hooks/useNewShortcut';
import { withSingleNewShortcutHint } from '../../../../../utils/globalNewShortcut';
import { maintenanceItemsApi, maintenanceSchemesApi } from '../../../services/equipmentOps';
import { formDateRangeFormItemProps } from '../../../../../utils/formDate';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { buildDocumentAuditColumns } from '../../shared/documentAuditColumns';
import {
  MASTER_DATA_PINNED_ACTIVE_FIELD,
  buildActiveStatusValueEnum,
  normalizeEquipmentListResponse,
  resolveMasterDataListParams,
} from '../../../utils/equipmentListCore';
import {
  buildDetailDrawerEditExtra,
  buildIsActiveDescriptionColumn,
  EquipmentMasterDetailDrawer,
  MasterDataLinesTable,
  renderEquipmentMasterRowActions,
  renderIsActiveTag,
} from '../shared/equipmentMasterDataDetail';
import {
  EquipmentMaintenanceItemQuickCreateModal,
  type EquipmentMaintenanceItemCreated,
} from '../shared/EquipmentMaintenanceItemQuickCreateModal';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../../utils/uniTableLayoutColumns';
import {
  CYCLE_TYPE_COUNT,
  CYCLE_TYPE_RUNTIME,
  CYCLE_TYPE_TIME,
  TIME_CYCLE_UNITS,
  isTimeCycleType,
  resolveCycleTypeDefault,
  resolveMaintenanceTypeDefaultCycle,
} from './maintenanceTypeCycleDefaults';

const P = 'app.kuaizhizao.equipmentOps.maintenanceScheme';
const ITEM_P = 'app.kuaizhizao.equipmentOps.maintenanceItem';
const RESOURCE = 'kuaizhizao:equipment-maintenance-scheme';
const ITEM_RESOURCE = 'kuaizhizao:equipment-maintenance-item';

interface SchemeLine {
  item_id?: number;
  sort_order?: number;
  item_code?: string;
  item_name?: string;
  requirement?: string;
  remark?: string;
}

type ItemMeta = { label: string; value: number; remark?: string };

interface MaintenanceScheme {
  id?: number;
  code?: string;
  name?: string;
  description?: string;
  maintenance_type?: string;
  cycle_type?: string;
  cycle_value?: number;
  cycle_unit?: string;
  is_active?: boolean;
  lines?: SchemeLine[];
  updated_at?: string;
}

const MaintenanceSchemesPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const perms = useResourcePermissions(RESOURCE);
  const itemPerms = useResourcePermissions(ITEM_RESOURCE);
  const actionRef = useRef<ActionType>(null);
  const formRef = useRef<any>(null);
  const linesTableRef = useRef<FormListDetailTableHandle>(null);
  const itemQuickCreateTargetRef = useRef<'bulk' | number | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [isEdit, setIsEdit] = useState(false);
  const [current, setCurrent] = useState<MaintenanceScheme | null>(null);
  const [formInitialValues, setFormInitialValues] = useState<Record<string, unknown> | undefined>(
    undefined,
  );
  const [itemOptions, setItemOptions] = useState<ItemMeta[]>([]);
  const [itemQuickCreateOpen, setItemQuickCreateOpen] = useState(false);
  const [detailVisible, setDetailVisible] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<MaintenanceScheme | null>(null);
  const [createCodeSessionKey, setCreateCodeSessionKey] = useState(0);

  const itemRemarkById = useMemo(() => {
    const map = new Map<number, string>();
    for (const opt of itemOptions) {
      if (opt.remark) map.set(opt.value, opt.remark);
    }
    return map;
  }, [itemOptions]);

  const openItemQuickCreate = useCallback((target: 'bulk' | number) => {
    itemQuickCreateTargetRef.current = target;
    setItemQuickCreateOpen(true);
  }, []);

  const handleItemQuickCreated = useCallback((item: EquipmentMaintenanceItemCreated) => {
    const remark = item.remark ? String(item.remark) : undefined;
    setItemOptions((prev) => {
      if (prev.some((opt) => opt.value === item.id)) return prev;
      return [
        ...prev,
        {
          label: `${item.code} - ${item.name}`,
          value: item.id,
          remark,
        },
      ];
    });
    const target = itemQuickCreateTargetRef.current;
    itemQuickCreateTargetRef.current = null;
    if (target === 'bulk') {
      linesTableRef.current?.pickBulkValue(item.id);
    } else if (typeof target === 'number') {
      formRef.current?.setFieldValue(['lines', target, 'item_id'], item.id);
      if (remark) {
        formRef.current?.setFieldValue(['lines', target, 'remark'], remark);
      }
    }
  }, []);

  const itemQuickCreateConfig = useMemo(
    () =>
      itemPerms.canCreate
        ? {
            label: t(`${ITEM_P}.quickCreate`),
            onClick: () => openItemQuickCreate('bulk'),
          }
        : undefined,
    [itemPerms.canCreate, openItemQuickCreate, t],
  );

  const loadItemOptions = async () => {
    const res = await maintenanceItemsApi.list({ limit: 1000, is_active: true });
    setItemOptions(
      (res.items ?? []).map(
        (it: { id: number; code: string; name: string; remark?: string }) => ({
          label: `${it.code} - ${it.name}`,
          value: it.id,
          remark: it.remark ? String(it.remark) : undefined,
        }),
      ),
    );
  };

  const handleCreate = () => {
    setIsEdit(false);
    setCurrent(null);
    setCreateCodeSessionKey((k) => k + 1);
    const defaultCycle = resolveMaintenanceTypeDefaultCycle('日常保养');
    setFormInitialValues({
      is_active: true,
      maintenance_type: '日常保养',
      cycle_type: '按时间',
      cycle_value: defaultCycle?.cycle_value ?? 1,
      cycle_unit: defaultCycle?.cycle_unit ?? '天',
      lines: [{ sort_order: 0 }],
    });
    setModalVisible(true);
    void loadItemOptions();
  };
  useNewShortcut(handleCreate);

  const applyCycleFromMaintenanceType = useCallback((maintenanceType: string) => {
    const cycleType = formRef.current?.getFieldValue('cycle_type');
    if (!isTimeCycleType(cycleType)) return;
    const preset = resolveMaintenanceTypeDefaultCycle(maintenanceType);
    if (!preset) return;
    formRef.current?.setFieldsValue({
      cycle_value: preset.cycle_value,
      cycle_unit: preset.cycle_unit,
    });
  }, []);

  const applySettingsFromCycleType = useCallback((cycleType: string) => {
    if (isTimeCycleType(cycleType)) {
      const maintenanceType =
        formRef.current?.getFieldValue('maintenance_type') || '日常保养';
      const preset = resolveMaintenanceTypeDefaultCycle(maintenanceType);
      formRef.current?.setFieldsValue({
        maintenance_type: maintenanceType,
        cycle_value: preset?.cycle_value ?? 1,
        cycle_unit: preset?.cycle_unit ?? '天',
      });
      return;
    }
    const preset = resolveCycleTypeDefault(cycleType);
    formRef.current?.setFieldsValue({
      maintenance_type: undefined,
      cycle_value: preset?.cycle_value ?? 100,
      cycle_unit: preset?.cycle_unit ?? (cycleType === CYCLE_TYPE_COUNT ? '次' : '小时'),
    });
  }, []);

  const handleEdit = async (record: MaintenanceScheme) => {
    if (!record.id) return;
    try {
      const loaded = await maintenanceSchemesApi.get(record.id);
      setIsEdit(true);
      setCurrent(loaded);
      setFormInitialValues({
        ...loaded,
        lines: (loaded.lines ?? []).map((l: SchemeLine, i: number) => ({
          item_id: l.item_id,
          sort_order: l.sort_order ?? i,
          remark: l.remark ?? '',
        })),
      });
      setModalVisible(true);
      void loadItemOptions();
    } catch (error: unknown) {
      messageApi.error(error instanceof Error ? error.message : t('common.loadFailed'));
    }
  };

  const handleDetail = useCallback(async (record: MaintenanceScheme) => {
    if (!record.id) return;
    setDetailVisible(true);
    setDetailLoading(true);
    setDetail(null);
    try {
      const loaded = await maintenanceSchemesApi.get(record.id);
      setDetail(loaded);
    } catch (error: unknown) {
      messageApi.error(error instanceof Error ? error.message : t('common.loadFailed'));
      setDetailVisible(false);
    } finally {
      setDetailLoading(false);
    }
  }, [messageApi, t]);

  const closeDetail = () => {
    setDetailVisible(false);
    setDetail(null);
  };

  const handleDelete = async (keys: React.Key[]) => {
    for (const id of keys) {
          await maintenanceSchemesApi.delete(Number(id));
        }
    messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
    actionRef.current?.reload();
  };

  const handleSubmit = async (values: Record<string, unknown>) => {
    const cycleType = String(values.cycle_type || '');
    const timeBased = isTimeCycleType(cycleType);
    const payload = {
      ...values,
      maintenance_type: timeBased ? values.maintenance_type : null,
      cycle_unit: timeBased
        ? values.cycle_unit
        : cycleType === CYCLE_TYPE_COUNT
          ? '次'
          : cycleType === CYCLE_TYPE_RUNTIME
            ? '小时'
            : values.cycle_unit,
      lines: ((values.lines as SchemeLine[]) ?? []).map((l, i) => ({
        item_id: l.item_id,
        sort_order: l.sort_order ?? i,
        remark: l.remark != null ? String(l.remark) : undefined,
      })),
    };
    if (isEdit && current?.id) {
      await maintenanceSchemesApi.update(current.id, payload);
      messageApi.success(t('common.updateSuccess'));
    } else {
      await maintenanceSchemesApi.create(payload);
      messageApi.success(t('common.createSuccess'));
    }
    setModalVisible(false);
    actionRef.current?.reload();
    if (detailVisible && detail?.id === current?.id && current?.id) {
      void handleDetail({ id: current.id });
    }
  };

  const activeStatusValueEnum = useMemo(() => buildActiveStatusValueEnum(t), [t]);

  const detailBasicColumns = useMemo<ProDescriptionsItemProps<MaintenanceScheme>[]>(
    () => [
      { title: t('common.code'), dataIndex: 'code' },
      { title: t('common.name'), dataIndex: 'name' },
      {
        title: t(`${P}.col.cycle`),
        dataIndex: 'cycle_type',
        render: (_, r) =>
          [r.cycle_type, r.cycle_value != null ? `${r.cycle_value}${r.cycle_unit ?? ''}` : undefined]
            .filter(Boolean)
            .join(' ') || '-',
      },
      {
        title: t(`${P}.col.maintenanceType`),
        dataIndex: 'maintenance_type',
        render: (_, r) =>
          r.maintenance_type != null && r.maintenance_type !== ''
            ? String(r.maintenance_type)
            : '-',
      },
      { title: t('common.remark'), dataIndex: 'description', span: 2 },
      buildIsActiveDescriptionColumn<MaintenanceScheme>(t),
    ],
    [t],
  );

  const detailLineColumns = useMemo<ColumnsType<SchemeLine>>(
    () => [
      {
        title: t(`${P}.form.item`),
        key: 'item',
        render: (_, row) => `${row.item_code ?? '-'} - ${row.item_name ?? '-'}`,
      },
      {
        title: t(`${ITEM_P}.col.requirement`),
        dataIndex: 'requirement',
        ellipsis: true,
        render: (v) => (v != null && String(v) !== '' ? String(v) : '-'),
      },
      {
        title: t('common.remark'),
        dataIndex: 'remark',
        ellipsis: true,
        render: (v) => (v != null && String(v) !== '' ? String(v) : '-'),
      },
      { title: t(`${P}.form.sortOrder`), dataIndex: 'sort_order', width: 80, align: 'right' },
    ],
    [t],
  );

  const columns: ProColumns<MaintenanceScheme>[] = useMemo(() => alignProColumns<MaintenanceScheme>([
      {
        title: t('common.updatedAt'),
        dataIndex: 'updated_at_range',
        valueType: 'dateRange',
        hideInTable: true,
        formItemProps: formDateRangeFormItemProps,
        search: { order: 10 } as ProColumns['search'],
      },
      {
        title: t('common.enabled'),
        dataIndex: 'is_active',
        valueType: 'select',
        valueEnum: activeStatusValueEnum,
        hideInTable: true,
        search: { order: 20 } as ProColumns['search'],
      },
      {
        title: t('common.code'),
        dataIndex: 'code',
        width: 160,
        minWidth: 160,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        fixed: 'left',
        sorter: true,
        search: { order: 30 } as ProColumns['search'],
      },
      {
        title: t('common.name'),
        dataIndex: 'name',
        width: 160,
        minWidth: 160,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        sorter: true,
        hideInSearch: true,
      },
      {
        title: t(`${P}.col.cycle`),
        dataIndex: 'cycle_type',
        width: 140,
        minWidth: 140,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        render: (_, r) =>
          [r.cycle_type, r.cycle_value != null ? `${r.cycle_value}${r.cycle_unit ?? ''}` : undefined]
            .filter(Boolean)
            .join(' ') || '-',
      },
      {
        title: t(`${P}.col.maintenanceType`),
        dataIndex: 'maintenance_type',
        width: 110,
        minWidth: 110,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        render: (_, r) =>
          r.maintenance_type != null && r.maintenance_type !== ''
            ? String(r.maintenance_type)
            : '-',
      },
      {
        title: t(`${P}.col.lineCount`),
        key: 'line_count',
        dataIndex: 'lines',
        width: 90,
        minWidth: 90,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        render: (_, r) => r.lines?.length ?? 0,
      },
      {
        title: t('common.remark'),
        dataIndex: 'description',
        minWidth: 160,
        uniTablePrimaryFlex: true,
        uniTableRemainderFlex: true,
        resizable: false,
        ellipsis: true,
        hideInSearch: true,
        render: (_, r) => (r.description != null && r.description !== '' ? String(r.description) : '-'),
      },
      {
        title: t('common.enabled'),
        dataIndex: 'is_active',
        ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
        sorter: true,
        hideInSearch: true,
        render: (_, r) => renderIsActiveTag(t, r.is_active),
      },
      ...buildDocumentAuditColumns<MaintenanceScheme>(t),
      {
        title: t('common.actions'),
        key: 'option',
        fixed: 'right',
        hideInSearch: true,
        render: (_, record) =>
          renderEquipmentMasterRowActions({
            record,
            t,
            canRead: perms.canRead,
            canUpdate: perms.canUpdate,
            canDelete: perms.canDelete,
            onDetail: (row) => {
              void handleDetail(row);
            },
            onEdit: (row) => {
              void handleEdit(row);
            },
            onDelete: (row) => {
              if (row.id != null) {
                void handleDelete([row.id]);
              }
            },
          }),
      },
    ], SALES_DOC_LIST_FIELD_RANK),
    [t, perms, activeStatusValueEnum, handleDetail],
  );

  return (
    <>
      <ListPageTemplate>
        <UniTable<MaintenanceScheme>
        viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.maintenanceSchemes)}
          headerTitle={t(`${P}.title`)}
          columnPersistenceId="apps.kuaizhizao.pages.equipment-management.maintenance-schemes-width-v3"
          actionRef={actionRef}
          rowKey="id"
          columns={columns}
          showAdvancedSearch={true}
          pinnedTabsField={MASTER_DATA_PINNED_ACTIVE_FIELD}
          skipFuzzyPinyinClientFilter
          request={async (params, sort, _filter, searchFormValues) => {
            try {
              const listParams = resolveMasterDataListParams(searchFormValues, sort);
              const res = await maintenanceSchemesApi.list({
                skip: ((params.current ?? 1) - 1) * (params.pageSize ?? 20),
                limit: params.pageSize,
                ...listParams,
              });
              const { data, total } = normalizeEquipmentListResponse(res);
              return { data: data as MaintenanceScheme[], success: true, total };
            } catch {
              messageApi.error(t(`${P}.listFailed`));
              return { data: [], success: false, total: 0 };
            }
          }}
          showCreateButton={perms.canCreate}
          createButtonText={withSingleNewShortcutHint(t(`${P}.create`))}
          onCreate={handleCreate}
          showDeleteButton={perms.canDelete}
          deleteConfirmTitle={t('common.batchDeleteTitle')}
          deleteConfirmDescription={(count) => t('common.batchDeleteContent', { count: count })}
          
          onDelete={handleDelete}
          enableRowSelection={perms.canDelete}
        />
      </ListPageTemplate>

      <EquipmentMasterDetailDrawer
        open={detailVisible}
        loading={detailLoading}
        detail={detail}
        title={`${t(`${P}.detailTitle`)}${detail?.code ? ` - ${detail.code}` : ''}`}
        onClose={closeDetail}
        basicColumns={detailBasicColumns}
        linesTitle={t(`${P}.form.lines`)}
        lines={
          <MasterDataLinesTable
            rows={detail?.lines ?? []}
            columns={detailLineColumns}
            rowKey={(row) => String(row.item_id ?? row.sort_order ?? '')}
            emptyDescription={t('common.noData')}
          />
        }
        extra={buildDetailDrawerEditExtra(t, Boolean(detail && perms.canUpdate), () => {
          if (!detail) return;
          closeDetail();
          void handleEdit(detail);
        })}
      />

      <FormModalTemplate
        title={isEdit ? t(`${P}.editModal`) : t(`${P}.createModal`)}
        open={modalVisible}
        onClose={() => {
          setModalVisible(false);
          setFormInitialValues(undefined);
        }}
        onFinish={handleSubmit}
        isEdit={isEdit}
        initialValues={formInitialValues}
        width={MODAL_CONFIG.LARGE_WIDTH}
        formRef={formRef}
        grid={false}
      >
        <Row gutter={16}>
          <Col span={12}>
            <CodeField
              key={
                isEdit
                  ? `maintenance-scheme-code-edit-${current?.id ?? 'none'}`
                  : `maintenance-scheme-code-create-${createCodeSessionKey}`
              }
              pageCode="kuaizhizao-equipment-maintenance-scheme"
              name="code"
              label={t('common.code')}
              required={false}
              autoGenerateOnCreate={!isEdit}
              showGenerateButton={false}
              documentId={isEdit ? current?.id : undefined}
              formRef={formRef}
              generateSessionKey={createCodeSessionKey}
            />
          </Col>
          <Col span={12}>
            <ProFormText name="name" label={t('common.name')} rules={[{ required: true }]} />
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <ProFormSelect
              name="cycle_type"
              label={t(`${P}.col.cycleType`)}
              rules={[{ required: true, message: t(`${P}.form.cycleTypeRequired`) }]}
              options={[
                { label: t(`${P}.cycleType.byTime`), value: CYCLE_TYPE_TIME },
                { label: t(`${P}.cycleType.byRuntime`), value: CYCLE_TYPE_RUNTIME },
                { label: t(`${P}.cycleType.byCount`), value: CYCLE_TYPE_COUNT },
              ]}
              fieldProps={{
                onChange: (value: string) => {
                  applySettingsFromCycleType(value);
                },
              }}
            />
          </Col>
          <Col span={12}>
            <ProFormDependency name={['cycle_type']}>
              {({ cycle_type }) =>
                isTimeCycleType(cycle_type) ? (
                  <ProFormSelect
                    name="maintenance_type"
                    label={t(`${P}.col.maintenanceType`)}
                    rules={[
                      { required: true, message: t(`${P}.form.maintenanceTypeRequired`) },
                    ]}
                    options={[
                      { label: t(`${P}.maintenanceType.daily`), value: '日常保养' },
                      { label: t(`${P}.maintenanceType.monthly`), value: '月度' },
                      { label: t(`${P}.maintenanceType.quarterly`), value: '季度' },
                      { label: t(`${P}.maintenanceType.semiAnnual`), value: '半年度' },
                      { label: t(`${P}.maintenanceType.annual`), value: '年度' },
                    ]}
                    fieldProps={{
                      onChange: (value: string) => {
                        applyCycleFromMaintenanceType(value);
                      },
                    }}
                  />
                ) : null
              }
            </ProFormDependency>
          </Col>
        </Row>
        <ProFormDependency name={['cycle_type']}>
          {({ cycle_type }) => {
            const timeBased = isTimeCycleType(cycle_type);
            const valueLabel =
              cycle_type === CYCLE_TYPE_COUNT
                ? t(`${P}.form.cycleValueCount`)
                : cycle_type === CYCLE_TYPE_RUNTIME
                  ? t(`${P}.form.cycleValueRuntime`)
                  : t(`${P}.form.cycleValue`);
            const unitOptions = timeBased
              ? TIME_CYCLE_UNITS.map((unit) => ({
                  label: t(
                    `${P}.cycleUnit.${
                      unit === '天'
                        ? 'day'
                        : unit === '周'
                          ? 'week'
                          : unit === '月'
                            ? 'month'
                            : 'year'
                    }`,
                  ),
                  value: unit,
                }))
              : cycle_type === CYCLE_TYPE_COUNT
                ? [{ label: t(`${P}.cycleUnit.count`), value: '次' }]
                : [{ label: t(`${P}.cycleUnit.hour`), value: '小时' }];
            return (
              <Row gutter={16}>
                <Col span={12}>
                  <ProFormDigit
                    name="cycle_value"
                    label={valueLabel}
                    min={1}
                    rules={[{ required: true, message: t(`${P}.form.cycleValueRequired`) }]}
                  />
                </Col>
                <Col span={12}>
                  <ProFormSelect
                    name="cycle_unit"
                    label={t(`${P}.form.cycleUnit`)}
                    rules={[{ required: true, message: t(`${P}.form.cycleUnitRequired`) }]}
                    options={unitOptions}
                    fieldProps={{ allowClear: timeBased }}
                  />
                </Col>
              </Row>
            );
          }}
        </ProFormDependency>
        <FormListDetailTable
          ref={linesTableRef}
          name="lines"
          label={t(`${P}.form.lines`)}
          addButtonText={t(`${P}.form.addLine`)}
          defaultRow={{ sort_order: 0 }}
          bulkAdd={{
            title: t('common.bulkAddPickTitle', { item: t(`${P}.form.item`) }),
            options: itemOptions,
            valueField: 'item_id',
            quickCreate: itemQuickCreateConfig,
          }}
          columns={[
            {
              title: t(`${P}.form.item`),
              key: 'item_id',
              width: 200,
              render: (field) => (
                <Form.Item
                  name={[field.name, 'item_id']}
                  rules={[{ required: true, message: t('common.required') }]}
                  noStyle
                >
                  <UniDropdown
                    options={itemOptions}
                    showSearch
                    optionFilterProp="label"
                    style={{ width: '100%' }}
                    placeholder={t('common.select')}
                    onChange={(val) => {
                      const itemId = Number(val);
                      const currentRemark = formRef.current?.getFieldValue([
                        'lines',
                        field.name,
                        'remark',
                      ]);
                      if (
                        Number.isFinite(itemId) &&
                        (currentRemark == null || String(currentRemark).trim() === '')
                      ) {
                        const fromItem = itemRemarkById.get(itemId);
                        if (fromItem) {
                          formRef.current?.setFieldValue(
                            ['lines', field.name, 'remark'],
                            fromItem,
                          );
                        }
                      }
                    }}
                    quickCreate={
                      itemPerms.canCreate
                        ? {
                            label: t(`${ITEM_P}.quickCreate`),
                            onClick: () => openItemQuickCreate(field.name),
                          }
                        : undefined
                    }
                  />
                </Form.Item>
              ),
            },
            {
              title: t('common.remark'),
              key: 'remark',
              width: 280,
              render: (field) => (
                <Form.Item name={[field.name, 'remark']} noStyle>
                  <Input
                    allowClear
                    placeholder={t('common.enterField', { field: t('common.remark') })}
                  />
                </Form.Item>
              ),
            },
            {
              title: t(`${P}.form.sortOrder`),
              key: 'sort_order',
              width: 88,
              align: 'right',
              render: (field) => (
                <ProFormDigit
                  name={[field.name, 'sort_order']}
                  min={0}
                  formItemProps={{ noStyle: true }}
                  fieldProps={{ style: { width: '100%' } }}
                />
              ),
            },
          ]}
        />
        <Row gutter={16} style={{ marginTop: 16 }}>
          <Col span={24}>
            <ProFormTextArea name="description" label={t('common.remark')} fieldProps={{ rows: 2 }} />
          </Col>
          <Col span={24}>
            <ProFormSwitch name="is_active" label={t('common.enabled')} />
          </Col>
        </Row>
      </FormModalTemplate>

      <EquipmentMaintenanceItemQuickCreateModal
        open={itemQuickCreateOpen}
        onClose={() => {
          setItemQuickCreateOpen(false);
          itemQuickCreateTargetRef.current = null;
        }}
        onCreated={handleItemQuickCreated}
      />
    </>
  );
};

export default MaintenanceSchemesPage;
