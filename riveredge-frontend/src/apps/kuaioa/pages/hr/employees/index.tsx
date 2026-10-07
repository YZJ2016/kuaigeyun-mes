import React, { useEffect, useMemo, useState } from 'react';
import { App, List, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import KuaioaCrudListPage from '../../../components/KuaioaCrudListPage';
import { runKuaioaListExport } from '../../../utils/kuaioaListExport';
import {
  buildOaEmployeeStatusEnum,
  buildOaEmploymentTypeOptions,
  buildOaPayMethodOptions,
} from '../../../utils/oaFormEnums';
import { loadOaProductionLineNameOptions, loadOaWorkshopNameOptions } from '../../../utils/oaWorkshopOptions';
import {
  bulkCreateEmployees,
  createEmployee,
  deleteEmployee,
  getEmployee,
  listEmployees,
  updateEmployee,
} from '../../../services/employees';
import BoundAccountQuickCreate from './BoundAccountQuickCreate';
import {
  buildFactoryImportTemplate,
  resolveFactoryImportHeaderIndexMap,
} from '../../../../master-data/utils/factoryImportTemplate';
import { importInChunks } from '../../../../../utils/chunkedBulkImport';
import { getAntdModal } from '../../../../../utils/antdAppApis';
import { normalizeImportSpreadsheetDate } from '../../../../../utils/importSpreadsheetDate';

type OptionItem = { label: string; value: string };

function resolveOptionValue(raw: string, options: OptionItem[]): string | undefined {
  const trimmed = raw.trim();
  if (!trimmed) return undefined;
  const byValue = options.find((o) => o.value === trimmed);
  if (byValue) return byValue.value;
  const byLabel = options.find((o) => o.label === trimmed);
  if (byLabel) return byLabel.value;
  return undefined;
}

function parseOptionalNumber(raw: string): number | undefined {
  const trimmed = raw.trim();
  if (!trimmed) return undefined;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : undefined;
}

const EmployeesPage: React.FC = () => {
  const { t, i18n } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [workshopOptions, setWorkshopOptions] = useState<OptionItem[]>([]);
  const [lineOptions, setLineOptions] = useState<OptionItem[]>([]);

  const employmentOptions = useMemo(() => buildOaEmploymentTypeOptions(t), [t]);

  const payMethodOptions = useMemo(() => buildOaPayMethodOptions(t), [t]);

  const statusOptions = useMemo(
    () => [
      { label: t('app.kuaioa.employee.status.active'), value: 'active' },
      { label: t('app.kuaioa.employee.status.left'), value: 'left' },
    ],
    [t],
  );

  const statusEnum = useMemo(() => buildOaEmployeeStatusEnum(t), [t]);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([loadOaWorkshopNameOptions(), loadOaProductionLineNameOptions()])
      .then(([workshops, lines]) => {
        if (cancelled) return;
        setWorkshopOptions(workshops);
        setLineOptions(lines.map(({ label, value }) => ({ label, value })));
      })
      .catch(() => {
        if (cancelled) return;
        setWorkshopOptions([]);
        setLineOptions([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const employeeImportTemplate = useMemo(
    () =>
      buildFactoryImportTemplate(
        t,
        [
          {
            field: 'employee_code',
            labelKey: 'app.kuaioa.employee.code',
            aliases: ['员工编号', '工号', '编号'],
          },
          {
            field: 'full_name',
            required: true,
            labelKey: 'app.kuaioa.employee.fullName',
            aliases: ['姓名', '员工姓名'],
          },
          {
            field: 'department_name',
            labelKey: 'app.kuaioa.common.department',
            aliases: ['部门', '所属部门'],
          },
          {
            field: 'workshop_name',
            labelKey: 'app.kuaioa.employee.workshop',
            aliases: ['车间', '所属车间'],
          },
          {
            field: 'production_line_name',
            labelKey: 'app.kuaioa.employee.productionLine',
            aliases: ['产线'],
          },
          {
            field: 'employment_type',
            required: true,
            labelKey: 'app.kuaioa.employee.employmentType',
            aliases: ['用工类型'],
            options: employmentOptions.map((o) => o.label),
          },
          {
            field: 'pay_method',
            required: true,
            labelKey: 'app.kuaioa.employee.payMethod',
            aliases: ['计薪方式'],
            options: payMethodOptions.map((o) => o.label),
          },
          {
            field: 'phone',
            labelKey: 'app.kuaioa.employee.phone',
            aliases: ['电话', '手机', '联系电话'],
          },
          {
            field: 'hourly_rate',
            labelKey: 'app.kuaioa.employee.hourlyRate',
            aliases: ['计时单价'],
          },
          {
            field: 'hire_date',
            labelKey: 'app.kuaioa.employee.hireDate',
            aliases: ['入职日期', '入职时间'],
          },
          {
            field: 'leave_date',
            labelKey: 'app.kuaioa.employee.leaveDate',
            aliases: ['离职日期', '离职时间'],
          },
          {
            field: 'bank_account',
            labelKey: 'app.kuaioa.employee.bankAccount',
            aliases: ['工资卡号', '银行卡号'],
          },
          {
            field: 'bank_name',
            labelKey: 'app.kuaioa.employee.bankName',
            aliases: ['银行名称', '开户银行'],
          },
          {
            field: 'bank_branch',
            labelKey: 'app.kuaioa.employee.bankBranch',
            aliases: ['开户行'],
          },
          {
            field: 'living_allowance',
            labelKey: 'app.kuaioa.employee.livingAllowance',
          },
          {
            field: 'post_wage',
            labelKey: 'app.kuaioa.employee.postWage',
          },
          {
            field: 'social_insurance',
            labelKey: 'app.kuaioa.employee.socialInsurance',
          },
          {
            field: 'housing_fund',
            labelKey: 'app.kuaioa.employee.housingFund',
          },
          {
            field: 'rent_utility',
            labelKey: 'app.kuaioa.employee.rentUtility',
          },
          {
            field: 'welfare_dragon_boat',
            labelKey: 'app.kuaioa.employee.welfareDragonBoat',
          },
          {
            field: 'welfare_mid_autumn',
            labelKey: 'app.kuaioa.employee.welfareMidAutumn',
          },
          {
            field: 'welfare_spring_festival',
            labelKey: 'app.kuaioa.employee.welfareSpringFestival',
          },
          {
            field: 'status',
            labelKey: 'common.status',
            aliases: ['在职状态'],
            options: statusOptions.map((o) => o.label),
          },
          {
            field: 'notes',
            labelKey: 'common.remark',
            aliases: ['备注'],
          },
        ],
        [
          t('app.kuaioa.employee.importExample.employeeCode'),
          t('app.kuaioa.employee.importExample.fullName'),
          t('app.kuaioa.employee.importExample.department'),
          t('app.kuaioa.employee.importExample.workshop'),
          t('app.kuaioa.employee.importExample.productionLine'),
          t('app.kuaioa.employee.employmentType.formal'),
          t('app.kuaioa.employee.payMethod.time'),
          t('app.kuaioa.employee.importExample.phone'),
          t('app.kuaioa.employee.importExample.hourlyRate'),
          t('app.kuaioa.employee.importExample.hireDate'),
          '',
          t('app.kuaioa.employee.importExample.bankAccount'),
          t('app.kuaioa.employee.importExample.bankName'),
          t('app.kuaioa.employee.importExample.bankBranch'),
          t('app.kuaioa.employee.importExample.livingAllowance'),
          '',
          '',
          '',
          '',
          '',
          '',
          '',
          t('app.kuaioa.employee.status.active'),
          '',
        ],
      ),
    [employmentOptions, payMethodOptions, statusOptions, t, i18n.language],
  );

  const fields = useMemo(
    () => [
      { name: 'employee_code', labelKey: 'app.kuaioa.employee.code', width: 140 },
      {
        name: 'full_name',
        labelKey: 'app.kuaioa.employee.fullName',
        required: true,
        width: 120,
      },
      {
        name: 'department_name',
        labelKey: 'app.kuaioa.common.department',
        type: 'department' as const,
        width: 120,
      },
      {
        name: 'workshop_name',
        labelKey: 'app.kuaioa.employee.workshop',
        type: 'select' as const,
        options: workshopOptions,
        width: 120,
      },
      {
        name: 'production_line_name',
        labelKey: 'app.kuaioa.employee.productionLine',
        type: 'select' as const,
        options: lineOptions,
        width: 100,
        hideInTable: true,
      },
      {
        name: 'user_display',
        labelKey: 'app.kuaioa.employee.boundAccount',
        width: 150,
        hideInForm: true,
      },
      {
        name: 'user_id',
        labelKey: 'app.kuaioa.employee.boundAccount',
        type: 'userId' as const,
        hideInTable: true,
        hideInDetail: true,
        userIdFillNameField: 'full_name',
        userIdExtra: <BoundAccountQuickCreate />,
      },
      {
        name: 'employment_type',
        labelKey: 'app.kuaioa.employee.employmentType',
        type: 'select' as const,
        options: employmentOptions,
        required: true,
        width: 100,
      },
      {
        name: 'pay_method',
        labelKey: 'app.kuaioa.employee.payMethod',
        type: 'select' as const,
        options: payMethodOptions,
        required: true,
        width: 100,
      },
      { name: 'phone', labelKey: 'app.kuaioa.employee.phone', width: 120 },
      {
        name: 'hourly_rate',
        labelKey: 'app.kuaioa.employee.hourlyRate',
        type: 'number' as const,
        width: 100,
        hideInTable: true,
      },
      {
        name: 'hire_date',
        labelKey: 'app.kuaioa.employee.hireDate',
        type: 'date' as const,
        width: 120,
      },
      {
        name: 'leave_date',
        labelKey: 'app.kuaioa.employee.leaveDate',
        type: 'date' as const,
        width: 120,
        hideInTable: true,
      },
      {
        name: 'bank_account',
        labelKey: 'app.kuaioa.employee.bankAccount',
        width: 140,
        hideInTable: true,
      },
      {
        name: 'bank_name',
        labelKey: 'app.kuaioa.employee.bankName',
        width: 120,
        hideInTable: true,
      },
      {
        name: 'bank_branch',
        labelKey: 'app.kuaioa.employee.bankBranch',
        width: 160,
        hideInTable: true,
      },
      {
        name: 'living_allowance',
        labelKey: 'app.kuaioa.employee.livingAllowance',
        type: 'number' as const,
        width: 100,
        hideInTable: true,
      },
      {
        name: 'post_wage',
        labelKey: 'app.kuaioa.employee.postWage',
        type: 'number' as const,
        width: 100,
        hideInTable: true,
      },
      {
        name: 'social_insurance',
        labelKey: 'app.kuaioa.employee.socialInsurance',
        type: 'number' as const,
        width: 100,
        hideInTable: true,
      },
      {
        name: 'housing_fund',
        labelKey: 'app.kuaioa.employee.housingFund',
        type: 'number' as const,
        width: 100,
        hideInTable: true,
      },
      {
        name: 'rent_utility',
        labelKey: 'app.kuaioa.employee.rentUtility',
        type: 'number' as const,
        width: 100,
        hideInTable: true,
      },
      {
        name: 'welfare_dragon_boat',
        labelKey: 'app.kuaioa.employee.welfareDragonBoat',
        type: 'number' as const,
        hideInTable: true,
      },
      {
        name: 'welfare_mid_autumn',
        labelKey: 'app.kuaioa.employee.welfareMidAutumn',
        type: 'number' as const,
        hideInTable: true,
      },
      {
        name: 'welfare_spring_festival',
        labelKey: 'app.kuaioa.employee.welfareSpringFestival',
        type: 'number' as const,
        hideInTable: true,
      },
      {
        name: 'id_card_file_uuid',
        labelKey: 'app.kuaioa.employee.idCard',
        type: 'file' as const,
        hideInTable: true,
        formTab: 'attachments',
      },
      {
        name: 'labor_contract_file_uuid',
        labelKey: 'app.kuaioa.employee.laborContract',
        type: 'file' as const,
        hideInTable: true,
        formTab: 'attachments',
      },
      {
        name: 'medical_report_file_uuid',
        labelKey: 'app.kuaioa.employee.medicalReport',
        type: 'file' as const,
        hideInTable: true,
        formTab: 'attachments',
      },
      {
        name: 'education_cert_file_uuid',
        labelKey: 'app.kuaioa.employee.educationCert',
        type: 'file' as const,
        hideInTable: true,
        formTab: 'attachments',
      },
      {
        name: 'disability_cert_file_uuid',
        labelKey: 'app.kuaioa.employee.disabilityCert',
        type: 'file' as const,
        hideInTable: true,
        formTab: 'attachments',
      },
      {
        name: 'status',
        labelKey: 'common.status',
        type: 'select' as const,
        options: statusOptions,
        width: 100,
      },
      {
        name: 'notes',
        labelKey: 'common.remark',
        type: 'textarea' as const,
        hideInTable: true,
      },
    ],
    [employmentOptions, payMethodOptions, statusOptions, workshopOptions, lineOptions],
  );

  const handleImport = async (data: unknown[][]) => {
    if (!data || data.length === 0) {
      messageApi.warning(t('app.kuaioa.employee.importEmpty'));
      return false;
    }

    const headers = (data[0] || []).map((h) => String(h ?? '').trim());

    const headerIndexMap = resolveFactoryImportHeaderIndexMap(
      headers,
      employeeImportTemplate.importHeaderMap,
    );

    if (headerIndexMap.full_name === undefined) {
      messageApi.error(
        t('app.kuaioa.employee.importMissingField', {
          field: t('app.kuaioa.employee.fullName'),
        }),
      );
      return false;
    }

    const exampleFullName = t('app.kuaioa.employee.importExample.fullName').trim();
    let bodyRows = data.slice(1);
    if (
      bodyRows.length > 0 &&
      String(bodyRows[0][headerIndexMap.full_name] ?? '').trim() === exampleFullName
    ) {
      bodyRows = bodyRows.slice(1);
    }

    const nonEmptyRows = bodyRows.filter((row) => {
      if (!Array.isArray(row) || row.length === 0) return false;
      return row.some((cell) => String(cell ?? '').trim() !== '');
    });

    if (nonEmptyRows.length === 0) {
      messageApi.warning(t('app.kuaioa.employee.importNoRows'));
      return false;
    }

    const importData: Record<string, unknown>[] = [];
    const errors: Array<{ row: number; message: string }> = [];
    const seenEmployeeCodes = new Map<string, number>();

    nonEmptyRows.forEach((row, rowIndex) => {
      if (!Array.isArray(row)) return;
      const actualRowIndex = rowIndex + (data.length - bodyRows.length) + 1;
      const cell = (field: string) => {
        const idx = headerIndexMap[field];
        if (idx === undefined) return '';
        return String(row[idx] ?? '').trim();
      };
      const parseImportDateField = (
        field: 'hire_date' | 'leave_date',
        labelKey: string,
      ): string | undefined | null => {
        const idx = headerIndexMap[field];
        if (idx === undefined) return undefined;
        const raw = row[idx];
        const rawText = String(raw ?? '').trim();
        if (!rawText) return undefined;
        const normalized = normalizeImportSpreadsheetDate(raw);
        if (!normalized) {
          errors.push({
            row: actualRowIndex,
            message: t('app.kuaioa.employee.importDateInvalid', {
              field: t(labelKey),
              value: rawText,
            }),
          });
          return null;
        }
        return normalized;
      };

      const fullName = cell('full_name');
      if (!fullName) {
        errors.push({ row: actualRowIndex, message: t('app.kuaioa.employee.importNameRequired') });
        return;
      }

      const employmentRaw = cell('employment_type');
      const employmentType = employmentRaw
        ? resolveOptionValue(employmentRaw, employmentOptions)
        : 'formal';
      if (employmentRaw && !employmentType) {
        errors.push({
          row: actualRowIndex,
          message: t('app.kuaioa.employee.importEmploymentInvalid'),
        });
        return;
      }

      const payMethodRaw = cell('pay_method');
      const payMethod = payMethodRaw
        ? resolveOptionValue(payMethodRaw, payMethodOptions)
        : 'time';
      if (payMethodRaw && !payMethod) {
        errors.push({
          row: actualRowIndex,
          message: t('app.kuaioa.employee.importPayMethodInvalid'),
        });
        return;
      }

      const statusRaw = cell('status');
      let status: string | undefined;
      if (statusRaw) {
        status = resolveOptionValue(statusRaw, statusOptions);
        if (!status) {
          errors.push({
            row: actualRowIndex,
            message: t('app.kuaioa.employee.importStatusInvalid'),
          });
          return;
        }
      }

      const employeeCode = cell('employee_code');
      if (employeeCode) {
        const prevRow = seenEmployeeCodes.get(employeeCode);
        if (prevRow !== undefined) {
          errors.push({
            row: actualRowIndex,
            message: t('app.kuaioa.employee.importEmployeeCodeDuplicate', {
              code: employeeCode,
            }),
          });
          return;
        }
        seenEmployeeCodes.set(employeeCode, actualRowIndex);
      }

      const payload: Record<string, unknown> = {
        full_name: fullName,
        employment_type: employmentType,
        pay_method: payMethod,
      };
      if (employeeCode) payload.employee_code = employeeCode;

      const departmentName = cell('department_name');
      if (departmentName) payload.department_name = departmentName;
      const workshopName = cell('workshop_name');
      if (workshopName) payload.workshop_name = workshopName;
      const productionLineName = cell('production_line_name');
      if (productionLineName) payload.production_line_name = productionLineName;
      const phone = cell('phone');
      if (phone) payload.phone = phone;
      const hireDate = parseImportDateField('hire_date', 'app.kuaioa.employee.hireDate');
      if (hireDate === null) return;
      if (hireDate) payload.hire_date = hireDate;
      const leaveDate = parseImportDateField('leave_date', 'app.kuaioa.employee.leaveDate');
      if (leaveDate === null) return;
      if (leaveDate) payload.leave_date = leaveDate;
      const bankAccount = cell('bank_account');
      if (bankAccount) payload.bank_account = bankAccount;
      const bankName = cell('bank_name');
      if (bankName) payload.bank_name = bankName;
      const bankBranch = cell('bank_branch');
      if (bankBranch) payload.bank_branch = bankBranch;
      const notes = cell('notes');
      if (notes) payload.notes = notes;
      if (status) payload.status = status;

      const hourlyRate = parseOptionalNumber(cell('hourly_rate'));
      if (hourlyRate !== undefined) payload.hourly_rate = hourlyRate;
      const livingAllowance = parseOptionalNumber(cell('living_allowance'));
      if (livingAllowance !== undefined) payload.living_allowance = livingAllowance;
      const postWage = parseOptionalNumber(cell('post_wage'));
      if (postWage !== undefined) payload.post_wage = postWage;
      const socialInsurance = parseOptionalNumber(cell('social_insurance'));
      if (socialInsurance !== undefined) payload.social_insurance = socialInsurance;
      const housingFund = parseOptionalNumber(cell('housing_fund'));
      if (housingFund !== undefined) payload.housing_fund = housingFund;
      const rentUtility = parseOptionalNumber(cell('rent_utility'));
      if (rentUtility !== undefined) payload.rent_utility = rentUtility;
      const welfareDragonBoat = parseOptionalNumber(cell('welfare_dragon_boat'));
      if (welfareDragonBoat !== undefined) payload.welfare_dragon_boat = welfareDragonBoat;
      const welfareMidAutumn = parseOptionalNumber(cell('welfare_mid_autumn'));
      if (welfareMidAutumn !== undefined) payload.welfare_mid_autumn = welfareMidAutumn;
      const welfareSpringFestival = parseOptionalNumber(cell('welfare_spring_festival'));
      if (welfareSpringFestival !== undefined) {
        payload.welfare_spring_festival = welfareSpringFestival;
      }

      importData.push(payload);
    });

    if (errors.length > 0) {
      getAntdModal().warning({
        title: t('app.kuaioa.employee.importValidationTitle'),
        width: 600,
        content: (
          <div>
            <p>{t('app.kuaioa.employee.importValidationIntro')}</p>
            <List
              size="small"
              dataSource={errors}
              renderItem={(item) => (
                <List.Item>
                  <Typography.Text type="danger">
                    {t('app.kuaioa.employee.rowError', {
                      row: item.row,
                      message: item.message,
                    })}
                  </Typography.Text>
                </List.Item>
              )}
            />
          </div>
        ),
      });
      return false;
    }

    if (importData.length === 0) {
      messageApi.warning(t('app.kuaioa.employee.importNoRows'));
      return false;
    }

    try {
      const result = await importInChunks({
        items: importData,
        title: t('app.kuaioa.employee.importTitle'),
        chunkSize: 100,
        rowNumberForIndex: (i) => i + (data.length - bodyRows.length) + 1,
        showResultModal: false,
        importChunk: async (chunk) => {
          const res = await bulkCreateEmployees(chunk);
          return {
            createdCount: res.createdCount,
            failedItems: res.failedItems,
          };
        },
      });

      if (result.failureCount > 0) {
        getAntdModal().warning({
          title: t('app.kuaioa.employee.importPartialTitle'),
          width: 600,
          content: (
            <div>
              <p>
                <strong>
                  {t('app.kuaioa.employee.importPartialIntro', {
                    success: result.successCount,
                    failure: result.failureCount,
                  })}
                </strong>
              </p>
              <List
                size="small"
                dataSource={result.errors}
                renderItem={(item) => (
                  <List.Item>
                    <Typography.Text type="danger">
                      {t('app.kuaioa.employee.rowError', {
                        row: item.row,
                        message: item.error,
                      })}
                    </Typography.Text>
                  </List.Item>
                )}
              />
            </div>
          ),
        });
      } else {
        messageApi.success(
          t('app.kuaioa.employee.importSuccess', { count: result.successCount }),
        );
      }
      return result.failureCount === 0;
    } catch (error: unknown) {
      const err = error as { message?: string };
      messageApi.error(err?.message || t('common.importFailed'));
      return false;
    }
  };

  return (
    <KuaioaCrudListPage
      createButtonKey="app.kuaioa.employee.createButton"
      resource="kuaioa:employee"
      codeField="employee_code"
      nameField="full_name"
      autoGenerateCode
      statusPresentation="marker"
      statusEnum={statusEnum}
      detailVariant="master"
      getDetailFn={getEmployee}
      columnPersistenceId="apps.kuaioa.employee.list-v2"
      fields={fields}
      formTabs={[
        { key: 'basic', labelKey: 'app.kuaioa.employee.tabBasic' },
        { key: 'attachments', labelKey: 'app.kuaioa.employee.tabAttachments' },
      ]}
      listFn={listEmployees}
      createFn={createEmployee}
      updateFn={updateEmployee}
      deleteFn={deleteEmployee}
      mapFormValuesToPayload={(values) => {
        const { user_display: _userDisplay, ...rest } = values;
        return { ...rest, user_id: values.user_id ?? null };
      }}
      showImportButton
      onImport={handleImport}
      importHeaders={employeeImportTemplate.importHeaders}
      importExampleRow={employeeImportTemplate.importExampleRow}
      importColumnOptions={employeeImportTemplate.importColumnOptions}
      importFieldMap={employeeImportTemplate.importHeaderMap}
      importTemplateName={t('app.kuaioa.employee.exportFileName')}
      importTemplateRevision="kuaioa-employee-v20260929-code"
      showExportButton
      onExport={async (type, keys, pageData) => {
        await runKuaioaListExport({
          type,
          keys,
          pageData,
          listFn: listEmployees,
          columns: [
            { key: 'employee_code', title: t('app.kuaioa.employee.code') },
            { key: 'full_name', title: t('app.kuaioa.employee.fullName') },
            { key: 'workshop_name', title: t('app.kuaioa.attendance.workshop') },
            { key: 'hire_date', title: t('app.kuaioa.employee.hireDate') },
            { key: 'leave_date', title: t('app.kuaioa.employee.leaveDate') },
            { key: 'status', title: t('common.status') },
          ],
          filename: t('app.kuaioa.employee.exportFileName'),
          messageApi,
          noDataText: t('common.exportNoData'),
        });
      }}
    />
  );
};

export default EmployeesPage;
