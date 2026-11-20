import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActionType,
  ProColumns,
  ProFormDigit,
  ProFormSelect,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { App, Button, Col, Empty, Row } from 'antd';
import { useTranslation } from 'react-i18next';
import CodeField from '../../../../../components/code-field';
import { UniTable } from '../../../../../components/uni-table';
import { UniTableDetail } from '../../../../../components/uni-table-detail';
import { rowActionKind } from '../../../../../components/uni-action';
import { FormModalTemplate, ListPageTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import PermissionGuard from '../../../../../components/permission/PermissionGuard';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useNewShortcut } from '../../../../../hooks/useNewShortcut';
import { withSingleNewShortcutHint } from '../../../../../utils/globalNewShortcut';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { renderDocumentStatusTag } from '../../../../../utils/documentLifecycleStatusTag';
import { pickListSearchKeyword, pickSearchString } from '../../../../../utils/tableQueryKey';
import {
  qualityQmsApi,
  QmsQualityObjective,
  QmsQualityObjectiveLine,
} from '../../../services/quality-qms';
import {
  QMS_OBJECTIVE_PERIOD_OPTIONS,
  QMS_OBJECTIVE_STATUS_OPTIONS,
} from '../qms/qmsMeta';

const RESOURCE = 'kuaizhizao:quality-management-quality-objectives';

const QualityObjectivesPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const actionRef = useRef<ActionType>(null);
  const formRef = useRef<any>(null);
  const tableRowsRef = useRef<QmsQualityObjective[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<QmsQualityObjective | null>(null);
  const { canCreate, canUpdate, canDelete } = useResourcePermissions(RESOURCE);

  const statusEnum = useMemo(
    () => Object.fromEntries(QMS_OBJECTIVE_STATUS_OPTIONS.map((o) => [o.value, { text: t(o.labelKey) }])),
    [t],
  );

  const openCreate = useCallback(() => {
    setEditing(null);
    setOpen(true);
    setTimeout(() => {
      formRef.current?.resetFields();
      formRef.current?.setFieldsValue({
        status: 'draft',
        plan_year: new Date().getFullYear(),
        lines: [{ name: '', target_value: '', period: 'month', sort_order: 0 }],
      });
    }, 0);
  }, []);
  useNewShortcut(() => {
    if (canCreate) openCreate();
  });

  const lineColumns: ProColumns<QmsQualityObjectiveLine>[] = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.quality.qms.objectiveLineName'),
        dataIndex: 'name',
        valueType: 'text',
        formItemProps: { rules: [{ required: true }] },
        width: 160,
      },
      {
        title: t('app.kuaizhizao.quality.qms.objectiveMetricScope'),
        dataIndex: 'metric_scope',
        valueType: 'text',
        width: 140,
      },
      {
        title: t('app.kuaizhizao.quality.qms.objectiveTargetValue'),
        dataIndex: 'target_value',
        valueType: 'text',
        formItemProps: { rules: [{ required: true }] },
        width: 100,
      },
      {
        title: t('app.kuaizhizao.quality.qms.objectiveActualValue'),
        dataIndex: 'actual_value',
        valueType: 'text',
        width: 100,
      },
      {
        title: t('app.kuaizhizao.quality.qms.objectiveResponsibleDept'),
        dataIndex: 'responsible_dept',
        valueType: 'text',
        width: 120,
      },
      {
        title: t('app.kuaizhizao.quality.qms.objectivePeriod.label'),
        dataIndex: 'period',
        valueType: 'select',
        valueEnum: Object.fromEntries(
          QMS_OBJECTIVE_PERIOD_OPTIONS.map((o) => [o.value, { text: t(o.labelKey) }]),
        ),
        width: 90,
      },
      {
        title: t('app.kuaizhizao.quality.qms.objectiveAchieved'),
        dataIndex: 'achieved',
        editable: false,
        width: 80,
        render: (_, row) => {
          if (row.achieved === true) return t('app.kuaizhizao.quality.qms.objectiveAchievedYes');
          if (row.achieved === false) return t('app.kuaizhizao.quality.qms.objectiveAchievedNo');
          return '-';
        },
      },
    ],
    [t],
  );

  const columns: ProColumns<QmsQualityObjective>[] = useMemo(
    () =>
      alignProColumns(
        [
          {
            title: t('app.kuaizhizao.quality.qms.objectiveCode'),
            dataIndex: 'objective_code',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            copyable: true,
            hideInSearch: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.objectivePlanYear'),
            dataIndex: 'plan_year',
            width: 90,
            minWidth: 90,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.keyword'),
            dataIndex: 'keyword',
            hideInTable: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.objectiveStandard'),
            dataIndex: 'standard_label',
            minWidth: 160,
            uniTablePrimaryFlex: true,
            uniTableRemainderFlex: true,
            resizable: false,
            ellipsis: true,
            hideInSearch: true,
            render: (_, row) => row.standard_label || '-',
          },
          {
            title: t('app.kuaizhizao.quality.qms.objectiveLineCount'),
            key: 'line_count',
            width: 80,
            minWidth: 80,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) => row.lines?.length ?? 0,
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
                    setTimeout(() => {
                      formRef.current?.setFieldsValue({
                        ...row,
                        lines: row.lines?.length
                          ? row.lines
                          : [{ name: '', target_value: '', period: 'month', sort_order: 0 }],
                      });
                    }, 0);
                  }}
                />
              ) : null,
            ],
          },
        ],
        GLOBAL_DOC_LIST_FIELD_RANK,
      ),
    [canUpdate, statusEnum, t],
  );

  return (
    <PermissionGuard
      permission="kuaizhizao:quality-management-quality-objectives:read"
      fallback={<Empty description={t('app.kuaizhizao.quality.qms.noPermission')} style={{ marginTop: 120 }} />}
    >
      <ListPageTemplate>
        <UniTable<QmsQualityObjective>
          headerTitle={t('app.kuaizhizao.menu.quality-management.quality-objectives')}
          actionRef={actionRef}
          rowKey="id"
          columns={columns}
          showAdvancedSearch
          columnPersistenceId="apps.kuaizhizao.pages.quality-management.quality-objectives-width-v1"
          skipFuzzyPinyinClientFilter
          toolBarRender={() =>
            canCreate
              ? [
                  <Button key="add" type="primary" onClick={openCreate}>
                    {withSingleNewShortcutHint(t('app.kuaizhizao.quality.qms.createQualityObjective'))}
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
            await Promise.all(keys.map((key) => qualityQmsApi.qualityObjectives.delete(Number(key))));
            messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
            actionRef.current?.reload();
          }}
          request={async (params, _sort, _filter, searchFormValues) => {
            const pageSize = params.pageSize || 20;
            const skip = ((params.current || 1) - 1) * pageSize;
            const res = await qualityQmsApi.qualityObjectives.list({
              skip,
              limit: pageSize,
              keyword: pickListSearchKeyword(searchFormValues),
              status: pickSearchString(searchFormValues, 'status'),
            });
            return { success: true, data: res.items || [], total: res.total || 0 };
          }}
        />

        <FormModalTemplate
          title={
            editing
              ? t('app.kuaizhizao.quality.qms.editQualityObjective')
              : t('app.kuaizhizao.quality.qms.createQualityObjective')
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
              const payload = {
                ...values,
                lines: (values.lines || []).map((line: QmsQualityObjectiveLine, idx: number) => ({
                  ...line,
                  sort_order: line.sort_order ?? idx,
                })),
              };
              if (editing?.id) {
                await qualityQmsApi.qualityObjectives.update(editing.id, payload);
              } else {
                await qualityQmsApi.qualityObjectives.create(payload);
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
                name="objective_code"
                label={t('app.kuaizhizao.quality.qms.objectiveCode')}
                pageCode="kuaizhizao-quality-objective"
                documentId={editing?.id}
              />
            </Col>
            <Col span={8}>
              <ProFormDigit
                name="plan_year"
                label={t('app.kuaizhizao.quality.qms.objectivePlanYear')}
                rules={[{ required: true }]}
                fieldProps={{ precision: 0, min: 2000, max: 2100 }}
              />
            </Col>
            <Col span={8}>
              <ProFormSelect
                name="status"
                label={t('common.status')}
                options={QMS_OBJECTIVE_STATUS_OPTIONS.map((o) => ({
                  value: o.value,
                  label: t(o.labelKey),
                }))}
                rules={[{ required: true }]}
              />
            </Col>
            <Col span={8}>
              <ProFormDigit
                name="standard_id"
                label={t('app.kuaizhizao.quality.qms.objectiveStandardId')}
                fieldProps={{ precision: 0, min: 1 }}
              />
            </Col>
          </Row>
          <UniTableDetail
            name="lines"
            title={t('app.kuaizhizao.quality.qms.objectiveLines')}
            required
            requiredMessage={t('app.kuaizhizao.quality.qms.objectiveLinesRequired')}
            columns={lineColumns}
            initialValue={{
              name: '',
              target_value: '',
              period: 'month',
              sort_order: 0,
            }}
          />
          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col span={24}>
              <ProFormTextArea name="remarks" label={t('common.remark')} fieldProps={{ rows: 2 }} />
            </Col>
          </Row>
        </FormModalTemplate>
      </ListPageTemplate>
    </PermissionGuard>
  );
};

export default QualityObjectivesPage;
