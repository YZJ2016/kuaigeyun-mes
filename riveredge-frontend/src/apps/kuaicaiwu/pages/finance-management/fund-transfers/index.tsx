import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import {
  ProFormDatePicker,
  ProFormDependency,
  ProFormDigit,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { App, Button, Col, Descriptions, Row } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import {
  DetailDrawerActions,
  DetailDrawerTemplate,
  DRAWER_CONFIG,
  FormModalTemplate,
  ListPageTemplate,
  MODAL_CONFIG,
} from '../../../../../components/layout-templates';
import { UniTable } from '../../../../../components/uni-table';
import { UniTableStackedPrimaryCell } from '../../../../../components/uni-table/stackedPrimaryColumn';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import {
  UniBatchMenuButton,
  pickCapability,
  runCapabilityBatchLoop,
  useAuditBatchRunner,
  withDocumentSubmitCombinedItem,
  type UniBatchMenuItem,
} from '../../../../../components/uni-batch';
import { UniPullCreateToolbar } from '../../../../../components/uni-pull';
import { rowActionKind } from '../../../../../components/uni-action';
import { UniWorkflowActions } from '../../../../../components/uni-workflow-actions';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { createListAuditPhaseColumn } from '../../../../kuaizhizao/pages/sales-management/shared/listAuditPhaseColumn';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useAuditRequired } from '../../../../../hooks/useAuditRequired';
import { isPendingReviewStatus } from '../../../../kuaizhizao/constants/documentStatus';
import { formatDateTime } from '../../../../../utils/format';
import { formDateRangeFormItemProps, toApiDateString } from '../../../../../utils/formDate';
import { renderDocumentStatusTag } from '../../../../../utils/documentLifecycleStatusTag';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../../utils/uniTableLayoutColumns';
import {
  FINANCE_DOC_PINNED_STATUS_FIELD,
  financeDocCreatedUpdatedColumns,
} from '../../../utils/financeListCore';
import { buildVoucherStatusEnum, formatBankAccountOptionLabel } from '../../../utils/financeSharedOptions';
import { bankAccountService, type BankAccount } from '../../../services/finance/bank-account';
import {
  FUND_TRANSFER_RESOURCE,
  fundTransferService,
  type FundTransfer,
  type FundTransferType,
} from '../../../services/finance/fund-transfer';
import DocumentAttachmentsField from '../../../../kuaizhizao/components/DocumentAttachmentsField';
import { normalizeDocumentAttachments } from '../../../../kuaizhizao/utils/documentAttachments';
import { formatCurrencyAmount } from '../../../../../utils/format';
import { pickSearchString } from '../../../../../utils/tableQueryKey';
import { getFinanceVoucherLifecycle } from '../../../utils/financeLifecycle';
import { UniLifecycle } from '../../../../../components/uni-lifecycle';

const P = 'app.kuaicaiwu.fundTransfer';
const FUND_TRANSFER_ENTITY = 'fund_transfer';

const isReviewApproved = (row: FundTransfer) => {
  const raw = String(row.review_status || '').trim();
  return ['已审核', 'approved', '审核通过', '已通过', '通过'].includes(raw);
};

const transferTypeLabel = (type: string, t: (k: string) => string) => {
  const key = `${P}.transferType.${type}`;
  const text = t(key);
  return text === key ? type : text;
};

const FundTransfersPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const perms = useResourcePermissions(FUND_TRANSFER_RESOURCE);
  const fundTransferAuditEnabled = useAuditRequired(FUND_TRANSFER_ENTITY, false);
  const fundTransferAuditColumn = useMemo(
    () =>
      createListAuditPhaseColumn<FundTransfer>({
        t,
        auditEnabled: fundTransferAuditEnabled,
      }),
    [t, fundTransferAuditEnabled],
  );
  const actionRef = useRef<ActionType>();
  const tableRowsRef = useRef<FundTransfer[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [tableRows, setTableRows] = useState<FundTransfer[]>([]);
  const [bankAccounts, setBankAccounts] = useState<BankAccount[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<FundTransfer | null>(null);
  const [createSeed, setCreateSeed] = useState<Record<string, unknown> | undefined>(undefined);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailRecord, setDetailRecord] = useState<FundTransfer | null>(null);

  const selectedRecordsForBatch = useMemo(
    () => tableRows.filter((row) => row.id != null && selectedRowKeys.includes(row.id)),
    [tableRows, selectedRowKeys],
  );

  const handleFundTransferAuditBatchSuccess = useCallback(() => {
    setSelectedRowKeys([]);
    actionRef.current?.reload();
  }, []);
  const {
    runAction: runFundTransferAuditBatch,
    auditModal: fundTransferAuditModal,
  } = useAuditBatchRunner<FundTransfer>({
    permGates: perms,
    handlers: {
      approve: (id) => fundTransferService.approveTransfer(id),
      revoke: (id) => fundTransferService.revokeTransfer(id),
      withdraw: (id) => fundTransferService.withdrawTransfer(id),
    },
    onBatchComplete: handleFundTransferAuditBatchSuccess,
    auditEntity: {
      entityType: FUND_TRANSFER_ENTITY,
      entityName: t(`${P}.entityName`),
    },
  });

  const fundTransferToolbarAuditMenus = useMemo(() => {
    const reviewOf = (row: FundTransfer) => String(row.review_status || '').trim();
    const allowed = (row: FundTransfer, key: string) => pickCapability(row, key)?.allowed === true;
    const run = (
      records: FundTransfer[],
      capabilityKey: string,
      permAllowed: boolean,
      onRun: (id: number) => Promise<unknown>,
      notAllowedMessage?: string,
    ) =>
      runCapabilityBatchLoop({
        keys: records.map((row) => Number(row.id)),
        records,
        capabilityKey,
        permAllowed,
        notAllowedMessage,
        onRun,
        onSuccess: () => {
          setSelectedRowKeys([]);
          actionRef.current?.reload();
        },
        message: messageApi,
        t,
      });
    const submitRows = selectedRecordsForBatch.filter((row) => allowed(row, 'submit'));
    const committedRows = selectedRecordsForBatch.filter(
      (row) => reviewOf(row) === 'SUBMITTED' && allowed(row, 'withdraw_submit'),
    );
    const pendingRows = selectedRecordsForBatch.filter((row) => {
      const review = reviewOf(row);
      return review !== 'SUBMITTED' && isPendingReviewStatus(review) && allowed(row, 'withdraw_submit');
    });
    const reviewRows = selectedRecordsForBatch.filter((row) => allowed(row, 'submit_review'));
    const approveRows = selectedRecordsForBatch.filter(
      (row) =>
        reviewOf(row) !== 'SUBMITTED' &&
        isPendingReviewStatus(reviewOf(row)) &&
        allowed(row, 'approve'),
    );
    const revokeRows = selectedRecordsForBatch.filter((row) => allowed(row, 'revoke_approval'));
    const canSubmit = perms.canAction?.('submit') ?? false;
    const canApprove = perms.canAction?.('approve') ?? false;
    const canRevoke = perms.canAction?.('revoke') ?? false;
    const hasSelection = selectedRecordsForBatch.length > 0;
    const submitDisabled = hasSelection && !(canSubmit && submitRows.length > 0);
    const submitItems: UniBatchMenuItem[] = withDocumentSubmitCombinedItem(
      [
        {
          key: 'submit',
          label: t('common.submit'),
          disabled: submitDisabled,
          onClick: () =>
            run(submitRows, 'submit', canSubmit, (id) => fundTransferService.commitTransfer(id)),
        },
        {
          key: 'withdraw-submit',
          label: t(`${P}.toolbar.withdrawSubmit`),
          disabled: hasSelection && committedRows.length === 0,
          onClick: () =>
            run(committedRows, 'withdraw_submit', canSubmit, (id) =>
              fundTransferService.withdrawTransfer(id),
            ),
        },
        {
          key: 'submit-review',
          label: t(`${P}.toolbar.submitReview`),
          disabled: hasSelection && !(canSubmit && reviewRows.length > 0),
          onClick: () =>
            run(
              reviewRows,
              'submit_review',
              canSubmit,
              (id) => fundTransferService.submitTransferForReview(id),
              t(`${P}.toolbar.submitReviewNotAllowed`),
            ),
        },
      ],
      {
        t,
        message: messageApi,
        disabled: submitDisabled,
        commitRecords: submitRows,
        permAllowed: canSubmit,
        commit: (id) => fundTransferService.commitTransfer(id),
        submitReview: (id) => fundTransferService.submitTransferForReview(id),
        onSuccess: () => {
          setSelectedRowKeys([]);
          actionRef.current?.reload();
        },
      },
    );
    const auditItems: UniBatchMenuItem[] = [
      {
        key: 'approve',
        label: t('components.uniAction.audit'),
        disabled: hasSelection && !(canApprove && approveRows.length > 0),
        onClick: () =>
          void runFundTransferAuditBatch(
            'approve',
            approveRows.map((row) => Number(row.id)),
            approveRows,
            fundTransferAuditEnabled,
          ),
      },
      {
        key: 'withdraw-review',
        label: t(`${P}.toolbar.withdrawReview`),
        disabled: hasSelection && pendingRows.length === 0,
        onClick: () =>
          run(pendingRows, 'withdraw_submit', canSubmit, (id) =>
            fundTransferService.withdrawTransfer(id),
          ),
      },
      {
        key: 'revoke',
        label: t(`${P}.toolbar.revoke`),
        disabled: hasSelection && !(canRevoke && revokeRows.length > 0),
        onClick: () =>
          run(revokeRows, 'revoke_approval', canRevoke, (id) =>
            fundTransferService.revokeTransfer(id),
          ),
      },
    ];
    return { submitItems, auditItems };
  }, [
    messageApi,
    perms,
    selectedRecordsForBatch,
    t,
    runFundTransferAuditBatch,
    fundTransferAuditEnabled,
  ]);

  useEffect(() => {
    void bankAccountService.list({ limit: 500, is_active: true }).then((res) => {
      setBankAccounts(res.data || []);
    });
  }, []);

  const accountOptions = useMemo(
    () =>
      bankAccounts.map((a) => ({
        label: formatBankAccountOptionLabel(a),
        value: a.id,
      })),
    [bankAccounts],
  );

  const transferTypeOptions = useMemo(
    () =>
      (['internal', 'external_out', 'external_in'] as FundTransferType[]).map((value) => ({
        value,
        label: transferTypeLabel(value, t),
      })),
    [t],
  );

  const openCreate = useCallback(() => {
    setEditing(null);
    setCreateSeed(undefined);
    setModalOpen(true);
  }, []);

  const openEdit = useCallback((row: FundTransfer) => {
    setEditing(row);
    setCreateSeed(undefined);
    setModalOpen(true);
  }, []);

  const openCopySelected = useCallback(() => {
    const row = selectedRecordsForBatch.length === 1 ? selectedRecordsForBatch[0] : null;
    if (!row) {
      messageApi.warning(t(`${P}.selectToCopy`));
      return;
    }
    setEditing(null);
    setCreateSeed({
      transfer_type: row.transfer_type || 'internal',
      amount: row.amount,
      from_bank_account_id: row.from_bank_account_id,
      to_bank_account_id: row.to_bank_account_id,
      external_account_name: row.external_account_name,
      external_bank_name: row.external_bank_name,
      external_account_number: row.external_account_number,
      notes: row.notes,
      transfer_date: dayjs(),
    });
    setModalOpen(true);
  }, [messageApi, selectedRecordsForBatch, t]);

  const loadDetail = useCallback(async (id: number) => {
    setDetailLoading(true);
    try {
      const row = await fundTransferService.get(id);
      setDetailRecord(row);
    } catch (e: unknown) {
      const err = e as { message?: string };
      messageApi.error(err?.message || t('common.loadFailed'));
      setDetailRecord(null);
    } finally {
      setDetailLoading(false);
    }
  }, [messageApi, t]);

  const openDetail = useCallback(
    (row: FundTransfer) => {
      setDetailOpen(true);
      void loadDetail(row.id);
    },
    [loadDetail],
  );

  const refreshDetail = useCallback(() => {
    if (detailRecord?.id) void loadDetail(detailRecord.id);
    actionRef.current?.reload();
  }, [detailRecord?.id, loadDetail]);

  const executeConfirm = async (row: FundTransfer) => {
    await fundTransferService.confirm(row.id);
    messageApi.success(t(`${P}.confirmSuccess`));
    refreshDetail();
  };

  const executeUnconfirm = async (row: FundTransfer) => {
    await fundTransferService.unconfirm(row.id);
    messageApi.success(t(`${P}.unconfirmSuccess`));
    refreshDetail();
  };

  const executeCancel = async (row: FundTransfer) => {
    await fundTransferService.cancel(row.id);
    messageApi.success(t(`${P}.voidSuccess`));
    refreshDetail();
  };

  const executeDelete = async (row: FundTransfer) => {
    await fundTransferService.delete(row.id);
    messageApi.success(t('common.deleteSuccess'));
    setDetailOpen(false);
    actionRef.current?.reload();
  };

  const handleBatchConfirm = async (keys: React.Key[]) => {
    try {
      for (const key of keys) {
        await fundTransferService.confirm(Number(key));
      }
      messageApi.success(t(`${P}.batchConfirmed`, { count: keys.length }));
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    } catch (error: unknown) {
      const err = error as { message?: string };
      messageApi.error(err?.message || t('app.kuaicaiwu.common.batchConfirmFailed'));
    }
  };

  const handleBatchVoid = async (keys: React.Key[]) => {
    try {
      for (const key of keys) {
        await fundTransferService.cancel(Number(key));
      }
      messageApi.success(t(`${P}.batchVoided`, { count: keys.length }));
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    } catch (error: unknown) {
      const err = error as { message?: string };
      messageApi.error(err?.message || t('app.kuaicaiwu.common.batchVoidFailed'));
    }
  };

  const handleBatchDelete = async (keys: React.Key[]) => {
    try {
      for (const key of keys) {
        await fundTransferService.delete(Number(key));
      }
      messageApi.success(t(`${P}.batchDeleted`, { count: keys.length }));
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    } catch (error: unknown) {
      const err = error as { message?: string };
      messageApi.error(err?.message || t('common.deleteFailed'));
    }
  };

  const batchMenuItems = useMemo(() => {
    const items = [];
    if (perms.canAction?.('audit')) {
      items.push({
        key: 'batch-confirm',
        label: t('app.kuaicaiwu.common.batchConfirm'),
        requireConfirm: true,
        confirmTitle: (count: number) => t(`${P}.batchConfirmTitle`, { count }),
        confirmDescription: t(`${P}.batchConfirmDesc`),
        onClick: handleBatchConfirm,
      });
    }
    if (perms.canAction?.('revoke')) {
      items.push({
        key: 'batch-void',
        label: t('app.kuaicaiwu.common.batchVoid'),
        requireConfirm: true,
        confirmTitle: (count: number) => t(`${P}.batchVoidTitle`, { count }),
        confirmDescription: t(`${P}.batchVoidDesc`),
        onClick: handleBatchVoid,
      });
    }
    return items;
  }, [perms, t]);

  const columns: ProColumns<FundTransfer>[] = useMemo(
    () =>
      alignProColumns(
        [
          {
            title: t(`${P}.col.code`),
            dataIndex: 'transfer_code',
            hideInTable: true,
            order: 10,
          },
          {
            title: t(`${P}.col.code`),
            key: 'fund_transfer_code_stacked',
            dataIndex: 'transfer_code',
            width: 240,
            minWidth: 240,
            uniTableKeepWidth: true,
            fixed: 'left',
            hideInSearch: true,
            sorter: true,
            render: (_, r) => (
              <UniTableStackedPrimaryCell
                primary={transferTypeLabel(String(r.transfer_type), t)}
                secondary={String(r.transfer_code ?? '')}
              />
            ),
          },
          {
            title: t(`${P}.col.transferType`),
            dataIndex: 'transfer_type',
            valueType: 'select',
            fieldProps: { options: transferTypeOptions },
            hideInTable: true,
          },
          {
            title: t(`${P}.col.date`),
            dataIndex: 'transfer_date',
            valueType: 'date',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            hideInSearch: true,
            sorter: true,
          },
          {
            title: t(`${P}.col.date`),
            dataIndex: 'transfer_date_range',
            valueType: 'dateRange',
            hideInTable: true,
            formItemProps: formDateRangeFormItemProps,
          },
          {
            title: t(`${P}.col.fromAccount`),
            dataIndex: 'from_account_name',
            width: 160,
            minWidth: 160,
            uniTableKeepWidth: true,
            hideInSearch: true,
            ellipsis: true,
            render: (_, r) => r.from_account_name || '—',
          },
          {
            title: t(`${P}.col.toAccount`),
            dataIndex: 'to_account_name',
            width: 160,
            minWidth: 160,
            uniTableKeepWidth: true,
            hideInSearch: true,
            ellipsis: true,
            render: (_, r) => r.to_account_name || r.external_account_name || '—',
          },
          {
            title: t(`${P}.col.amount`),
            dataIndex: 'amount',
            valueType: 'money',
            align: 'right',
            width: 130,
            minWidth: 130,
            uniTableKeepWidth: true,
            hideInSearch: true,
            sorter: true,
          },
          {
            title: t(`${P}.col.transferType`),
            dataIndex: 'transfer_type',
            ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
            hideInSearch: true,
            render: (_, r) => (
              <MarkerTag>{transferTypeLabel(String(r.transfer_type), t)}</MarkerTag>
            ),
          },
          {
            title: t('common.remark'),
            dataIndex: 'notes',
            minWidth: 120,
            uniTableRemainderFlex: true,
            hideInSearch: true,
            ellipsis: true,
          },
          ...financeDocCreatedUpdatedColumns<FundTransfer>(t),
          ...(fundTransferAuditColumn ? [fundTransferAuditColumn] : []),
          {
            title: t('common.status'),
            dataIndex: FINANCE_DOC_PINNED_STATUS_FIELD,
            key: 'lifecycle',
            fixed: 'right',
            hideInSearch: true,
            sorter: true,
            valueType: 'select',
            valueEnum: buildVoucherStatusEnum(t),
            render: (_, record) => {
              const lc = getFinanceVoucherLifecycle(record as Record<string, unknown>, t);
              return (
                <UniLifecycle
                  percent={lc.percent}
                  stageName={lc.stageName}
                  status={lc.status}
                  showLabel
                  size="small"
                  showCircleTooltip={false}
                />
              );
            },
          },
          {
            title: t('common.actions'),
            key: 'action',
            fixed: 'right',
            hideInSearch: true,
            render: (_, record) => {
              const acts: React.ReactNode[] = [
                <Button key="det" {...rowActionKind('read')} onClick={() => openDetail(record)} />,
                <UniWorkflowActions
                  {...rowActionKind('skip')}
                  key="wf"
                  record={record}
                  entityType={FUND_TRANSFER_ENTITY}
                  auditNodeKey={FUND_TRANSFER_ENTITY}
                  workflowAuditEnabled={fundTransferAuditEnabled}
                  resourcePrefix={FUND_TRANSFER_RESOURCE}
                  entityName={t(`${P}.entityName`)}
                  statusField="status"
                  reviewStatusField="review_status"
                  draftStatuses={['草稿', 'draft']}
                  pendingStatuses={['待审核']}
                  approvedStatuses={['已审核']}
                  rejectedStatuses={['已驳回', '驳回']}
                  theme="link"
                  size="small"
                  onSuccess={() => actionRef.current?.reload()}
                />,
              ];
              if (
                record.status === 'Draft' &&
                isReviewApproved(record) &&
                perms.canAction?.('audit')
              ) {
                acts.push(
                  <ActionConfirmPopconfirm
                    key="cf"
                    title={t(`${P}.confirmTitle`)}
                    description={t(`${P}.confirmContent`, { code: record.transfer_code })}
                    onConfirm={() => executeConfirm(record)}
                  >
                    <Button {...rowActionKind('audit')} onClick={(e) => e.stopPropagation()} />
                  </ActionConfirmPopconfirm>,
                );
              }
              if (record.status === 'Draft' && perms.canAction?.('revoke')) {
                acts.push(
                  <ActionConfirmPopconfirm
                    key="void"
                    title={t(`${P}.voidTitle`)}
                    description={t(`${P}.voidContent`, { code: record.transfer_code })}
                    onConfirm={() => executeCancel(record)}
                  >
                    <Button {...rowActionKind('obsolete')} onClick={(e) => e.stopPropagation()} />
                  </ActionConfirmPopconfirm>,
                );
              }
              if (record.status === 'Confirmed' && perms.canAction?.('revoke')) {
                acts.push(
                  <ActionConfirmPopconfirm
                    key="uc"
                    title={t(`${P}.unconfirmTitle`)}
                    description={t(`${P}.unconfirmContent`, { code: record.transfer_code })}
                    onConfirm={() => executeUnconfirm(record)}
                  >
                    <Button {...rowActionKind('revoke')} onClick={(e) => e.stopPropagation()} />
                  </ActionConfirmPopconfirm>,
                );
              }
              return acts;
            },
          },
        ],
        SALES_DOC_LIST_FIELD_RANK,
      ),
    [
      fundTransferAuditColumn,
      fundTransferAuditEnabled,
      openDetail,
      perms,
      t,
      transferTypeOptions,
    ],
  );

  const handleSubmit = async (values: Record<string, unknown>) => {
    const payload = {
      transfer_date: toApiDateString(values.transfer_date as dayjs.Dayjs | string),
      transfer_type: values.transfer_type as FundTransferType,
      amount: Number(values.amount),
      from_bank_account_id: values.from_bank_account_id
        ? Number(values.from_bank_account_id)
        : undefined,
      to_bank_account_id: values.to_bank_account_id
        ? Number(values.to_bank_account_id)
        : undefined,
      external_account_name: pickSearchString(values.external_account_name),
      external_bank_name: pickSearchString(values.external_bank_name),
      external_account_number: pickSearchString(values.external_account_number),
      notes: pickSearchString(values.notes),
      attachments: normalizeDocumentAttachments(values.attachments),
    };
    try {
      if (editing?.id) {
        await fundTransferService.update(editing.id, payload);
        messageApi.success(t('common.updateSuccess'));
      } else {
        await fundTransferService.create(payload);
        messageApi.success(t('common.createSuccess'));
      }
      setModalOpen(false);
      actionRef.current?.reload();
      return true;
    } catch (e: unknown) {
      const err = e as { message?: string };
      messageApi.error(err?.message || t('common.saveFailed'));
      return false;
    }
  };

  const modalInitialValues = useMemo(() => {
    if (editing) {
      return {
        ...editing,
        transfer_date: editing.transfer_date ? dayjs(editing.transfer_date) : dayjs(),
        attachments: editing.attachments,
      };
    }
    if (createSeed) {
      return {
        transfer_date: dayjs(),
        transfer_type: 'internal' as FundTransferType,
        ...createSeed,
      };
    }
    return {
      transfer_date: dayjs(),
      transfer_type: 'internal' as FundTransferType,
    };
  }, [createSeed, editing]);

  return (
    <>
    <ListPageTemplate>
      <UniTable<FundTransfer>
        headerTitle={t(`${P}.pageTitle`)}
        actionRef={actionRef}
        rowKey="id"
        columnPersistenceId="apps.kuaicaiwu.pages.finance-management.fund-transfers.list-v2"
        columns={columns}
        showAdvancedSearch
        pinnedTabsField={FINANCE_DOC_PINNED_STATUS_FIELD}
        enableRowSelection
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        onTableDataChange={(rows) => {
          tableRowsRef.current = rows;
          setTableRows(rows);
        }}
        createButtonText={t(`${P}.createTitle`)}
        showCreateButton={false}
        showDeleteButton={perms.canDelete}
        deleteButtonText={t('common.delete')}
        onDelete={handleBatchDelete}
        deleteConfirmTitle={t('app.kuaicaiwu.common.confirmBatchDelete')}
        deleteConfirmDescription={(count) => t(`${P}.batchDeleteConfirm`, { count })}
        toolBarRender={() =>
          perms.canCreate
            ? [
                <UniPullCreateToolbar
                  key="create-fund-transfer"
                  compactKey="create-fund-transfer"
                  createIcon={<PlusOutlined />}
                  createLabel={t(`${P}.createTitle`)}
                  onCreate={openCreate}
                  menuItems={[
                    {
                      key: 'copy-selected',
                      label: t(`${P}.copySelectedCreate`),
                      disabled: selectedRecordsForBatch.length !== 1,
                      onClick: openCopySelected,
                    },
                  ]}
                />,
              ]
            : []
        }
        toolBarActions={[
          <UniBatchMenuButton
            key="fund-transfer-submit"
            selectedRowKeys={selectedRowKeys}
            menuItems={fundTransferToolbarAuditMenus.submitItems}
            buttonText={t('common.submit')}
          />,
          <UniBatchMenuButton
            key="fund-transfer-audit"
            selectedRowKeys={selectedRowKeys}
            menuItems={fundTransferToolbarAuditMenus.auditItems}
            buttonText={t('components.uniAction.audit')}
          />,
        ]}
        toolBarActionsAfterDelete={
          batchMenuItems.length
            ? [
                <UniBatchMenuButton
                  key="fund-transfer-batch"
                  selectedRowKeys={selectedRowKeys}
                  buttonText={t('components.uniBatch.batchActions')}
                  menuItems={batchMenuItems}
                />,
              ]
            : undefined
        }
        request={async (params, sort, _filter, searchFormValues) => {
          const { current, pageSize } = params;
          const range = searchFormValues?.transfer_date_range as [string, string] | undefined;
          const sortField = sort && Object.keys(sort)[0];
          const sortOrder = sortField ? sort[sortField] : undefined;
          try {
            const res = await fundTransferService.list({
              skip: ((current || 1) - 1) * (pageSize || 20),
              limit: pageSize || 20,
              keyword: pickSearchString(searchFormValues?.keyword),
              transfer_code: pickSearchString(searchFormValues?.transfer_code),
              transfer_type: searchFormValues?.transfer_type as FundTransferType | undefined,
              status: pickSearchString(searchFormValues?.status),
              transfer_date_start: range?.[0],
              transfer_date_end: range?.[1],
              sort_field: sortField,
              sort_order: sortOrder === 'ascend' ? 'ascend' : sortOrder === 'descend' ? 'descend' : undefined,
            });
            return { data: res.items || [], success: true, total: res.total || 0 };
          } catch (error: unknown) {
            const err = error as { message?: string };
            messageApi.error(err?.message || t('app.kuaicaiwu.common.loadListFailed'));
            return { data: [], success: false, total: 0 };
          }
        }}
      />

      <FormModalTemplate
        key={
          editing
            ? `edit-fund-transfer-${editing.id}`
            : createSeed
              ? 'create-fund-transfer-copy'
              : 'create-fund-transfer'
        }
        title={editing ? t(`${P}.editTitle`) : t(`${P}.createTitle`)}
        open={modalOpen}
        onOpenChange={(open) => {
          setModalOpen(open);
          if (!open) setCreateSeed(undefined);
        }}
        width={MODAL_CONFIG.LARGE_WIDTH}
        grid={false}
        modalProps={{ destroyOnHidden: true }}
        onFinish={handleSubmit}
        initialValues={modalInitialValues}
      >
        <Row gutter={16}>
          <Col span={12}>
            <ProFormDatePicker
              name="transfer_date"
              label={t(`${P}.field.date`)}
              rules={[{ required: true }]}
              fieldProps={{ style: { width: '100%' } }}
            />
          </Col>
          <Col span={12}>
            <ProFormSelect
              name="transfer_type"
              label={t(`${P}.field.transferType`)}
              rules={[{ required: true }]}
              options={transferTypeOptions}
            />
          </Col>
          <Col span={12}>
            <ProFormDigit
              name="amount"
              label={t(`${P}.field.amount`)}
              min={0.01}
              rules={[{ required: true }]}
              fieldProps={{ precision: 2, style: { width: '100%' } }}
            />
          </Col>
          <ProFormDependency name={['transfer_type']}>
            {({ transfer_type }) => {
              const type = String(transfer_type || 'internal');
              const showFrom = type === 'internal' || type === 'external_out';
              const showTo = type === 'internal' || type === 'external_in';
              const showExternal = type === 'external_out' || type === 'external_in';
              return (
                <>
                  {showFrom ? (
                    <Col span={12}>
                      <ProFormSelect
                        name="from_bank_account_id"
                        label={t(`${P}.field.fromAccount`)}
                        rules={[{ required: true }]}
                        options={accountOptions}
                        showSearch
                      />
                    </Col>
                  ) : null}
                  {showTo ? (
                    <Col span={12}>
                      <ProFormSelect
                        name="to_bank_account_id"
                        label={t(`${P}.field.toAccount`)}
                        rules={[{ required: true }]}
                        options={accountOptions}
                        showSearch
                      />
                    </Col>
                  ) : null}
                  {showExternal ? (
                    <>
                      <Col span={12}>
                        <ProFormText
                          name="external_account_name"
                          label={t(`${P}.field.externalAccountName`)}
                          rules={[{ required: true }]}
                        />
                      </Col>
                      <Col span={12}>
                        <ProFormText
                          name="external_bank_name"
                          label={t(`${P}.field.externalBankName`)}
                          rules={[{ required: true }]}
                        />
                      </Col>
                      <Col span={12}>
                        <ProFormText
                          name="external_account_number"
                          label={t(`${P}.field.externalAccountNumber`)}
                          rules={[{ required: true }]}
                        />
                      </Col>
                    </>
                  ) : null}
                </>
              );
            }}
          </ProFormDependency>
          <Col span={24}>
            <DocumentAttachmentsField name="attachments" />
          </Col>
          <Col span={24}>
            <ProFormTextArea name="notes" label={t(`${P}.field.notes`)} fieldProps={{ rows: 2 }} />
          </Col>
        </Row>
      </FormModalTemplate>

      <DetailDrawerTemplate
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        width={DRAWER_CONFIG.STANDARD_WIDTH}
        title={detailRecord?.transfer_code || t(`${P}.detailTitle`)}
        loading={detailLoading}
        extra={
          detailRecord ? (
            <DetailDrawerActions
              actions={[
                {
                  key: 'workflow',
                  visible: true,
                  render: (
                    <UniWorkflowActions
                      record={detailRecord}
                      entityType={FUND_TRANSFER_ENTITY}
                      auditNodeKey={FUND_TRANSFER_ENTITY}
                      workflowAuditEnabled={fundTransferAuditEnabled}
                      resourcePrefix={FUND_TRANSFER_RESOURCE}
                      entityName={t(`${P}.entityName`)}
                      statusField="status"
                      reviewStatusField="review_status"
                      draftStatuses={['草稿', 'draft']}
                      pendingStatuses={['待审核']}
                      approvedStatuses={['已审核']}
                      rejectedStatuses={['已驳回', '驳回']}
                      theme="default"
                      size="middle"
                      onSuccess={() => void loadDetail(detailRecord.id)}
                    />
                  ),
                },
                {
                  key: 'confirm',
                  visible:
                    detailRecord.status === 'Draft' &&
                    isReviewApproved(detailRecord) &&
                    Boolean(perms.canAction?.('audit')),
                  render: (
                    <ActionConfirmPopconfirm
                      title={t(`${P}.confirmTitle`)}
                      description={t(`${P}.confirmContent`, { code: detailRecord.transfer_code })}
                      onConfirm={() => executeConfirm(detailRecord)}
                    >
                      <Button {...rowActionKind('audit')} onClick={(e) => e.stopPropagation()}>
                        {t('common.confirm')}
                      </Button>
                    </ActionConfirmPopconfirm>
                  ),
                },
                {
                  key: 'edit',
                  visible:
                    detailRecord.status === 'Draft' &&
                    !isReviewApproved(detailRecord) &&
                    String(detailRecord.review_status || '').trim() !== 'SUBMITTED' &&
                    !isPendingReviewStatus(String(detailRecord.review_status || '')) &&
                    perms.canUpdate,
                  render: (
                    <Button {...rowActionKind('update')} onClick={() => openEdit(detailRecord)}>
                      {t('common.edit')}
                    </Button>
                  ),
                },
                {
                  key: 'unconfirm',
                  visible:
                    detailRecord.status === 'Confirmed' && Boolean(perms.canAction?.('revoke')),
                  render: (
                    <Button {...rowActionKind('revoke')} onClick={() => void executeUnconfirm(detailRecord)}>
                      {t(`${P}.unconfirm`)}
                    </Button>
                  ),
                },
                {
                  key: 'void',
                  visible: detailRecord.status === 'Draft' && Boolean(perms.canAction?.('revoke')),
                  render: (
                    <ActionConfirmPopconfirm
                      title={t(`${P}.voidTitle`)}
                      description={t(`${P}.voidContent`, { code: detailRecord.transfer_code })}
                      onConfirm={() => executeCancel(detailRecord)}
                    >
                      <Button {...rowActionKind('revoke')} onClick={(e) => e.stopPropagation()}>
                        {t('app.kuaicaiwu.common.void')}
                      </Button>
                    </ActionConfirmPopconfirm>
                  ),
                },
                {
                  key: 'delete',
                  visible:
                    perms.canDelete &&
                    (detailRecord.status === 'Draft' || detailRecord.status === 'Cancelled'),
                  render: (
                    <ActionConfirmPopconfirm
                      title={t(`${P}.deleteTitle`)}
                      description={t(`${P}.deleteContent`, { code: detailRecord.transfer_code })}
                      okType="danger"
                      onConfirm={() => executeDelete(detailRecord)}
                    >
                      <Button danger {...rowActionKind('delete')} onClick={(e) => e.stopPropagation()}>
                        {t('common.delete')}
                      </Button>
                    </ActionConfirmPopconfirm>
                  ),
                },
              ]}
            />
          ) : null
        }
      >
        {detailRecord ? (
          <Descriptions column={2} size="small">
            <Descriptions.Item label={t(`${P}.col.date`)}>
              {detailRecord.transfer_date
                ? formatDateTime(detailRecord.transfer_date, 'YYYY-MM-DD')
                : '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t('common.status')}>
              {renderDocumentStatusTag(detailRecord.status, detailRecord.status)}
            </Descriptions.Item>
            <Descriptions.Item label={t(`${P}.col.transferType`)}>
              {transferTypeLabel(detailRecord.transfer_type, t)}
            </Descriptions.Item>
            <Descriptions.Item label={t(`${P}.col.amount`)}>
              {formatCurrencyAmount(detailRecord.amount)} {detailRecord.currency}
            </Descriptions.Item>
            <Descriptions.Item label={t(`${P}.col.fromAccount`)}>
              {detailRecord.from_account_name || '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t(`${P}.col.toAccount`)}>
              {detailRecord.to_account_name || '—'}
            </Descriptions.Item>
            {detailRecord.external_account_name ? (
              <>
                <Descriptions.Item label={t(`${P}.field.externalAccountName`)}>
                  {detailRecord.external_account_name}
                </Descriptions.Item>
                <Descriptions.Item label={t(`${P}.field.externalBankName`)}>
                  {detailRecord.external_bank_name || '—'}
                </Descriptions.Item>
                <Descriptions.Item label={t(`${P}.field.externalAccountNumber`)} span={2}>
                  {detailRecord.external_account_number || '—'}
                </Descriptions.Item>
              </>
            ) : null}
            <Descriptions.Item label={t(`${P}.field.notes`)} span={2}>
              {detailRecord.notes || '—'}
            </Descriptions.Item>
          </Descriptions>
        ) : null}
      </DetailDrawerTemplate>
    </ListPageTemplate>
    {fundTransferAuditModal}
    </>
  );
};

export default FundTransfersPage;
