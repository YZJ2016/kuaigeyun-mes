/**
 * 年度审核计划（内审年度计划独立菜单；权限与内部审核同资源）
 */
import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActionType,
  ProColumns,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { App, Button, Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import { UniTable } from '../../../../../components/uni-table';
import { rowActionKind } from '../../../../../components/uni-action';
import { FormModalTemplate, ListPageTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import PermissionGuard from '../../../../../components/permission/PermissionGuard';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useNewShortcut } from '../../../../../hooks/useNewShortcut';
import { withSingleNewShortcutHint } from '../../../../../utils/globalNewShortcut';
import {
  qualityQmsApi,
  QmsInternalAuditAnnualPlan,
} from '../../../services/quality-qms';

const RESOURCE = 'kuaizhizao:quality-management-internal-audits';

const InternalAuditAnnualPlansPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const actionRef = useRef<ActionType>(null);
  const formRef = useRef<any>(null);
  const tableRowsRef = useRef<QmsInternalAuditAnnualPlan[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<QmsInternalAuditAnnualPlan | null>(null);
  const { canCreate, canUpdate, canDelete } = useResourcePermissions(RESOURCE);

  const openCreate = useCallback(() => {
    setEditing(null);
    setOpen(true);
    setTimeout(() => {
      formRef.current?.resetFields();
      formRef.current?.setFieldsValue({
        plan_year: new Date().getFullYear(),
      });
    }, 0);
  }, []);

  useNewShortcut(() => {
    if (canCreate) openCreate();
  });

  const columns: ProColumns<QmsInternalAuditAnnualPlan>[] = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.quality.qms.annualPlan.year'),
        dataIndex: 'plan_year',
        width: 100,
        uniTableKeepWidth: true,
      },
      {
        title: t('app.kuaizhizao.quality.qms.annualPlan.coveredProcesses'),
        dataIndex: 'covered_processes',
        ellipsis: true,
        uniTableRemainderFlex: true,
      },
      {
        title: t('app.kuaizhizao.quality.qms.annualPlan.months'),
        dataIndex: 'planned_months',
        width: 160,
        uniTableKeepWidth: true,
        render: (_, row) => (row.planned_months || []).join('、') || '-',
      },
      {
        title: t('app.kuaizhizao.quality.qms.leadAuditor'),
        dataIndex: 'lead_auditor',
        width: 120,
        uniTableKeepWidth: true,
      },
      {
        title: t('common.actions'),
        key: 'option',
        fixed: 'right',
        width: 120,
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
    [canUpdate, t],
  );

  return (
    <PermissionGuard
      permission="kuaizhizao:quality-management-internal-audits:read"
      fallback={<Empty description={t('app.kuaizhizao.quality.qms.noPermission')} style={{ marginTop: 120 }} />}
    >
      <ListPageTemplate>
        <UniTable<QmsInternalAuditAnnualPlan>
          headerTitle={t('app.kuaizhizao.menu.quality-management.internal-audit-annual-plans')}
          actionRef={actionRef}
          rowKey="id"
          columns={columns}
          columnPersistenceId="apps.kuaizhizao.pages.quality-management.internal-audit-annual-plans-v1"
          showCreateButton={canCreate}
          createButtonText={withSingleNewShortcutHint(
            t('app.kuaizhizao.quality.qms.annualPlan.createTitle'),
          )}
          onCreate={openCreate}
          enableRowSelection={canDelete}
          showDeleteButton={canDelete}
          deleteButtonText={t('common.delete')}
          onTableDataChange={(rows) => {
            tableRowsRef.current = rows;
          }}
          onDelete={async (keys) => {
            await Promise.all(keys.map((key) => qualityQmsApi.annualPlans.delete(Number(key))));
            messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
            actionRef.current?.reload();
          }}
          request={async (params) => {
            const pageSize = params.pageSize || 20;
            const skip = ((params.current || 1) - 1) * pageSize;
            const res = await qualityQmsApi.annualPlans.list({ skip, limit: pageSize });
            return { success: true, data: res.items || [], total: res.total || 0 };
          }}
        />

        <FormModalTemplate
          title={
            editing
              ? t('app.kuaizhizao.quality.qms.annualPlan.editTitle')
              : t('app.kuaizhizao.quality.qms.annualPlan.createTitle')
          }
          open={open}
          width={MODAL_CONFIG.STANDARD_WIDTH}
          grid
          formRef={formRef}
          onClose={() => {
            setOpen(false);
            setEditing(null);
          }}
          onFinish={async (values) => {
            try {
              const payload = {
                ...values,
                planned_months: (values.planned_months || []).map((m: string | number) => Number(m)),
              };
              if (editing?.id) {
                await qualityQmsApi.annualPlans.update(editing.id, payload);
              } else {
                await qualityQmsApi.annualPlans.create(payload);
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
          <ProFormSelect
            name="plan_year"
            label={t('app.kuaizhizao.quality.qms.annualPlan.year')}
            options={Array.from({ length: 8 }).map((_, i) => {
              const year = new Date().getFullYear() - 2 + i;
              return { value: year, label: String(year) };
            })}
            rules={[{ required: true }]}
            disabled={!!editing}
            colProps={{ span: 12 }}
          />
          <ProFormText
            name="lead_auditor"
            label={t('app.kuaizhizao.quality.qms.leadAuditor')}
            colProps={{ span: 12 }}
          />
          <ProFormSelect
            name="planned_months"
            label={t('app.kuaizhizao.quality.qms.annualPlan.months')}
            mode="multiple"
            options={Array.from({ length: 12 }).map((_, i) => ({
              value: i + 1,
              label: t('app.kuaizhizao.quality.qms.annualPlan.monthN', { n: i + 1 }),
            }))}
            colProps={{ span: 24 }}
          />
          <ProFormTextArea
            name="covered_processes"
            label={t('app.kuaizhizao.quality.qms.annualPlan.coveredProcesses')}
            fieldProps={{ rows: 3 }}
            colProps={{ span: 24 }}
          />
          <ProFormTextArea
            name="remarks"
            label={t('common.remark')}
            fieldProps={{ rows: 2 }}
            colProps={{ span: 24 }}
          />
        </FormModalTemplate>
      </ListPageTemplate>
    </PermissionGuard>
  );
};

export default InternalAuditAnnualPlansPage;
