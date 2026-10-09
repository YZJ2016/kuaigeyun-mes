import React, { useEffect, useMemo, useState } from 'react';
import { Result, Spin } from 'antd';
import { Descriptions, Divider } from 'antd';
import type { ProColumns } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { MODAL_CONFIG } from '../../../../../components/layout-templates';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import KuaioaCrudListPage from '../../../components/KuaioaCrudListPage';
import FormRequestModalBody from '../../../components/FormRequestModalBody';
import { FormRequestCapabilitiesTags } from '../../../components/FormRequestCapabilitiesTags';
import FormRequestIssueModal from '../../../components/FormRequestIssueModal';
import FormRequestSalesReplyModal from '../../../components/FormRequestSalesReplyModal';
import {
  renderDynamicFieldReadonly,
  serializeDynamicFormValues,
  dynamicFormValuesFromRecord,
} from '../../../components/OaDynamicFormFields';
import {
  createFormRequest,
  deleteFormRequest,
  getFormRequest,
  getFormTemplateByCode,
  listFormRequests,
  updateFormRequest,
  type FormRequest,
  type FormTemplate,
} from '../../../services/forms';
import { normalizeFieldsSchema } from '../../../utils/oaFormSchema';
import { buildOaApprovalStatusEnum } from '../../../utils/oaFormEnums';
import { isFormRequestIssueScopedBusinessType } from '../../../utils/formRequestIssueScopedTypes';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../../utils/uniTableLayoutColumns';

function isCompleteMachineConfirmation(record: Record<string, unknown>): boolean {
  const formData =
    record.form_data && typeof record.form_data === 'object'
      ? (record.form_data as Record<string, unknown>)
      : {};
  return String(formData.confirmation_kind || '').trim() === 'complete_machine';
}

