import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns, ProFormInstance } from '@ant-design/pro-components';
import { ProForm } from '@ant-design/pro-components';
import { App, Button, DatePicker, Form, Input, Modal, Rate, Select } from 'antd';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import { rowActionKind, rowActionLabelKeep } from '../../../../../components/uni-action';
import { DetailDrawerActions, ListPageTemplate } from '../../../../../components/layout-templates';
import {
  CustomFieldsDetailSection,
  CustomFieldsFormSection,
  hasCustomFieldsDetailContent,
} from '../../../../../components/custom-fields';
import { UniTable, type UniTableRequestMeta } from '../../../../../components/uni-table';
import { SourceDocumentCode } from '../../../../../components/linked-document-code/SourceDocumentCode';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import { formDateFormItemProps } from '../../../../../utils/formDate';
import { formatDateTime } from '../../../../../utils/format';
import { formatApiErrorDetail } from '../../../../../services/api';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../../utils/uniTableLayoutColumns';
import { CustomerSelectDropdown } from '../../../../master-data/components/CustomerSelectDropdown';
import type { Customer } from '../../../../master-data/types/supply-chain';
import {
  AFTER_SALES_CUSTOMER_NAME_COLUMN_DEFAULTS,
  renderAfterSalesStatusTag,
  renderAfterSalesTypeMarker,
} from '../shared/afterSalesListPresentation';
import { AfterSalesSourceDocumentSelect } from '../shared/AfterSalesSourceDocumentSelect';
import { pickListSearchKeyword, pickSearchString } from '../../../../../utils/tableQueryKey';
import {
  customerReturnVisitApi,
  type CustomerReturnVisit,
  type CustomerReturnVisitPayload,
} from '../../../services/after-sales-service';
import { CustomerReturnVisitDetailDrawer } from './components/CustomerReturnVisitDetailDrawer';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';

const canEditStatus = (status?: string) => status !== '已完成';
const canCompleteStatus = (status?: string) => status === '待登记' || !status;

function customerDisplayName(c: Customer | null | undefined): string {
  if (!c) return '';
  const row = c as Record<string, unknown>;
  return String(row.name ?? row.customer_name ?? '').trim();
}

const RESOURCE = 'kuaizhizao:customer-return-visit';
const CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_customer_return_visits';

const VISIT_METHODS = ['电话', '现场', '在线'];

const ReturnVisitsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const perms = useResourcePermissions(RESOURCE);
  const actionRef = useRef<ActionType>();
  const cfFormRef = useRef<ProFormInstance>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<CustomerReturnVisit | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<CustomerReturnVisit | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailRetryIdRef = useRef<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [completeTarget, setCompleteTarget] = useState<CustomerReturnVisit | null>(null);
  const [completeSubmitting, setCompleteSubmitting] = useState(false);
  const [completeForm] = Form.useForm<{
    visit_method?: string;
    satisfaction_score?: number;
    feedback?: string;
    visited_at_picker?: dayjs.Dayjs;
    notes?: string;
  }>();
  const [form] = Form.useForm<CustomerReturnVisitPayload & { visited_at_picker?: dayjs.Dayjs }>();
  const customerId = Form.useWatch('customer_id', form);
  const sourceType = Form.useWatch('source_type', form) as string | undefined;
  const [blockedSources, setBlockedSources] = useState<Record<number, { disabled: boolean; reason: string }>>({});
  const {
    customFields: formCustomFields,
    customFieldValues: formCustomFieldValues,
    loadFieldValues: loadFormCustomFieldValues,
    extractFormValues: extractCustomFormValues,
    saveCustomFieldValues,
    resetFieldValues: resetFormCustomFieldValues,
  } = useCustomFields({
    tableName: CUSTOM_FIELD_TABLE,
    hostResource: RESOURCE,
    loadWhenOpen: true,
    open: modalOpen,
  });
  const {
    customFields: listCustomFields,
    customFieldValues: detailCustomFieldValues,
    generateCustomFieldColumns,
    enrichRecordsWithCustomFields,
    loadFieldValuesForDetail,
    resetDetailFieldValues,
  } = useCustomFieldsForList<CustomerReturnVisit>({
    tableName: CUSTOM_FIELD_TABLE,
    hostResource: RESOURCE,
  });
  const customFieldColumns = generateCustomFieldColumns();
  const showDetailCustomFields = hasCustomFieldsDetailContent(
    listCustomFields,
    detailCustomFieldValues,
  );

  useEffect(() => {
    if (!modalOpen) return;
    let cancelled = false;
    void customerReturnVisitApi
      .list({ skip: 0, limit: 200 })
      .then((res) => {
        if (cancelled) return;
        const blocked: Record<number, { disabled: boolean; reason: string }> = {};
        for (const row of res.items ?? []) {
          if (sourceType && row.source_type !== sourceType) continue;
          if (editing?.id && row.id === editing.id) continue;
          blocked[row.source_id] = {
            disabled: true,
            reason: t('app.kuaizhizao.afterSalesService.returnVisit.sourceAlreadyVisited', {
              code: row.visit_code,
            }),
          };
        }
        setBlockedSources(blocked);
      })
      .catch(() => {
        if (!cancelled) setBlockedSources({});
      });
    return () => {
      cancelled = true;
    };
  }, [editing?.id, modalOpen, sourceType, t]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    resetFormCustomFieldValues();
    form.setFieldsValue({ visit_method: '电话', visited_at_picker: dayjs() });
    setModalOpen(true);
  };

  const loadDetail = useCallback(async (id: number) => {
    setDetailLoading(true);
    setDetailError(null);
    resetDetailFieldValues();
    try {
      setDetail(await customerReturnVisitApi.get(id));
      await loadFieldValuesForDetail(id);
    } catch (error) {
      setDetail(null);
      setDetailError(getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.detail.loadFailed')));
    } finally {
      setDetailLoading(false);
    }
  }, [loadFieldValuesForDetail, resetDetailFieldValues, t]);

  const openDetail = (row: CustomerReturnVisit) => {
    detailRetryIdRef.current = row.id;
    setDetailOpen(true);
    setDetail(null);
    setDetailError(null);
    void loadDetail(row.id);
  };

  const openEdit = async (row: CustomerReturnVisit) => {
    const full = await customerReturnVisitApi.get(row.id);
    setEditing(full);
    form.setFieldsValue({
      ...full,
      visited_at_picker: full.visited_at ? dayjs(full.visited_at) : undefined,
    });
    setModalOpen(true);
    const cfValues = await loadFormCustomFieldValues(full.id);
    cfFormRef.current?.setFieldsValue(cfValues);
  };

  const openComplete = useCallback((row: CustomerReturnVisit) => {
    setCompleteTarget(row);
    completeForm.setFieldsValue({
      visit_method: row.visit_method || '电话',
      satisfaction_score: row.satisfaction_score ?? undefined,
      feedback: row.feedback ?? undefined,
      visited_at_picker: row.visited_at ? dayjs(row.visited_at) : dayjs(),
      notes: row.notes ?? undefined,
    });
    setCompleteOpen(true);
  }, [completeForm]);

  const refreshOpenDetail = useCallback(
    async (id: number) => {
      actionRef.current?.reload();
      if (detail?.id === id) {
        setDetail(await customerReturnVisitApi.get(id));
      }
    },
    [detail?.id],
  );

  const executeComplete = useCallback(async () => {
    if (!completeTarget) return;
    const values = await completeForm.validateFields();
    setCompleteSubmitting(true);
    try {
      await customerReturnVisitApi.complete(completeTarget.id, {
        satisfaction_score: Number(values.satisfaction_score),
        visit_method: values.visit_method,
        feedback: values.feedback,
        visited_at: values.visited_at_picker?.format('YYYY-MM-DD HH:mm:ss'),
        notes: values.notes,
      });
      message.success(t('app.kuaizhizao.afterSalesService.returnVisit.completeSuccess'));
      setCompleteOpen(false);
      setCompleteTarget(null);
      await refreshOpenDetail(completeTarget.id);
    } catch (error) {
      message.error(
        getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.returnVisit.actionFailed')),
      );
      throw error;
    } finally {
      setCompleteSubmitting(false);
    }
  }, [completeForm, completeTarget, message, refreshOpenDetail, t]);

  const columns: ProColumns<CustomerReturnVisit>[] = useMemo(
    () =>
      alignProColumns<CustomerReturnVisit>(
        [
          {
            title: t('app.kuaizhizao.afterSalesService.returnVisit.field.visitCode'),
            dataIndex: 'visit_code',
            width: 188,
            minWidth: 188,
            uniTableKeepWidth: true,
            resizable: false,
            fixed: 'left',
            copyable: true,
          },
          {
            title: t('app.kuaizhizao.afterSalesService.returnVisit.field.customerName'),
            dataIndex: 'customer_name',
            ...AFTER_SALES_CUSTOMER_NAME_COLUMN_DEFAULTS,
          },
          {
            title: t('app.kuaizhizao.afterSalesService.returnVisit.field.sourceCode'),
            dataIndex: 'source_code',
            width: 188,
            minWidth: 188,
            uniTableKeepWidth: true,
            resizable: false,
            render: (_, row) => (
              <SourceDocumentCode
                sourceType={row.source_type}
                sourceId={row.source_id}
                sourceCode={row.source_code}
              />
            ),
          },
          {
            title: t('app.kuaizhizao.afterSalesService.returnVisit.field.visitMethod'),
            dataIndex: 'visit_method',
            ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
            render: (_, row) => renderAfterSalesTypeMarker(row.visit_method),
          },
          {
            title: t('app.kuaizhizao.afterSalesService.returnVisit.field.satisfactionScore'),
            dataIndex: 'satisfaction_score',
            width: 132,
            minWidth: 132,
            uniTableKeepWidth: true,
            resizable: false,
            align: 'center',
            render: (_, row) =>
              row.satisfaction_score != null ? (
                <Rate disabled value={Number(row.satisfaction_score)} count={5} style={{ fontSize: 14 }} />
              ) : (
                '-'
              ),
          },
          {
            // 无行项目：客户反馈吃余量（对齐工单「问题描述」）；单号统一 188
            title: t('app.kuaizhizao.afterSalesService.returnVisit.field.feedback'),
            dataIndex: 'feedback',
            minWidth: 160,
            uniTableRemainderFlex: true,
            uniTablePrimaryFlex: true,
            resizable: false,
            ellipsis: true,
            hideInSearch: true,
            render: (_, row) => {
              const text = String(row.feedback ?? '').trim();
              return text || '—';
            },
          },
          {
            title: t('app.kuaizhizao.afterSalesService.returnVisit.field.visitedAt'),
            dataIndex: 'visited_at',
            width: 168,
            minWidth: 168,
            uniTableKeepWidth: true,
            resizable: false,
            render: (_, row) => (row.visited_at ? formatDateTime(row.visited_at) : '-'),
          },
          {
            title: t('common.status'),
            key: 'lifecycle',
            dataIndex: 'status',
            fixed: 'right',
            valueType: 'select',
            valueEnum: {
              待登记: { text: '待登记' },
              已完成: { text: '已完成' },
            },
            render: (_, row) => renderAfterSalesStatusTag(row.status),
          },
          ...customFieldColumns,
          {
            title: t('common.actions'),
            key: 'action',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) => {
              const parts: React.ReactNode[] = [
                <Button
                  {...rowActionKind('read')}
                  key="read"
                  onClick={() => openDetail(row)}
                />,
              ];
              if (perms.canUpdate && canEditStatus(row.status)) {
                parts.push(
                  <Button
                    {...rowActionKind('update')}
                    key="edit"
                    onClick={() => void openEdit(row)}
                  />,
                );
              }
              if (perms.canUpdate && canCompleteStatus(row.status)) {
                parts.push(
                  <Button
                    key="complete"
                    {...rowActionKind('complete')}
                    {...rowActionLabelKeep()}
                    onClick={(e) => {
                      e.stopPropagation();
                      openComplete(row);
                    }}
                  >
                    {t('app.kuaizhizao.afterSalesService.returnVisit.actionComplete')}
                  </Button>,
                );
              }
              return parts;
            },
          },
        ],
        SALES_DOC_LIST_FIELD_RANK,
      ),
    [customFieldColumns, openComplete, perms.canUpdate, t],
  );

  return (
    <ListPageTemplate>
      <UniTable<CustomerReturnVisit>
        viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.afterSalesReturnVisit)}
        actionRef={actionRef}
        columns={columns}
        columnPersistenceId="apps.kuaizhizao.pages.after-sales-service.return-visits.v9-complete"
        showAdvancedSearch
        skipFuzzyPinyinClientFilter
        rowKey="id"
        headerTitle={t('app.kuaizhizao.menu.after-sales-service.return-visits')}
        request={async (params, _sort, _filter, searchFormValues, meta?: UniTableRequestMeta) => {
          const res = await customerReturnVisitApi.list({
            skip: ((params.current || 1) - 1) * (params.pageSize || 20),
            limit: params.pageSize,
            keyword: pickListSearchKeyword(searchFormValues),
            status: pickSearchString(searchFormValues, 'status'),
          });
          const data =
            meta?.purpose === 'prefetch'
              ? res.items
              : await enrichRecordsWithCustomFields(res.items);
          return { data, total: res.total, success: true };
        }}
        showCreateButton={perms.canCreate}
        createButtonText={t('app.kuaizhizao.afterSalesService.returnVisit.createTitle')}
        onCreate={openCreate}
        enableRowSelection={perms.canDelete}
        showDeleteButton={perms.canDelete}
        deleteButtonText={t('common.delete')}
        onDelete={async (keys) => {
          await Promise.all(keys.map((key) => customerReturnVisitApi.delete(Number(key))));
          message.success(t('common.batchDeleteSuccess', { count: keys.length }));
    actionRef.current?.reload();
        }}
      />

      <Modal
        open={modalOpen}
        title={
          editing
            ? t('app.kuaizhizao.afterSalesService.returnVisit.editTitle')
            : t('app.kuaizhizao.afterSalesService.returnVisit.createTitle')
        }
        onCancel={() => {
          resetFormCustomFieldValues();
          setModalOpen(false);
        }}
        confirmLoading={submitting}
        onOk={async () => {
          try {
            const values = await form.validateFields();
            const { visited_at_picker, ...rest } = values;
            const payload: CustomerReturnVisitPayload = {
              ...rest,
              visited_at: visited_at_picker?.format('YYYY-MM-DD HH:mm:ss') ?? '',
            };
            const cfValues = cfFormRef.current?.getFieldsValue?.(true) ?? {};
            const { customData } = extractCustomFormValues(cfValues, cfFormRef.current);
            setSubmitting(true);
            let savedId = editing?.id;
            if (editing) {
              await customerReturnVisitApi.update(editing.id, payload);
              message.success(t('common.saveSuccess'));
            } else {
              const created = await customerReturnVisitApi.create(payload);
              savedId = created.id;
              message.success(t('common.createSuccess'));
            }
            if (savedId != null) {
              await saveCustomFieldValues(savedId, customData);
            }
            resetFormCustomFieldValues();
            setModalOpen(false);
            actionRef.current?.reload();
          } catch (error: unknown) {
            if (error && typeof error === 'object' && 'errorFields' in error) {
              return;
            }
            message.error(formatApiErrorDetail(error) || t('common.saveFailed'));
          } finally {
            setSubmitting(false);
          }
        }}
        destroyOnHidden
        width={720}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="customer_name" hidden>
            <Input />
          </Form.Item>
          <Form.Item
            name="customer_id"
            label={t('app.kuaizhizao.afterSalesService.returnVisit.field.customerName')}
            rules={[{ required: true, message: t('app.kuaizhizao.afterSalesTicket.selectCustomerFirst') }]}
          >
            <CustomerSelectDropdown
              hostResource={RESOURCE}
              placeholder={t('app.kuaizhizao.afterSalesTicket.selectCustomerFirst')}
              style={{ width: '100%' }}
              onCustomerPick={(c) => {
                form.setFieldsValue({
                  customer_id: c?.id,
                  customer_name: customerDisplayName(c),
                  source_id: undefined,
                  source_code: undefined,
                });
              }}
            />
          </Form.Item>
          <AfterSalesSourceDocumentSelect
            customerId={customerId}
            allowedTypes={['after_sales_ticket', 'repair_order']}
            typeLabelKeyPrefix="app.kuaizhizao.afterSalesService.returnVisit.field"
            optionStateById={blockedSources}
          />
          <Form.Item name="visit_method" label={t('app.kuaizhizao.afterSalesService.returnVisit.field.visitMethod')}>
            <Select options={VISIT_METHODS.map((value) => ({ value, label: value }))} />
          </Form.Item>
          <Form.Item
            name="satisfaction_score"
            label={t('app.kuaizhizao.afterSalesService.returnVisit.field.satisfactionScore')}
          >
            <Rate count={5} />
          </Form.Item>
          <Form.Item
            name="visited_at_picker"
            label={t('app.kuaizhizao.afterSalesService.returnVisit.field.visitedAt')}
            rules={[{ required: true, message: t('common.required') }]}
            {...formDateFormItemProps}
          >
            <DatePicker showTime style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="feedback" label={t('app.kuaizhizao.afterSalesService.returnVisit.field.feedback')}>
            <Input.TextArea rows={3} />
          </Form.Item>
          {formCustomFields.length > 0 ? (
            <ProForm formRef={cfFormRef} submitter={false} grid={false}>
              <CustomFieldsFormSection
                customFields={formCustomFields}
                customFieldValues={formCustomFieldValues}
                gridColumns={1}
              />
            </ProForm>
          ) : null}
          <Form.Item name="notes" label={t('common.remark')}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <CustomerReturnVisitDetailDrawer
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false);
          setDetail(null);
          setDetailError(null);
          resetDetailFieldValues();
        }}
        record={detail}
        loading={detailLoading}
        error={detailError}
        onRetry={() => {
          const id = detailRetryIdRef.current;
          if (id != null) void loadDetail(id);
        }}
        supplementaryTitle={
          showDetailCustomFields
            ? t('app.master-data.customFields', { defaultValue: '自定义字段' })
            : undefined
        }
        supplementary={
          showDetailCustomFields ? (
            <CustomFieldsDetailSection
              customFields={listCustomFields}
              customFieldValues={detailCustomFieldValues}
            />
          ) : undefined
        }
        extra={
          <DetailDrawerActions
            items={[
              {
                key: 'edit',
                visible: Boolean(detail && perms.canUpdate && canEditStatus(detail.status)),
                render: (
                  <Button
                    onClick={() => {
                      if (!detail) return;
                      void openEdit(detail);
                    }}
                  >
                    {t('common.edit')}
                  </Button>
                ),
              },
              {
                key: 'complete',
                visible: Boolean(detail && perms.canUpdate && canCompleteStatus(detail.status)),
                render: (
                  <Button
                    type="primary"
                    onClick={() => {
                      if (!detail) return;
                      openComplete(detail);
                    }}
                  >
                    {t('app.kuaizhizao.afterSalesService.returnVisit.actionComplete')}
                  </Button>
                ),
              },
            ]}
          />
        }
      />

      <Modal
        open={completeOpen}
        title={t('app.kuaizhizao.afterSalesService.returnVisit.completeTitle')}
        onCancel={() => {
          setCompleteOpen(false);
          setCompleteTarget(null);
        }}
        confirmLoading={completeSubmitting}
        onOk={() => executeComplete()}
        destroyOnHidden
        width={520}
      >
        <Form form={completeForm} layout="vertical">
          <Form.Item
            name="visit_method"
            label={t('app.kuaizhizao.afterSalesService.returnVisit.field.visitMethod')}
            rules={[{ required: true, message: t('common.required') }]}
          >
            <Select options={VISIT_METHODS.map((value) => ({ value, label: value }))} />
          </Form.Item>
          <Form.Item
            name="satisfaction_score"
            label={t('app.kuaizhizao.afterSalesService.returnVisit.field.satisfactionScore')}
            rules={[{ required: true, message: t('app.kuaizhizao.afterSalesService.returnVisit.scoreRequired') }]}
          >
            <Rate count={5} />
          </Form.Item>
          <Form.Item
            name="visited_at_picker"
            label={t('app.kuaizhizao.afterSalesService.returnVisit.field.visitedAt')}
            rules={[{ required: true, message: t('common.required') }]}
            {...formDateFormItemProps}
          >
            <DatePicker showTime style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="feedback" label={t('app.kuaizhizao.afterSalesService.returnVisit.field.feedback')}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="notes" label={t('common.remark')}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </ListPageTemplate>
  );
};

export default ReturnVisitsPage;
