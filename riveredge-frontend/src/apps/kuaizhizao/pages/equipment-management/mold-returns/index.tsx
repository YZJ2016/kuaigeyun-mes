import React, { useRef, useState, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ActionType,
  ProColumns,
  ProDescriptionsItemProps,
  ProFormDatePicker,
  ProFormDigit,
  ProFormSelect,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { App, Button, Row, Col } from 'antd';
import dayjs from 'dayjs';
import { useSearchParams } from 'react-router-dom';
import { EQUIPMENT_DATE_FIELD_PROPS } from '../../../utils/equipmentFormFieldProps';
import { UniTable } from '../../../../../components/uni-table';
import { ListPageTemplate, FormModalTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useNewShortcut } from '../../../../../hooks/useNewShortcut';
import { withSingleNewShortcutHint } from '../../../../../utils/globalNewShortcut';
import { rowActionKind } from '../../../../../components/uni-action';
import { borrowsApi, returnsApi } from '../../../services/moldOps';
import { formDateRangeFormItemProps } from '../../../../../utils/formDate';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { buildDocumentAuditColumns } from '../../shared/documentAuditColumns';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import {
  normalizeEquipmentListResponse,
  resolveAssetWorkflowListParams,
} from '../../../utils/equipmentListCore';
import {
  buildDetailDrawerEditExtra,
  EquipmentMasterDetailDrawer,
  useEquipmentDetailDrawer,
} from '../shared/equipmentMasterDataDetail';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';


const P = 'app.kuaizhizao.moldOps.return';
const RESOURCE = 'kuaizhizao:mold-return';

interface MoldReturn {
  id?: number;
  document_no?: string;
  return_no?: string;
  borrow_id?: number;
  borrow_no?: string;
  borrow_document_no?: string;
  mold_id?: number;
  mold_code?: string;
  mold_name?: string;
  return_date?: string;
  manufacture_qty?: number;
  usage_count?: number;
  remark?: string;
  updated_at?: string;
}

type BorrowOption = {
  label: string;
  value: number;
  moldId: number;
};

const MoldReturnsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const perms = useResourcePermissions(RESOURCE);
  const actionRef = useRef<ActionType>(null);
  const formRef = useRef<any>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [isEdit, setIsEdit] = useState(false);
  const [current, setCurrent] = useState<MoldReturn | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [borrowOptions, setBorrowOptions] = useState<BorrowOption[]>([]);
  const [formInitialValues, setFormInitialValues] = useState<Record<string, unknown> | undefined>();
  const pushHandledRef = useRef<string | null>(null);
  const { open: detailVisible, loading: detailLoading, detail, openDetail, closeDetail } =
    useEquipmentDetailDrawer<MoldReturn>();

  const handleDetail = (record: MoldReturn) => {
    if (!record.id) return;
    void openDetail(() => returnsApi.get(record.id!), t(`${P}.listFailed`));
  };

  const loadBorrowOptions = async (): Promise<BorrowOption[]> => {
    const res = await borrowsApi.listOutstanding({ limit: 500 });
    const options = (res.items ?? []).map(
      (b: {
        id: number;
        document_no?: string;
        borrow_no?: string;
        mold_name?: string;
        mold_id?: number;
      }) => ({
        label: `${b.document_no ?? b.borrow_no ?? b.id} - ${b.mold_name ?? ''}`,
        value: b.id,
        moldId: Number(b.mold_id),
      }),
    );
    setBorrowOptions(options);
    return options;
  };

  const applyUsagePreview = async (borrowId: number) => {
    try {
      const preview = await returnsApi.usagePreview(borrowId);
      formRef.current?.setFieldsValue({
        borrow_id: borrowId,
        mold_id: preview.mold_id,
        manufacture_qty: preview.manufacture_qty ?? undefined,
        usage_count: preview.usage_count ?? 1,
      });
      setFormInitialValues((prev) => ({
        ...(prev || {}),
        borrow_id: borrowId,
        mold_id: preview.mold_id,
        manufacture_qty: preview.manufacture_qty ?? undefined,
        usage_count: preview.usage_count ?? 1,
      }));
    } catch (error: unknown) {
      messageApi.error(getApiErrorMessage(error, t(`${P}.usagePreviewFailed`)));
    }
  };

  const openCreate = async (prefillBorrowId?: number) => {
    setIsEdit(false);
    setCurrent(null);
    const options = await loadBorrowOptions();
    const borrowId = prefillBorrowId;
    const moldId = borrowId
      ? options.find((o) => o.value === borrowId)?.moldId
      : undefined;
    setFormInitialValues({
      return_date: dayjs(),
      usage_count: 1,
      borrow_id: borrowId,
      mold_id: moldId,
    });
    setModalVisible(true);
    if (borrowId) {
      void applyUsagePreview(borrowId);
    }
  };

  const handleCreate = () => {
    void openCreate();
  };
  useNewShortcut(handleCreate);

  useEffect(() => {
    const borrowIdRaw = searchParams.get('borrow_id');
    if (!borrowIdRaw || !perms.canCreate) return;
    if (pushHandledRef.current === borrowIdRaw) return;
    pushHandledRef.current = borrowIdRaw;
    const borrowId = Number(borrowIdRaw);
    if (!Number.isFinite(borrowId)) return;
    void openCreate(borrowId);
    const next = new URLSearchParams(searchParams);
    next.delete('borrow_id');
    setSearchParams(next, { replace: true });
  }, [searchParams, perms.canCreate]);

  const handleEdit = async (record: MoldReturn) => {
    if (!record.id) return;
    try {
      const detail = await returnsApi.get(record.id);
      setIsEdit(true);
      setCurrent(detail);
      await loadBorrowOptions();
      setFormInitialValues({
        borrow_id: detail.borrow_id,
        mold_id: detail.mold_id,
        return_date: detail.return_date ? dayjs(detail.return_date) : dayjs(),
        manufacture_qty: detail.manufacture_qty,
        usage_count: detail.usage_count,
        remark: detail.remark,
      });
      setModalVisible(true);
    } catch (error: unknown) {
      messageApi.error(getApiErrorMessage(error, t(`${P}.listFailed`)));
    }
  };

  const executeDelete = async (keys: React.Key[]) => {
    try {
      for (const id of keys) {
        await returnsApi.delete(Number(id));
      }
      messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
      actionRef.current?.reload();
    } catch (error: unknown) {
      messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
    }
  };

  const handleSubmit = async (values: Record<string, unknown>) => {
    const borrowId = Number(values.borrow_id);
    const moldIdFromOption = borrowOptions.find((o) => o.value === borrowId)?.moldId;
    const moldId = Number(values.mold_id ?? moldIdFromOption);
    if (!Number.isFinite(moldId) || moldId <= 0) {
      messageApi.error(t(`${P}.moldRequired`));
      return;
    }
    const payload = {
      mold_id: moldId,
      borrow_id: Number.isFinite(borrowId) ? borrowId : undefined,
      return_date: (values.return_date as dayjs.Dayjs)?.format('YYYY-MM-DD'),
      usage_count: Number(values.usage_count) || 1,
      remark: values.remark,
    };
    setSubmitting(true);
    try {
      if (isEdit && current?.id) {
        await returnsApi.update(current.id, payload);
        messageApi.success(t('common.updateSuccess'));
      } else {
        await returnsApi.create(payload);
        messageApi.success(t('common.createSuccess'));
      }
      setModalVisible(false);
      setFormInitialValues(undefined);
      actionRef.current?.reload();
    } catch (error: unknown) {
      messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
    } finally {
      setSubmitting(false);
    }
  };

  const detailColumns: ProDescriptionsItemProps<MoldReturn>[] = useMemo(
    () => [
      {
        title: t(`${P}.col.returnNo`),
        dataIndex: 'document_no',
        render: (_, r) => r.document_no ?? r.return_no ?? '-',
      },
      {
        title: t(`${P}.col.borrowNo`),
        dataIndex: 'borrow_document_no',
        render: (_, r) => r.borrow_document_no ?? r.borrow_no ?? '-',
      },
      { title: t(`${P}.col.mold`), dataIndex: 'mold_name' },
      { title: t(`${P}.col.returnDate`), dataIndex: 'return_date', valueType: 'date' },
      { title: t(`${P}.col.manufactureQty`), dataIndex: 'manufacture_qty' },
      { title: t(`${P}.col.usageCount`), dataIndex: 'usage_count' },
      { title: t('common.remark'), dataIndex: 'remark', span: 2 },
    ],
    [t],
  );

  const columns: ProColumns<MoldReturn>[] = useMemo(() => alignProColumns<MoldReturn>([
      {
        title: t(`${P}.col.returnDate`),
        dataIndex: 'doc_date_range',
        valueType: 'dateRange',
        hideInTable: true,
        formItemProps: formDateRangeFormItemProps,
        search: { order: 10 } as ProColumns['search'],
      },
      {
        title: t('common.updatedAt'),
        dataIndex: 'updated_at_range',
        valueType: 'dateRange',
        hideInTable: true,
        formItemProps: formDateRangeFormItemProps,
        search: { order: 11 } as ProColumns['search'],
      },
      {
        title: t(`${P}.col.returnNo`),
        dataIndex: 'document_no',
        width: 160,
        minWidth: 160,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        fixed: 'left',
        sorter: true,
        search: { order: 30 } as ProColumns['search'],
        render: (_, r) => {
          const no = r.document_no ?? r.return_no;
          return no != null && no !== '' ? String(no) : '-';
        },
      },
      {
        title: t(`${P}.col.borrowNo`),
        dataIndex: 'borrow_document_no',
        width: 130,
        minWidth: 130,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        hideInSearch: true,
        render: (_, r) => {
          const no = r.borrow_document_no ?? r.borrow_no;
          return no != null && no !== '' ? String(no) : '-';
        },
      },
      {
        title: t(`${P}.col.mold`),
        dataIndex: 'mold_name',
        minWidth: 160,
        uniTablePrimaryFlex: true,
        uniTableRemainderFlex: true,
        resizable: false,
        ellipsis: true,
        hideInSearch: true,
        render: (_, r) => (r.mold_name != null && r.mold_name !== '' ? String(r.mold_name) : '-'),
      },
      {
        title: t(`${P}.col.returnDate`),
        dataIndex: 'return_date',
        width: 132,
        minWidth: 132,
        uniTableKeepWidth: true,
        resizable: false,
        sorter: true,
        hideInSearch: true,
        valueType: 'date',
      },
      {
        title: t(`${P}.col.manufactureQty`),
        dataIndex: 'manufacture_qty',
        width: 100,
        minWidth: 100,
        uniTableKeepWidth: true,
        resizable: false,
        sorter: true,
        hideInSearch: true,
        render: (_, r) => (r.manufacture_qty != null ? String(r.manufacture_qty) : '-'),
      },
      {
        title: t(`${P}.col.usageCount`),
        dataIndex: 'usage_count',
        width: 90,
        minWidth: 90,
        uniTableKeepWidth: true,
        resizable: false,
        sorter: true,
        hideInSearch: true,
        render: (_, r) => (r.usage_count != null ? String(r.usage_count) : '-'),
      },
      ...buildDocumentAuditColumns<Record<string, unknown>>(t),
      {
        title: t('common.actions'),
        key: 'option',
        fixed: 'right',
        hideInSearch: true,
        render: (_, record) => (
          <>
            <Button
              {...rowActionKind('read')}
              type="link"
              size="small"
              onClick={(e) => {
                e.stopPropagation();
                handleDetail(record);
              }}
            >
              {t('common.detail')}
            </Button>
            {perms.canUpdate && (
              <Button
                {...rowActionKind('update')}
                type="link"
                size="small"
                onClick={(e) => {
                  e.stopPropagation();
                  void handleEdit(record);
                }}
              >
                {t('common.edit')}
              </Button>
            )}
            {perms.canDelete && (
              <ActionConfirmPopconfirm
                title={t('common.deleteTitle')}
                onConfirm={() => record.id && void executeDelete([record.id])}
              >
                <Button
                  {...rowActionKind('delete')}
                  type="link"
                  size="small"
                  danger
                  onClick={(e) => e.stopPropagation()}
                >
                  {t('common.delete')}
                </Button>
              </ActionConfirmPopconfirm>
            )}
          </>
        ),
      },
    ], SALES_DOC_LIST_FIELD_RANK),
    [t, perms],
  );

  return (
    <>
      <ListPageTemplate>
        <UniTable<MoldReturn>
          viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.moldReturns)}
          headerTitle={t(`${P}.title`)}
          columnPersistenceId="apps.kuaizhizao.pages.equipment-management.mold-returns-width-v3"
          actionRef={actionRef}
          rowKey="id"
          columns={columns}
          showAdvancedSearch
          skipFuzzyPinyinClientFilter
          request={async (params, sort, _filter, searchFormValues) => {
            try {
              const listParams = resolveAssetWorkflowListParams(searchFormValues, sort);
              const res = await returnsApi.list({
                skip: ((params.current ?? 1) - 1) * (params.pageSize ?? 20),
                limit: params.pageSize,
                ...listParams,
              });
              const { data, total } = normalizeEquipmentListResponse(res);
              return { data: data as MoldReturn[], success: true, total };
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
          onDelete={executeDelete}
          enableRowSelection={perms.canDelete}
        />
      </ListPageTemplate>

      <FormModalTemplate
        title={isEdit ? t(`${P}.editModal`) : t(`${P}.createModal`)}
        open={modalVisible}
        onClose={() => {
          setModalVisible(false);
          setFormInitialValues(undefined);
        }}
        onFinish={handleSubmit}
        isEdit={isEdit}
        loading={submitting}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        formRef={formRef}
        initialValues={formInitialValues}
        grid={false}
      >
        <Row gutter={16}>
          <Col span={24}>
            <ProFormSelect
              name="borrow_id"
              label={t(`${P}.form.borrow`)}
              options={borrowOptions}
              rules={[{ required: true }]}
              showSearch
              disabled={isEdit}
              fieldProps={{
                onChange: (value: number) => {
                  const moldId = borrowOptions.find((o) => o.value === value)?.moldId;
                  formRef.current?.setFieldsValue({ mold_id: moldId });
                  if (value) void applyUsagePreview(value);
                },
              }}
            />
            <ProFormDigit name="mold_id" hidden />
          </Col>
          <Col span={12}>
            <ProFormDatePicker
              name="return_date"
              label={t(`${P}.col.returnDate`)}
              rules={[{ required: true }]}
              fieldProps={EQUIPMENT_DATE_FIELD_PROPS}
            />
          </Col>
          <Col span={12}>
            <ProFormDigit
              name="manufacture_qty"
              label={t(`${P}.col.manufactureQty`)}
              min={0}
              fieldProps={{ disabled: true }}
              tooltip={t(`${P}.form.manufactureQtyHint`)}
            />
          </Col>
          <Col span={12}>
            <ProFormDigit
              name="usage_count"
              label={t(`${P}.col.usageCount`)}
              min={1}
              rules={[{ required: true }]}
            />
          </Col>
          <Col span={24}>
            <ProFormTextArea name="remark" label={t('common.remark')} fieldProps={{ rows: 2 }} />
          </Col>
        </Row>
      </FormModalTemplate>

      <EquipmentMasterDetailDrawer
        open={detailVisible}
        loading={detailLoading}
        detail={detail}
        title={`${t('common.detail')}${detail?.document_no ?? detail?.return_no ? ` - ${detail.document_no ?? detail.return_no}` : ''}`}
        onClose={closeDetail}
        basicColumns={detailColumns}
        extra={buildDetailDrawerEditExtra(t, Boolean(detail && perms.canUpdate), () => {
          if (!detail) return;
          closeDetail();
          void handleEdit(detail);
        })}
      />
    </>
  );
};

export default MoldReturnsPage;
