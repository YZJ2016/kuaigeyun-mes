import { alignIotTableColumns } from '../../components/table-parity';
/**
 * 产品模型运营列表：模糊 + 高级搜索、新建、编辑、详情抽屉、删除 / 批量删除。
 * 列表接口为数组响应，筛选、排序、分页在前端完成。
 * 权限与后端一致：列表/详情 kuaiiot:device:display，新建 kuaiiot:device:create，
 * 编辑/删除 kuaiiot:device:update（后端删除走 update 权限，无独立 delete/export 权限码）。
 */

import { DeleteOutlined } from '@ant-design/icons';
import React, { useCallback, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ActionType,
  ProColumns,
  ProDescriptionsItemProps,
  ProFormDigit,
  ProFormGroup,
  ProFormInstance,
  ProFormItem,
  ProFormList,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { App, AutoComplete, Button, Descriptions, Input, Popconfirm, Result, Table, Tag } from 'antd';
import { UniTable } from '../../../../components/uni-table';
import { UniBatchDeleteButton } from '../../../../components/uni-batch';
import { UniExportMenuButton } from '../../../../components/uni-export/UniExportMenuButton';
import { rowActionKind } from '../../../../components/uni-action';
import {
  DetailDrawerTemplate,
  DetailDrawerSection,
  DRAWER_CONFIG,
  FormModalTemplate,
  ListPageTemplate,
  MODAL_CONFIG,
  detailDrawerDescriptionItems,
} from '../../../../components/layout-templates';
import { buildListPageHelpViewConfig } from '../../../../components/page-help-wiki';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { withSingleNewShortcutHint } from '../../../../utils/globalNewShortcut';
import { getApiErrorMessage } from '../../../../utils/errorHandler';
import { downloadRecordsAsXlsx } from '../../../../utils/exportRecordsXlsx';
import { todaySiteDateString } from '../../../../utils/format';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { SeverityTag, ValueTypeTag } from '../../components/status-tags';
import type { ProductEvent, ProductFunction, ProductTag } from '../../services/kuaiiot';
import {
  createProductFull,
  deleteProductRow,
  filterProductRows,
  getProductRow,
  listProductRows,
  loadBuiltinProducts,
  sortLocalRows,
  updateProductRow,
  type ProductRow,
  type ProductWritePayload,
} from './api';

const MAP_TARGET_OPTIONS = [
  'temperature',
  'pressure',
  'vibration',
  'status',
  'is_online',
  'other_parameters',
].map((value) => ({ value, label: value }));

const VALUE_TYPE_OPTIONS = ['number', 'boolean', 'text'].map((value) => ({
  value,
  label: value,
}));

const SEVERITY_OPTIONS = ['info', 'warning', 'critical'].map((value) => ({
  value,
  label: value,
}));

/** UniTable 布局扩展列属性（uniTable* 由布局引擎读取，页面侧仅声明可选）。 */
type TableColumn<T extends Record<string, unknown>> = ProColumns<T> & {
  uniTableKeepWidth?: boolean;
  uniTableRemainderFlex?: boolean;
  uniTablePrimaryFlex?: boolean;
};

type FunctionFormRow = {
  function_key?: string;
  name?: string;
  timeout_seconds?: number;
  params_json?: string;
  edge_action_json?: string;
};

type ProductFormValues = {
  code?: string;
  name?: string;
  description?: string;
  remark?: string;
  tags?: ProductTag[];
  events?: ProductEvent[];
  functions?: FunctionFormRow[];
};

function parseJsonField(raw: string | undefined): { ok: true; value?: unknown } | { ok: false } {
  const text = (raw ?? '').trim();
  if (!text) return { ok: true, value: undefined };
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch {
    return { ok: false };
  }
}

const ProductsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const perms = useResourcePermissions('kuaiiot:device');
  const canDisplay = perms.canAction?.('display') ?? false;
  const canCreate = perms.canAction?.('create') ?? false;
  const canUpdate = perms.canAction?.('update') ?? false;

  const actionRef = useRef<ActionType>(null);
  const formRef = useRef<ProFormInstance>(null);
  /** 跨页批量删除解析：request 内增量累积（prefetch 只增不覆盖），不依赖当前展示页。 */
  const allRowsRef = useRef<Map<number, ProductRow>>(new Map());
  const [pageRows, setPageRows] = useState<ProductRow[]>([]);
  const [builtinBusy, setBuiltinBusy] = useState(false);
  const builtinBusyRef = useRef(false);
  const handleLoadBuiltin = async () => {
    if (builtinBusyRef.current) return;
    builtinBusyRef.current = true; setBuiltinBusy(true);
    try {
      const result = await loadBuiltinProducts();
      messageApi.success(`内置产品新增 ${result.created} 个，保留已有 ${result.skipped} 个`);
      actionRef.current?.reload();
    } catch { messageApi.error('内置产品加载失败，请检查权限后重试'); }
    finally { builtinBusyRef.current = false; setBuiltinBusy(false); }
  };
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ProductRow | null>(null);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [detail, setDetail] = useState<ProductRow | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailIdRef = useRef<number | null>(null);

  const openCreate = useCallback(() => {
    if (!canCreate) return;
    setEditing(null);
    setFormOpen(true);
  }, [canCreate]);

  const openEdit = useCallback((row: ProductRow) => {
    setEditing(row);
    setFormOpen(true);
  }, []);

  const loadDetail = useCallback(
    async (id: number) => {
      detailIdRef.current = id;
      setDetailLoading(true);
      setDetailError(null);
      try {
        const row = await getProductRow(id);
        if (detailIdRef.current === id) {
          setDetail(row);
        }
      } catch (e) {
        if (detailIdRef.current === id) {
          setDetail(null);
          setDetailError(getApiErrorMessage(e, t('app.kuaiiot.products.detailLoadFailed')));
        }
      } finally {
        if (detailIdRef.current === id) {
          setDetailLoading(false);
        }
      }
    },
    [t],
  );

  const openDetail = useCallback(
    (row: ProductRow) => {
      setDrawerOpen(true);
      setDetail(row);
      void loadDetail(row.id);
    },
    [loadDetail],
  );

  const formInitialValues = useMemo<Record<string, unknown>>(() => {
    if (!editing) return { tags: [], events: [], functions: [] };
    return {
      code: editing.code,
      name: editing.name,
      description: editing.description ?? undefined,
      remark: editing.remark ?? undefined,
      tags: (editing.tags || []).map((tag) => ({ ...tag })),
      events: (editing.events || []).map((event) => ({ ...event })),
      functions: (editing.functions || []).map((fn) => ({
        function_key: fn.function_key,
        name: fn.name,
        timeout_seconds: fn.timeout_seconds ?? undefined,
        params_json:
          fn.params && fn.params.length ? JSON.stringify(fn.params, null, 2) : undefined,
        edge_action_json: fn.edge_action ? JSON.stringify(fn.edge_action, null, 2) : undefined,
      })),
    };
  }, [editing]);

  const handleSubmit = useCallback(
    async (values: ProductFormValues) => {
      const tags = (values.tags || [])
        .filter((tag) => tag && String(tag.tag_key || '').trim())
        .map((tag) => ({
          tag_key: String(tag.tag_key).trim(),
          name: String(tag.name || '').trim(),
          value_type: tag.value_type || 'number',
          map_target: String(tag.map_target || '').trim(),
          ...(tag.unit ? { unit: String(tag.unit).trim() } : {}),
          fill_target: String(tag.fill_target ?? '').trim() || null,
          is_enabled: tag.is_enabled ?? true,
        }));
      if (tags.some((tag) => !tag.name || !tag.map_target)) {
        messageApi.error(t('app.kuaiiot.products.tagFieldsRequired'));
        return;
      }
      if (new Set(tags.map((tag) => tag.tag_key)).size !== tags.length) {
        messageApi.error(t('app.kuaiiot.products.tagKeyDup'));
        return;
      }

      const events = (values.events || [])
        .filter((event) => event && String(event.event_key || '').trim())
        .map((event) => ({
          event_key: String(event.event_key).trim(),
          name: String(event.name || '').trim(),
          severity: event.severity || 'info',
          ...(event.message ? { message: String(event.message) } : {}),
        }));
      if (events.some((event) => !event.name)) {
        messageApi.error(t('app.kuaiiot.products.eventFieldsRequired'));
        return;
      }
      if (new Set(events.map((event) => event.event_key)).size !== events.length) {
        messageApi.error(t('app.kuaiiot.products.eventKeyDup'));
        return;
      }

      const functions: ProductFunction[] = [];
      for (const row of values.functions || []) {
        if (!row || !String(row.function_key || '').trim()) continue;
        const params = parseJsonField(row.params_json);
        const edgeAction = parseJsonField(row.edge_action_json);
        if (!params.ok || !edgeAction.ok) {
          messageApi.error(t('app.kuaiiot.message.invalidJson'));
          return;
        }
        functions.push({
          function_key: String(row.function_key).trim(),
          name: String(row.name || '').trim(),
          ...(row.timeout_seconds != null && Number(row.timeout_seconds) >= 1
            ? { timeout_seconds: Number(row.timeout_seconds) }
            : {}),
          ...(Array.isArray(params.value)
            ? { params: params.value as ProductFunction['params'] }
            : {}),
          ...(edgeAction.value && typeof edgeAction.value === 'object'
            ? { edge_action: edgeAction.value as ProductFunction['edge_action'] }
            : {}),
        });
      }
      if (functions.some((fn) => !fn.name)) {
        messageApi.error(t('app.kuaiiot.products.functionFieldsRequired'));
        return;
      }
      if (new Set(functions.map((fn) => fn.function_key)).size !== functions.length) {
        messageApi.error(t('app.kuaiiot.products.functionKeyDup'));
        return;
      }

      try {
        if (editing) {
          await updateProductRow(editing.id, {
            name: String(values.name || '').trim(),
            description: values.description?.trim() || undefined,
            remark: values.remark?.trim() || undefined,
            tags,
            events,
            functions,
          });
        } else {
          const payload: ProductWritePayload = {
            code: String(values.code || '').trim(),
            name: String(values.name || '').trim(),
            description: values.description?.trim() || undefined,
            remark: values.remark?.trim() || undefined,
            tags,
            events,
            functions,
          };
          await createProductFull(payload);
        }
        messageApi.success(t('common.saveSuccess'));
        setFormOpen(false);
        setEditing(null);
        actionRef.current?.reload();
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('common.saveFailed')));
      }
    },
    [editing, messageApi, t],
  );

  const handleDelete = useCallback(
    async (row: ProductRow) => {
      try {
        await deleteProductRow(row.id);
        messageApi.success(t('common.deleteSuccess'));
        actionRef.current?.reload();
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('common.deleteFailed')));
      }
    },
    [messageApi, t],
  );

  /** 串行批量删除：首条失败即停并报明细（与后端 update 权限一致）。 */
  const handleBatchDelete = useCallback(
    async (keys: React.Key[]) => {
      const rows = keys
        .map((key) => allRowsRef.current.get(Number(key)))
        .filter((row): row is ProductRow => Boolean(row));
      let success = 0;
      for (const row of rows) {
        try {
          await deleteProductRow(row.id);
          success += 1;
        } catch (e) {
          messageApi.error(
            t('app.kuaiiot.message.batchDeleteStopped', {
              success,
              name: row.name || row.code,
              reason: getApiErrorMessage(e, t('common.operationFailed')),
            }),
          );
          break;
        }
      }
      if (success === rows.length && rows.length > 0) {
        messageApi.success(t('common.batchDeleteSuccess', { count: success }));
      }
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    },
    [messageApi, t],
  );

  const handleExport = useCallback(
    async (type: 'selected' | 'currentPage' | 'all', keys?: React.Key[], pageData?: ProductRow[]) => {
      try {
        let rows: ProductRow[] = [];
        if (type === 'selected' && keys?.length) {
          rows = keys
            .map((key) => allRowsRef.current.get(Number(key)))
            .filter((row): row is ProductRow => Boolean(row));
        } else if (type === 'currentPage' && pageData) {
          rows = pageData;
        } else {
          rows = await listProductRows();
        }
        if (!rows.length) {
          messageApi.warning(t('common.noDataToExport'));
          return;
        }
        await downloadRecordsAsXlsx(
          rows.map((row) => ({
            code: row.code,
            name: row.name,
            description: row.description || '',
            tag_count: (row.tags || []).length,
            tag_keys: (row.tags || []).map((tag) => tag.tag_key).join(', '),
            event_count: (row.events || []).length,
            function_count: (row.functions || []).length,
            remark: row.remark || '',
          })),
          `${t('app.kuaiiot.products.exportFileName', { date: todaySiteDateString() })}.xlsx`,
          {
            columns: [
              { key: 'code', title: t('common.code') },
              { key: 'name', title: t('common.name') },
              { key: 'description', title: t('app.kuaiiot.products.colDescription') },
              { key: 'tag_count', title: t('app.kuaiiot.products.colTagCount') },
              { key: 'tag_keys', title: t('app.kuaiiot.products.colTagKeys') },
              { key: 'event_count', title: t('app.kuaiiot.products.colEvents') },
              { key: 'function_count', title: t('app.kuaiiot.products.colFunctions') },
              { key: 'remark', title: t('common.remark') },
            ],
          },
        );
        messageApi.success(t('common.exportSuccess', { count: rows.length }));
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('common.exportFailed')));
      }
    },
    [messageApi, t],
  );

  const columns = useMemo<TableColumn<ProductRow>[]>(
    () =>
      alignProColumns<ProductRow>(
        [
          {
            title: t('common.code'),
            dataIndex: 'code',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            copyable: true,
            ellipsis: true,
            sorter: true,
          },
          {
            title: t('common.name'),
            dataIndex: 'name',
            width: 180,
            minWidth: 160,
            ellipsis: true,
            sorter: true,
          },
          {
            title: t('app.kuaiiot.products.colDescription'),
            dataIndex: 'description',
            minWidth: 180,
            uniTableRemainderFlex: true,
            uniTablePrimaryFlex: true,
            resizable: false,
            ellipsis: true,
            hideInSearch: true,
            render: (_, row) => row.description || '—',
          },
          { title: t('common.remark'), dataIndex: 'remark', width: 160, ellipsis: true, hideInSearch: true, render: (_, row) => row.remark || '—' },
          {
            title: '点位数',
            dataIndex: 'tags',
            width: 220,
            minWidth: 160,
            ellipsis: true,
            hideInSearch: true,
            render: (_, row) => (row.tags || []).length,
          },
          {
            title: t('app.kuaiiot.products.colEvents'),
            dataIndex: 'events',
            width: 90,
            minWidth: 90,
            uniTableKeepWidth: true,
            resizable: false,
            align: 'right',
            hideInSearch: true,
            sorter: true,
            render: (_, row) => (row.events || []).length,
          },
          {
            title: t('app.kuaiiot.products.colFunctions'),
            dataIndex: 'functions',
            width: 90,
            minWidth: 90,
            uniTableKeepWidth: true,
            resizable: false,
            align: 'right',
            hideInSearch: true,
            sorter: true,
            render: (_, row) => (row.functions || []).length,
          },
          {
            title: t('common.actions'),
            key: 'action',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) => [
              <Button
                key="detail"
                type="link"
                size="small"
                {...rowActionKind('display')}
                onClick={() => openDetail(row)}
              >
                {t('common.detail')}
              </Button>,
              <Button
                key="edit"
                type="link"
                size="small"
                {...rowActionKind('update')}
                onClick={() => openEdit(row)}
              >
                {t('common.edit')}
              </Button>,
              <Popconfirm
                key="delete"
                title={t('app.kuaiiot.products.deleteConfirm', { name: row.name || row.code })}
                onConfirm={() => void handleDelete(row)}
              >
                <Button type="link" size="small" danger icon={<DeleteOutlined />} {...rowActionKind('skip')}>
                  {t('common.delete')}
                </Button>
              </Popconfirm>,
            ],
          },
        ] as TableColumn<ProductRow>[],
        GLOBAL_DOC_LIST_FIELD_RANK,
      ),
    [t, openDetail, openEdit, handleDelete],
  );

  const detailColumns = useMemo<ProDescriptionsItemProps<ProductRow>[]>(
    () => [
      { title: t('common.code'), dataIndex: 'code' },
      { title: t('common.name'), dataIndex: 'name' },
      { title: t('app.kuaiiot.products.colDescription'), dataIndex: 'description', span: 2 },
      { title: t('common.remark'), dataIndex: 'remark', span: 2 },
    ],
    [t],
  );

  if (!canDisplay) {
    return <Result status="403" title={t('common.noPermission')} />;
  }

  return (
    <ListPageTemplate>
      <UniTable<ProductRow>
        viewTypes={['table', 'help']}
        helpViewConfig={buildListPageHelpViewConfig('kuaiiot.products')}
        columnPersistenceId="apps.kuaiiot.pages.products.list-v1"
        permissionResource="kuaiiot:device"
        actionRef={actionRef}
        rowKey="id"
        headerTitle={t('app.kuaiiot.menu.products')}
        columns={alignIotTableColumns(columns, 'products')}
        showCreateButton={canCreate}
        createButtonText={withSingleNewShortcutHint(t('app.kuaiiot.action.createProduct'))}
        onCreate={openCreate}
        toolBarActionsAfterCreate={[
          ...(canCreate ? [<Button key="load-builtin" loading={builtinBusy} onClick={() => void handleLoadBuiltin()}>加载内置产品</Button>] : []),
          ...(canUpdate
            ? [
                <UniBatchDeleteButton
                  key="batch-delete"
                  selectedRowKeys={selectedRowKeys}
                  onConfirm={handleBatchDelete}
                  confirmTitle={t('common.batchDeleteTitle')}
                  confirmDescription={(count) => t('common.batchDeleteContent', { count })}
                />,
              ]
            : [])
        ]}
        rightToolBarActionsBeforeExport={
          canDisplay
            ? [
                <UniExportMenuButton<ProductRow>
                  key="export"
                  onExport={handleExport}
                  selectedRowKeys={selectedRowKeys}
                  tableData={pageRows}
                />,
              ]
            : []
        }
        enableRowSelection={canUpdate}
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        onTableDataChange={(rows) => {
          setPageRows(rows);
        }}
        defaultPageSize={20}
        request={async (params, sort, _filter, searchFormValues) => {
          try {
            const rows = await listProductRows();
            for (const row of rows) {
              allRowsRef.current.set(row.id, row);
            }
            const filtered = sortLocalRows(filterProductRows(rows, searchFormValues), sort);
            const pageSize = params.pageSize || 20;
            const current = params.current || 1;
            return {
              data: filtered.slice((current - 1) * pageSize, current * pageSize),
              success: true,
              total: filtered.length,
            };
          } catch (e) {
            messageApi.error(getApiErrorMessage(e, t('app.kuaiiot.products.listFailed')));
            return { data: [], success: false, total: 0 };
          }
        }}
      />

      <FormModalTemplate
        title={
          editing
            ? t('app.kuaiiot.products.editTitle')
            : t('app.kuaiiot.action.createProduct')
        }
        open={formOpen}
        onClose={() => {
          setFormOpen(false);
          setEditing(null);
        }}
        isEdit={Boolean(editing)}
        formRef={formRef}
        initialValues={formInitialValues}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        onFinish={handleSubmit}
      >
        <ProFormText
          name="code"
          label={t('common.code')}
          disabled={Boolean(editing)}
          rules={[{ required: !editing, message: t('common.required') }]}
          fieldProps={{ maxLength: 50 }}
        />
        <ProFormText
          name="name"
          label={t('common.name')}
          rules={[{ required: true, message: t('common.required') }]}
          fieldProps={{ maxLength: 100 }}
        />
        <ProFormTextArea
          name="description"
          label={t('app.kuaiiot.products.colDescription')}
          fieldProps={{ rows: 2, maxLength: 500 }}
        />
        <ProFormList
          name="tags"
          label={t('app.kuaiiot.products.sectionTags')}
          creatorButtonProps={{ creatorButtonText: t('app.kuaiiot.action.addTagRow') }}
          copyIconProps={false}
          deleteIconProps={{ tooltipText: t('common.delete') }}
        >
          <ProFormGroup>
            <ProFormItem
              name="tag_key"
              label={t('app.kuaiiot.field.tagKey')}
              rules={[{ required: true, message: t('common.required') }]}
            >
              <AutoComplete
                options={Array.from(new Set(Array.from(allRowsRef.current.values()).flatMap(row => (row.tags ?? []).map(tag => tag.tag_key)))).map(value => ({ value }))}
                style={{ width: 216, maxWidth: '100%' }}
              ><Input maxLength={100} /></AutoComplete>
            </ProFormItem>
            <ProFormText
              name="name"
              label={t('common.name')}
              rules={[{ required: true, message: t('common.required') }]}
              width="sm"
              fieldProps={{ maxLength: 100 }}
            />
            <ProFormSelect
              name="value_type"
              label={t('app.kuaiiot.field.valueType')}
              options={VALUE_TYPE_OPTIONS}
              width="xs"
            />
            <ProFormItem
              name="map_target"
              label={t('app.kuaiiot.field.mapTarget')}
              rules={[{ required: true, message: t('common.required') }]}
            >
              <AutoComplete
                options={MAP_TARGET_OPTIONS}
                placeholder={t('app.kuaiiot.placeholder.mapTargetCustom')}
                style={{ width: 220, maxWidth: '100%' }}
              />
            </ProFormItem>
            <ProFormText name="fill_target" label="填充目标" width="sm" fieldProps={{ maxLength: 100, placeholder: 'spot_check.<项编码> / sop_parameters.<字段>' }} />
            <ProFormText
              name="unit"
              label={t('app.kuaiiot.products.fieldUnit')}
              width="xs"
              fieldProps={{ maxLength: 30 }}
            />
          </ProFormGroup>
        </ProFormList>
        <ProFormList
          name="events"
          label={t('app.kuaiiot.section.events')}
          creatorButtonProps={{ creatorButtonText: t('app.kuaiiot.action.addEventRow') }}
          copyIconProps={false}
          deleteIconProps={{ tooltipText: t('common.delete') }}
        >
          <ProFormGroup>
            <ProFormText
              name="event_key"
              label={t('app.kuaiiot.field.eventKey')}
              rules={[{ required: true, message: t('common.required') }]}
              width="sm"
              fieldProps={{ maxLength: 100 }}
            />
            <ProFormText
              name="name"
              label={t('common.name')}
              rules={[{ required: true, message: t('common.required') }]}
              width="sm"
              fieldProps={{ maxLength: 100 }}
            />
            <ProFormSelect
              name="severity"
              label={t('app.kuaiiot.field.severity')}
              options={SEVERITY_OPTIONS}
              width="xs"
            />
            <ProFormText
              name="message"
              label={t('app.kuaiiot.field.message')}
              width="md"
            />
          </ProFormGroup>
        </ProFormList>
        <ProFormList
          name="functions"
          label={t('app.kuaiiot.section.functions')}
          creatorButtonProps={{ creatorButtonText: t('app.kuaiiot.action.addFunctionRow') }}
          copyIconProps={false}
          deleteIconProps={{ tooltipText: t('common.delete') }}
        >
          <ProFormGroup>
            <ProFormText
              name="function_key"
              label={t('app.kuaiiot.field.functionKey')}
              rules={[{ required: true, message: t('common.required') }]}
              width="sm"
              fieldProps={{ maxLength: 100 }}
            />
            <ProFormText
              name="name"
              label={t('common.name')}
              rules={[{ required: true, message: t('common.required') }]}
              width="sm"
              fieldProps={{ maxLength: 100 }}
            />
            <ProFormDigit
              name="timeout_seconds"
              label={t('app.kuaiiot.field.timeoutSeconds')}
              width="xs"
              min={1}
              fieldProps={{ precision: 0 }}
            />
            <ProFormTextArea
              name="params_json"
              label={t('app.kuaiiot.products.fieldParamsJson')}
              fieldProps={{ rows: 2 }}
            />
            <ProFormTextArea
              name="edge_action_json"
              label={t('app.kuaiiot.products.fieldEdgeActionJson')}
              fieldProps={{ rows: 2 }}
            />
          </ProFormGroup>
        </ProFormList>
        <ProFormTextArea
          name="remark"
          label={t('common.remark')}
          fieldProps={{ rows: 2, maxLength: 500 }}
        />
      </FormModalTemplate>

      <DetailDrawerTemplate
        title={t('app.kuaiiot.products.detailTitle')}
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          setDetail(null);
          setDetailError(null);
          detailIdRef.current = null;
        }}
        size={DRAWER_CONFIG.STANDARD_WIDTH}
        loading={detailLoading}
        plainBody={
          detailError && !detail ? (
            <Result
              status="error"
              title={detailError}
              extra={
                <Button
                  type="primary"
                  onClick={() => {
                    const id = detailIdRef.current;
                    if (id != null) void loadDetail(id);
                  }}
                >
                  {t('common.retry')}
                </Button>
              }
            />
          ) : undefined
        }
        basic={
          detail ? (
            <Descriptions
              column={2}
              size="small"
              items={detailDrawerDescriptionItems(detailColumns, detail)}
            />
          ) : undefined
        }
        linesTitle={detail ? t('app.kuaiiot.products.modelSection') : undefined}
        lines={
          detail ? (
            <>
              <DetailDrawerSection title={t('app.kuaiiot.products.sectionTags')}>
                <Table<ProductTag>
                  rowKey="tag_key"
                  size="small"
                  pagination={false}
                  dataSource={detail.tags || []}
                  columns={[
                    { title: t('app.kuaiiot.field.tagKey'), dataIndex: 'tag_key' },
                    { title: t('common.name'), dataIndex: 'name' },
                    {
                      title: t('app.kuaiiot.field.valueType'),
                      dataIndex: 'value_type',
                      render: (_, tag) => <ValueTypeTag value={tag.value_type} />,
                    },
                    { title: t('app.kuaiiot.field.mapTarget'), dataIndex: 'map_target' },
                    {
                      title: t('app.kuaiiot.products.fieldUnit'),
                      dataIndex: 'unit',
                      render: (_, tag) => tag.unit || '—',
                    },
                  ]}
                />
              </DetailDrawerSection>
              <DetailDrawerSection title={t('app.kuaiiot.section.events')}>
                <Table<ProductEvent>
                  rowKey="event_key"
                  size="small"
                  pagination={false}
                  dataSource={detail.events || []}
                  columns={[
                    { title: t('app.kuaiiot.field.eventKey'), dataIndex: 'event_key' },
                    { title: t('common.name'), dataIndex: 'name' },
                    {
                      title: t('app.kuaiiot.field.severity'),
                      dataIndex: 'severity',
                      render: (_, event) => <SeverityTag value={event.severity} />,
                    },
                    {
                      title: t('app.kuaiiot.field.message'),
                      dataIndex: 'message',
                      render: (_, event) => event.message || '—',
                    },
                  ]}
                />
              </DetailDrawerSection>
              <DetailDrawerSection title={t('app.kuaiiot.section.functions')} marginBottom={0}>
                <Table<ProductFunction>
                  rowKey="function_key"
                  size="small"
                  pagination={false}
                  dataSource={detail.functions || []}
                  columns={[
                    { title: t('app.kuaiiot.field.functionKey'), dataIndex: 'function_key' },
                    { title: t('common.name'), dataIndex: 'name' },
                    {
                      title: t('app.kuaiiot.field.timeoutSeconds'),
                      dataIndex: 'timeout_seconds',
                      render: (_, fn) => fn.timeout_seconds ?? '—',
                    },
                    {
                      title: t('app.kuaiiot.products.colParams'),
                      dataIndex: 'params',
                      render: (_, fn) =>
                        (fn.params || []).map((param) => param.key).join(', ') || '—',
                    },
                  ]}
                />
              </DetailDrawerSection>
            </>
          ) : undefined
        }
      />
    </ListPageTemplate>
  );
};

export default ProductsPage;
