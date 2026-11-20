import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActionType,
  ProColumns,
  ProFormDatePicker,
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
import { ThemedSegmented } from '../../../../../components/themed-segmented';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { formatBusinessDateOnly } from '../../../../../utils/format';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { pickListSearchKeyword, pickSearchString } from '../../../../../utils/tableQueryKey';
import {
  qualityQmsApi,
  QmsCertificate,
  QmsExternalAudit,
} from '../../../services/quality-qms';
import {
  QMS_CERTIFICATE_STATUS_OPTIONS,
  QMS_EXTERNAL_AUDIT_TYPE_OPTIONS,
  QMS_NC_SEVERITY_OPTIONS,
} from '../qms/qmsMeta';

const RESOURCE = 'kuaizhizao:quality-management-external-audits';
const NC_RESOURCE = 'kuaizhizao:quality-management-nonconformity-reports';

type ViewMode = 'audits' | 'certificates';

const ExternalAuditsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const auditActionRef = useRef<ActionType>(null);
  const certActionRef = useRef<ActionType>(null);
  const auditFormRef = useRef<any>(null);
  const certFormRef = useRef<any>(null);
  const ncFormRef = useRef<any>(null);
  const auditRowsRef = useRef<QmsExternalAudit[]>([]);
  const certRowsRef = useRef<QmsCertificate[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>('audits');
  const [auditOpen, setAuditOpen] = useState(false);
  const [certOpen, setCertOpen] = useState(false);
  const [ncOpen, setNcOpen] = useState(false);
  const [editingAudit, setEditingAudit] = useState<QmsExternalAudit | null>(null);
  const [editingCert, setEditingCert] = useState<QmsCertificate | null>(null);
  const [ncSource, setNcSource] = useState<QmsExternalAudit | null>(null);
  const { canCreate, canUpdate, canDelete } = useResourcePermissions(RESOURCE);
  const { canCreate: canCreateNc } = useResourcePermissions(NC_RESOURCE);

  const auditTypeEnum = useMemo(
    () =>
      Object.fromEntries(
        QMS_EXTERNAL_AUDIT_TYPE_OPTIONS.map((o) => [o.value, { text: t(o.labelKey) }]),
      ),
    [t],
  );
  const certStatusEnum = useMemo(
    () =>
      Object.fromEntries(QMS_CERTIFICATE_STATUS_OPTIONS.map((o) => [o.value, { text: t(o.labelKey) }])),
    [t],
  );

  const openCreateAudit = useCallback(() => {
    setEditingAudit(null);
    setAuditOpen(true);
    setTimeout(() => {
      auditFormRef.current?.resetFields();
      auditFormRef.current?.setFieldsValue({ audit_type: 'surveillance' });
    }, 0);
  }, []);
  const openCreateCert = useCallback(() => {
    setEditingCert(null);
    setCertOpen(true);
    setTimeout(() => {
      certFormRef.current?.resetFields();
    }, 0);
  }, []);
  useNewShortcut(() => {
    if (!canCreate) return;
    if (viewMode === 'audits') openCreateAudit();
    else openCreateCert();
  });

  const auditColumns: ProColumns<QmsExternalAudit>[] = useMemo(
    () =>
      alignProColumns(
        [
          {
            title: t('app.kuaizhizao.quality.qms.externalAuditCode'),
            dataIndex: 'audit_code',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            copyable: true,
            hideInSearch: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.externalBodyName'),
            dataIndex: 'body_name',
            minWidth: 160,
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
            title: t('app.kuaizhizao.quality.qms.externalAuditType.label'),
            dataIndex: 'audit_type',
            width: 100,
            minWidth: 100,
            uniTableKeepWidth: true,
            resizable: false,
            valueEnum: auditTypeEnum,
          },
          {
            title: t('app.kuaizhizao.quality.qms.externalPlannedOn'),
            dataIndex: 'planned_on',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => formatBusinessDateOnly(row.planned_on) || '-',
          },
          {
            title: t('app.kuaizhizao.quality.qms.externalActualOn'),
            dataIndex: 'actual_on',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => formatBusinessDateOnly(row.actual_on) || '-',
          },
          {
            title: t('app.kuaizhizao.quality.qms.externalOpenNcCount'),
            dataIndex: 'open_nc_count',
            width: 100,
            minWidth: 100,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => {
              const count = row.open_nc_count || 0;
              if (count > 0) return <MarkerTag color="warning">{count}</MarkerTag>;
              return count;
            },
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
                    setEditingAudit(row);
                    setAuditOpen(true);
                    setTimeout(() => auditFormRef.current?.setFieldsValue(row), 0);
                  }}
                />
              ) : null,
              canCreateNc ? (
                <Button
                  key="nc"
                  type="link"
                  size="small"
                  onClick={() => {
                    setNcSource(row);
                    setNcOpen(true);
                    setTimeout(() => {
                      ncFormRef.current?.resetFields();
                      ncFormRef.current?.setFieldsValue({
                        severity: 'general',
                        source_type: 'external_audit',
                        source_id: row.id,
                        source_code: row.audit_code,
                      });
                    }, 0);
                  }}
                >
                  {t('app.kuaizhizao.quality.qms.actions.createExternalNc')}
                </Button>
              ) : null,
            ],
          },
        ],
        GLOBAL_DOC_LIST_FIELD_RANK,
      ),
    [auditTypeEnum, canCreateNc, canUpdate, t],
  );

  const certColumns: ProColumns<QmsCertificate>[] = useMemo(
    () =>
      alignProColumns(
        [
          {
            title: t('app.kuaizhizao.quality.qms.certificateName'),
            dataIndex: 'name',
            minWidth: 160,
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
            title: t('app.kuaizhizao.quality.qms.certificateNo'),
            dataIndex: 'certificate_no',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            copyable: true,
            hideInSearch: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.certificateStandard'),
            dataIndex: 'standard_name',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => row.standard_name || '-',
          },
          {
            title: t('app.kuaizhizao.quality.qms.certificateIssuer'),
            dataIndex: 'issuer',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => row.issuer || '-',
          },
          {
            title: t('app.kuaizhizao.quality.qms.certificateExpireOn'),
            dataIndex: 'expire_on',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => formatBusinessDateOnly(row.expire_on) || '-',
          },
          {
            title: t('common.status'),
            key: 'lifecycle',
            dataIndex: 'status',
            fixed: 'right',
            valueEnum: certStatusEnum,
            render: (_, row) => {
              const color =
                row.status === 'expired' ? 'error' : row.status === 'expiring' ? 'warning' : 'success';
              return (
                <MarkerTag color={color}>
                  {certStatusEnum[row.status]?.text || row.status || '-'}
                </MarkerTag>
              );
            },
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
                    setEditingCert(row);
                    setCertOpen(true);
                    setTimeout(() => certFormRef.current?.setFieldsValue(row), 0);
                  }}
                />
              ) : null,
            ],
          },
        ],
        GLOBAL_DOC_LIST_FIELD_RANK,
      ),
    [canUpdate, certStatusEnum, t],
  );

  const segment = (
    <ThemedSegmented
      value={viewMode}
      onChange={(v) => setViewMode(v as ViewMode)}
      options={[
        { label: t('app.kuaizhizao.quality.qms.externalSegment.audits'), value: 'audits' },
        {
          label: t('app.kuaizhizao.quality.qms.externalSegment.certificates'),
          value: 'certificates',
        },
      ]}
    />
  );

  return (
    <PermissionGuard
      permission="kuaizhizao:quality-management-external-audits:read"
      fallback={<Empty description={t('app.kuaizhizao.quality.qms.noPermission')} style={{ marginTop: 120 }} />}
    >
      <ListPageTemplate>
        {viewMode === 'audits' ? (
          <UniTable<QmsExternalAudit>
            headerTitle={t('app.kuaizhizao.menu.quality-management.external-audits')}
            actionRef={auditActionRef}
            rowKey="id"
            columns={auditColumns}
            showAdvancedSearch
            columnPersistenceId="apps.kuaizhizao.pages.quality-management.external-audits-width-v1"
            skipFuzzyPinyinClientFilter
            beforeSearchButtons={segment}
            toolBarRender={() =>
              canCreate
                ? [
                    <Button key="add" type="primary" onClick={openCreateAudit}>
                      {withSingleNewShortcutHint(t('app.kuaizhizao.quality.qms.createExternalAudit'))}
                    </Button>,
                  ]
                : []
            }
            enableRowSelection={canDelete}
            showDeleteButton={canDelete}
            deleteButtonText={t('common.delete')}
            onTableDataChange={(rows) => {
              auditRowsRef.current = rows;
            }}
            onDelete={async (keys) => {
              await Promise.all(keys.map((key) => qualityQmsApi.externalAudits.delete(Number(key))));
              messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
              auditActionRef.current?.reload();
            }}
            request={async (params, _sort, _filter, searchFormValues) => {
              const pageSize = params.pageSize || 20;
              const skip = ((params.current || 1) - 1) * pageSize;
              const res = await qualityQmsApi.externalAudits.list({
                skip,
                limit: pageSize,
                keyword: pickListSearchKeyword(searchFormValues),
                audit_type: pickSearchString(searchFormValues, 'audit_type'),
              });
              return { success: true, data: res.items || [], total: res.total || 0 };
            }}
          />
        ) : (
          <UniTable<QmsCertificate>
            headerTitle={t('app.kuaizhizao.menu.quality-management.external-audits')}
            actionRef={certActionRef}
            rowKey="id"
            columns={certColumns}
            showAdvancedSearch
            columnPersistenceId="apps.kuaizhizao.pages.quality-management.certificates-width-v1"
            skipFuzzyPinyinClientFilter
            beforeSearchButtons={segment}
            toolBarRender={() =>
              canCreate
                ? [
                    <Button key="add" type="primary" onClick={openCreateCert}>
                      {withSingleNewShortcutHint(t('app.kuaizhizao.quality.qms.createCertificate'))}
                    </Button>,
                  ]
                : []
            }
            enableRowSelection={canDelete}
            showDeleteButton={canDelete}
            deleteButtonText={t('common.delete')}
            onTableDataChange={(rows) => {
              certRowsRef.current = rows;
            }}
            onDelete={async (keys) => {
              await Promise.all(keys.map((key) => qualityQmsApi.certificates.delete(Number(key))));
              messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
              certActionRef.current?.reload();
            }}
            request={async (params, _sort, _filter, searchFormValues) => {
              const pageSize = params.pageSize || 20;
              const skip = ((params.current || 1) - 1) * pageSize;
              const res = await qualityQmsApi.certificates.list({
                skip,
                limit: pageSize,
                keyword: pickListSearchKeyword(searchFormValues),
                status: pickSearchString(searchFormValues, 'status'),
              });
              return { success: true, data: res.items || [], total: res.total || 0 };
            }}
          />
        )}

        <FormModalTemplate
          title={
            editingAudit
              ? t('app.kuaizhizao.quality.qms.editExternalAudit')
              : t('app.kuaizhizao.quality.qms.createExternalAudit')
          }
          open={auditOpen}
          width={MODAL_CONFIG.LARGE_WIDTH}
          grid={false}
          formRef={auditFormRef}
          onClose={() => {
            setAuditOpen(false);
            setEditingAudit(null);
          }}
          onFinish={async (values) => {
            try {
              if (editingAudit?.id) {
                await qualityQmsApi.externalAudits.update(editingAudit.id, values);
              } else {
                await qualityQmsApi.externalAudits.create(values);
              }
              messageApi.success(t('common.saveSuccess'));
              setAuditOpen(false);
              auditActionRef.current?.reload();
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
                name="audit_code"
                label={t('app.kuaizhizao.quality.qms.externalAuditCode')}
                pageCode="kuaizhizao-quality-external-audit"
                documentId={editingAudit?.id}
              />
            </Col>
            <Col span={8}>
              <ProFormText
                name="body_name"
                label={t('app.kuaizhizao.quality.qms.externalBodyName')}
                rules={[{ required: true }]}
              />
            </Col>
            <Col span={8}>
              <ProFormSelect
                name="audit_type"
                label={t('app.kuaizhizao.quality.qms.externalAuditType.label')}
                options={QMS_EXTERNAL_AUDIT_TYPE_OPTIONS.map((o) => ({
                  value: o.value,
                  label: t(o.labelKey),
                }))}
                rules={[{ required: true }]}
              />
            </Col>
            <Col span={8}>
              <ProFormDatePicker
                name="planned_on"
                label={t('app.kuaizhizao.quality.qms.externalPlannedOn')}
              />
            </Col>
            <Col span={8}>
              <ProFormDatePicker
                name="actual_on"
                label={t('app.kuaizhizao.quality.qms.externalActualOn')}
              />
            </Col>
            <Col span={24}>
              <ProFormTextArea
                name="audit_scope"
                label={t('app.kuaizhizao.quality.qms.externalAuditScope')}
                fieldProps={{ rows: 2 }}
              />
            </Col>
            <Col span={24}>
              <ProFormTextArea name="remarks" label={t('common.remark')} fieldProps={{ rows: 2 }} />
            </Col>
          </Row>
        </FormModalTemplate>

        <FormModalTemplate
          title={
            editingCert
              ? t('app.kuaizhizao.quality.qms.editCertificate')
              : t('app.kuaizhizao.quality.qms.createCertificate')
          }
          open={certOpen}
          width={MODAL_CONFIG.LARGE_WIDTH}
          grid={false}
          formRef={certFormRef}
          onClose={() => {
            setCertOpen(false);
            setEditingCert(null);
          }}
          onFinish={async (values) => {
            try {
              if (editingCert?.id) {
                await qualityQmsApi.certificates.update(editingCert.id, values);
              } else {
                await qualityQmsApi.certificates.create(values);
              }
              messageApi.success(t('common.saveSuccess'));
              setCertOpen(false);
              certActionRef.current?.reload();
              return true;
            } catch (e: any) {
              messageApi.error(e?.message || t('common.saveFailed'));
              return false;
            }
          }}
        >
          <Row gutter={16}>
            <Col span={12}>
              <ProFormText
                name="name"
                label={t('app.kuaizhizao.quality.qms.certificateName')}
                rules={[{ required: true }]}
              />
            </Col>
            <Col span={12}>
              <ProFormText
                name="certificate_no"
                label={t('app.kuaizhizao.quality.qms.certificateNo')}
                rules={[{ required: true }]}
              />
            </Col>
            <Col span={12}>
              <ProFormText
                name="standard_name"
                label={t('app.kuaizhizao.quality.qms.certificateStandard')}
              />
            </Col>
            <Col span={12}>
              <ProFormText name="issuer" label={t('app.kuaizhizao.quality.qms.certificateIssuer')} />
            </Col>
            <Col span={12}>
              <ProFormDatePicker
                name="effective_on"
                label={t('app.kuaizhizao.quality.qms.certificateEffectiveOn')}
              />
            </Col>
            <Col span={12}>
              <ProFormDatePicker
                name="expire_on"
                label={t('app.kuaizhizao.quality.qms.certificateExpireOn')}
                rules={[{ required: true }]}
              />
            </Col>
            <Col span={24}>
              <ProFormTextArea name="remarks" label={t('common.remark')} fieldProps={{ rows: 2 }} />
            </Col>
          </Row>
        </FormModalTemplate>

        <FormModalTemplate
          title={t('app.kuaizhizao.quality.qms.createExternalNcTitle', {
            code: ncSource?.audit_code || '',
          })}
          open={ncOpen}
          width={MODAL_CONFIG.LARGE_WIDTH}
          grid={false}
          formRef={ncFormRef}
          onClose={() => {
            setNcOpen(false);
            setNcSource(null);
          }}
          onFinish={async (values) => {
            try {
              if (!ncSource) return false;
              await qualityQmsApi.nonconformityReports.create({
                ...values,
                source_type: 'external_audit',
                source_id: ncSource.id,
                source_code: ncSource.audit_code,
                status: 'open',
              });
              messageApi.success(t('app.kuaizhizao.quality.qms.messages.externalNcCreated'));
              setNcOpen(false);
              setNcSource(null);
              auditActionRef.current?.reload();
              return true;
            } catch (e: any) {
              messageApi.error(e?.message || t('common.saveFailed'));
              return false;
            }
          }}
        >
          <Row gutter={16}>
            <Col span={12}>
              <ProFormSelect
                name="severity"
                label={t('app.kuaizhizao.quality.qms.ncSeverity.label')}
                options={QMS_NC_SEVERITY_OPTIONS.map((o) => ({
                  value: o.value,
                  label: t(o.labelKey),
                }))}
                rules={[{ required: true }]}
              />
            </Col>
            <Col span={12}>
              <ProFormText
                name="responsible_dept"
                label={t('app.kuaizhizao.quality.qms.ncResponsibleDept')}
              />
            </Col>
            <Col span={24}>
              <ProFormTextArea
                name="fact"
                label={t('app.kuaizhizao.quality.qms.ncFact')}
                rules={[{ required: true }]}
                fieldProps={{ rows: 4 }}
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

export default ExternalAuditsPage;
