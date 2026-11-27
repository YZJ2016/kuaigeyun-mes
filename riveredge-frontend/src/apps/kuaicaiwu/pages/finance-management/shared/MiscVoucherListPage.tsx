import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns, ProFormInstance } from '@ant-design/pro-components';
import {
  ProForm,
  ProFormDatePicker,
  ProFormDependency,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { PlusOutlined, PrinterOutlined } from '@ant-design/icons';
import { App, Button, Col, Descriptions, Form, Input, InputNumber, Row, Select, Space, Table, theme } from 'antd';
import type { TableColumnsType } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useLinkedDocumentDetail } from '../../../../../components/linked-document-detail';
import { useOptionalFinanceVoucherDetail } from '../../../components/FinanceVoucherDetailProvider';
import type { FormListFieldData } from 'antd/es/form/FormList';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import { rowActionKind, rowActionLabelKeep } from '../../../../../components/uni-action';
import {
  FormModalTemplate,
  ListPageTemplate,
  MODAL_CONFIG,
} from '../../../../../components/layout-templates';
import { MiscVoucherDetailDrawer } from './MiscVoucherDetailDrawer';
import { MODAL_NESTED_ABOVE_PARENT_OFFSET } from '../../../../../components/layout-templates/constants';
import { UniDropdown, QuickCreateModal } from '../../../../../components/uni-dropdown';
import { UniTable } from '../../../../../components/uni-table';
import { UniTableDetail } from '../../../../../components/uni-table-detail';
import { UniTableStackedPrimaryCell } from '../../../../../components/uni-table/stackedPrimaryColumn';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import {
  UniAuditBatchMenuButton,
  UniBatchMenuButton,
  UniCapabilityBatchButton,
  pickCapability,
  runCapabilityBatchLoop,
  useAuditBatchRunner,
  withDocumentSubmitCombinedItem,
  type UniBatchMenuItem,
} from '../../../../../components/uni-batch';
import { useKuaizhizaoPrintModal } from '../../../../kuaizhizao/hooks/useKuaizhizaoPrintModal';
import { UniWorkflowActions } from '../../../../../components/uni-workflow-actions';
import { isPendingReviewStatus } from '../../../../kuaizhizao/constants/documentStatus';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useAuditRequired } from '../../../../../hooks/useAuditRequired';
import { formatCurrencyAmount } from '../../../../../utils/format';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { coerceFormDate, toApiDateString } from '../../../../../utils/formDate';
import { normalizeFormListItems } from '../../../../../utils/formListItems';
import { formDateRangeFormItemProps } from '../../../../../utils/formDate';
import { pickSearchString } from '../../../../../utils/tableQueryKey';
import {
  assertBankAccountForPaymentMethod,
  BANK_TRANSFER_PAYMENT_METHOD,
  buildMiscVoucherStatusEnum,
  formatBankAccountOptionLabel,
  formatPaymentMethod,
  getPaymentMethodOptions,
  isEmployeeAdvancePaymentMethod,
} from '../../../utils/financeSharedOptions';
import DocumentAttachmentsField from '../../../../kuaizhizao/components/DocumentAttachmentsField';
import {
  mapAttachmentsToUploadList,
  normalizeDocumentAttachments,
  openDocumentAttachment,
  type DocumentAttachmentFile,
} from '../../../../kuaizhizao/utils/documentAttachments';
import { resolveAdvancePayeeName } from './PaymentAdvancePayeeField';
import { formatPayeeAccountFields } from '../../../utils/partnerPayeeAccounts';
import {
  UniPullQueryModal,
  useUniPullQuery,
  toUniPullQueryHttpParams,
  renderPullQueryDocStatus,
  renderPullQueryEmptyValue,
  renderPullQueryOptionalText,
} from '../../../../../components/uni-pull-query';
import {
  DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
  DOCUMENT_LINE_MATERIALS_KEY,
  renderDocumentLineMaterialsPreview,
  type DocumentLineMaterialPreviewItem,
} from '../../../../../components/document-line-materials-preview';
import {
  otherExpenseService,
  type OtherExpenseApplicationPullCandidate,
  type OtherExpensePurchaseReceiptLinkCandidate,
  type RelatedPurchaseReceiptRef,
} from '../../../services/finance/other-expense';
import { otherExpenseApplicationService } from '../../../services/finance/other-expense-application';
import { UniPullCreateToolbar, type UniPullMenuItem } from '../../../../../components/uni-pull';
import {
  buildUniPushMenuItem,
  buildUniPushMenuItems,
  buildUniPushToolbarDisabledReason,
  UniPushToolbarButton,
} from '../../../../../components/uni-push';
import {
  OTHER_EXPENSE_APPLICATION_UI_ENTRIES_ENABLED,
  buildKuaicaiwuPullCreateMenuItems,
  getKuaicaiwuDocumentAction,
} from '../../../constants/documentActionRegistry';
import { renderDocumentStatusTag } from '../../../../../utils/documentLifecycleStatusTag';
import { bankAccountService, type BankAccount } from '../../../services/finance/bank-account';
import {
  financeMiscCategoryService,
  type MiscCategory,
  type MiscCategoryKind,
} from '../../../services/finance/finance-misc-category';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { createListAuditPhaseColumn } from '../../../../kuaizhizao/pages/sales-management/shared/listAuditPhaseColumn';
import { buildDocumentAuditColumns } from '../../../../kuaizhizao/pages/shared/documentAuditColumns';
import {
  FINANCE_DOC_PINNED_STATUS_FIELD,
  FINANCE_INVOICE_PINNED_REVIEW_FIELD,
  financeDocCodePartnerSearchColumns,
  resolveMiscVoucherListKeywordParams,
} from '../../../utils/financeListCore';
import {
  loadCustomerFormReferenceList,
  loadDepartmentFormReferenceOptions,
  loadSupplierFormReferenceList,
  loadUserFormReferenceOptions,
  type DocumentFormSelectOption,
} from '../../../../../utils/documentFormReferenceLoad';
import { ReferenceDisplayAccessError } from '../../../../../utils/referenceDisplay';
import { useQuery } from '@tanstack/react-query';
import { getBusinessConfig } from '../../../../../services/businessConfig';
import {
  buildOtherExpensePayableLedgerRecognitionOptions,
  buildPayableLedgerRecognitionOptions,
  buildRevenueLedgerRecognitionOptions,
  orgFinancePayableDefault,
  orgFinanceRevenueDefault,
  otherExpenseSupplierPayableRecognitionForForm,
  payableLedgerRecognitionLabel,
} from '../../../../../utils/documentLedgerRecognition';
import { MiscVoucherCounterpartyPayeeSection } from './MiscVoucherCounterpartyPayeeSection';

type VoucherKind = 'income' | 'expense';
type AuditEntityType = 'other_income' | 'other_expense' | 'other_expense_application';
type DocumentVariant = 'default' | 'expense_application';

type VoucherRow = {
  id: number;
  income_code?: string;
  expense_code?: string;
  application_code?: string;
  pushed_amount?: number;
  remaining_amount?: number;
  business_date?: string;
  total_amount?: number;
  status?: string;
  review_status?: string;
  counterparty_kind?: string;
  counterparty_id?: number | null;
  counterparty_name?: string;
  payment_method?: string;
  notes?: string;
  capabilities?: Record<string, { allowed: boolean; reason?: string | null } | undefined>;
  audit?: { phase?: string; allowed_actions?: string[]; [key: string]: unknown };
  receivable_id?: number | null;
  receivable_code?: string | null;
  receipt_id?: number | null;
  receipt_code?: string | null;
  payable_id?: number | null;
  payable_code?: string | null;
  payment_id?: number | null;
  payment_code?: string | null;
  lines?: LineFormRow[];
};

type LineFormRow = {
  category_code?: string;
  category_name?: string;
  amount?: number;
  description?: string;
  payee_id?: number;
  payee_name?: string;
};

function mapOtherExpenseLinePreviewItems(
  lines: LineFormRow[] | undefined,
): DocumentLineMaterialPreviewItem[] {
  if (!lines?.length) return [];
  const out: DocumentLineMaterialPreviewItem[] = [];
  for (const line of lines) {
    const category = String(line.category_name ?? line.category_code ?? '').trim();
    const description = String(line.description ?? '').trim();
    const materialName = description || category;
    if (!materialName) continue;
    out.push({
      material_name: materialName,
      material_code: category && description ? category : undefined,
    });
  }
  return out;
}

type MiscVoucherListPageProps = {
  kind: VoucherKind;
  documentVariant?: DocumentVariant;
  auditEntityType: AuditEntityType;
  resource: string;
  hostResource: string;
  menuTitleKey: string;
  i18nPrefix: string;
  columnPersistenceId: string;
  /** 与 i18nPrefix 分设时用于新建/编辑标题与工具栏新建文案 */
  createButtonI18nKey?: string;
  createTitleI18nKey?: string;
  editTitleI18nKey?: string;
  service: {
    list: (params?: Record<string, unknown>) => Promise<{ items: VoucherRow[]; total: number }>;
    get: (id: number) => Promise<VoucherRow & { lines?: LineFormRow[]; notes?: string; bank_account_id?: number; counterparty_kind?: string }>;
    create: (data: Record<string, unknown>) => Promise<unknown>;
    update: (id: number, data: Record<string, unknown>) => Promise<unknown>;
    delete: (id: number) => Promise<unknown>;
    submit: (id: number) => Promise<unknown>;
    commit?: (id: number) => Promise<unknown>;
    submitForReview?: (id: number) => Promise<unknown>;
    withdraw?: (id: number) => Promise<unknown>;
    revoke?: (id: number) => Promise<unknown>;
    approve: (id: number) => Promise<unknown>;
    reject: (id: number) => Promise<unknown>;
    confirm: (id: number) => Promise<unknown>;
    unconfirm: (id: number) => Promise<unknown>;
    cancel: (id: number) => Promise<unknown>;
  };
};

function incomeReviewRaw(row: VoucherRow): string {
  return String(row.review_status || '').trim();
}

function capAllowed(row: VoucherRow, action: string) {
  return row.capabilities?.[action]?.allowed === true;
}

function resolveDocCode(
  row: VoucherRow,
  codeField: 'income_code' | 'expense_code' | 'application_code',
) {
  return String(row[codeField] ?? '').trim();
}

const COUNTERPARTY_KINDS = ['none', 'customer', 'supplier', 'employee', 'other'] as const;

/** 注册不展示的 Form 字段（如关联入库快照数组） */
function FormValueSink(_props: { value?: unknown; onChange?: (v: unknown) => void }) {
  return null;
}

type MiscCategoryQuickSelectProps = {
  value?: string;
  onChange?: (value: string) => void;
  catKind: MiscCategoryKind;
  options: { label: string; value: string }[];
  onCategoriesReload: () => Promise<void>;
  canQuickCreate: boolean;
  i18nPrefix: string;
};

