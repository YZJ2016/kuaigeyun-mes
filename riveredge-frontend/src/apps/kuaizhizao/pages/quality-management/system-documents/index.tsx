import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActionType,
  ProColumns,
  ProFormDateTimePicker,
  ProFormDependency,
  ProFormItem,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { App, Breadcrumb, Button, Col, Empty, Row, Table, Alert, Modal } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import CodeField from '../../../../../components/code-field';
import { UniTable } from '../../../../../components/uni-table';
import {
  rowActionDrawingDistribute,
  rowActionDrawingNewRevision,
  rowActionKind,
  rowActionLabelKeep,
  rowActionViewHistory,
} from '../../../../../components/uni-action';
import { FormModalTemplate, MODAL_CONFIG, TwoColumnLayout } from '../../../../../components/layout-templates';
import PermissionGuard from '../../../../../components/permission/PermissionGuard';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useNewShortcut } from '../../../../../hooks/useNewShortcut';
import { withSingleNewShortcutHint } from '../../../../../utils/globalNewShortcut';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { formatDateTimeBySiteSetting } from '../../../../../utils/format';
import { renderDocumentStatusTag } from '../../../../../utils/documentLifecycleStatusTag';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { UNI_TABLE_SITE_DATETIME_COLUMN_DEFAULTS } from '../../../../../utils/uniTableLayoutColumns';
import { pickListSearchKeyword, pickSearchString } from '../../../../../utils/tableQueryKey';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import { mapAttachmentsToUploadList, normalizeDocumentAttachments } from '../../../utils/documentAttachments';
import {
  qualityQmsApi,
  QmsSystemDocument,
  QmsSystemDocumentVersion,
} from '../../../services/quality-qms';
import {
  EVIDENCE_LINKS_PARSE_INVALID_JSON,
  parseEvidenceLinksText,
  stringifyEvidenceLinks,
  QMS_DOC_STATUS_OPTIONS,
  QMS_DOC_TYPE_OPTIONS,
} from '../qms/qmsMeta';
import QmsClauseSelect from '../qms/QmsClauseSelect';
import SystemDocumentCirculationModal from './SystemDocumentCirculationModal';
import SystemDocumentDetailDrawer from './SystemDocumentDetailDrawer';
import SystemDocumentNavTree from './SystemDocumentNavTree';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import {
  buildLifecycleTreeKey,
  dimensionLabel,
  loadStoredSystemDocumentNav,
  navHidesStatusSearch,
  navSelectionToListParams,
  resolveNavNodeTitle,
  saveStoredSystemDocumentNav,
  type StoredSystemDocumentNav,
  type SystemDocumentNavDimension,
} from './systemDocumentNav';
import { buildListPageHelpViewConfig } from '../../../../../components/page-help-wiki';
import { hasDocumentGlobalView } from '../../../../../utils/permissionContract';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import { CustomFieldsFormSection } from '../../../../../components/custom-fields';

const RESOURCE = 'kuaizhizao:quality-management-system-documents';
const SYSTEM_DOCUMENT_CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_qms_system_documents';

const SystemDocumentsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const actionRef = useRef<ActionType>(null);
  const formRef = useRef<any>(null);
  const tableRowsRef = useRef<QmsSystemDocument[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<QmsSystemDocument | null>(null);
  const [nav, setNav] = useState<StoredSystemDocumentNav>(() => loadStoredSystemDocumentNav());
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyDoc, setHistoryDoc] = useState<QmsSystemDocument | null>(null);
  const [historyRows, setHistoryRows] = useState<QmsSystemDocumentVersion[]>([]);
  const [historyAudience, setHistoryAudience] = useState('');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [circulationDoc, setCirculationDoc] = useState<QmsSystemDocument | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailDoc, setDetailDoc] = useState<QmsSystemDocument | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailIdRef = useRef<number | null>(null);
  const { canCreate, canUpdate, canDelete, canAction } = useResourcePermissions(RESOURCE);
  const canPublish = !!canAction?.('publish');
  const canSubmit = !!canAction?.('submit');
  const canObsolete = !!canAction?.('obsolete');
  const canReject = !!canAction?.('reject');
  const currentUser = useCurrentUser();
  const canSeeFullHistoryHint = hasDocumentGlobalView(currentUser);

  const {
    customFields: systemDocFormCustomFields,
    customFieldValues: systemDocFormCustomFieldValues,
    loadFieldValues: loadSystemDocFormFieldValues,
    extractFormValues: extractSystemDocFormValues,
    saveCustomFieldValues: saveSystemDocCustomFieldValues,
    resetFieldValues: resetSystemDocFormFieldValues,
  } = useCustomFields({
    tableName: SYSTEM_DOCUMENT_CUSTOM_FIELD_TABLE,
    loadWhenOpen: true,
    open,
  });

  const {
    customFields: systemDocListCustomFields,
    generateCustomFieldColumns: generateSystemDocCustomFieldColumns,
    enrichRecordsWithCustomFields: enrichSystemDocRecordsWithCustomFields,
    customFieldValues: systemDocDetailCustomFieldValues,
    loadFieldValuesForDetail: loadSystemDocFieldValuesForDetail,
    resetDetailFieldValues: resetSystemDocDetailFieldValues,
  } = useCustomFieldsForList<QmsSystemDocument>({
    tableName: SYSTEM_DOCUMENT_CUSTOM_FIELD_TABLE,
  });

  const statusEnum = useMemo(
    () =>
      Object.fromEntries(
        QMS_DOC_STATUS_OPTIONS.map((o) => [o.value, { text: t(o.labelKey) }]),
      ),
    [t],
  );
  const typeEnum = useMemo(
    () => Object.fromEntries(QMS_DOC_TYPE_OPTIONS.map((o) => [o.value, { text: t(o.labelKey) }])),
    [t],
  );

  const openCreate = useCallback(() => {
    setEditing(null);
    resetSystemDocFormFieldValues();
    setOpen(true);
    setTimeout(() => {
      formRef.current?.resetFields();
      formRef.current?.setFieldsValue({
        doc_type: 'procedure',
        version: 'A0',
        status: 'draft',
        evidence_links_text: '',
        training_refs_text: '[]',
        attachments: [],
      });
    }, 0);
  }, [resetSystemDocFormFieldValues]);

  const fillEditForm = useCallback(
    async (row: QmsSystemDocument) => {
      const customFormValues =
        row.id != null ? await loadSystemDocFormFieldValues(row.id) : {};
      formRef.current?.setFieldsValue({
        ...row,
        evidence_links_text: stringifyEvidenceLinks(row.evidence_links),
        training_refs_text: stringifyEvidenceLinks(row.training_refs),
        attachments: mapAttachmentsToUploadList(row.attachments as any),
        ...customFormValues,
      });
    },
    [loadSystemDocFormFieldValues],
  );
  useNewShortcut(() => {
    if (canCreate) openCreate();
  });

  const { data: reviewDueSummary } = useQuery({
    queryKey: ['qms-system-documents-review-due'],
    queryFn: () => qualityQmsApi.systemDocuments.reviewDueSummary(),
  });

  const { data: standardsEnvelope } = useQuery({
    queryKey: ['qms-standards'],
    queryFn: () => qualityQmsApi.standards.list({ limit: 200 }),
  });

  const standardValueEnum = useMemo(() => {
    const items = standardsEnvelope?.items ?? [];
    return Object.fromEntries(items.map((s) => [s.id, { text: s.code }]));
  }, [standardsEnvelope?.items]);

  const standardNavItems = useMemo(
    () =>
      (standardsEnvelope?.items ?? []).map((s) => ({
        id: s.id,
        code: s.code,
        name: s.name,
      })),
    [standardsEnvelope?.items],
  );

  const navListParams = useMemo(
    () => navSelectionToListParams(nav.dimension, nav.selectedKey),
    [nav.dimension, nav.selectedKey],
  );

  const updateNav = useCallback((dimension: SystemDocumentNavDimension, selectedKey: string) => {
    const next = { dimension, selectedKey };
    setNav(next);
    saveStoredSystemDocumentNav(next);
  }, []);

  const focusLifecycle = useCallback(
    (part: string) => {
      updateNav('lifecycle', buildLifecycleTreeKey(part));
    },
    [updateNav],
  );

  const navBreadcrumbTitle = useMemo(
    () =>
      `${dimensionLabel(nav.dimension, t)} / ${resolveNavNodeTitle(nav.dimension, nav.selectedKey, t, standardNavItems)}`,
    [nav.dimension, nav.selectedKey, standardNavItems, t],
  );

  const hideStatusInSearch = navHidesStatusSearch(nav.dimension, nav.selectedKey);

  const openVersionHistory = useCallback(
    async (row: QmsSystemDocument) => {
      setHistoryDoc(row);
      setHistoryOpen(true);
      setHistoryLoading(true);
      try {
        const res = await qualityQmsApi.systemDocuments.versions(row.id);
        setHistoryRows(res.items || []);
        setHistoryAudience(res.audience || '');
      } catch (e: any) {
        messageApi.error(e?.message || t('common.loadFailed'));
        setHistoryRows([]);
      } finally {
        setHistoryLoading(false);
      }
    },
    [messageApi, t],
  );

  const loadDetail = useCallback(async (id: number) => {
    detailIdRef.current = id;
    setDetailOpen(true);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const doc = await qualityQmsApi.systemDocuments.get(id);
      if (detailIdRef.current !== id) return;
      setDetailDoc(doc);
      await loadSystemDocFieldValuesForDetail(id);
    } catch (e) {
      if (detailIdRef.current !== id) return;
      setDetailDoc(null);
      setDetailError(getApiErrorMessage(e, t('common.loadFailed')));
    } finally {
      if (detailIdRef.current === id) setDetailLoading(false);
    }
  }, [loadSystemDocFieldValuesForDetail, t]);

  const openDetail = useCallback(
    (row: QmsSystemDocument) => {
      setDetailDoc(null);
      void loadDetail(row.id);
    },
    [loadDetail],
  );

  const openEditFromDetail = useCallback((row: QmsSystemDocument) => {
    setDetailOpen(false);
    setEditing(row);
    setOpen(true);
    setTimeout(() => {
      void fillEditForm(row);
    }, 0);
  }, [fillEditForm]);

  const columns: ProColumns<QmsSystemDocument>[] = useMemo(() => {
    const customFieldColumns = generateSystemDocCustomFieldColumns();
    return alignProColumns(
        [
          {
            title: t('app.kuaizhizao.quality.qms.documentCode'),
            dataIndex: 'document_code',
            width: 176,
            minWidth: 176,
            uniTableKeepWidth: true,
            resizable: false,
            copyable: true,
            hideInSearch: true,
          },
          {
            // 标题长短不一：唯一 RemainderFlex
            title: t('app.kuaizhizao.quality.qms.title'),
            dataIndex: 'title',
            minWidth: 200,
            uniTablePrimaryFlex: true,
            uniTableRemainderFlex: true,
            resizable: false,
            ellipsis: true,
            hideInSearch: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.keyword'),
            dataIndex: 'keyword',
            hideInTable: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.docTypeLabel'),
            dataIndex: 'doc_type',
            key: 'qms_system_doc_type',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            valueEnum: typeEnum,
            hideInSearch: nav.dimension === 'doc_type',
            render: (_, row) => {
              const text = typeEnum[row.doc_type]?.text || row.doc_type;
              return text ? <MarkerTag color="geekblue">{text}</MarkerTag> : '-';
            },
          },
          {
            title: t('app.kuaizhizao.quality.qms.version'),
            dataIndex: 'version',
            width: 88,
            minWidth: 88,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.applicableStandard'),
            dataIndex: 'standard_id',
            key: 'qms_system_standard',
            width: 136,
            minWidth: 136,
            uniTableKeepWidth: true,
            resizable: false,
            valueEnum: standardValueEnum,
            render: (_, row) =>
              (row.standard_id != null && standardValueEnum[row.standard_id]?.text) || '-',
            hideInSearch: nav.dimension === 'standard',
          },
          {
            title: t('app.kuaizhizao.quality.qms.clauseLabel'),
            dataIndex: 'clause_labels',
            key: 'qms_system_clause_labels',
            width: 160,
            minWidth: 160,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            ellipsis: true,
            render: (_, row) => {
              const labels = row.clause_labels;
              if (!labels?.length) return '-';
              if (labels.length === 1) return labels[0];
              return `${labels[0]} +${labels.length - 1}`;
            },
          },
          {
            title: t('app.kuaizhizao.quality.qms.nextReviewAt'),
            dataIndex: 'next_review_at',
            key: 'qms_system_next_review_at',
            ...UNI_TABLE_SITE_DATETIME_COLUMN_DEFAULTS,
            render: (_, row) => {
              const text = formatDateTimeBySiteSetting(row.next_review_at) || '-';
              if (row.review_due) {
                return <MarkerTag color="warning">{text}</MarkerTag>;
              }
              return text;
            },
          },
          {
            title: t('app.kuaizhizao.quality.qms.circulation.outstandingColumn'),
            dataIndex: 'outstanding_copies',
            key: 'qms_system_outstanding_copies',
            width: 88,
            minWidth: 88,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => row.outstanding_copies ?? 0,
          },
          {
            title: t('common.status'),
            key: 'lifecycle',
            dataIndex: 'status',
            fixed: 'right',
            valueEnum: statusEnum,
            hideInSearch: hideStatusInSearch,
            render: (_, row) =>
              renderDocumentStatusTag(
                statusEnum[row.status]?.text || row.status || '-',
                row.status || undefined,
              ),
          },
          ...customFieldColumns,
          {
            title: t('common.actions'),
            key: 'action',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) => [
              <Button
                key="view"
                {...rowActionKind('read')}
                onClick={() => openDetail(row)}
              />,
              <Button
                key="circulation"
                {...rowActionDrawingDistribute('skip')}
                onClick={() => setCirculationDoc(row)}
              />,
              <Button
                key="history"
                {...rowActionViewHistory()}
                onClick={() => void openVersionHistory(row)}
              />,
              canUpdate ? (
                <Button
                  key="edit"
                  {...rowActionKind('update')}
                  onClick={() => {
                    setEditing(row);
                    setOpen(true);
                    setTimeout(() => {
                      void fillEditForm(row);
                    }, 0);
                  }}
                />
              ) : null,
              canUpdate && row.status === 'effective' ? (
                <Button
                  key="revise"
                  {...rowActionDrawingNewRevision('skip')}
                  onClick={async () => {
                    await qualityQmsApi.systemDocuments.revise(row.id, {});
                    messageApi.success(t('app.kuaizhizao.quality.qms.messages.reviseSuccess'));
                    focusLifecycle('pending');
                    actionRef.current?.reload();
                  }}
                />
              ) : null,
              canSubmit && (row.status === 'draft' || row.status === 'rejected') ? (
                <Button
                  key="submit"
                  {...rowActionKind('submit')}
                  onClick={async () => {
                    await qualityQmsApi.systemDocuments.submit(row.id);
                    messageApi.success(t('app.kuaizhizao.quality.qms.messages.submitSuccess'));
                    focusLifecycle('pending');
                    actionRef.current?.reload();
                  }}
                />
              ) : null,
              canPublish && row.status === 'draft' ? (
                <Button
                  key="publish"
                  {...rowActionKind('execute')}
                  {...rowActionLabelKeep()}
                  onClick={async () => {
                    await qualityQmsApi.systemDocuments.publish(row.id);
                    messageApi.success(t('app.kuaizhizao.quality.qms.messages.publishSuccess'));
                    focusLifecycle('formal');
                    actionRef.current?.reload();
                  }}
                >
                  {t('app.kuaizhizao.quality.qms.actions.publish')}
                </Button>
              ) : null,
              canReject && (row.status === 'draft' || row.status === 'pending') ? (
                <Button
                  key="reject"
                  {...rowActionKind('reject')}
                  onClick={async () => {
                    await qualityQmsApi.systemDocuments.reject(row.id, {});
                    messageApi.success(t('app.kuaizhizao.quality.qms.messages.rejectSuccess'));
                    actionRef.current?.reload();
                  }}
                />
              ) : null,
              canObsolete && row.status === 'effective' ? (
                <Button
                  key="obsolete"
                  {...rowActionKind('obsolete')}
                  onClick={async () => {
                    await qualityQmsApi.systemDocuments.obsolete(row.id);
                    messageApi.success(t('app.kuaizhizao.quality.qms.messages.obsoleteSuccess'));
                    focusLifecycle('obsolete');
                    actionRef.current?.reload();
                  }}
                />
              ) : null,
            ],
          },
        ],
        GLOBAL_DOC_LIST_FIELD_RANK,
      );
  }, [
      canObsolete,
      canPublish,
      canSubmit,
      canReject,
      canUpdate,
      fillEditForm,
      generateSystemDocCustomFieldColumns,
      messageApi,
      openDetail,
      openVersionHistory,
      statusEnum,
      systemDocListCustomFields,
      t,
      typeEnum,
      hideStatusInSearch,
      nav.dimension,
      focusLifecycle,
      standardValueEnum,
    ]);

  return (
    <PermissionGuard
      permission="kuaizhizao:quality-management-system-documents:read"
      fallback={<Empty description={t('app.kuaizhizao.quality.qms.noPermission')} style={{ marginTop: 120 }} />}
    >
      <TwoColumnLayout
        layoutPersistenceId="apps.kuaizhizao.pages.quality-management.system-documents-nav"
        leftPanel={{
          width: 280,
          minWidth: 248,
          maxWidth: 360,
          leftContent: (
            <SystemDocumentNavTree
              dimension={nav.dimension}
              selectedKey={nav.selectedKey}
              standards={standardNavItems}
              onDimensionChange={(dimension, selectedKey) => updateNav(dimension, selectedKey)}
              onSelectKey={(selectedKey) => updateNav(nav.dimension, selectedKey)}
            />
          ),
        }}
        rightPanel={{
          header: (
            <Breadcrumb
              items={[
                { title: t('app.kuaizhizao.menu.quality-management.system-documents') },
                { title: navBreadcrumbTitle },
              ]}
            />
          ),
          content: (
            <>
              {reviewDueSummary && reviewDueSummary.due_count > 0 ? (
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginBottom: 16 }}
                  title={t('app.kuaizhizao.quality.qms.reviewDueBanner', {
                    count: reviewDueSummary.due_count,
                  })}
                />
              ) : null}
              <UniTable<QmsSystemDocument>
          viewTypes={['table', 'help']}
          helpViewConfig={buildListPageHelpViewConfig('kuaizhizao.systemDocuments')}
          headerTitle={t('app.kuaizhizao.menu.quality-management.system-documents')}
          actionRef={actionRef}
          rowKey="id"
          columns={columns}
          showAdvancedSearch
          columnPersistenceId="apps.kuaizhizao.pages.quality-management.system-documents-cf-v1"
          skipFuzzyPinyinClientFilter
          params={{ navDimension: nav.dimension, navKey: nav.selectedKey }}
          toolBarRender={() =>
            canCreate
              ? [
                  <Button key="add" type="primary" onClick={openCreate}>
                    {withSingleNewShortcutHint(t('app.kuaizhizao.quality.qms.createDocument'))}
                  </Button>,
                ]
              : []
          }
          enableRowSelection={canDelete}
          showDeleteButton={canDelete}
          deleteButtonText={t('common.delete')}
          onTableDataChange={(rows) => {
            tableRowsRef.current = rows;
          }}
          onDelete={async (keys) => {
            const keySet = new Set(keys.map((k) => Number(k)));
            const deletable = tableRowsRef.current.filter(
              (row) => keySet.has(row.id) && row.status !== 'effective',
            );
            if (deletable.length === 0) {
              messageApi.warning(t('app.kuaizhizao.quality.qms.messages.batchDeleteEmpty'));
              return;
            }
            await Promise.all(
              deletable.map((row) => qualityQmsApi.systemDocuments.delete(row.id)),
            );
            messageApi.success(t('common.batchDeleteSuccess', { count: deletable.length }));
            actionRef.current?.reload();
          }}
          request={async (params, _sort, _filter, searchFormValues, meta) => {
            const pageSize = params.pageSize || 20;
            const skip = ((params.current || 1) - 1) * pageSize;
            const standardIdRaw = pickSearchString(searchFormValues, 'standard_id');
            const searchDocType = pickSearchString(searchFormValues, 'doc_type');
            const searchStatus = pickSearchString(searchFormValues, 'status');
            const res = await qualityQmsApi.systemDocuments.list({
              skip,
              limit: pageSize,
              keyword: pickListSearchKeyword(searchFormValues),
              status: navListParams.status ?? searchStatus ?? undefined,
              status_in: navListParams.status_in,
              doc_type: navListParams.doc_type ?? searchDocType ?? undefined,
              standard_id:
                navListParams.standard_id ??
                (standardIdRaw != null && Number.isFinite(Number(standardIdRaw))
                  ? Number(standardIdRaw)
                  : undefined),
              standard_id_null: navListParams.standard_id_null,
              zone: navListParams.zone ?? 'all',
              review_due: navListParams.review_due,
            });
            const rows = res.items || [];
            const enriched =
              meta?.purpose === 'prefetch'
                ? rows
                : await enrichSystemDocRecordsWithCustomFields(rows);
            return { success: true, data: enriched, total: res.total || 0 };
          }}
        />
            </>
          ),
        }}
      />

        <Modal
          title={
            historyDoc
              ? t('app.kuaizhizao.quality.qms.versionHistoryTitle', {
                  code: historyDoc.document_code,
                })
              : t('app.kuaizhizao.quality.qms.actions.versionHistory')
          }
          open={historyOpen}
          onCancel={() => {
            setHistoryOpen(false);
            setHistoryDoc(null);
            setHistoryRows([]);
          }}
          footer={null}
          width={MODAL_CONFIG.LARGE_WIDTH}
          destroyOnHidden
        >
          {canSeeFullHistoryHint ? (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              title={t('app.kuaizhizao.quality.qms.versionHistoryGlobalHint')}
            />
          ) : (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              title={t('app.kuaizhizao.quality.qms.versionHistoryConsumerHint', {
                audience: historyAudience || '-',
              })}
            />
          )}
          <Table
            size="small"
            loading={historyLoading}
            rowKey="id"
            pagination={false}
            dataSource={historyRows}
            locale={{ emptyText: t('app.kuaizhizao.salesOrder.emptyItems') }}
            columns={[
              { title: t('app.kuaizhizao.quality.qms.version'), dataIndex: 'version', width: 90 },
              {
                title: t('common.status'),
                dataIndex: 'status',
                width: 110,
                render: (v: string) => statusEnum[v]?.text || v,
              },
              {
                title: t('app.kuaizhizao.quality.qms.changeSummary'),
                dataIndex: 'change_summary',
                ellipsis: true,
              },
              {
                title: t('app.kuaizhizao.quality.qms.createdBy'),
                dataIndex: 'created_by_name',
                width: 100,
              },
              {
                title: t('app.kuaizhizao.quality.qms.effectiveAt'),
                dataIndex: 'effective_at',
                width: 160,
                render: (v) => formatDateTimeBySiteSetting(v) || '-',
              },
            ]}
          />
        </Modal>

        <SystemDocumentDetailDrawer
          open={detailOpen}
          document={detailDoc}
          loading={detailLoading}
          error={detailError}
          onRetry={() => {
            if (detailIdRef.current != null) void loadDetail(detailIdRef.current);
          }}
          onClose={() => {
            setDetailOpen(false);
            setDetailDoc(null);
            setDetailError(null);
            detailIdRef.current = null;
            resetSystemDocDetailFieldValues();
          }}
          canUpdate={canUpdate}
          onEdit={openEditFromDetail}
          standardLabel={(id) =>
            id != null && standardValueEnum[id]?.text ? String(standardValueEnum[id].text) : ''
          }
          customFields={systemDocListCustomFields}
          customFieldValues={systemDocDetailCustomFieldValues}
        />

        <SystemDocumentCirculationModal
          open={circulationDoc != null}
          document={circulationDoc}
          canUpdate={canUpdate}
          onClose={() => setCirculationDoc(null)}
          onChanged={() => actionRef.current?.reload()}
        />

        <FormModalTemplate
          title={
            editing
              ? t('app.kuaizhizao.quality.qms.editDocument')
              : t('app.kuaizhizao.quality.qms.createDocument')
          }
          open={open}
          width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
          grid={false}
          formRef={formRef}
          onClose={() => {
            setOpen(false);
            setEditing(null);
            resetSystemDocFormFieldValues();
          }}
          onFinish={async (values) => {
            try {
              const { customData, standardValues } = extractSystemDocFormValues(values);
              const payload = {
                ...standardValues,
                evidence_links: parseEvidenceLinksText(standardValues.evidence_links_text),
                training_refs: parseEvidenceLinksText(standardValues.training_refs_text),
                attachments: normalizeDocumentAttachments(standardValues.attachments),
              };
              delete (payload as any).evidence_links_text;
              delete (payload as any).training_refs_text;
              if (editing?.id) {
                await qualityQmsApi.systemDocuments.update(editing.id, payload);
                await saveSystemDocCustomFieldValues(editing.id, customData);
              } else {
                const created = await qualityQmsApi.systemDocuments.create(payload);
                if (created?.id != null) {
                  await saveSystemDocCustomFieldValues(created.id, customData);
                }
                focusLifecycle('pending');
              }
              messageApi.success(t('common.saveSuccess'));
              setOpen(false);
              resetSystemDocFormFieldValues();
              actionRef.current?.reload();
              return true;
            } catch (e: any) {
              if (e?.message === EVIDENCE_LINKS_PARSE_INVALID_JSON) {
                messageApi.error(t('app.kuaizhizao.quality.qms.evidenceLinksInvalidJson'));
              } else {
                messageApi.error(e?.message || t('common.saveFailed'));
              }
              return false;
            }
          }}
        >
          <Row gutter={16}>
            <Col span={8}>
              <CodeField
                name="document_code"
                label={t('app.kuaizhizao.quality.qms.documentCode')}
                pageCode="kuaizhizao-quality-system-document"
                documentId={editing?.id}
              />
            </Col>
            <Col span={8}>
              <ProFormText name="title" label={t('app.kuaizhizao.quality.qms.title')} rules={[{ required: true }]} />
            </Col>
            <Col span={8}>
              <ProFormSelect
                name="doc_type"
                label={t('app.kuaizhizao.quality.qms.docTypeLabel')}
                options={QMS_DOC_TYPE_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
                rules={[{ required: true }]}
              />
            </Col>
            <Col span={8}>
              <ProFormText name="version" label={t('app.kuaizhizao.quality.qms.version')} rules={[{ required: true }]} />
            </Col>
            <Col span={8}>
              <ProFormSelect
                name="standard_id"
                label={t('app.kuaizhizao.quality.qms.applicableStandard')}
                options={(standardsEnvelope?.items ?? []).map((s) => ({
                  value: s.id,
                  label: `${s.code} ${s.name}`,
                }))}
              />
            </Col>
            <Col span={16}>
              <ProFormDependency name={['standard_id']}>
                {({ standard_id }) => (
                  <ProFormItem name="clause_ids" label={t('app.kuaizhizao.quality.qms.clauseLabel')}>
                    <QmsClauseSelect
                      standardId={standard_id as number | undefined}
                      multiple
                      disabled={!standard_id}
                    />
                  </ProFormItem>
                )}
              </ProFormDependency>
            </Col>
            <Col span={8}>
              <ProFormText name="owner_name" label={t('app.kuaizhizao.quality.qms.ownerName')} />
            </Col>
            <Col span={8}>
              <ProFormDateTimePicker name="next_review_at" label={t('app.kuaizhizao.quality.qms.nextReviewAt')} />
            </Col>
            <Col span={8}>
              <ProFormText name="file_url" label={t('app.kuaizhizao.quality.qms.fileUrl')} />
            </Col>
            <Col span={24}>
              <ProFormTextArea name="content" label={t('app.kuaizhizao.quality.qms.content')} fieldProps={{ rows: 3 }} />
            </Col>
            <Col span={24}>
              <ProFormTextArea
                name="evidence_links_text"
                label={t('app.kuaizhizao.quality.qms.evidenceLinks')}
                tooltip={t('app.kuaizhizao.quality.qms.evidenceLinksHint')}
                fieldProps={{ rows: 3 }}
              />
            </Col>
            <Col span={24}>
              <ProFormTextArea
                name="training_refs_text"
                label={t('app.kuaizhizao.quality.qms.trainingRefs')}
                tooltip={t('app.kuaizhizao.quality.qms.crossAppRefsHint')}
                fieldProps={{ rows: 2 }}
              />
            </Col>
            <CustomFieldsFormSection
              customFields={systemDocFormCustomFields}
              customFieldValues={systemDocFormCustomFieldValues}
              gridColumns={3}
              embedInParentRow
            />
            <Col span={24}>
              <ProFormTextArea name="remarks" label={t('common.remark')} fieldProps={{ rows: 2 }} />
            </Col>
            <Col span={24}>
              <DocumentAttachmentsField category="qms_system_document_attachments" />
            </Col>
          </Row>
        </FormModalTemplate>
    </PermissionGuard>
  );
};

export default SystemDocumentsPage;