const MountedFormRequestsPage: React.FC = () => {
  const { t } = useTranslation();
  const perms = useResourcePermissions('kuaioa:form-request');
  const { templateCode = '' } = useParams<{ templateCode: string }>();
  const statusEnum = useMemo(() => buildOaApprovalStatusEnum(t), [t]);
  const [template, setTemplate] = useState<FormTemplate | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [issueOpen, setIssueOpen] = useState(false);
  const [issueTarget, setIssueTarget] = useState<FormRequest | null>(null);
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyTarget, setReplyTarget] = useState<FormRequest | null>(null);
  const [tableReloadToken, setTableReloadToken] = useState(0);

  useEffect(() => {
    if (!templateCode) return;
    void getFormTemplateByCode(templateCode)
      .then((row) => {
        setTemplate(row);
        setLoadError(null);
      })
      .catch((error: { message?: string }) => {
        setTemplate(null);
        setLoadError(error?.message || t('common.operationFailed'));
      });
  }, [t, templateCode]);

  const schema = useMemo(
    () => normalizeFieldsSchema(template?.fields_schema),
    [template?.fields_schema],
  );

  const issueScoped = isFormRequestIssueScopedBusinessType(template?.business_type);
  const isConfirmationTemplate = template?.business_type === 'confirmation';
  const isReviewSheetTemplate = template?.business_type === 'review_sheet';
  const isMaterialIssueTemplate = template?.business_type === 'material_issue';
  const capabilitiesWide =
    isConfirmationTemplate || isReviewSheetTemplate || isMaterialIssueTemplate;

  const listExtraColumns = useMemo((): ProColumns<Record<string, unknown>>[] | undefined => {
    if (!issueScoped) return undefined;
    return [
      {
        title: t('app.kuaioa.formRequest.capabilitiesColumn'),
        dataIndex: 'capabilities',
        key: 'capabilities',
        ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
        width: capabilitiesWide ? 360 : 280,
        minWidth: capabilitiesWide ? 320 : 240,
        uniTableKeepWidth: true,
        hideInSearch: true,
        render: (_, row) => (
          <FormRequestCapabilitiesTags
            capabilities={row.capabilities as FormRequest['capabilities']}
            showResponded={isConfirmationTemplate}
            showCountersignSelected={isReviewSheetTemplate || isMaterialIssueTemplate}
          />
        ),
      },
    ];
  }, [
    issueScoped,
    isConfirmationTemplate,
    isReviewSheetTemplate,
    isMaterialIssueTemplate,
    capabilitiesWide,
    t,
  ]);

  if (loadError) {
    return <Result status="404" title={loadError} />;
  }

  if (!template) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spin description={t('app.kuaioa.common.loading')} />
      </div>
    );
  }

  return (
    <>
      <KuaioaCrudListPage
        reloadSignal={tableReloadToken}
        createButtonKey="app.kuaioa.formRequest.createButton"
        resource="kuaioa:form-request"
        codeField="request_code"
        nameField="title"
        autoGenerateCode
        modalWidth={MODAL_CONFIG.STANDARD_WIDTH}
        statusEnum={statusEnum}
        statusPresentation="lifecycle"
        detailVariant="approval"
        getDetailFn={getFormRequest}
        auditWorkflow={{
          entityType: 'kuaioa_form_request',
          resourcePrefix: 'kuaioa:form-request',
          auditNodeKey: 'kuaioa_form_request',
          entityNameKey: 'app.kuaioa.formRequest.entityName',
        }}
        listExtraColumns={listExtraColumns}
        fields={[
          { name: 'request_code', labelKey: 'app.kuaioa.formRequest.code', width: 150 },
          { name: 'title', labelKey: 'app.kuaioa.formRequest.title', required: true, width: 200 },
          { name: 'applicant_name', labelKey: 'app.kuaioa.common.applicant', width: 100 },
          { name: 'department_name', labelKey: 'app.kuaioa.common.department', hideInTable: true },
          { name: 'status', labelKey: 'common.status', width: 100 },
          { name: 'notes', labelKey: 'common.remark', hideInTable: true, type: 'textarea' },
        ]}
        listFn={(params) =>
          listFormRequests({
            ...params,
            template_id: template.id,
          })
        }
        createFn={createFormRequest}
        updateFn={updateFormRequest}
        deleteFn={deleteFormRequest}
        mapRecordToFormValues={(record) => ({
          template_id: template.id,
          title: record.title,
          department_name: record.department_name,
          notes: record.notes,
          ...dynamicFormValuesFromRecord(schema, record),
        })}
        mapFormValuesToPayload={(values) => ({
          template_id: template.id,
          title: values.title,
          department_name: values.department_name,
          notes: values.notes,
          form_data: serializeDynamicFormValues(schema, values),
        })}
        renderModalBody={(form, editing) => (
          <FormRequestModalBody
            form={form}
            editing={editing}
            templates={[template]}
            hideTemplateSelect
            fixedTemplateId={template.id}
          />
        )}
        extraActions={
          issueScoped
            ? [
                {
                  key: 'sales-reply',
                  labelKey: 'app.kuaioa.formRequest.actions.salesReply',
                  deferSuccess: true,
                  visible: (record) => {
                    if (!isConfirmationTemplate || !perms.canApprove) return false;
                    if (String(record.status || '').toLowerCase() !== 'pending') return false;
                    if (!isCompleteMachineConfirmation(record)) return false;
                    const cap = record.capabilities as FormRequest['capabilities'] | undefined;
                    return !cap?.responded;
                  },
                  onClick: (record) => {
                    setReplyTarget(record as FormRequest);
                    setReplyOpen(true);
                  },
                },
                {
                  key: 'issue',
                  labelKey: 'app.kuaioa.formRequest.actions.issue',
                  requireUpdate: true,
                  deferSuccess: true,
                  visible: (record) =>
                    String(record.status || '').toLowerCase() === 'approved',
                  onClick: (record) => {
                    setIssueTarget(record as FormRequest);
                    setIssueOpen(true);
                  },
                },
              ]
            : []
        }
        renderDetailExtra={(record) => {
          const blocks: React.ReactNode[] = [];
          if (issueScoped && record.capabilities) {
            blocks.push(
              <div key="caps">
                <Divider orientation="horizontal">{t('app.kuaioa.formRequest.capabilitiesColumn')}</Divider>
                <FormRequestCapabilitiesTags
                  capabilities={record.capabilities as FormRequest['capabilities']}
                  showResponded={isConfirmationTemplate}
                />
              </div>,
            );
          }
          if (!schema.length) return blocks.length ? <>{blocks}</> : null;
          const formData =
            record.form_data && typeof record.form_data === 'object'
              ? (record.form_data as Record<string, unknown>)
              : {};
          const cap = record.capabilities as FormRequest['capabilities'] | undefined;
          blocks.push(
            <React.Fragment key="form">
              <Divider orientation="horizontal">{t('app.kuaioa.formRequest.formData')}</Divider>
              <Descriptions
                column={2}
                size="small"
                items={schema.map((field) => ({
                  key: field.name,
                  label: field.label,
                  children:
                    field.type === 'file' && cap && !cap.can_download
                      ? t('app.kuaioa.formRequest.downloadDenied')
                      : renderDynamicFieldReadonly(field, formData[field.name]),
                }))}
              />
            </React.Fragment>,
          );
          return <>{blocks}</>;
        }}
      />
      <FormRequestIssueModal
        open={issueOpen}
        target={issueTarget}
        onClose={() => {
          setIssueOpen(false);
          setIssueTarget(null);
        }}
        onSuccess={() => setTableReloadToken((n) => n + 1)}
      />
      <FormRequestSalesReplyModal
        open={replyOpen}
        target={replyTarget}
        onClose={() => {
          setReplyOpen(false);
          setReplyTarget(null);
        }}
        onSuccess={() => setTableReloadToken((n) => n + 1)}
      />
    </>
  );
};

export default MountedFormRequestsPage;
