/**
 * 休息 / 夜班登记：列表展示历史登记；新建 Modal 支持日期区间写入月度考勤草稿。
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ProFormDateRangePicker,
  ProFormSelect,
  type ActionType,
  type ProColumns,
} from '@ant-design/pro-components';
import { App, Button, Form, Typography } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import {
  FormModalTemplate,
  ListPageTemplate,
  MODAL_CONFIG,
} from '../../../../../components/layout-templates';
import { UniTable } from '../../../../../components/uni-table';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { formatDateBySiteSetting } from '../../../../../utils/format';
import { withSingleNewShortcutHint } from '../../../../../utils/globalNewShortcut';
import { pickListSearchKeyword } from '../../../../../utils/tableQueryKey';
import {
  alignProColumns,
  GLOBAL_DOC_LIST_FIELD_RANK,
} from '../../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { buildDocumentAuditColumns } from '../../../../kuaizhizao/pages/shared/documentAuditColumns';
import { listEmployees } from '../../../services/employees';
import {
  createAttendanceDayRegister,
  listAttendanceDayRegisters,
} from '../../../services/attendance';
import {
  loadOaProductionLineNameOptions,
  loadOaWorkshopNameOptions,
} from '../../../utils/oaWorkshopOptions';
import {
  buildOaEmploymentTypeOptions,
  resolveOaEmploymentTypeLabel,
} from '../../../utils/oaFormEnums';

type Mode = 'rest' | 'night';

const AttendanceDayRegisterPage: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [params] = useSearchParams();
  const mode: Mode = params.get('mode') === 'night' ? 'night' : 'rest';
  const perms = useResourcePermissions('kuaioa:attendance');
  const actionRef = useRef<ActionType>();
  const [form] = Form.useForm();
  const [modalOpen, setModalOpen] = useState(false);
  const [employeeOptions, setEmployeeOptions] = useState<Array<{ label: string; value: number }>>(
    [],
  );
  const [workshopOptions, setWorkshopOptions] = useState<Array<{ label: string; value: string }>>(
    [],
  );
  const [lineOptions, setLineOptions] = useState<Array<{ label: string; value: string }>>([]);
  const employmentOptions = useMemo(() => buildOaEmploymentTypeOptions(t), [t]);

  useEffect(() => {
    void (async () => {
      const [emps, workshops, lines] = await Promise.all([
        listEmployees({ status: 'active' }),
        loadOaWorkshopNameOptions(),
        loadOaProductionLineNameOptions(),
      ]);
      setEmployeeOptions(
        emps.items.map((e) => ({
          label: `${e.employee_code || ''} ${e.full_name}`.trim(),
          value: Number(e.id),
        })),
      );
      setWorkshopOptions(workshops);
      setLineOptions(lines.map(({ label, value }) => ({ label, value })));
    })();
  }, []);

  useEffect(() => {
    setModalOpen(false);
    actionRef.current?.reload();
  }, [mode]);

  const createButtonText = useMemo(
    () =>
      mode === 'night'
        ? t('app.kuaioa.attendance.nightRegisterCreate')
        : t('app.kuaioa.attendance.restRegisterCreate'),
    [mode, t],
  );

  const listHint = useMemo(
    () =>
      mode === 'night'
        ? t('app.kuaioa.attendance.nightRegisterHint')
        : t('app.kuaioa.attendance.restRegisterHint'),
    [mode, t],
  );

  const openCreate = useCallback(() => {
    if (!perms.canUpdate) {
      message.error(t('common.noPermission'));
      return;
    }
    form.resetFields();
    form.setFieldsValue({
      date_range: [dayjs(), dayjs()],
    });
    setModalOpen(true);
  }, [form, message, perms.canUpdate, t]);

  const handleFinish = useCallback(
    async (values: Record<string, unknown>) => {
      if (!perms.canUpdate) {
        message.error(t('common.noPermission'));
        return;
      }
      const workshopName = String(values.workshop_name || '').trim();
      if (!workshopName) {
        message.error(t('app.kuaioa.attendance.workshopRequired'));
        return;
      }
      const range = values.date_range as [Dayjs, Dayjs] | undefined;
      if (!range?.[0] || !range?.[1]) {
        message.error(t('app.kuaioa.attendance.workDateRangeRequired'));
        return;
      }
      const dateFrom = range[0].format('YYYY-MM-DD');
      const dateTo = range[1].format('YYYY-MM-DD');
      const employeeIds = Array.isArray(values.employee_ids)
        ? (values.employee_ids as number[]).map(Number).filter((id) => id > 0)
        : [];
      const employmentTypes = (
        Array.isArray(values.employment_types)
          ? values.employment_types
          : values.employment_types != null && values.employment_types !== ''
            ? [values.employment_types]
            : []
      )
        .map((v) => String(v).trim())
        .filter(Boolean);

      try {
        await createAttendanceDayRegister({
          register_type: mode,
          date_from: dateFrom,
          date_to: dateTo,
          workshop_name: workshopName,
          production_line_name: String(values.production_line_name || '').trim() || null,
          employment_types: employmentTypes.length > 0 ? employmentTypes : undefined,
          employee_ids: employeeIds.length > 0 ? employeeIds : undefined,
        });
        message.success(t('common.success'));
        setModalOpen(false);
        actionRef.current?.reload();
      } catch (error) {
        message.error(getApiErrorMessage(error));
        throw error;
      }
    },
    [message, mode, perms.canUpdate, t],
  );

  const columns = useMemo<ProColumns<Record<string, unknown>>[]>(() => {
    const base: ProColumns<Record<string, unknown>>[] = [
      {
        title: t('app.kuaioa.attendance.registerCode'),
        dataIndex: 'register_code',
        key: 'register_code',
        width: 150,
        copyable: true,
        uniTableKeepWidth: true,
      },
      {
        title: t('app.kuaioa.attendance.workDateRange'),
        key: 'date_range',
        dataIndex: 'date_from',
        width: 200,
        search: false,
        render: (_, record) => {
          const from = formatDateBySiteSetting(record.date_from as string, '');
          const to = formatDateBySiteSetting(record.date_to as string, '');
          if (!from && !to) return '-';
          // 区间列始终起止并排，起止同日也显示「日 ~ 日」，避免看起来像单日
          return `${from || '-'} ~ ${to || '-'}`;
        },
      },
      {
        title: t('app.kuaioa.attendance.workshop'),
        dataIndex: 'workshop_name',
        key: 'workshop_name',
        width: 140,
        uniTableKeepWidth: true,
      },
      {
        title: t('app.kuaioa.attendance.productionLine'),
        dataIndex: 'production_line_name',
        key: 'production_line_name',
        width: 120,
        search: false,
        uniTableKeepWidth: true,
        render: (v) => (v ? String(v) : '-'),
      },
      {
        title: t('app.kuaioa.employee.employmentTypeLabel'),
        dataIndex: 'employment_types',
        key: 'employment_types',
        width: 160,
        search: false,
        uniTableKeepWidth: true,
        render: (_, record) => {
          const raw = record.employment_types;
          const values = Array.isArray(raw)
            ? raw.map((v) => String(v ?? '').trim()).filter(Boolean)
            : [];
          if (values.length === 0) return t('app.kuaioa.attendance.employmentTypesAll');
          return values.map((code) => resolveOaEmploymentTypeLabel(code, t)).join('、');
        },
      },
      {
        title: t('app.kuaioa.attendance.employeeSummary'),
        dataIndex: 'employee_summary',
        key: 'employee_summary',
        width: 180,
        search: false,
        ellipsis: true,
        uniTableRemainderFlex: true,
      },
      {
        title: t('app.kuaioa.attendance.markedCellCount'),
        dataIndex: 'marked_cell_count',
        key: 'marked_cell_count',
        width: 100,
        search: false,
        uniTableKeepWidth: true,
      },
      ...buildDocumentAuditColumns(t),
    ];
    return alignProColumns(base, GLOBAL_DOC_LIST_FIELD_RANK);
  }, [t]);

  return (
    <ListPageTemplate>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
        {listHint}
      </Typography.Paragraph>
      <UniTable<Record<string, unknown>>
        actionRef={actionRef}
        rowKey="id"
        columnPersistenceId={
          mode === 'night'
            ? 'apps.kuaioa.attendance.night-register.list-v2'
            : 'apps.kuaioa.attendance.rest-register.list-v2'
        }
        columns={columns}
        permissionResource="kuaioa:attendance"
        showCreateButton={false}
        onCreate={perms.canUpdate ? openCreate : undefined}
        toolBarActionsBeforeCreate={
          perms.canUpdate
            ? [
                <Button key="create-register" type="primary" onClick={openCreate}>
                  {withSingleNewShortcutHint(createButtonText)}
                </Button>,
              ]
            : []
        }
        request={async (_params, _sort, _filter, searchFormValues) => {
          const res = await listAttendanceDayRegisters({
            register_type: mode,
            keyword: pickListSearchKeyword(searchFormValues),
          });
          return { data: res.items, success: true, total: res.total };
        }}
        showAdvancedSearch
      />

      <FormModalTemplate
        open={modalOpen}
        title={createButtonText}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        form={form}
        grid
        onClose={() => setModalOpen(false)}
        onFinish={handleFinish}
        submitText={t('common.confirm')}
      >
        <ProFormSelect
          name="workshop_name"
          label={t('app.kuaioa.attendance.workshop')}
          options={workshopOptions}
          rules={[{ required: true, message: t('app.kuaioa.attendance.workshopRequired') }]}
          fieldProps={{ showSearch: true, optionFilterProp: 'label', allowClear: true }}
          colProps={{ span: 12 }}
        />
        <ProFormSelect
          name="production_line_name"
          label={t('app.kuaioa.attendance.productionLineOptional')}
          options={lineOptions}
          fieldProps={{ showSearch: true, optionFilterProp: 'label', allowClear: true }}
          colProps={{ span: 12 }}
        />
        <ProFormSelect
          name="employment_types"
          label={t('app.kuaioa.employee.employmentTypeLabel')}
          options={employmentOptions}
          placeholder={t('app.kuaioa.attendance.employmentTypesOptional')}
          fieldProps={{
            mode: 'multiple',
            allowClear: true,
            showSearch: true,
            optionFilterProp: 'label',
          }}
          colProps={{ span: 12 }}
        />
        <ProFormDateRangePicker
          name="date_range"
          label={t('app.kuaioa.attendance.workDateRange')}
          rules={[{ required: true, message: t('app.kuaioa.attendance.workDateRangeRequired') }]}
          fieldProps={{ style: { width: '100%' } }}
          colProps={{ span: 12 }}
        />
        <ProFormSelect
          name="employee_ids"
          label={t('app.kuaioa.attendance.employeeOptional')}
          options={employeeOptions}
          fieldProps={{
            mode: 'multiple',
            allowClear: true,
            showSearch: true,
            optionFilterProp: 'label',
          }}
          colProps={{ span: 12 }}
        />
      </FormModalTemplate>
    </ListPageTemplate>
  );
};

export default AttendanceDayRegisterPage;
