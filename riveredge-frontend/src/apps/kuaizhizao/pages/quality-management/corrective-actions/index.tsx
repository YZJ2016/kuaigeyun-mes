import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActionType,
  ProColumns,
  ProFormDatePicker,
  ProFormDigit,
  ProFormSelect,
  ProFormSwitch,
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
import { pickListSearchKeyword, pickSearchString } from '../../../../../utils/tableQueryKey';
import { qualityQmsApi, QmsCorrectiveAction } from '../../../services/quality-qms';
import { QMS_CA_SOURCE_OPTIONS, QMS_CA_STATUS_OPTIONS } from '../qms/qmsMeta';

const RESOURCE = 'kuaizhizao:quality-management-corrective-actions';

const CorrectiveActionsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const actionRef = useRef<ActionType>(null);
  const formRef = useRef<any>(null);
  const tableRowsRef = useRef<QmsCorrectiveAction[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<QmsCorrectiveAction | null>(null);
  const { canCreate, canUpdate, canDelete, canAction } = useResourcePermissions(RESOURCE);
  const canClose = !!canAction?.('close');

  const statusEnum = useMemo(
    () => Object.fromEntries(QMS_CA_STATUS_OPTIONS.map((o) => [o.value, { text: t(o.labelKey) }])),
    [t],
  );
  const sourceEnum = useMemo(
    () => Object.fromEntries(QMS_CA_SOURCE_OPTIONS.map((o) => [o.value, { text: t(o.labelKey) }])),
    [t],
  );

  const openCreate = useCallback(() => {
    setEditing(null);
    setOpen(true);
    setTimeout(() => {
      formRef.current?.resetFields();
      formRef.current?.setFieldsValue({
        status: 'registered',
        source_type: 'nonconformity_report',
        need_eight_d: false,
      });
    }, 0);
  }, []);
  useNewShortcut(() => {
    if (canCreate) openCreate();
  });

  const columns: ProColumns<QmsCorrectiveAction>[] = useMemo(
    () =>
      alignProColumns(
        [
          {
            title: t('app.kuaizhizao.quality.qms.caActionCode'),
            dataIndex: 'action_code',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            copyable: true,
            hideInSearch: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.caProblemSummary'),
            dataIndex: 'problem_summary',
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
            title: t('app.kuaizhizao.quality.qms.caSource.label'),
            dataIndex: 'source_type',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            valueEnum: sourceEnum,
          },
          {
            title: t('app.kuaizhizao.quality.qms.caSource.code'),
            dataIndex: 'source_code',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.caResponsiblePerson'),
            dataIndex: 'responsible_person',
            width: 100,
            minWidth: 100,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => row.responsible_person || '-',
          },
          {
            title: t('app.kuaizhizao.quality.qms.caDueOn'),
            dataIndex: 'due_on',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => formatBusinessDateOnly(row.due_on) || '-',
          },
          {
            title: t('app.kuaizhizao.quality.qms.caEightDCode'),
            dataIndex: 'eight_d_code',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => row.eight_d_code || '-',
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
              canClose && row.status !== 'closed' ? (
                <Button
                  key="close"
                  {...rowActionKind('close')}
                  onClick={async () => {
                    if (!row.verification_conclusion) {
                      messageApi.warning(t('app.kuaizhizao.quality.qms.messages.caCloseNeedVerify'));
                      setEditing(row);
                      setOpen(true);
                      setTimeout(() => formRef.current?.setFieldsValue(row), 0);
                      return;
                    }
                    await qualityQmsApi.correctiveActions.close(row.id, {
                      verification_conclusion: row.verification_conclusion,
                      verifier_name: row.verifier_name,
                      verified_on: row.verified_on,
                    });
                    messageApi.success(t('app.kuaizhizao.quality.qms.messages.caClosed'));
                    actionRef.current?.reload();
                  }}
                >
                  {t('app.kuaizhizao.quality.qms.actions.closeCa')}
                </Button>
              ) : null,
            ],
          },
        ],
        GLOBAL_DOC_LIST_FIELD_RANK,
      ),
    [canClose, canUpdate, messageApi, sourceEnum, statusEnum, t],
  );

  return (
    <PermissionGuard
      permission="kuaizhizao:quality-management-corrective-actions:read"
      fallback={<Empty description={t('app.kuaizhizao.quality.qms.noPermission')} style={{ marginTop: 120 }} />}
    >
      <ListPageTemplate>
        <UniTable<QmsCorrectiveAction>
          headerTitle={t('app.kuaizhizao.menu.quality-management.corrective-actions')}
          actionRef={actionRef}
          rowKey="id"
          columns={columns}
          showAdvancedSearch
          columnPersistenceId="apps.kuaizhizao.pages.quality-management.corrective-actions-width-v1"
          skipFuzzyPinyinClientFilter
          toolBarRender={() =>
            canCreate
              ? [
                  <Button key="add" type="primary" onClick={openCreate}>
                    {withSingleNewShortcutHint(t('app.kuaizhizao.quality.qms.createCorrectiveAction'))}
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
              keys.map((key) => qualityQmsApi.correctiveActions.delete(Number(key))),
            );
            messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
            actionRef.current?.reload();
          }}
          request={async (params, _sort, _filter, searchFormValues) => {
            const pageSize = params.pageSize || 20;
            const skip = ((params.current || 1) - 1) * pageSize;
            const res = await qualityQmsApi.correctiveActions.list({
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
              ? t('app.kuaizhizao.quality.qms.editCorrectiveAction')
              : t('app.kuaizhizao.quality.qms.createCorrectiveAction')
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
                if (payload.status === 'closed') {
                  await qualityQmsApi.correctiveActions.close(editing.id, payload);
                } else {
                  await qualityQmsApi.correctiveActions.update(editing.id, payload);
                }
              } else {
                await qualityQmsApi.correctiveActions.create(payload);
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
                name="action_code"
                label={t('app.kuaizhizao.quality.qms.caActionCode')}
                pageCode="kuaizhizao-quality-corrective-action"
                documentId={editing?.id}
              />
            </Col>
            <Col span={8}>
              <ProFormSelect
                name="source_type"
                label={t('app.kuaizhizao.quality.qms.caSource.label')}
                options={QMS_CA_SOURCE_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
                rules={[{ required: true }]}
                disabled={!!editing}
              />
            </Col>
            <Col span={8}>
              <ProFormDigit
                name="source_id"
                label={t('app.kuaizhizao.quality.qms.caSource.id')}
                rules={editing ? undefined : [{ required: true }]}
                disabled={!!editing}
                fieldProps={{ precision: 0, min: 1 }}
              />
            </Col>
            {editing ? (
              <Col span={8}>
                <ProFormText
                  name="source_code"
                  label={t('app.kuaizhizao.quality.qms.caSource.code')}
                  disabled
                />
              </Col>
            ) : null}
            <Col span={8}>
              <ProFormSelect
                name="status"
                label={t('common.status')}
                options={QMS_CA_STATUS_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
                rules={[{ required: true }]}
              />
            </Col>
            <Col span={8}>
              <ProFormText
                name="responsible_person"
                label={t('app.kuaizhizao.quality.qms.caResponsiblePerson')}
              />
            </Col>
            <Col span={8}>
              <ProFormDatePicker name="due_on" label={t('app.kuaizhizao.quality.qms.caDueOn')} />
            </Col>
            <Col span={24}>
              <ProFormTextArea
                name="problem_summary"
                label={t('app.kuaizhizao.quality.qms.caProblemSummary')}
                rules={[{ required: true }]}
                fieldProps={{ rows: 3 }}
              />
            </Col>
            <Col span={24}>
              <ProFormTextArea
                name="cause"
                label={t('app.kuaizhizao.quality.qms.caCause')}
                fieldProps={{ rows: 2 }}
              />
            </Col>
            <Col span={24}>
              <ProFormTextArea
                name="correction"
                label={t('app.kuaizhizao.quality.qms.caCorrection')}
                fieldProps={{ rows: 2 }}
              />
            </Col>
            <Col span={24}>
              <ProFormTextArea
                name="prevention"
                label={t('app.kuaizhizao.quality.qms.caPrevention')}
                fieldProps={{ rows: 2 }}
              />
            </Col>
            <Col span={8}>
              <ProFormSwitch name="need_eight_d" label={t('app.kuaizhizao.quality.qms.caNeedEightD')} />
            </Col>
            <Col span={8}>
              <ProFormText name="eight_d_code" label={t('app.kuaizhizao.quality.qms.caEightDCode')} />
            </Col>
            <Col span={8}>
              <ProFormText name="verifier_name" label={t('app.kuaizhizao.quality.qms.caVerifier')} />
            </Col>
            <Col span={8}>
              <ProFormDatePicker name="verified_on" label={t('app.kuaizhizao.quality.qms.caVerifiedOn')} />
            </Col>
            <Col span={24}>
              <ProFormTextArea
                name="verification_conclusion"
                label={t('app.kuaizhizao.quality.qms.caVerificationConclusion')}
                fieldProps={{ rows: 2 }}
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

export default CorrectiveActionsPage;
