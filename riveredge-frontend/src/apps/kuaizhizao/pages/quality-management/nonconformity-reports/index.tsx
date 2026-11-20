import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActionType,
  ProColumns,
  ProFormDatePicker,
  ProFormItem,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { App, Button, Col, Empty, Row } from 'antd';
import { useTranslation } from 'react-i18next';
import CodeField from '../../../../../components/code-field';
import { UniTable } from '../../../../../components/uni-table';
import { rowActionKind } from '../../../../../components/uni-action';
import { FormModalTemplate, ListPageTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import PermissionGuard from '../../../../../components/permission/PermissionGuard';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useNewShortcut } from '../../../../../hooks/useNewShortcut';
import { withSingleNewShortcutHint } from '../../../../../utils/globalNewShortcut';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { formatBusinessDateOnly } from '../../../../../utils/format';
import { renderDocumentStatusTag } from '../../../../../utils/documentLifecycleStatusTag';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { pickListSearchKeyword, pickSearchString } from '../../../../../utils/tableQueryKey';
import { qualityQmsApi, QmsNonconformityReport } from '../../../services/quality-qms';
import QmsClauseSelect from '../qms/QmsClauseSelect';
import {
  QMS_NC_SEVERITY_OPTIONS,
  QMS_NC_SOURCE_OPTIONS,
  QMS_NC_STATUS_OPTIONS,
} from '../qms/qmsMeta';

const RESOURCE = 'kuaizhizao:quality-management-nonconformity-reports';

const NonconformityReportsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const actionRef = useRef<ActionType>(null);
  const formRef = useRef<any>(null);
  const tableRowsRef = useRef<QmsNonconformityReport[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<QmsNonconformityReport | null>(null);
  const { canCreate, canUpdate, canDelete, canAction } = useResourcePermissions(RESOURCE);
  const { canCreate: canCreateCa } = useResourcePermissions(
    'kuaizhizao:quality-management-corrective-actions',
  );
  const canClose = !!canAction?.('close');

  const statusEnum = useMemo(
    () => Object.fromEntries(QMS_NC_STATUS_OPTIONS.map((o) => [o.value, { text: t(o.labelKey) }])),
    [t],
  );
  const severityEnum = useMemo(
    () => Object.fromEntries(QMS_NC_SEVERITY_OPTIONS.map((o) => [o.value, { text: t(o.labelKey) }])),
    [t],
  );
  const sourceEnum = useMemo(
    () => Object.fromEntries(QMS_NC_SOURCE_OPTIONS.map((o) => [o.value, { text: t(o.labelKey) }])),
    [t],
  );

  const openCreate = useCallback(() => {
    setEditing(null);
    setOpen(true);
    setTimeout(() => {
      formRef.current?.resetFields();
      formRef.current?.setFieldsValue({
        status: 'open',
        source_type: 'internal_audit',
        severity: 'general',
      });
    }, 0);
  }, []);
  useNewShortcut(() => {
    if (canCreate) openCreate();
  });

  const columns: ProColumns<QmsNonconformityReport>[] = useMemo(
    () =>
      alignProColumns(
        [
          {
            title: t('app.kuaizhizao.quality.qms.ncReportCode'),
            dataIndex: 'report_code',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            copyable: true,
            hideInSearch: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.ncFact'),
            dataIndex: 'fact',
            minWidth: 220,
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
            title: t('app.kuaizhizao.quality.qms.ncSource.label'),
            dataIndex: 'source_type',
            width: 110,
            minWidth: 110,
            uniTableKeepWidth: true,
            resizable: false,
            valueEnum: sourceEnum,
          },
          {
            title: t('app.kuaizhizao.quality.qms.ncSource.code'),
            dataIndex: 'source_code',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.clauseLabel'),
            dataIndex: 'clause_label',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            ellipsis: true,
            render: (_, row) => row.clause_label || '-',
          },
          {
            title: t('app.kuaizhizao.quality.qms.ncSeverity.label'),
            dataIndex: 'severity',
            width: 88,
            minWidth: 88,
            uniTableKeepWidth: true,
            resizable: false,
            valueEnum: severityEnum,
            render: (_, row) => (
              <MarkerTag color={row.severity === 'severe' ? 'error' : 'default'}>
                {severityEnum[row.severity]?.text || row.severity}
              </MarkerTag>
            ),
          },
          {
            title: t('app.kuaizhizao.quality.qms.ncDueOn'),
            dataIndex: 'due_on',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => formatBusinessDateOnly(row.due_on) || '-',
          },
          {
            title: t('common.status'),
            key: 'lifecycle',
            dataIndex: 'status',
            fixed: 'right',
            valueEnum: statusEnum,
            render: (_, row) =>
              renderDocumentStatusTag(
                statusEnum[row.status]?.text || row.status || '-',
                row.status || undefined,
              ),
          },
          {
            title: t('common.actions'),
            key: 'option',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) => [
              canUpdate ? (
                <Button
                  key="edit"
                  {...rowActionKind('update')}
                  onClick={() => {
                    setEditing(row);
                    setOpen(true);
                    setTimeout(() => formRef.current?.setFieldsValue(row), 0);
                  }}
                />
              ) : null,
              canCreateCa &&
              row.status !== 'closed' &&
              row.severity !== 'observation' &&
              !row.capa_code ? (
                <Button
                  key="gen-ca"
                  type="link"
                  size="small"
                  onClick={async () => {
                    try {
                      await qualityQmsApi.correctiveActions.fromSource({
                        source_type: 'nonconformity_report',
                        source_id: row.id,
                        problem_summary: row.fact,
                        cause: row.cause || undefined,
                        correction: row.correction || undefined,
                        due_on: row.due_on || undefined,
                      });
                      messageApi.success(t('app.kuaizhizao.quality.qms.messages.caCreatedFromSource'));
                      actionRef.current?.reload();
                    } catch (e: any) {
                      messageApi.error(e?.message || t('common.saveFailed'));
                    }
                  }}
                >
                  {t('app.kuaizhizao.quality.qms.actions.generateCa')}
                </Button>
              ) : null,
              canClose && row.status !== 'closed' ? (
                <Button
                  key="close"
                  {...rowActionKind('close')}
                  onClick={async () => {
                    if (!row.verification_conclusion) {
                      messageApi.warning(t('app.kuaizhizao.quality.qms.messages.ncCloseNeedVerify'));
                      setEditing(row);
                      setOpen(true);
                      setTimeout(() => formRef.current?.setFieldsValue(row), 0);
                      return;
                    }
                    if (
                      (row.severity === 'severe' || row.severity === 'general') &&
                      !row.capa_code
                    ) {
                      messageApi.warning(t('app.kuaizhizao.quality.qms.messages.ncCloseNeedCa'));
                      return;
                    }
                    await qualityQmsApi.nonconformityReports.close(row.id, {
                      verification_conclusion: row.verification_conclusion,
                      verifier_name: row.verifier_name,
                      verified_on: row.verified_on,
                    });
                    messageApi.success(t('app.kuaizhizao.quality.qms.messages.ncClosed'));
                    actionRef.current?.reload();
                  }}
                >
                  {t('app.kuaizhizao.quality.qms.actions.closeNc')}
                </Button>
              ) : null,
            ],
          },
        ],
        GLOBAL_DOC_LIST_FIELD_RANK,
      ),
    [canClose, canCreateCa, canUpdate, messageApi, severityEnum, sourceEnum, statusEnum, t],
  );

  return (
    <PermissionGuard
      permission="kuaizhizao:quality-management-nonconformity-reports:read"
      fallback={<Empty description={t('app.kuaizhizao.quality.qms.noPermission')} style={{ marginTop: 120 }} />}
    >
      <ListPageTemplate>
        <UniTable<QmsNonconformityReport>
          headerTitle={t('app.kuaizhizao.menu.quality-management.nonconformity-reports')}
          actionRef={actionRef}
          rowKey="id"
          columns={columns}
          showAdvancedSearch
          columnPersistenceId="apps.kuaizhizao.pages.quality-management.nonconformity-reports-width-v1"
          skipFuzzyPinyinClientFilter
          toolBarRender={() =>
            canCreate
              ? [
                  <Button key="add" type="primary" onClick={openCreate}>
                    {withSingleNewShortcutHint(t('app.kuaizhizao.quality.qms.createNcReport'))}
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
            await Promise.all(
              keys.map((key) => qualityQmsApi.nonconformityReports.delete(Number(key))),
            );
            messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
            actionRef.current?.reload();
          }}
          request={async (params, _sort, _filter, searchFormValues) => {
            const pageSize = params.pageSize || 20;
            const skip = ((params.current || 1) - 1) * pageSize;
            const res = await qualityQmsApi.nonconformityReports.list({
              skip,
              limit: pageSize,
              keyword: pickListSearchKeyword(searchFormValues),
              status: pickSearchString(searchFormValues, 'status'),
              source_type: pickSearchString(searchFormValues, 'source_type'),
            });
            return { success: true, data: res.items || [], total: res.total || 0 };
          }}
        />

        <FormModalTemplate
          title={
            editing
              ? t('app.kuaizhizao.quality.qms.editNcReport')
              : t('app.kuaizhizao.quality.qms.createNcReport')
          }
          open={open}
          width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
          grid={false}
          formRef={formRef}
          onClose={() => {
            setOpen(false);
            setEditing(null);
          }}
          onFinish={async (values) => {
            try {
              const payload = { ...values };
              if (editing?.id) {
                const locked =
                  editing.source_type === 'internal_audit' && editing.checklist_item_id != null;
                if (locked) {
                  delete payload.source_type;
                  delete payload.source_id;
                  delete payload.source_code;
                  delete payload.clause_id;
                }
                if (payload.status === 'closed') {
                  await qualityQmsApi.nonconformityReports.close(editing.id, payload);
                } else {
                  await qualityQmsApi.nonconformityReports.update(editing.id, payload);
                }
              } else {
                await qualityQmsApi.nonconformityReports.create(payload);
              }
              messageApi.success(t('common.saveSuccess'));
              setOpen(false);
              actionRef.current?.reload();
              return true;
            } catch (e: any) {
              messageApi.error(e?.message || t('common.saveFailed'));
              return false;
            }
          }}
        >
          <Row gutter={16}>
            <Col span={8}>
              <CodeField
                name="report_code"
                label={t('app.kuaizhizao.quality.qms.ncReportCode')}
                pageCode="kuaizhizao-quality-nonconformity-report"
                documentId={editing?.id}
              />
            </Col>
            <Col span={8}>
              <ProFormSelect
                name="source_type"
                label={t('app.kuaizhizao.quality.qms.ncSource.label')}
                options={QMS_NC_SOURCE_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
                rules={[{ required: true }]}
                disabled={!!editing?.checklist_item_id}
              />
            </Col>
            <Col span={8}>
              <ProFormText
                name="source_code"
                label={t('app.kuaizhizao.quality.qms.ncSource.code')}
                disabled={!!editing?.checklist_item_id}
              />
            </Col>
            <Col span={8}>
              <ProFormSelect
                name="severity"
                label={t('app.kuaizhizao.quality.qms.ncSeverity.label')}
                options={QMS_NC_SEVERITY_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
                rules={[{ required: true }]}
              />
            </Col>
            <Col span={8}>
              <ProFormSelect
                name="status"
                label={t('common.status')}
                options={QMS_NC_STATUS_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
                rules={[{ required: true }]}
              />
            </Col>
            <Col span={8}>
              <ProFormText name="responsible_dept" label={t('app.kuaizhizao.quality.qms.ncResponsibleDept')} />
            </Col>
            <Col span={12}>
              <ProFormItem name="clause_id" label={t('app.kuaizhizao.quality.qms.clauseLabel')}>
                <QmsClauseSelect disabled={!!editing?.checklist_item_id} />
              </ProFormItem>
            </Col>
            <Col span={12}>
              <ProFormDatePicker name="due_on" label={t('app.kuaizhizao.quality.qms.ncDueOn')} />
            </Col>
            <Col span={24}>
              <ProFormTextArea
                name="fact"
                label={t('app.kuaizhizao.quality.qms.ncFact')}
                rules={[{ required: true }]}
                fieldProps={{ rows: 3 }}
              />
            </Col>
            <Col span={24}>
              <ProFormTextArea name="cause" label={t('app.kuaizhizao.quality.qms.ncCause')} fieldProps={{ rows: 2 }} />
            </Col>
            <Col span={24}>
              <ProFormTextArea
                name="correction"
                label={t('app.kuaizhizao.quality.qms.ncCorrection')}
                fieldProps={{ rows: 2 }}
              />
            </Col>
            <Col span={24}>
              <ProFormTextArea
                name="corrective_action"
                label={t('app.kuaizhizao.quality.qms.ncCorrectiveAction')}
                fieldProps={{ rows: 2 }}
              />
            </Col>
            <Col span={8}>
              <ProFormText name="verifier_name" label={t('app.kuaizhizao.quality.qms.ncVerifier')} />
            </Col>
            <Col span={8}>
              <ProFormDatePicker name="verified_on" label={t('app.kuaizhizao.quality.qms.ncVerifiedOn')} />
            </Col>
            <Col span={24}>
              <ProFormTextArea
                name="verification_conclusion"
                label={t('app.kuaizhizao.quality.qms.ncVerificationConclusion')}
                fieldProps={{ rows: 2 }}
              />
            </Col>
            <Col span={12}>
              <ProFormText
                name="capa_code"
                label={t('app.kuaizhizao.quality.qms.ncCapaCode')}
                disabled
              />
            </Col>
            <Col span={24}>
              <ProFormTextArea name="remarks" label={t('common.remark')} fieldProps={{ rows: 2 }} />
            </Col>
          </Row>
        </FormModalTemplate>
      </ListPageTemplate>
    </PermissionGuard>
  );
};

export default NonconformityReportsPage;
