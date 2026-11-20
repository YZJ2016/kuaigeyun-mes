import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActionType,
  ProColumns,
  ProFormDatePicker,
  ProFormSelect,
  ProFormSwitch,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { App, Button, Col, Empty, Row } from 'antd';
import { useTranslation } from 'react-i18next';
import { UniTable } from '../../../../../components/uni-table';
import { rowActionKind } from '../../../../../components/uni-action';
import { FormModalTemplate, ListPageTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import PermissionGuard from '../../../../../components/permission/PermissionGuard';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useNewShortcut } from '../../../../../hooks/useNewShortcut';
import { withSingleNewShortcutHint } from '../../../../../utils/globalNewShortcut';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { formatBusinessDateOnly } from '../../../../../utils/format';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { pickListSearchKeyword } from '../../../../../utils/tableQueryKey';
import { qualityQmsApi, QmsLegalRegulation } from '../../../services/quality-qms';
import { QMS_LEGAL_CONCLUSION_OPTIONS } from '../qms/qmsMeta';

const RESOURCE = 'kuaizhizao:quality-management-legal-regulations';

const LegalRegulationsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const actionRef = useRef<ActionType>(null);
  const formRef = useRef<any>(null);
  const tableRowsRef = useRef<QmsLegalRegulation[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<QmsLegalRegulation | null>(null);
  const [dueOnly, setDueOnly] = useState(false);
  const { canCreate, canUpdate, canDelete } = useResourcePermissions(RESOURCE);

  const conclusionEnum = useMemo(
    () =>
      Object.fromEntries(QMS_LEGAL_CONCLUSION_OPTIONS.map((o) => [o.value, { text: t(o.labelKey) }])),
    [t],
  );

  const openCreate = useCallback(() => {
    setEditing(null);
    setOpen(true);
    setTimeout(() => {
      formRef.current?.resetFields();
      formRef.current?.setFieldsValue({ evaluation_completed: false });
    }, 0);
  }, []);
  useNewShortcut(() => {
    if (canCreate) openCreate();
  });

  const columns: ProColumns<QmsLegalRegulation>[] = useMemo(
    () =>
      alignProColumns(
        [
          {
            title: t('app.kuaizhizao.quality.qms.legalName'),
            dataIndex: 'name',
            minWidth: 180,
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
            title: t('app.kuaizhizao.quality.qms.legalDocNo'),
            dataIndex: 'doc_no',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            copyable: true,
            hideInSearch: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.legalIssuingAuthority'),
            dataIndex: 'issuing_authority',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => row.issuing_authority || '-',
          },
          {
            title: t('app.kuaizhizao.quality.qms.legalEffectiveOn'),
            dataIndex: 'effective_on',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => formatBusinessDateOnly(row.effective_on) || '-',
          },
          {
            title: t('app.kuaizhizao.quality.qms.legalConclusion.label'),
            dataIndex: 'evaluation_conclusion',
            width: 100,
            minWidth: 100,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            valueEnum: conclusionEnum,
            render: (_, row) => {
              if (!row.evaluation_conclusion) return '-';
              return (
                <MarkerTag color={row.evaluation_conclusion === 'need_rectify' ? 'warning' : 'success'}>
                  {conclusionEnum[row.evaluation_conclusion]?.text || row.evaluation_conclusion}
                </MarkerTag>
              );
            },
          },
          {
            title: t('app.kuaizhizao.quality.qms.legalNextEvaluationOn'),
            dataIndex: 'next_evaluation_on',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => {
              const text = formatBusinessDateOnly(row.next_evaluation_on) || '-';
              if (row.due_for_evaluation) {
                return <MarkerTag color="warning">{text}</MarkerTag>;
              }
              return text;
            },
          },
          {
            title: t('app.kuaizhizao.quality.qms.legalCapaCode'),
            dataIndex: 'capa_code',
            width: 130,
            minWidth: 130,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => row.capa_code || '-',
          },
          {
            title: t('app.kuaizhizao.quality.qms.legalEvalCompleted'),
            dataIndex: 'evaluation_completed',
            width: 90,
            minWidth: 90,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) =>
              row.evaluation_completed
                ? t('app.kuaizhizao.quality.qms.legalEvalCompletedYes')
                : t('app.kuaizhizao.quality.qms.legalEvalCompletedNo'),
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
            ],
          },
        ],
        GLOBAL_DOC_LIST_FIELD_RANK,
      ),
    [canUpdate, conclusionEnum, t],
  );

  return (
    <PermissionGuard
      permission="kuaizhizao:quality-management-legal-regulations:read"
      fallback={<Empty description={t('app.kuaizhizao.quality.qms.noPermission')} style={{ marginTop: 120 }} />}
    >
      <ListPageTemplate>
        <UniTable<QmsLegalRegulation>
          headerTitle={t('app.kuaizhizao.menu.quality-management.legal-regulations')}
          actionRef={actionRef}
          rowKey="id"
          columns={columns}
          showAdvancedSearch
          columnPersistenceId="apps.kuaizhizao.pages.quality-management.legal-regulations-width-v1"
          skipFuzzyPinyinClientFilter
          params={{ dueOnly }}
          toolBarRender={() => [
            <Button
              key="due"
              type={dueOnly ? 'primary' : 'default'}
              onClick={() => {
                setDueOnly((v) => !v);
                actionRef.current?.reload();
              }}
            >
              {t('app.kuaizhizao.quality.qms.legalDueOnly')}
            </Button>,
            ...(canCreate
              ? [
                  <Button key="add" type="primary" onClick={openCreate}>
                    {withSingleNewShortcutHint(t('app.kuaizhizao.quality.qms.createLegalRegulation'))}
                  </Button>,
                ]
              : []),
          ]}
          enableRowSelection={canDelete}
          showDeleteButton={canDelete}
          deleteButtonText={t('common.delete')}
          onTableDataChange={(rows) => {
            tableRowsRef.current = rows;
          }}
          onDelete={async (keys) => {
            await Promise.all(keys.map((key) => qualityQmsApi.legalRegulations.delete(Number(key))));
            messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
            actionRef.current?.reload();
          }}
          request={async (params, _sort, _filter, searchFormValues) => {
            const pageSize = params.pageSize || 20;
            const skip = ((params.current || 1) - 1) * pageSize;
            const res = await qualityQmsApi.legalRegulations.list({
              skip,
              limit: pageSize,
              keyword: pickListSearchKeyword(searchFormValues),
              due_only: dueOnly,
            });
            return { success: true, data: res.items || [], total: res.total || 0 };
          }}
        />

        <FormModalTemplate
          title={
            editing
              ? t('app.kuaizhizao.quality.qms.editLegalRegulation')
              : t('app.kuaizhizao.quality.qms.createLegalRegulation')
          }
          open={open}
          width={MODAL_CONFIG.LARGE_WIDTH}
          grid={false}
          formRef={formRef}
          onClose={() => {
            setOpen(false);
            setEditing(null);
          }}
          onFinish={async (values) => {
            try {
              if (editing?.id) {
                await qualityQmsApi.legalRegulations.update(editing.id, values);
              } else {
                await qualityQmsApi.legalRegulations.create(values);
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
            <Col span={12}>
              <ProFormText
                name="name"
                label={t('app.kuaizhizao.quality.qms.legalName')}
                rules={[{ required: true }]}
              />
            </Col>
            <Col span={12}>
              <ProFormText
                name="doc_no"
                label={t('app.kuaizhizao.quality.qms.legalDocNo')}
                rules={[{ required: true }]}
              />
            </Col>
            <Col span={12}>
              <ProFormText
                name="issuing_authority"
                label={t('app.kuaizhizao.quality.qms.legalIssuingAuthority')}
              />
            </Col>
            <Col span={12}>
              <ProFormDatePicker
                name="effective_on"
                label={t('app.kuaizhizao.quality.qms.legalEffectiveOn')}
              />
            </Col>
            <Col span={24}>
              <ProFormTextArea
                name="applicable_scope"
                label={t('app.kuaizhizao.quality.qms.legalApplicableScope')}
                fieldProps={{ rows: 2 }}
              />
            </Col>
            <Col span={8}>
              <ProFormSelect
                name="evaluation_conclusion"
                label={t('app.kuaizhizao.quality.qms.legalConclusion.label')}
                options={QMS_LEGAL_CONCLUSION_OPTIONS.map((o) => ({
                  value: o.value,
                  label: t(o.labelKey),
                }))}
                allowClear
              />
            </Col>
            <Col span={8}>
              <ProFormDatePicker
                name="evaluated_on"
                label={t('app.kuaizhizao.quality.qms.legalEvaluatedOn')}
              />
            </Col>
            <Col span={8}>
              <ProFormDatePicker
                name="next_evaluation_on"
                label={t('app.kuaizhizao.quality.qms.legalNextEvaluationOn')}
              />
            </Col>
            <Col span={12}>
              <ProFormText name="capa_code" label={t('app.kuaizhizao.quality.qms.legalCapaCode')} />
            </Col>
            <Col span={12}>
              <ProFormSwitch
                name="evaluation_completed"
                label={t('app.kuaizhizao.quality.qms.legalEvalCompleted')}
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

export default LegalRegulationsPage;