const MiscCategoryQuickSelect: React.FC<MiscCategoryQuickSelectProps> = ({
  value,
  onChange,
  catKind,
  options,
  onCategoriesReload,
  canQuickCreate,
  i18nPrefix,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const { token } = theme.useToken();
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createForm] = Form.useForm<{ name: string }>();

  const handleCreate = async () => {
    const values = await createForm.validateFields();
    const name = String(values.name ?? '').trim();
    if (!name) return;
    setCreating(true);
    try {
      const created = await financeMiscCategoryService.createQuick(catKind, name);
      await onCategoriesReload();
      if (created?.code) {
        onChange?.(created.code);
      }
      setCreateOpen(false);
      createForm.resetFields();
      messageApi.success(t(`${i18nPrefix}.quickAddCategorySuccess`));
    } catch (e) {
      messageApi.error(getApiErrorMessage(e, t(`${i18nPrefix}.quickAddCategoryFailed`)));
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <UniDropdown
        value={value}
        onChange={(v) => onChange?.(v == null ? '' : String(v))}
        options={options}
        size="small"
        showSearch
        allowClear
        style={{ width: '100%' }}
        optionFilterProp="label"
        placeholder={t(`${i18nPrefix}.line.categoryPlaceholder`)}
        quickCreate={
          canQuickCreate
            ? {
                label: t(`${i18nPrefix}.quickAddCategory`),
                onClick: () => {
                  createForm.resetFields();
                  setCreateOpen(true);
                },
              }
            : undefined
        }
      />
      <QuickCreateModal
        open={createOpen}
        title={t(`${i18nPrefix}.quickAddCategoryTitle`)}
        zIndex={token.zIndexPopupBase + MODAL_NESTED_ABOVE_PARENT_OFFSET}
        confirmLoading={creating}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        onClose={() => {
          setCreateOpen(false);
          createForm.resetFields();
        }}
        onConfirm={handleCreate}
      >
        <Form form={createForm} layout="vertical" preserve={false}>
          <Form.Item
            name="name"
            rules={[
              { required: true, whitespace: true, message: t(`${i18nPrefix}.quickAddCategoryNameRequired`) },
            ]}
            style={{ marginBottom: 0 }}
          >
            <Input
              placeholder={t(`${i18nPrefix}.quickAddCategoryNamePlaceholder`)}
              maxLength={100}
              autoFocus
            />
          </Form.Item>
        </Form>
      </QuickCreateModal>
    </>
  );
};

export const MiscVoucherListPage: React.FC<MiscVoucherListPageProps> = ({
  kind,
  documentVariant = 'default',
  auditEntityType,
  resource,
  hostResource,
  menuTitleKey,
  i18nPrefix,
  columnPersistenceId,
  createButtonI18nKey,
  createTitleI18nKey,
  editTitleI18nKey,
  service,
}) => {
  const { t } = useTranslation();
  const { message: messageApi, modal } = App.useApp();
  const { token } = theme.useToken();
  const linkedDetail = useLinkedDocumentDetail();
  const navigate = useNavigate();
  const financeVoucherDetail = useOptionalFinanceVoucherDetail();
  const actionRef = useRef<ActionType>();
  const tableRowsRef = useRef<VoucherRow[]>([]);
  const perms = useResourcePermissions(resource);
  const miscCategoryPerms = useResourcePermissions('kuaicaiwu:finance-misc-category');
  const { openPrint, PrintModal } = useKuaizhizaoPrintModal();
  const auditEnabled = useAuditRequired(auditEntityType, true);
  const miscAuditColumn = useMemo(
    () => createListAuditPhaseColumn<VoucherRow>({ t, auditEnabled }),
    [t, auditEnabled],
  );
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<VoucherRow | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailRow, setDetailRow] = useState<(VoucherRow & { lines?: LineFormRow[]; notes?: string }) | null>(null);
  const [bankAccounts, setBankAccounts] = useState<BankAccount[]>([]);
  const [categories, setCategories] = useState<MiscCategory[]>([]);
  const [customerOptions, setCustomerOptions] = useState<DocumentFormSelectOption[]>([]);
  const [supplierOptions, setSupplierOptions] = useState<DocumentFormSelectOption[]>([]);
  const [employeeOptions, setEmployeeOptions] = useState<DocumentFormSelectOption[]>([]);
  const [departmentOptions, setDepartmentOptions] = useState<Array<{ label: string; value: number }>>([]);
  const formRef = useRef<ProFormInstance>();
  const pendingFormValuesRef = useRef<Record<string, unknown> | null>(null);
  const pullReceiptSupplierIdRef = useRef<number | null>(null);
  const purchaseReceiptLinkCloseRef = useRef<(() => void) | null>(null);
  const attachmentCategory =
    kind === 'income' ? 'other_income_attachments' : 'other_expense_attachments';
  const nestedPullZIndex = token.zIndexPopupBase + MODAL_NESTED_ABOVE_PARENT_OFFSET;

  const catKind: MiscCategoryKind = kind;
  const isExpenseApplication = documentVariant === 'expense_application';
  const isOtherExpenseDoc = kind === 'expense' && !isExpenseApplication;
  const isExpenseKind = kind === 'expense';
  const codeField: 'income_code' | 'expense_code' | 'application_code' = isExpenseApplication
    ? 'application_code'
    : kind === 'income'
      ? 'income_code'
      : 'expense_code';
  const pullFromApplicationAction =
    OTHER_EXPENSE_APPLICATION_UI_ENTRIES_ENABLED &&
    kind === 'expense' &&
    !isExpenseApplication
      ? getKuaicaiwuDocumentAction('other_expense.pull_from_application')
      : null;

  const selectedRowsForBatch = useMemo(
    () =>
      selectedRowKeys
        .map((key) => tableRowsRef.current.find((row) => String(row.id) === String(key)))
        .filter((row): row is VoucherRow => row != null),
    [selectedRowKeys],
  );

  const selectedVoucherForToolbar = useMemo(() => {
    if (selectedRowsForBatch.length !== 1) return null;
    return selectedRowsForBatch[0] ?? null;
  }, [selectedRowsForBatch]);

  const auditBatchHandlers = useMemo(
    () => ({
      submit: (id: number) => service.submit(id),
      approve: (id: number) => service.approve(id),
    }),
    [service],
  );

  const handleAuditBatchSuccess = useCallback(() => {
    setSelectedRowKeys([]);
    actionRef.current?.reload();
  }, []);

  const miscAuditEntityName = t(menuTitleKey);
  const {
    runAction: runMiscAuditBatch,
    auditModal: miscIncomeAuditModal,
  } = useAuditBatchRunner<VoucherRow>({
    permGates: perms,
    handlers: {
      approve: (id: number) => service.approve(id),
      revoke: (id: number) =>
        service.revoke ? service.revoke(id) : Promise.reject(new Error('revoke unavailable')),
      withdraw: (id: number) =>
        service.withdraw ? service.withdraw(id) : Promise.reject(new Error('withdraw unavailable')),
    },
    onBatchComplete: handleAuditBatchSuccess,
    auditEntity: {
      entityType: auditEntityType,
      entityName: miscAuditEntityName,
    },
  });

  const incomeSaveSubmitSplit = kind === 'income' || kind === 'expense' || isExpenseApplication;

  const incomeToolbarAuditMenus = useMemo(() => {
    if (!incomeSaveSubmitSplit) {
      return { submitItems: [] as UniBatchMenuItem[], auditItems: [] as UniBatchMenuItem[] };
    }
    const selected = tableRowsRef.current.filter((row) => selectedRowKeys.includes(row.id));
    const reviewOf = (row: VoucherRow) => incomeReviewRaw(row);
    const allowed = (row: VoucherRow, key: string) => pickCapability(row, key)?.allowed === true;
    const run = (
      records: VoucherRow[],
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
    const submitRows = selected.filter((row) => allowed(row, 'submit'));
    const canSubmit = Boolean(perms.canAction?.('submit'));
    const submitDisabled = !selected.some((row) => allowed(row, 'submit'));
    const onBatchSuccess = () => {
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    };
    const commitFn = (id: number) => (service.commit ? service.commit(id) : service.submit(id));
    const submitReviewFn = (id: number) =>
      service.submitForReview
        ? service.submitForReview(id)
        : Promise.reject(new Error('submitForReview unavailable'));
    const submitItems: UniBatchMenuItem[] = withDocumentSubmitCombinedItem(
      [
        {
          key: 'submit',
          label: t('common.submit'),
          disabled: submitDisabled,
          onClick: () => run(submitRows, 'submit', canSubmit, commitFn),
        },
        {
          key: 'withdraw-submit',
          label: t(`${i18nPrefix}.toolbar.withdrawSubmit`),
          disabled: !selected.some((row) => reviewOf(row) === 'SUBMITTED' && allowed(row, 'withdraw_submit')),
          onClick: () =>
            run(
              selected.filter((row) => reviewOf(row) === 'SUBMITTED' && allowed(row, 'withdraw_submit')),
              'withdraw_submit',
              canSubmit,
              (id) => (service.withdraw ? service.withdraw(id) : Promise.reject(new Error('withdraw unavailable'))),
            ),
        },
        {
          key: 'submit-review',
          label: t(`${i18nPrefix}.toolbar.submitReview`),
          disabled: !selected.some((row) => reviewOf(row) === 'SUBMITTED' && allowed(row, 'submit_review')),
          onClick: () =>
            run(
              selected.filter((row) => reviewOf(row) === 'SUBMITTED' && allowed(row, 'submit_review')),
              'submit_review',
              canSubmit,
              submitReviewFn,
              t(`${i18nPrefix}.toolbar.submitReviewNotAllowed`),
            ),
        },
      ],
      {
        t,
        message: messageApi,
        disabled: submitDisabled,
        commitRecords: submitRows,
        permAllowed: canSubmit,
        commit: commitFn,
        submitReview: submitReviewFn,
        onSuccess: onBatchSuccess,
      },
    );
    const approveRows = selected.filter(
      (row) => reviewOf(row) !== 'SUBMITTED' && isPendingReviewStatus(reviewOf(row)) && allowed(row, 'approve'),
    );
    const auditItems: UniBatchMenuItem[] = [
      {
        key: 'approve',
        label: t('components.uniAction.audit'),
        disabled: !selected.some(
          (row) => reviewOf(row) !== 'SUBMITTED' && isPendingReviewStatus(reviewOf(row)) && allowed(row, 'approve'),
        ),
        onClick: () =>
          void runMiscAuditBatch(
            'approve',
            approveRows.map((row) => Number(row.id)),
            approveRows,
            auditEnabled,
          ),
      },
      {
        key: 'withdraw-review',
        label: t(`${i18nPrefix}.toolbar.withdrawReview`),
        disabled: !selected.some(
          (row) =>
            reviewOf(row) !== 'SUBMITTED' && isPendingReviewStatus(reviewOf(row)) && allowed(row, 'withdraw_submit'),
        ),
        onClick: () =>
          run(
            selected.filter(
              (row) =>
                reviewOf(row) !== 'SUBMITTED'
                && isPendingReviewStatus(reviewOf(row))
                && allowed(row, 'withdraw_submit'),
            ),
            'withdraw_submit',
            Boolean(perms.canAction?.('submit')),
            (id) => (service.withdraw ? service.withdraw(id) : Promise.reject(new Error('withdraw unavailable'))),
          ),
      },
      {
        key: 'revoke',
        label: t(`${i18nPrefix}.toolbar.revoke`),
        disabled: !selected.some((row) => allowed(row, 'revoke_approval')),
        onClick: () =>
          run(
            selected.filter((row) => allowed(row, 'revoke_approval')),
            'revoke_approval',
            Boolean(perms.canAction?.('revoke')),
            (id) => (service.revoke ? service.revoke(id) : Promise.reject(new Error('revoke unavailable'))),
          ),
      },
    ];
    return { submitItems, auditItems };
  }, [
    incomeSaveSubmitSplit,
    selectedRowKeys,
    perms,
    service,
    messageApi,
    t,
    i18nPrefix,
    runMiscAuditBatch,
    auditEnabled,
  ]);

  const incomeReviewStatusEnum = useMemo(
    () => ({
      草稿: { text: t('app.kuaicaiwu.financeLifecycle.voucherDraft') },
      SUBMITTED: { text: t('common.submitted') },
      待审核: { text: t('app.kuaicaiwu.financeStatus.review.pending') },
      已审核: { text: t('app.kuaicaiwu.financeStatus.review.approved') },
      已驳回: { text: t('app.kuaicaiwu.financeStatus.review.rejected') },
    }),
    [t],
  );

  const miscWorkflowStatuses = useMemo(() => {
    if (incomeSaveSubmitSplit) {
      return {
        draftStatuses: ['草稿', 'Draft', 'SUBMITTED'],
        pendingStatuses: ['待审核'],
        approvedStatuses: ['已审核', '审核通过', '已通过', '通过'],
        rejectedStatuses: ['已驳回', '驳回'],
      };
    }
    return {
      draftStatuses: ['Draft', '草稿'],
      pendingStatuses: ['PendingReview', '待审核'],
      approvedStatuses: ['Approved', 'Confirmed', '已审核', '已确认'],
      rejectedStatuses: ['Rejected', '已驳回'],
    };
  }, [incomeSaveSubmitSplit]);

  const reloadAfterWorkflow = useCallback(
    (rowId?: number) => {
      actionRef.current?.reload();
      if (detailOpen && detailRow?.id != null && (rowId == null || detailRow.id === rowId)) {
        void service.get(detailRow.id).then(setDetailRow).catch(() => {});
      }
    },
    [detailOpen, detailRow?.id, service],
  );

  const paymentMethodOptions = useMemo(() => getPaymentMethodOptions(t), [t]);
  const miscStatusEnum = useMemo(() => buildMiscVoucherStatusEnum(t), [t]);
  const renderMiscStatusTag = useCallback(
    (status: string | null | undefined) => {
      const code = String(status ?? 'Draft');
      const label =
        miscStatusEnum[code as keyof typeof miscStatusEnum]?.text ?? code;
      return renderDocumentStatusTag(label, code);
    },
    [miscStatusEnum],
  );
  const categoryOptions = useMemo(
    () => categories.map((c) => ({ label: c.name, value: c.code })),
    [categories],
  );

  const renderMiscDocumentStatus = useCallback(
    (row: VoucherRow) => {
      if (!incomeSaveSubmitSplit || row.status === 'Confirmed' || row.status === 'Cancelled') {
        return renderMiscStatusTag(row.status);
      }
      const review = incomeReviewRaw(row) || '草稿';
      const label =
        incomeReviewStatusEnum[review as keyof typeof incomeReviewStatusEnum]?.text ?? review;
      return renderDocumentStatusTag(label, review);
    },
    [incomeSaveSubmitSplit, incomeReviewStatusEnum, renderMiscStatusTag],
  );

  const canQuickAddCategory = perms.canCreate || miscCategoryPerms.canCreate;

  const reloadCategories = useCallback(async () => {
    const cats = await financeMiscCategoryService.list(catKind, {
      is_active: true,
      ensure_defaults: true,
    });
    setCategories(Array.isArray(cats) ? cats : []);
  }, [catKind]);

  const { data: financeBusinessConfig } = useQuery({
    queryKey: ['businessConfigFinanceRecognition', kind],
    queryFn: getBusinessConfig,
    staleTime: 60_000,
  });
  const ledgerRecognitionOptions = useMemo(
    () =>
      kind === 'income'
        ? buildRevenueLedgerRecognitionOptions(t)
        : isOtherExpenseDoc
          ? buildOtherExpensePayableLedgerRecognitionOptions(t)
          : buildPayableLedgerRecognitionOptions(t),
    [isOtherExpenseDoc, kind, t],
  );
  const orgLedgerRecognitionDefault = useMemo(() => {
    const raw =
      kind === 'income'
        ? orgFinanceRevenueDefault(financeBusinessConfig)
        : orgFinancePayableDefault(financeBusinessConfig);
    if (isOtherExpenseDoc && kind === 'expense') {
      return otherExpenseSupplierPayableRecognitionForForm(raw);
    }
    return raw;
  }, [financeBusinessConfig, isOtherExpenseDoc, kind]);
  const ledgerRecognitionFieldName = kind === 'income' ? 'revenue_recognition' : 'payable_recognition';

  const onCounterpartyKindChange = useCallback(
    (nextKind: string) => {
      formRef.current?.setFieldsValue({
        counterparty_id: undefined,
        counterparty_name: undefined,
        counterparty_account_name: undefined,
        counterparty_bank_name: undefined,
        counterparty_bank_account: undefined,
        related_purchase_receipts: [],
        ...(isOtherExpenseDoc
          ? {
              payable_recognition:
                String(nextKind) === 'supplier' ? orgLedgerRecognitionDefault : 'manual',
            }
          : {}),
      });
      if (kind === 'expense') {
        pullReceiptSupplierIdRef.current = null;
        purchaseReceiptLinkCloseRef.current?.();
      }
    },
    [isOtherExpenseDoc, kind, orgLedgerRecognitionDefault],
  );

  const counterpartyKindOptions = useMemo(() => {
    const kinds = isExpenseKind
      ? COUNTERPARTY_KINDS.filter((value) => value !== 'none')
      : [...COUNTERPARTY_KINDS];
    return kinds.map((value) => ({
      value,
      label: t(`${i18nPrefix}.counterparty.${value}`),
    }));
  }, [i18nPrefix, isExpenseKind, t]);

  const loadMeta = useCallback(async () => {
    const settled = await Promise.allSettled([
      bankAccountService.list({ limit: 200, is_active: true }),
      financeMiscCategoryService.list(catKind, { is_active: true, ensure_defaults: true }),
      loadCustomerFormReferenceList(hostResource),
      loadSupplierFormReferenceList(hostResource),
      loadUserFormReferenceOptions(hostResource),
      loadDepartmentFormReferenceOptions(hostResource),
    ]);

    const warnReferenceDenied = (result: PromiseSettledResult<unknown>, label: string) => {
      if (result.status !== 'rejected') {
        return;
      }
      const reason = result.reason;
      if (reason instanceof ReferenceDisplayAccessError) {
        messageApi.warning(
          reason.message ||
            t('app.kuaicaiwu.otherExpense.referenceLoadDenied', { label, defaultValue: `${label}加载被拒绝，请授予查看或回显权限` }),
        );
      }
    };

    const [banksR, catsR, customersR, suppliersR, employeesR, deptR] = settled;
    warnReferenceDenied(customersR, t('app.kuaicaiwu.otherExpense.counterparty.customer', { defaultValue: '客户' }));
    warnReferenceDenied(suppliersR, t('app.kuaicaiwu.otherExpense.counterparty.supplier', { defaultValue: '供应商' }));
    warnReferenceDenied(employeesR, t('app.kuaicaiwu.otherExpense.counterparty.employee', { defaultValue: '职员' }));
    warnReferenceDenied(deptR, t(`${i18nPrefix}.field.department`));

    if (banksR.status === 'fulfilled') {
      setBankAccounts(banksR.value.data ?? []);
    }
    if (catsR.status === 'fulfilled') {
      setCategories(Array.isArray(catsR.value) ? catsR.value : []);
    }
    if (customersR.status === 'fulfilled') {
      setCustomerOptions(
        customersR.value.map((c) => ({
          value: c.id,
          label: String(c.name ?? c.code ?? c.id),
        })),
      );
    } else {
      setCustomerOptions([]);
    }
    if (suppliersR.status === 'fulfilled') {
      setSupplierOptions(
        suppliersR.value.map((s) => ({
          value: s.id,
          label: String(s.name ?? s.code ?? s.id),
        })),
      );
    } else {
      setSupplierOptions([]);
    }
    if (employeesR.status === 'fulfilled') {
      setEmployeeOptions(employeesR.value);
    } else {
      setEmployeeOptions([]);
    }
    if (deptR.status === 'fulfilled') {
      setDepartmentOptions(deptR.value);
    } else {
      setDepartmentOptions([]);
    }
  }, [catKind, hostResource, i18nPrefix, messageApi, t]);

  useEffect(() => {
    void loadMeta();
  }, [loadMeta]);

  const purchaseReceiptLinkQuery = useUniPullQuery<OtherExpensePurchaseReceiptLinkCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    loadData: async (params) => {
      const supplierId = pullReceiptSupplierIdRef.current;
      if (!supplierId || kind !== 'expense') {
        return { data: [], total: 0 };
      }
      const http = toUniPullQueryHttpParams(params);
      try {
        const res = await otherExpenseService.listPurchaseReceiptLinkCandidates({
          supplier_id: supplierId,
          skip: http.skip,
          limit: http.limit,
          ...(http.keyword ? { keyword: http.keyword } : {}),
        });
        return { data: res.data ?? [], total: res.total ?? 0 };
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t(`${i18nPrefix}.loadPurchaseReceiptFailed`)));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const selected = rows.filter((row) => keys.some((k) => String(k) === String(row.id)));
      if (!selected.length) {
        messageApi.warning(t(`${i18nPrefix}.selectPurchaseReceiptRequired`));
        return;
      }
      const refs: RelatedPurchaseReceiptRef[] = selected.map((row) => ({
        id: Number(row.id),
        code: String(row.receipt_code || row.code || row.id),
      }));
      formRef.current?.setFieldsValue({ related_purchase_receipts: refs });
      purchaseReceiptLinkCloseRef.current?.();
    },
  });
  purchaseReceiptLinkCloseRef.current = purchaseReceiptLinkQuery.closeModal;

  const pullFromApplicationCloseRef = useRef<(() => void) | null>(null);
  const pullFromApplicationQuery = useUniPullQuery<OtherExpenseApplicationPullCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    loadData: async (params) => {
      const http = toUniPullQueryHttpParams(params);
      try {
        const res = await otherExpenseService.listApplicationPullCandidates({
          skip: http.skip,
          limit: http.limit,
          ...(http.keyword ? { keyword: http.keyword } : {}),
        });
        return { data: res.data ?? [], total: res.total ?? 0 };
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t(`${i18nPrefix}.loadPullFailed`)));
        return { data: [], total: 0 };
      }
    },
    isRowDisabled: (record) => record.capabilities?.pull_other_expense?.allowed === false,
    onConfirm: async (keys, rows) => {
      const selectedRows = rows.filter((row) => keys.some((k) => String(k) === String(row.id)));
      const selected = selectedRows[0];
      if (!selected?.id) {
        messageApi.warning(
          t(`${i18nPrefix}.selectPullSource`, {
            label: pullFromApplicationAction?.sourceLabel ?? '',
          }),
        );
        return;
      }
      try {
        const preview = await otherExpenseService.previewFromApplication(Number(selected.id));
        if (preview.has_blocking_issues) {
          messageApi.warning(String(preview.blocking_reason || t(`${i18nPrefix}.pullBlocked`)));
          return;
        }
        const header = (preview.header ?? {}) as Record<string, unknown>;
        const items = (preview.items ?? []) as Array<Record<string, unknown>>;
        pendingFormValuesRef.current = {
          business_date: header.business_date ? dayjs(String(header.business_date)) : dayjs(),
          counterparty_kind: header.counterparty_kind ?? 'none',
          counterparty_id: header.counterparty_id,
          counterparty_name: header.counterparty_name,
          payment_method: header.payment_method,
          bank_account_id: header.bank_account_id,
          department_id: header.department_id,
          notes: header.notes,
          payable_recognition: otherExpenseSupplierPayableRecognitionForForm(
            header.payable_recognition as string | undefined,
          ),
          source_type: 'other_expense_application',
          source_id: preview.source_id,
          source_code: preview.source_code,
          lines: items.length
            ? items.map((item) => ({
                category_code: item.category_code,
                amount: Number(item.max_push_quantity ?? 0),
                description: item.description,
                payee_id: item.payee_id,
                payee_name: item.payee_name,
              }))
            : [{}],
        };
        pullFromApplicationCloseRef.current?.();
        if (selectedRows.length > 1) {
          messageApi.info(t('components.uniPullQuery.multiSelectedFirstOnly'));
        }
        setEditing(null);
        setModalOpen(true);
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t(`${i18nPrefix}.loadPullFailed`)));
      }
    },
  });
  pullFromApplicationCloseRef.current = pullFromApplicationQuery.closeModal;

  const handlePushOtherExpense = useCallback(
    async (row: VoucherRow) => {
      if (!isExpenseApplication) return;
      try {
        const res = await otherExpenseApplicationService.pushOtherExpense(row.id);
        messageApi.success(
          t(`${i18nPrefix}.pushSuccess`, { code: res.expense_code ?? res.expense_id }),
        );
        actionRef.current?.reload();
        if (detailRow?.id === row.id) {
          const full = await service.get(row.id);
          setDetailRow(full);
        }
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t(`${i18nPrefix}.pushFailed`)));
      }
    },
    [detailRow?.id, i18nPrefix, isExpenseApplication, messageApi, service, t],
  );

  const openPurchaseReceiptLink = useCallback(() => {
    if (kind !== 'expense') return;
    const supplierId = Number(formRef.current?.getFieldValue('counterparty_id') ?? 0);
    if (!Number.isFinite(supplierId) || supplierId <= 0) {
      messageApi.warning(t(`${i18nPrefix}.selectSupplierFirst`));
      return;
    }
    pullReceiptSupplierIdRef.current = supplierId;
    purchaseReceiptLinkQuery.openModal();
  }, [i18nPrefix, kind, messageApi, purchaseReceiptLinkQuery, t]);

  const purchaseReceiptLinkColumns: TableColumnsType<OtherExpensePurchaseReceiptLinkCandidate> = useMemo(
    () => [
      {
        title: t(`${i18nPrefix}.pull.col.receiptCode`),
        dataIndex: 'receipt_code',
        width: 148,
        ellipsis: true,
        render: (_, row) => row.receipt_code || row.code,
      },
      {
        title: t('app.kuaizhizao.common.colLineMaterials'),
        key: DOCUMENT_LINE_MATERIALS_KEY,
        dataIndex: 'items',
        ellipsis: false,
        render: (_, row) => {
          const items = row.items;
          if (!items?.length) {
            return renderPullQueryEmptyValue();
          }
          return renderDocumentLineMaterialsPreview(items, t);
        },
      },
      {
        title: t(`${i18nPrefix}.pull.col.purchaseOrderCode`),
        dataIndex: 'purchase_order_code',
        width: 136,
        ellipsis: true,
        render: (v) => renderPullQueryOptionalText(v),
      },
      {
        title: t(`${i18nPrefix}.pull.col.totalQuantity`),
        dataIndex: 'total_quantity',
        width: 96,
        align: 'right',
        render: (v) => {
          const n = Number(v);
          if (!Number.isFinite(n) || n === 0) {
            return renderPullQueryEmptyValue();
          }
          return n;
        },
      },
      {
        title: t(`${i18nPrefix}.pull.col.status`),
        dataIndex: 'source_status',
        width: 96,
        render: (v) => renderPullQueryDocStatus(t, v),
      },
      {
        title: t(`${i18nPrefix}.pull.col.date`),
        dataIndex: 'source_date',
        width: 112,
        ellipsis: true,
      },
      {
        title: t(`${i18nPrefix}.pull.col.amount`),
        dataIndex: 'amount',
        width: 108,
        align: 'right',
        render: (v) => formatCurrencyAmount(v),
      },
    ],
    [i18nPrefix, t],
  );

  const openCreate = useCallback(() => {
    setEditing(null);
    setModalOpen(true);
  }, []);

  const fillPendingFormFromVoucher = useCallback(
    (full: Awaited<ReturnType<typeof service.get>>, options?: { forCopy?: boolean }) => {
      const forCopy = options?.forCopy === true;
      const fullExt = full as typeof full & {
        department_id?: number | null;
        attachments?: unknown;
        revenue_recognition?: string;
        revenueRecognition?: string;
        payable_recognition?: string;
        payableRecognition?: string;
        source_type?: string;
        source_id?: number;
        source_code?: string;
      };
      const loadedCounterpartyKind = full.counterparty_kind ?? 'none';
      pendingFormValuesRef.current = {
        business_date: forCopy
          ? dayjs()
          : full.business_date
            ? dayjs(full.business_date)
            : dayjs(),
        counterparty_kind:
          isExpenseKind && loadedCounterpartyKind === 'none' ? 'other' : loadedCounterpartyKind,
        counterparty_id: full.counterparty_id,
        counterparty_name: full.counterparty_name,
        counterparty_account_name: (full as { counterparty_account_name?: string })
          .counterparty_account_name,
        counterparty_bank_name: (full as { counterparty_bank_name?: string }).counterparty_bank_name,
        counterparty_bank_account: (full as { counterparty_bank_account?: string })
          .counterparty_bank_account,
        payment_method: full.payment_method,
        bank_account_id: full.bank_account_id,
        department_id: fullExt.department_id ?? undefined,
        notes: full.notes,
        attachments: mapAttachmentsToUploadList(
          fullExt.attachments as Parameters<typeof mapAttachmentsToUploadList>[0],
        ),
        related_purchase_receipts: forCopy
          ? []
          : ((fullExt as { related_purchase_receipts?: RelatedPurchaseReceiptRef[] })
              .related_purchase_receipts ?? []),
        revenue_recognition: fullExt.revenue_recognition ?? fullExt.revenueRecognition,
        payable_recognition:
          isOtherExpenseDoc && loadedCounterpartyKind === 'supplier'
            ? otherExpenseSupplierPayableRecognitionForForm(
                fullExt.payable_recognition ?? fullExt.payableRecognition,
              )
            : isOtherExpenseDoc
              ? 'manual'
              : (fullExt.payable_recognition ?? fullExt.payableRecognition),
        lines: (full.lines ?? []).length
          ? (full.lines ?? []).map((l) => ({
              category_code: l.category_code,
              amount: Number(l.amount),
              description: l.description,
              payee_id: (l as LineFormRow).payee_id,
              payee_name: (l as LineFormRow).payee_name,
            }))
          : [{}],
        ...(forCopy || !(fullExt.source_type && fullExt.source_id)
          ? {}
          : {
              source_type: fullExt.source_type,
              source_id: fullExt.source_id,
              source_code: fullExt.source_code,
            }),
        ...(isOtherExpenseDoc
          ? {
              employee_advance_enabled: isEmployeeAdvancePaymentMethod(full.payment_method),
              advance_payee_id: (
                (full.lines ?? []).find((l) => (l as LineFormRow).payee_id != null) as
                  | LineFormRow
                  | undefined
              )?.payee_id,
            }
          : {}),
      };
    },
    [isExpenseKind, isOtherExpenseDoc],
  );

  const openEdit = useCallback(
    async (row: VoucherRow) => {
      if (!capAllowed(row, 'update')) {
        messageApi.warning(t('common.updateFailed'));
        return;
      }
      try {
        const full = await service.get(row.id);
        setEditing(row);
        fillPendingFormFromVoucher(full);
        setModalOpen(true);
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t(`${i18nPrefix}.loadFailed`)));
      }
    },
    [fillPendingFormFromVoucher, i18nPrefix, messageApi, service, t],
  );

  const canCopySelectedVoucher = isExpenseApplication || isOtherExpenseDoc;

  const openCopySelectedVoucher = useCallback(async () => {
    if (!canCopySelectedVoucher) {
      return;
    }
    const row = selectedRowsForBatch.length === 1 ? selectedRowsForBatch[0] : null;
    if (!row) {
      messageApi.warning(
        t(
          isExpenseApplication
            ? 'app.kuaicaiwu.otherExpenseApplication.selectToCopy'
            : `${i18nPrefix}.selectToCopy`,
        ),
      );
      return;
    }
    try {
      const full = await service.get(row.id);
      setEditing(null);
      fillPendingFormFromVoucher(full, { forCopy: true });
      setModalOpen(true);
    } catch (e) {
      messageApi.error(getApiErrorMessage(e, t(`${i18nPrefix}.loadFailed`)));
    }
  }, [
    canCopySelectedVoucher,
    fillPendingFormFromVoucher,
    i18nPrefix,
    isExpenseApplication,
    messageApi,
    selectedRowsForBatch,
    service,
    t,
  ]);

  const openDetail = useCallback(
    async (row: VoucherRow) => {
      setDetailOpen(true);
      setDetailLoading(true);
      setDetailError(null);
      try {
        const full = await service.get(row.id);
        setDetailRow({
          ...full,
          review_status: full.review_status ?? row.review_status,
          audit: full.audit ?? row.audit,
          capabilities: { ...(row.capabilities ?? {}), ...(full.capabilities ?? {}) },
        });
      } catch (e) {
        setDetailRow(null);
        const msg = getApiErrorMessage(e, t(`${i18nPrefix}.loadFailed`));
        setDetailError(msg);
        messageApi.error(msg);
      } finally {
        setDetailLoading(false);
      }
    },
    [i18nPrefix, messageApi, service, t],
  );

  const detailBankAccountLabel = useMemo(() => {
    const bankId = (detailRow as { bank_account_id?: number } | null)?.bank_account_id;
    if (!bankId) return '';
    const acc = bankAccounts.find((a) => a.id === bankId);
    return acc ? formatBankAccountOptionLabel(acc) : '';
  }, [bankAccounts, detailRow, t]);

  const handleSave = async (values: Record<string, unknown>) => {
    let paymentMethodForSave: string;
    if (isExpenseApplication) {
      paymentMethodForSave = BANK_TRANSFER_PAYMENT_METHOD;
    } else {
      paymentMethodForSave = String(values.payment_method ?? '');
    }
    if (kind === 'income') {
      assertBankAccountForPaymentMethod(
        paymentMethodForSave,
        values.bank_account_id as number | undefined,
        t,
      );
    }
    const employeeAdvance =
      isOtherExpenseDoc && isEmployeeAdvancePaymentMethod(paymentMethodForSave);
    const headerAdvancePayeeId = values.advance_payee_id as number | undefined;
    const headerAdvancePayeeName = employeeAdvance
      ? resolveAdvancePayeeName(headerAdvancePayeeId, employeeOptions)
      : undefined;
    if (employeeAdvance && (!headerAdvancePayeeId || !headerAdvancePayeeName)) {
      throw new Error(t('app.kuaicaiwu.payment.advancePayeeRequired'));
    }
    const lines = normalizeFormListItems<LineFormRow>(values.lines)
      .filter((l) => l.category_code && l.amount != null && Number(l.amount) > 0)
      .map((l) => ({
        category_code: l.category_code,
        amount: l.amount,
        description: l.description,
        ...(employeeAdvance
          ? {
              payee_id: headerAdvancePayeeId,
              payee_name: headerAdvancePayeeName,
            }
          : {}),
      }));
    if (!lines.length) {
      throw new Error(t(`${i18nPrefix}.linesRequired`));
    }
    const kindValue = String(values.counterparty_kind || 'none');
    const counterpartyIdRaw = values.counterparty_id as number | undefined;
    let counterpartyName: string | undefined;
    if (kindValue === 'customer' && counterpartyIdRaw != null) {
      counterpartyName = String(
        customerOptions.find((o) => o.value === counterpartyIdRaw)?.label ?? '',
      ).trim();
    } else if (kindValue === 'supplier' && counterpartyIdRaw != null) {
      counterpartyName = String(
        supplierOptions.find((o) => o.value === counterpartyIdRaw)?.label ?? '',
      ).trim();
    } else if (kindValue === 'employee' && counterpartyIdRaw != null) {
      counterpartyName = String(
        employeeOptions.find((o) => o.value === counterpartyIdRaw)?.label ?? '',
      ).trim();
    } else if (kindValue === 'other') {
      counterpartyName = String(values.counterparty_name ?? '').trim() || undefined;
    }
    if (
      (kindValue === 'customer' || kindValue === 'supplier' || kindValue === 'employee') &&
      (counterpartyIdRaw == null || !counterpartyName)
    ) {
      throw new Error(t(`${i18nPrefix}.counterpartyPickRequired`));
    }
    if (kindValue === 'other' && !counterpartyName) {
      throw new Error(t(`${i18nPrefix}.counterpartyNameRequired`));
    }
    const departmentIdRaw = values.department_id as number | undefined;
    const departmentName =
      departmentIdRaw != null
        ? String(departmentOptions.find((o) => o.value === departmentIdRaw)?.label ?? '').trim() ||
          undefined
        : undefined;
    const relatedReceiptsRaw = values.related_purchase_receipts;
    const related_purchase_receipts =
      kind === 'expense' && kindValue === 'supplier' && Array.isArray(relatedReceiptsRaw)
        ? (relatedReceiptsRaw as RelatedPurchaseReceiptRef[])
            .map((r) => ({
              id: Number(r.id),
              code: String(r.code || '').trim(),
            }))
            .filter((r) => Number.isFinite(r.id) && r.id > 0 && r.code)
        : kind === 'expense'
          ? []
          : undefined;
    const payload = {
      business_date: toApiDateString(coerceFormDate(values.business_date)),
      counterparty_kind: kindValue,
      counterparty_id:
        kindValue === 'customer' || kindValue === 'supplier' || kindValue === 'employee'
          ? counterpartyIdRaw
          : undefined,
      counterparty_name: kindValue === 'none' ? undefined : counterpartyName,
      counterparty_account_name:
        kind === 'expense' && (kindValue === 'supplier' || kindValue === 'employee')
          ? (values.counterparty_account_name as string | undefined)
          : undefined,
      counterparty_bank_name:
        kind === 'expense' && (kindValue === 'supplier' || kindValue === 'employee')
          ? (values.counterparty_bank_name as string | undefined)
          : undefined,
      counterparty_bank_account:
        kind === 'expense' && (kindValue === 'supplier' || kindValue === 'employee')
          ? (values.counterparty_bank_account as string | undefined)
          : undefined,
      payment_method: paymentMethodForSave,
      bank_account_id:
        isExpenseKind ? undefined : (values.bank_account_id as number | undefined),
      department_id: departmentIdRaw,
      department_name: departmentName,
      attachments: normalizeDocumentAttachments(
        values.attachments as DocumentAttachmentFile[] | null | undefined,
      ),
      notes: values.notes,
      lines,
      ...(kind === 'expense' ? { related_purchase_receipts } : {}),
      ...(kind === 'income'
        ? { revenue_recognition: values.revenue_recognition }
        : isExpenseApplication
          ? {}
          : {
              payable_recognition:
                kindValue === 'supplier'
                  ? values.payable_recognition
                  : 'manual',
            }),
      ...(values.source_type && values.source_id
        ? {
            source_type: values.source_type,
            source_id: values.source_id,
            source_code: values.source_code,
          }
        : {}),
    };
    if (editing) {
      await service.update(editing.id, payload);
      messageApi.success(t('common.updateSuccess'));
    } else {
      await service.create(payload);
      messageApi.success(t('common.createSuccess'));
    }
    setModalOpen(false);
    actionRef.current?.reload();
  };

  const runAction = useCallback(
    async (label: string, fn: () => Promise<unknown>) => {
      try {
        await fn();
        messageApi.success(label);
        actionRef.current?.reload();
        if (detailOpen && detailRow) {
          const full = await service.get(detailRow.id);
          setDetailRow(full);
        }
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, label));
      }
    },
    [detailOpen, detailRow, messageApi, service],
  );

  const confirmPushFinanceVoucher = useCallback(
    (row: VoucherRow) => {
      const pushAction = kind === 'income' ? 'push_receipt' : 'push_payment';
      const pushLabel =
        kind === 'income'
          ? t('app.kuaicaiwu.otherIncome.pushReceipt')
          : t('app.kuaicaiwu.otherExpense.pushPayment');
      if (!capAllowed(row, pushAction)) {
        messageApi.warning(t(`${i18nPrefix}.toolbar.pushNotAllowed`));
        return;
      }
      const code = resolveDocCode(row, codeField);
      modal.confirm({
        title: pushLabel,
        content: t(`${i18nPrefix}.confirmPostDesc`, { code }),
        onOk: () => runAction(pushLabel, () => service.confirm(row.id)),
      });
    },
    [codeField, i18nPrefix, kind, messageApi, modal, runAction, service, t],
  );

  const toolbarPushMenuItems = useMemo(() => {
    if (isExpenseApplication) {
      return buildUniPushMenuItems([
        buildUniPushMenuItem({
          key: 'push-other-expense',
          label: t('app.kuaicaiwu.otherExpenseApplication.pushOtherExpense'),
          targetDocumentType: 'other_expense',
          disabledReason:
            selectedVoucherForToolbar
            && (
              perms.canAction?.('push') !== true
              || selectedVoucherForToolbar.capabilities?.push_other_expense?.allowed !== true
            )
              ? t(`${i18nPrefix}.toolbar.pushNotAllowed`)
              : undefined,
          onClick: () => {
            const row = selectedVoucherForToolbar;
            if (!row?.id) return;
            void handlePushOtherExpense(row);
          },
        }),
      ]);
    }
    const pushAction = kind === 'income' ? 'push_receipt' : 'push_payment';
    const pushLabel =
      kind === 'income'
        ? t('app.kuaicaiwu.otherIncome.pushReceipt')
        : t('app.kuaicaiwu.otherExpense.pushPayment');
    const targetDocumentType = kind === 'income' ? 'receipt' : 'payment';
    return buildUniPushMenuItems([
      buildUniPushMenuItem({
        key: 'push-finance',
        label: pushLabel,
        targetDocumentType,
        disabledReason:
          selectedVoucherForToolbar
          && (
            perms.canAction?.('audit') !== true
            || selectedVoucherForToolbar.capabilities?.[pushAction]?.allowed !== true
          )
            ? t(`${i18nPrefix}.toolbar.pushNotAllowed`)
            : undefined,
        onClick: () => {
          const row = selectedVoucherForToolbar;
          if (!row?.id) return;
          confirmPushFinanceVoucher(row);
        },
      }),
    ]);
  }, [
    confirmPushFinanceVoucher,
    handlePushOtherExpense,
    i18nPrefix,
    isExpenseApplication,
    kind,
    perms,
    selectedVoucherForToolbar,
    t,
  ]);

  const toolbarPushDisabledReason = buildUniPushToolbarDisabledReason(t, {
    selectedCount: selectedRowKeys.length,
    hasSelectedRecord: Boolean(selectedVoucherForToolbar),
  });

  const toolbarPushSourceDocument = useMemo(() => {
    if (!selectedVoucherForToolbar?.id) return null;
    if (isExpenseApplication) {
      return { type: 'other_expense_application', id: Number(selectedVoucherForToolbar.id) };
    }
    return {
      type: kind === 'income' ? 'other_income' : 'other_expense',
      id: Number(selectedVoucherForToolbar.id),
    };
  }, [isExpenseApplication, kind, selectedVoucherForToolbar]);

  const toolbarPushTargets = useMemo<Record<string, string | string[]> | undefined>(() => {
    if (isExpenseApplication) {
      return { 'push-other-expense': 'other_expense' } as Record<string, string | string[]>;
    }
    return {
      'push-finance': kind === 'income' ? 'receipt' : 'payment',
    } as Record<string, string | string[]>;
  }, [isExpenseApplication, kind]);

  const handleBatchDelete = useCallback(
    async (keys: React.Key[]) => {
      if (!keys.length) return;
      const rows = keys
        .map((key) => tableRowsRef.current.find((row) => String(row.id) === String(key)))
        .filter((row): row is VoucherRow => row != null);
      const deletable = rows.filter((row) => capAllowed(row, 'delete'));
      if (deletable.length === 0) {
        messageApi.warning(t(`${i18nPrefix}.batchDeleteNoneDeletable`));
        return;
      }
      if (deletable.length < rows.length) {
        messageApi.warning(t(`${i18nPrefix}.batchDeletePartial`));
      }
      for (const row of deletable) {
        await service.delete(row.id);
      }
      messageApi.success(t(`${i18nPrefix}.batchDeleteSuccess`, { count: deletable.length }));
      setSelectedRowKeys([]);
      if (detailRow?.id != null && deletable.some((row) => row.id === detailRow.id)) {
        setDetailRow(null);
        setDetailOpen(false);
      }
      actionRef.current?.reload();
    },
    [detailRow?.id, i18nPrefix, messageApi, service, t],
  );

  const columns: ProColumns<VoucherRow>[] = useMemo(
    () =>
      alignProColumns(
        [
          ...financeDocCodePartnerSearchColumns({
            docCodeLabel: t(`${i18nPrefix}.col.code`),
            docCodeField: codeField,
            partnerLabel: t(`${i18nPrefix}.col.counterparty`),
            partnerIdField: 'counterparty_id',
            partnerNameField: 'counterparty_name',
          }),
          ...(isOtherExpenseDoc
            ? [
                {
                  title: t(`${i18nPrefix}.col.lineKeyword`),
                  dataIndex: 'lineKeyword',
                  hideInTable: true,
                  order: 13,
                  fieldProps: { allowClear: true },
                },
              ]
            : []),
          {
            title: t(`${i18nPrefix}.col.code`),
            key: 'finance_doc_partner_stacked',
            dataIndex: codeField,
            width: 240,
            minWidth: 240,
            uniTableKeepWidth: true,
            uniTablePrimaryFlex: false,
            resizable: false,
            fixed: 'left',
            hideInSearch: true,
            ellipsis: false,
            render: (_, row) => {
              const partner = String(row.counterparty_name ?? '').trim() || '—';
              const code = resolveDocCode(row, codeField);
              return (
                <UniTableStackedPrimaryCell
                  primary={partner}
                  secondary={code}
                  onSecondaryClick={() => void openDetail(row)}
                />
              );
            },
          },
          {
            title: t(`${i18nPrefix}.col.counterparty`),
            dataIndex: 'counterparty_name',
            hideInTable: true,
          },
          {
            title: t(`${i18nPrefix}.col.businessDate`),
            key: 'business_date',
            dataIndex: 'business_date',
            valueType: 'date',
            width: 132,
            minWidth: 132,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            sorter: true,
          },
          {
            title: t(`${i18nPrefix}.col.businessDate`),
            dataIndex: 'business_date_range',
            valueType: 'dateRange',
            hideInTable: true,
            order: 20,
            formItemProps: formDateRangeFormItemProps,
          },
          {
            title: t(`${i18nPrefix}.col.amount`),
            key: 'total_amount',
            dataIndex: 'total_amount',
            align: 'right',
            width: 132,
            minWidth: 132,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            sorter: true,
            render: (_, r) => formatCurrencyAmount(r.total_amount),
          },
          ...(isOtherExpenseDoc
            ? [
                {
                  title: t('app.kuaizhizao.common.colLineMaterials'),
                  ...DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
                  hideInSearch: true,
                  render: (_: unknown, r: VoucherRow) =>
                    renderDocumentLineMaterialsPreview(mapOtherExpenseLinePreviewItems(r.lines), t),
                },
              ]
            : []),
          ...(isExpenseApplication
            ? [
                {
                  title: t('app.kuaicaiwu.otherExpenseApplication.col.remainingAmount'),
                  dataIndex: 'remaining_amount',
                  width: 120,
                  uniTableKeepWidth: true,
                  hideInSearch: true,
                  align: 'right' as const,
                  render: (_: unknown, r: VoucherRow) => formatCurrencyAmount(r.remaining_amount),
                },
              ]
            : []),
          {
            title: t(`${i18nPrefix}.field.notes`),
            dataIndex: 'notes',
            minWidth: 160,
            uniTableRemainderFlex: true,
            uniTablePrimaryFlex: true,
            resizable: false,
            hideInSearch: true,
            ellipsis: true,
            render: (_, r) => r.notes?.trim() || '—',
          },
          {
            title: t('common.status'),
            dataIndex: incomeSaveSubmitSplit ? 'review_status' : 'status',
            hideInTable: true,
            order: 22,
            valueEnum: incomeSaveSubmitSplit ? incomeReviewStatusEnum : miscStatusEnum,
          },
          ...buildDocumentAuditColumns<VoucherRow>(t),
          ...(miscAuditColumn ? [miscAuditColumn] : []),
          {
            title: t('common.status'),
            key: 'lifecycle',
            dataIndex: incomeSaveSubmitSplit ? 'review_status' : 'status',
            fixed: 'right',
            hideInSearch: true,
            render: (_, r) => renderMiscDocumentStatus(r),
          },
          {
            title: t('common.actions'),
            key: 'action',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) => {
              const code = resolveDocCode(row, codeField);
              const nodes: React.ReactNode[] = [];
              if (perms.canRead) {
                nodes.push(
                  <Button key="read" {...rowActionKind('read')} onClick={() => void openDetail(row)} />,
                );
              }
              if (perms.canUpdate && capAllowed(row, 'update')) {
                nodes.push(
                  <Button key="edit" {...rowActionKind('update')} onClick={() => void openEdit(row)} />,
                );
              }
              if (!incomeSaveSubmitSplit) {
                nodes.push(
                  <span {...rowActionKind('skip')} key="wf">
                    <UniWorkflowActions
                      {...rowActionKind('skip')}
                      record={row}
                      entityType={auditEntityType}
                      auditNodeKey={auditEntityType}
                      resourcePrefix={resource}
                      workflowAuditEnabled={auditEnabled}
                      entityName={t(menuTitleKey)}
                      statusField="status"
                      reviewStatusField="review_status"
                      {...miscWorkflowStatuses}
                      onSuccess={() => reloadAfterWorkflow(row.id)}
                    />
                  </span>,
                );
              }
              if (!isExpenseApplication && perms.canAction?.('revoke') && capAllowed(row, 'unconfirm')) {
                nodes.push(
                  <ActionConfirmPopconfirm
                    key="unconfirm"
                    title={t(`${i18nPrefix}.unconfirmTitle`)}
                    description={t(`${i18nPrefix}.unconfirmDesc`, { code })}
                    onConfirm={() => void runAction(t(`${i18nPrefix}.unconfirm`), () => service.unconfirm(row.id))}
                  >
                    <Button
                      {...rowActionKind('revoke')}
                      {...rowActionLabelKeep()}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t(`${i18nPrefix}.unconfirm`)}
                    </Button>
                  </ActionConfirmPopconfirm>,
                );
              }
              if (!isExpenseApplication && perms.canAction?.('revoke') && capAllowed(row, 'cancel')) {
                nodes.push(
                  <ActionConfirmPopconfirm
                    key="cancel"
                    title={t(`${i18nPrefix}.voidTitle`)}
                    description={t(`${i18nPrefix}.voidDesc`, { code })}
                    onConfirm={() => void runAction(t('app.kuaicaiwu.common.void'), () => service.cancel(row.id))}
                  >
                    <Button {...rowActionKind('obsolete')} onClick={(e) => e.stopPropagation()} />
                  </ActionConfirmPopconfirm>,
                );
              }
              return nodes;
            },
          },
        ],
        SALES_DOC_LIST_FIELD_RANK,
      ),
    [
      auditEnabled,
      auditEntityType,
      codeField,
      i18nPrefix,
      incomeReviewStatusEnum,
      incomeSaveSubmitSplit,
      isOtherExpenseDoc,
      kind,
      menuTitleKey,
      miscAuditColumn,
      miscStatusEnum,
      miscWorkflowStatuses,
      openDetail,
      openEdit,
      perms,
      reloadAfterWorkflow,
      renderMiscStatusTag,
      renderMiscDocumentStatus,
      resource,
      runAction,
      service,
      t,
    ],
  );

  const createButtonText = t(createButtonI18nKey ?? `${i18nPrefix}.createButton`);
  const usePullCreateToolbar = Boolean(
    perms.canCreate && (pullFromApplicationAction || isExpenseApplication || isOtherExpenseDoc),
  );

  const pullCreateToolbarMenuItems = useMemo(() => {
    const items: UniPullMenuItem[] = [];
    if (pullFromApplicationAction) {
      items.push(
        ...buildKuaicaiwuPullCreateMenuItems([
          {
            key: 'pull-from-application',
            actionKey: 'other_expense.pull_from_application',
            onClick: pullFromApplicationQuery.openModal,
          },
        ]),
      );
    }
    if (canCopySelectedVoucher) {
      if (items.length > 0) {
        items.push({ type: 'divider', key: 'copy-selected-divider' });
      }
      items.push({
        key: 'copy-selected',
        label: t(
          isExpenseApplication
            ? 'app.kuaicaiwu.otherExpenseApplication.copySelectedCreate'
            : `${i18nPrefix}.copySelectedCreate`,
        ),
        disabled: selectedRowsForBatch.length !== 1,
        onClick: () => void openCopySelectedVoucher(),
      });
    }
    return items;
  }, [
    canCopySelectedVoucher,
    i18nPrefix,
    isExpenseApplication,
    openCopySelectedVoucher,
    pullFromApplicationAction,
    pullFromApplicationQuery.openModal,
    selectedRowsForBatch.length,
    t,
  ]);

  const rowSelectionEnabled =
    perms.canDelete ||
    Boolean(perms.canAction?.('submit')) ||
    Boolean(perms.canAction?.('approve')) ||
    Boolean(perms.canAction?.('audit')) ||
    Boolean(perms.canAction?.('push')) ||
    (Boolean(perms.canCreate) && canCopySelectedVoucher);

  return (
    <>
      <ListPageTemplate>
        <UniTable<VoucherRow>
          actionRef={actionRef}
          permissionResource={resource}
          columnPersistenceId={columnPersistenceId}
          headerTitle={t(menuTitleKey)}
          rowKey="id"
          columns={columns}
          pinnedTabsField={
            incomeSaveSubmitSplit ? FINANCE_INVOICE_PINNED_REVIEW_FIELD : FINANCE_DOC_PINNED_STATUS_FIELD
          }
          showAdvancedSearch
          skipFuzzyPinyinClientFilter={isOtherExpenseDoc}
          showCreateButton={Boolean(perms.canCreate) && !usePullCreateToolbar}
          createButtonText={createButtonText}
          onCreate={openCreate}
          enableRowSelection={rowSelectionEnabled}
          selectedRowKeys={selectedRowKeys}
          onRowSelectionChange={setSelectedRowKeys}
          showDeleteButton={Boolean(perms.canDelete)}
          deleteButtonText={t('common.delete')}
          onDelete={handleBatchDelete}
          deleteConfirmTitle={(count) => t(`${i18nPrefix}.confirmBatchDelete`, { count })}
          toolBarActionsAfterCreate={[
            <UniPushToolbarButton
              key={`misc-voucher-push-${selectedVoucherForToolbar?.id ?? 'none'}`}
              menuItems={toolbarPushMenuItems}
              disabled={selectedRowKeys.length !== 1 || !selectedVoucherForToolbar}
              disabledReason={toolbarPushDisabledReason}
              sourceDocument={toolbarPushSourceDocument}
              pushTargets={toolbarPushTargets}
            />,
          ]}
          toolBarActions={
            incomeSaveSubmitSplit
              ? [
                  <UniBatchMenuButton
                    key="other-income-submit"
                    selectedRowKeys={selectedRowKeys}
                    buttonText={t('common.submit')}
                    menuItems={incomeToolbarAuditMenus.submitItems}
                  />,
                  <UniBatchMenuButton
                    key="other-income-audit"
                    selectedRowKeys={selectedRowKeys}
                    buttonText={t('components.uniAction.audit')}
                    menuItems={incomeToolbarAuditMenus.auditItems}
                  />,
                ]
              : undefined
          }
          toolBarActionsBeforeCreate={
            usePullCreateToolbar
              ? [
                  <UniPullCreateToolbar
                    key="pull-create-other-expense"
                    compactKey="pull-create-other-expense"
                    createIcon={<PlusOutlined />}
                    createLabel={createButtonText}
                    onCreate={openCreate}
                    menuItems={pullCreateToolbarMenuItems}
                  />,
                ]
              : undefined
          }
          toolBarActionsAfterDelete={
            incomeSaveSubmitSplit
              ? undefined
              : [
                  <UniAuditBatchMenuButton
                    key="misc-voucher-batch-audit"
                    selectedRowKeys={selectedRowKeys}
                    selectedRecords={selectedRowsForBatch}
                    auditEnabled={auditEnabled}
                    permGates={perms}
                    handlers={auditBatchHandlers}
                    auditEntity={{
                      entityType: auditEntityType,
                      entityName: miscAuditEntityName,
                    }}
                    onSuccess={handleAuditBatchSuccess}
                    toolBarButtonSize="middle"
                  />,
                ]
          }
          rightToolBarActionsBeforeExport={
            isOtherExpenseDoc
              ? [
                  <UniCapabilityBatchButton
                    key="other-expense-print"
                    selectedRowKeys={selectedRowKeys}
                    selectedRecords={selectedRowsForBatch}
                    capabilityKey="print"
                    permAllowed={Boolean(perms.canPrint)}
                    batchAllowed={(records, perm) =>
                      Boolean(perm) &&
                      records.some((record) => record.capabilities?.print?.allowed === true)
                    }
                    singleOnly
                    onRun={async (id) => {
                      openPrint({ documentType: 'other_expense', documentId: id });
                    }}
                    labels={{
                      single: t('components.uniAction.print'),
                      batch: t('components.uniAction.print'),
                    }}
                    icon={<PrinterOutlined />}
                    size="medium"
                  />,
                ]
              : undefined
          }
          onTableDataChange={(rows) => {
            tableRowsRef.current = rows;
          }}
          request={async (params, _sort, _filter, searchFormValues) => {
            const reviewFilter = pickSearchString(searchFormValues, 'review_status') ?? params.review_status;
            const statusFilter = pickSearchString(searchFormValues, 'status') ?? params.status;
            const keywordParams = resolveMiscVoucherListKeywordParams(searchFormValues, {
              codeField,
              partnerNameField: 'counterparty_name',
              lineSearchField: 'lineKeyword',
            });
            const res = await service.list({
              skip: ((params.current ?? 1) - 1) * (params.pageSize ?? 20),
              limit: params.pageSize ?? 20,
              ...keywordParams,
              ...(incomeSaveSubmitSplit
                ? { review_status: reviewFilter }
                : { status: statusFilter }),
            });
            return { data: res.items, success: true, total: res.total };
          }}
        />
      </ListPageTemplate>

      <FormModalTemplate
        open={modalOpen}
        formRef={formRef}
        isEdit={editing != null}
        title={
          editing
            ? t(editTitleI18nKey ?? `${i18nPrefix}.editTitle`)
            : t(createTitleI18nKey ?? `${i18nPrefix}.createTitle`)
        }
        onClose={() => setModalOpen(false)}
        afterOpenChange={(open) => {
          if (!open) {
            formRef.current?.resetFields();
            setEditing(null);
            pendingFormValuesRef.current = null;
            return;
          }
          const pending = pendingFormValuesRef.current;
          if (pending) {
            formRef.current?.setFieldsValue(pending);
            pendingFormValuesRef.current = null;
            return;
          }
          if (editing == null) {
            formRef.current?.setFieldsValue({
              business_date: dayjs(),
              counterparty_kind: isOtherExpenseDoc ? 'supplier' : isExpenseKind ? 'other' : 'none',
              ...(isOtherExpenseDoc ? { payable_recognition: orgLedgerRecognitionDefault } : {}),
              ...(isExpenseKind
                ? {
                    payment_method: BANK_TRANSFER_PAYMENT_METHOD,
                    employee_advance_enabled: false,
                  }
                : { payment_method: BANK_TRANSFER_PAYMENT_METHOD }),
              related_purchase_receipts: [],
              lines: [{}],
            });
          }
        }}
        onFinish={async (values) => {
          try {
            await handleSave(values as Record<string, unknown>);
          } catch (e) {
            messageApi.error(getApiErrorMessage(e, t('common.saveFailed')));
          }
        }}
        width={MODAL_CONFIG.LARGE_WIDTH}
        grid={false}
      >
        <Row gutter={16}>
          <Col span={12}>
            <ProFormDatePicker
              name="business_date"
              label={t(`${i18nPrefix}.field.businessDate`)}
              rules={[{ required: true }]}
              fieldProps={{ style: { width: '100%' } }}
            />
          </Col>
          <Col span={12}>
            {isExpenseKind ? (
              <ProFormSelect
                name="counterparty_kind"
                label={t(`${i18nPrefix}.field.counterpartyKind`)}
                options={counterpartyKindOptions}
                fieldProps={{
                  onChange: (val: string) => onCounterpartyKindChange(String(val)),
                }}
              />
            ) : (
              <ProFormSelect
                name="payment_method"
                label={t(`${i18nPrefix}.field.paymentMethod`)}
                options={paymentMethodOptions}
                rules={[{ required: true }]}
              />
            )}
          </Col>
        </Row>
        {kind === 'income' ? (
          <Row gutter={16}>
            <Col span={12}>
              <ProFormSelect
                name="bank_account_id"
                label={t(`${i18nPrefix}.field.bankAccount`)}
                options={bankAccounts.map((a) => ({
                  label: formatBankAccountOptionLabel(a),
                  value: a.id,
                }))}
              />
            </Col>
            <Col span={12}>
              <ProFormSelect
                name="counterparty_kind"
                label={t(`${i18nPrefix}.field.counterpartyKind`)}
                options={counterpartyKindOptions}
                fieldProps={{
                  onChange: (val: string) => onCounterpartyKindChange(String(val)),
                }}
              />
            </Col>
          </Row>
        ) : null}
        <ProFormDependency name={['counterparty_kind']} formItemProps={{ style: { marginBottom: 0 } }}>
          {({ counterparty_kind: cpKind }) => {
            const kindStr = String(cpKind ?? 'none');
            const counterpartyField =
              kindStr === 'customer' ? (
                <ProFormSelect
                  name="counterparty_id"
                  label={t(`${i18nPrefix}.field.counterpartyCustomer`)}
                  rules={[{ required: true, message: t('common.required') }]}
                  options={customerOptions}
                  fieldProps={{
                    showSearch: true,
                    optionFilterProp: 'label',
                  }}
                />
              ) : kindStr === 'supplier' ? (
                <ProFormSelect
                  name="counterparty_id"
                  label={t(`${i18nPrefix}.field.counterpartySupplier`)}
                  rules={[{ required: true, message: t('common.required') }]}
                  options={supplierOptions}
                  fieldProps={{
                    showSearch: true,
                    optionFilterProp: 'label',
                    allowClear: true,
                    onChange: (val: number | undefined) => {
                      formRef.current?.setFieldsValue({ related_purchase_receipts: [] });
                      const supplierId =
                        val != null && Number.isFinite(Number(val)) && Number(val) > 0
                          ? Number(val)
                          : null;
                      pullReceiptSupplierIdRef.current = supplierId;
                      if (supplierId == null) {
                        purchaseReceiptLinkQuery.closeModal();
                        return;
                      }
                    },
                  }}
                />
              ) : kindStr === 'employee' ? (
                <ProFormSelect
                  name="counterparty_id"
                  label={t(`${i18nPrefix}.field.counterpartyEmployee`)}
                  rules={[{ required: true, message: t('common.required') }]}
                  options={employeeOptions}
                  fieldProps={{
                    showSearch: true,
                    optionFilterProp: 'label',
                  }}
                />
              ) : kindStr === 'other' ? (
                <ProFormText
                  name="counterparty_name"
                  label={t(`${i18nPrefix}.field.counterpartyName`)}
                  rules={[{ required: true, message: t('common.required') }]}
                  extra={
                    isOtherExpenseDoc
                      ? t('app.kuaicaiwu.otherExpense.counterpartyOtherLedgerHint')
                      : undefined
                  }
                />
              ) : null;
            if (isExpenseKind) {
              const departmentSelect = (
                <ProFormSelect
                  name="department_id"
                  label={t(`${i18nPrefix}.field.department`)}
                  options={departmentOptions}
                  fieldProps={{
                    showSearch: true,
                    optionFilterProp: 'label',
                    allowClear: true,
                  }}
                />
              );
              const hasCounterparty = kindStr !== 'none';
              return (
                <Row gutter={16}>
                  <Col span={12}>
                    {hasCounterparty ? counterpartyField : departmentSelect}
                  </Col>
                  <Col span={12}>{hasCounterparty ? departmentSelect : null}</Col>
                </Row>
              );
            }
            if (kindStr === 'none') {
              return null;
            }
            return (
              <Row gutter={16}>
                <Col span={12}>{counterpartyField}</Col>
              </Row>
            );
          }}
        </ProFormDependency>
        {!isExpenseApplication ? (
          <Row gutter={16}>
            <Col span={12}>
              <ProFormDependency name={['counterparty_kind']}>
                {({ counterparty_kind: ledgerCpKind }) => {
                  const supplierLedger =
                    !isOtherExpenseDoc || String(ledgerCpKind ?? '') === 'supplier';
                  if (!supplierLedger) {
                    return (
                      <>
                        <Form.Item name={ledgerRecognitionFieldName} hidden initialValue="manual">
                          <Input />
                        </Form.Item>
                        <Form.Item
                          label={t('field.document.ledgerRecognition')}
                          extra={t('app.kuaicaiwu.otherExpense.counterpartyOtherLedgerHint')}
                        >
                          {isOtherExpenseDoc
                            ? t('app.kuaicaiwu.otherExpense.counterpartyOtherLedgerRecognition')
                            : payableLedgerRecognitionLabel(t, 'manual')}
                        </Form.Item>
                      </>
                    );
                  }
                  return (
                    <ProForm.Item
                      name={ledgerRecognitionFieldName}
                      label={t('field.document.ledgerRecognition')}
                      initialValue={orgLedgerRecognitionDefault}
                      rules={[
                        { required: true, message: t('field.document.ledgerRecognitionRequired') },
                      ]}
                    >
                      <UniDropdown options={ledgerRecognitionOptions} style={{ width: '100%' }} />
                    </ProForm.Item>
                  );
                }}
              </ProFormDependency>
            </Col>
            {!isExpenseKind ? (
              <Col span={12}>
                <ProFormSelect
                  name="department_id"
                  label={t(`${i18nPrefix}.field.department`)}
                  options={departmentOptions}
                  fieldProps={{
                    showSearch: true,
                    optionFilterProp: 'label',
                    allowClear: true,
                  }}
                />
              </Col>
            ) : null}
          </Row>
        ) : null}
        {kind === 'expense' ? (
          <ProForm.Item name="related_purchase_receipts" noStyle>
            <FormValueSink />
          </ProForm.Item>
        ) : null}
        {kind === 'expense' ? (
          <ProFormDependency
            name={['counterparty_kind', 'related_purchase_receipts']}
            formItemProps={{ style: { marginBottom: 0 } }}
          >
            {({ counterparty_kind: ck, related_purchase_receipts: links }) => {
              if (String(ck ?? '') !== 'supplier') {
                return null;
              }
              const list = Array.isArray(links) ? (links as RelatedPurchaseReceiptRef[]) : [];
              return (
                <div style={{ marginBottom: 12 }}>
                  <Space wrap size={[8, 4]}>
                    <span>{t(`${i18nPrefix}.relatedPurchaseReceipts`)}：</span>
                    {list.length > 0 ? (
                      list.map((item) => (
                        <Button
                          key={item.id}
                          type="link"
                          size="small"
                          style={{ padding: 0, height: 'auto' }}
                          onClick={() =>
                            linkedDetail?.openLinkedDocumentDetail('purchase_receipt', Number(item.id))
                          }
                        >
                          {item.code || item.id}
                        </Button>
                      ))
                    ) : (
                      <span>—</span>
                    )}
                    <Button type="link" size="small" onClick={openPurchaseReceiptLink}>
                      {t(`${i18nPrefix}.linkPurchaseReceipt`)}
                    </Button>
                  </Space>
                </div>
              );
            }}
          </ProFormDependency>
        ) : null}
        {isOtherExpenseDoc ? (
          <>
            <Row gutter={16} align="middle">
              <Col span={12}>
                <ProFormSelect
                  name="payment_method"
                  label={t(`${i18nPrefix}.field.paymentMethod`)}
                  options={paymentMethodOptions}
                  rules={[{ required: true }]}
                  fieldProps={{
                    onChange: (method: string) => {
                      const employeeAdvance = isEmployeeAdvancePaymentMethod(method);
                      formRef.current?.setFieldsValue({
                        employee_advance_enabled: employeeAdvance,
                        ...(employeeAdvance ? {} : { advance_payee_id: undefined }),
                      });
                    },
                  }}
                />
              </Col>
              <ProFormDependency name={['payment_method']}>
                {({ payment_method: method }) =>
                  isEmployeeAdvancePaymentMethod(method) ? (
                    <Col span={12}>
                      <ProFormSelect
                        name="advance_payee_id"
                        label={t('app.kuaicaiwu.payment.advancePayee')}
                        options={employeeOptions.map((o) => ({
                          label: o.label,
                          value: o.value,
                        }))}
                        rules={[
                          {
                            required: true,
                            message: t('app.kuaicaiwu.payment.advancePayeeRequired'),
                          },
                        ]}
                        fieldProps={{
                          showSearch: true,
                          optionFilterProp: 'label',
                          allowClear: true,
                        }}
                      />
                    </Col>
                  ) : null
                }
              </ProFormDependency>
            </Row>
          </>
        ) : null}
        {kind === 'expense' ? <MiscVoucherCounterpartyPayeeSection required={isOtherExpenseDoc} /> : null}
        <UniTableDetail
          name="lines"
          title={t(`${i18nPrefix}.linesTitle`)}
          required
          initialValue={{}}
          onBatchSelect={
            kind === 'expense'
              ? () => {
                  const ck = String(formRef.current?.getFieldValue('counterparty_kind') ?? '');
                  if (ck !== 'supplier') {
                    messageApi.warning(t(`${i18nPrefix}.selectSupplierFirst`));
                    return;
                  }
                  openPurchaseReceiptLink();
                }
              : undefined
          }
          batchSelectText={kind === 'expense' ? t(`${i18nPrefix}.linkPurchaseReceipt`) : undefined}
          leftExtra={
            <ProFormDependency name={['lines']}>
              {({ lines: lineRows }) => {
                const sum = normalizeFormListItems<LineFormRow>(lineRows).reduce(
                  (acc, row) => acc + (Number(row.amount) || 0),
                  0,
                );
                return (
                  <span>
                    {t(`${i18nPrefix}.amountTotal`)}：{formatCurrencyAmount(sum)}
                  </span>
                );
              }}
            </ProFormDependency>
          }
          columns={[
            {
              title: t(`${i18nPrefix}.line.category`),
              dataIndex: 'category_code',
              width: 200,
              render: (_: unknown, field: FormListFieldData) => (
                <Form.Item
                  name={[field.name, 'category_code']}
                  style={{ margin: 0 }}
                  rules={[{ required: true, message: t('common.required') }]}
                >
                  <MiscCategoryQuickSelect
                    catKind={catKind}
                    options={categoryOptions}
                    onCategoriesReload={reloadCategories}
                    canQuickCreate={canQuickAddCategory}
                    i18nPrefix={i18nPrefix}
                  />
                </Form.Item>
              ),
            },
            {
              title: t(`${i18nPrefix}.line.description`),
              dataIndex: 'description',
              render: (_: unknown, field: FormListFieldData) => (
                <Form.Item name={[field.name, 'description']} style={{ margin: 0 }}>
                  <Input size="small" />
                </Form.Item>
              ),
            },
            {
              title: isExpenseApplication
                ? t('app.kuaicaiwu.otherExpenseApplication.line.estimatedAmount')
                : t(`${i18nPrefix}.line.amount`),
              dataIndex: 'amount',
              width: 140,
              render: (_: unknown, field: FormListFieldData) => (
                <Form.Item
                  name={[field.name, 'amount']}
                  style={{ margin: 0 }}
                  rules={[{ required: true, message: t('common.required') }]}
                >
                  <InputNumber size="small" min={0.01} precision={2} style={{ width: '100%' }} />
                </Form.Item>
              ),
            },
          ]}
        />
        <Row gutter={16}>
          <Col span={24}>
            <DocumentAttachmentsField category={attachmentCategory} />
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={24}>
            <ProFormTextArea
              name="notes"
              label={t(`${i18nPrefix}.field.notes`)}
              fieldProps={{ rows: 2 }}
            />
          </Col>
        </Row>
        <Form.Item name="source_type" hidden>
          <FormValueSink />
        </Form.Item>
        <Form.Item name="source_id" hidden>
          <FormValueSink />
        </Form.Item>
        <Form.Item name="source_code" hidden>
          <FormValueSink />
        </Form.Item>
      </FormModalTemplate>

      <MiscVoucherDetailDrawer
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false);
          setDetailError(null);
        }}
        loading={detailLoading}
        error={detailError}
        onRetry={
          detailRow?.id
            ? () => {
                const id = detailRow.id;
                setDetailLoading(true);
                setDetailError(null);
                void service
                  .get(id)
                  .then((full) => setDetailRow(full))
                  .catch((e) => {
                    const msg = getApiErrorMessage(e, t(`${i18nPrefix}.loadFailed`));
                    setDetailError(msg);
                  })
                  .finally(() => setDetailLoading(false));
              }
            : undefined
        }
        record={detailRow}
        codeField={codeField}
        i18nPrefix={i18nPrefix}
        kind={kind}
        isExpenseApplication={isExpenseApplication}
        isOtherExpenseDoc={isOtherExpenseDoc}
        bankAccountLabel={detailBankAccountLabel}
        documentType={auditEntityType}
        renderDocumentStatus={renderMiscDocumentStatus}
        onOpenLinkedDocument={(type, id) => {
          if (type === 'receivable' || type === 'payable') {
            navigate(`/apps/kuaicaiwu/finance-management/${type}s/${id}`);
            return;
          }
          if ((type === 'receipt' || type === 'payment') && financeVoucherDetail) {
            financeVoucherDetail.openFinanceVoucherDetail({ kind: type, id: Number(id) });
            return;
          }
          linkedDetail?.openLinkedDocumentDetail(type, id);
        }}
        extra={
          detailRow ? (
            <Space>
              <UniWorkflowActions
                record={detailRow}
                entityType={auditEntityType}
                auditNodeKey={auditEntityType}
                resourcePrefix={resource}
                workflowAuditEnabled={auditEnabled}
                entityName={t(menuTitleKey)}
                statusField="status"
                reviewStatusField="review_status"
                {...miscWorkflowStatuses}
                theme="default"
                size="medium"
                onSuccess={() => reloadAfterWorkflow(detailRow.id)}
              />
              {isOtherExpenseDoc &&
              perms.canPrint &&
              detailRow.capabilities?.print?.allowed !== false ? (
                <Button
                  icon={<PrinterOutlined />}
                  onClick={() =>
                    openPrint({ documentType: 'other_expense', documentId: detailRow.id })
                  }
                >
                  {t('components.uniAction.print')}
                </Button>
              ) : null}
              {isExpenseApplication &&
              detailRow.capabilities?.push_other_expense?.allowed &&
              perms.canAction?.('push') ? (
                <Button type="primary" onClick={() => void handlePushOtherExpense(detailRow)}>
                  {t('app.kuaicaiwu.otherExpenseApplication.pushOtherExpense')}
                </Button>
              ) : null}
            </Space>
          ) : null
        }
      />

      {pullFromApplicationAction ? (
        <UniPullQueryModal<OtherExpenseApplicationPullCandidate>
          open={pullFromApplicationQuery.open}
          title={pullFromApplicationAction.label}
          onCancel={pullFromApplicationQuery.closeModal}
          onOk={() => {
            void pullFromApplicationQuery.handleConfirm();
          }}
          rowKey="id"
          columns={[
            {
              title: t(`${i18nPrefix}.col.code`),
              dataIndex: 'application_code',
              width: 168,
              ellipsis: true,
            },
            {
              title: t(`${i18nPrefix}.col.counterparty`),
              dataIndex: 'counterparty_name',
              ellipsis: true,
            },
            {
              title: t(`${i18nPrefix}.col.remainingAmount`),
              dataIndex: 'remaining_amount',
              width: 120,
              align: 'right',
              render: (v) => formatCurrencyAmount(v),
            },
          ]}
          dataSource={pullFromApplicationQuery.dataSource}
          loading={pullFromApplicationQuery.loading}
          confirmLoading={pullFromApplicationQuery.confirmLoading}
          selectionType={pullFromApplicationQuery.selectionType}
          selectedRowKeys={pullFromApplicationQuery.selectedRowKeys}
          selectedRows={pullFromApplicationQuery.selectedRows}
          onSelectedRowKeysChange={pullFromApplicationQuery.handleSelectedRowKeysChange}
          isRowDisabled={pullFromApplicationQuery.isRowDisabled}
          searchDraft={pullFromApplicationQuery.searchDraft}
          onSearchDraftChange={pullFromApplicationQuery.setSearchDraft}
          onSearchApply={pullFromApplicationQuery.handleSearchApply}
          onSearchClear={pullFromApplicationQuery.handleSearchClear}
          appliedKeyword={pullFromApplicationQuery.appliedKeyword}
          searchPlaceholder={t(`${i18nPrefix}.pullApplication.searchPlaceholder`)}
          page={pullFromApplicationQuery.page}
          pageSize={pullFromApplicationQuery.pageSize}
          total={pullFromApplicationQuery.total}
          onPageChange={pullFromApplicationQuery.handlePageChange}
          pullQuery={pullFromApplicationQuery.pullQuery}
          zIndex={nestedPullZIndex}
          okText={t('common.next')}
        />
      ) : null}

      {kind === 'expense' ? (
        <UniPullQueryModal<OtherExpensePurchaseReceiptLinkCandidate>
          open={purchaseReceiptLinkQuery.open}
          title={t(`${i18nPrefix}.linkPurchaseReceiptTitle`)}
          onCancel={purchaseReceiptLinkQuery.closeModal}
          onOk={() => {
            void purchaseReceiptLinkQuery.handleConfirm();
          }}
          rowKey="id"
          columns={purchaseReceiptLinkColumns}
          dataSource={purchaseReceiptLinkQuery.dataSource}
          loading={purchaseReceiptLinkQuery.loading}
          confirmLoading={purchaseReceiptLinkQuery.confirmLoading}
          selectionType={purchaseReceiptLinkQuery.selectionType}
          selectedRowKeys={purchaseReceiptLinkQuery.selectedRowKeys}
          selectedRows={purchaseReceiptLinkQuery.selectedRows}
          onSelectedRowKeysChange={purchaseReceiptLinkQuery.handleSelectedRowKeysChange}
          searchDraft={purchaseReceiptLinkQuery.searchDraft}
          onSearchDraftChange={purchaseReceiptLinkQuery.setSearchDraft}
          onSearchApply={purchaseReceiptLinkQuery.handleSearchApply}
          onSearchClear={purchaseReceiptLinkQuery.handleSearchClear}
          appliedKeyword={purchaseReceiptLinkQuery.appliedKeyword}
          searchPlaceholder={t(`${i18nPrefix}.pull.searchPlaceholder`)}
          page={purchaseReceiptLinkQuery.page}
          pageSize={purchaseReceiptLinkQuery.pageSize}
          total={purchaseReceiptLinkQuery.total}
          onPageChange={purchaseReceiptLinkQuery.handlePageChange}
          pullQuery={purchaseReceiptLinkQuery.pullQuery}
          zIndex={nestedPullZIndex}
          okText={t('common.confirm')}
        />
      ) : null}

      {incomeSaveSubmitSplit ? miscIncomeAuditModal : null}
      {isOtherExpenseDoc ? PrintModal : null}
    </>
  );
};

export default MiscVoucherListPage;
