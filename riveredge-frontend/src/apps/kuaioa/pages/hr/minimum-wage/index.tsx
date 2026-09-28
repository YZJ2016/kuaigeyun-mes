import React, { useMemo } from 'react';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import KuaioaCrudListPage from '../../../components/KuaioaCrudListPage';
import {
  createMinimumWageConfig,
  deleteMinimumWageConfig,
  getMinimumWageConfig,
  listMinimumWageConfigs,
  updateMinimumWageConfig,
} from '../../../services/minimumWage';
import { runKuaioaListExport } from '../../../utils/kuaioaListExport';
import { buildFactoryImportTemplate } from '../../../../master-data/utils/factoryImportTemplate';
import {
  buildOaImportCellReader,
  collectOaImportNonEmptyRows,
  runOaChunkedCreateImport,
  showOaImportValidationErrors,
  type OaImportRowError,
} from '../../../utils/kuaioaSpreadsheetImport';

const MinimumWagePage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();

  const fields = useMemo(
    () => [
      {
        name: 'amount',
        labelKey: 'app.kuaioa.minimumWage.amount',
        type: 'number' as const,
        required: true,
        width: 120,
      },
      {
        name: 'effective_date',
        labelKey: 'app.kuaioa.minimumWage.effectiveDate',
        type: 'date' as const,
        required: true,
        width: 120,
      },
      { name: 'notes', labelKey: 'common.remark', type: 'textarea' as const, hideInTable: true },
    ],
    [],
  );

  const importTemplate = useMemo(
    () =>
      buildFactoryImportTemplate(
        t,
        [
          {
            field: 'amount',
            required: true,
            labelKey: 'app.kuaioa.minimumWage.amount',
            aliases: ['金额', '最低工资'],
          },
          {
            field: 'effective_date',
            required: true,
            labelKey: 'app.kuaioa.minimumWage.effectiveDate',
            aliases: ['生效日期', '执行开始时间'],
          },
          { field: 'notes', labelKey: 'common.remark', aliases: ['备注'] },
        ],
        ['2490', '2026-01-01', ''],
      ),
    [t],
  );

  const handleImport = async (data: unknown[][]) => {
    const parsed = collectOaImportNonEmptyRows(data);
    if (!parsed) {
      messageApi.warning(t('app.kuaioa.import.empty'));
      return false;
    }
    if (parsed.rows.length === 0) {
      messageApi.warning(t('app.kuaioa.import.noRows'));
      return false;
    }
    const cellOf = buildOaImportCellReader(parsed.headers, importTemplate.importHeaderMap);
    const importData: Record<string, unknown>[] = [];
    const errors: OaImportRowError[] = [];
    parsed.rows.forEach((row, rowIndex) => {
      if (!Array.isArray(row)) return;
      const actualRowIndex = rowIndex + 3;
      const amount = Number(cellOf(row, 'amount'));
      if (!Number.isFinite(amount)) {
        errors.push({ row: actualRowIndex, message: t('app.kuaioa.import.amountInvalid') });
        return;
      }
      const effectiveDate = cellOf(row, 'effective_date');
      if (!effectiveDate) {
        errors.push({
          row: actualRowIndex,
          message: t('app.kuaioa.import.missingField', {
            field: t('app.kuaioa.minimumWage.effectiveDate'),
          }),
        });
        return;
      }
      importData.push({
        amount,
        effective_date: effectiveDate,
        notes: cellOf(row, 'notes') || undefined,
      });
    });
    if (errors.length > 0) {
      showOaImportValidationErrors(t, errors);
      return false;
    }
    return runOaChunkedCreateImport({
      t,
      messageApi,
      items: importData,
      createOne: (item) => createMinimumWageConfig(item),
      title: t('app.kuaioa.minimumWage.importTitle'),
      successKey: 'app.kuaioa.minimumWage.importSuccess',
    });
  };

  return (
    <KuaioaCrudListPage
      createButtonKey="app.kuaioa.minimumWage.createButton"
      resource="kuaioa:minimum-wage"
      codeField="id"
      nameField="amount"
      statusPresentation="marker"
      detailVariant="master"
      getDetailFn={getMinimumWageConfig}
      columnPersistenceId="apps.kuaioa.minimum-wage.list-v2"
      fields={fields}
      listFn={listMinimumWageConfigs}
      createFn={createMinimumWageConfig}
      updateFn={updateMinimumWageConfig}
      deleteFn={deleteMinimumWageConfig}
      showExportButton
      onExport={async (type, keys, pageData) => {
        await runKuaioaListExport({
          type,
          keys,
          pageData,
          listFn: listMinimumWageConfigs,
          columns: [
            { key: 'amount', title: t('app.kuaioa.minimumWage.amount') },
            { key: 'effective_date', title: t('app.kuaioa.minimumWage.effectiveDate') },
            { key: 'notes', title: t('common.remark') },
          ],
          filename: t('app.kuaioa.minimumWage.exportFileName'),
          messageApi,
          noDataText: t('common.exportNoData'),
        });
      }}
      showImportButton
      onImport={handleImport}
      importHeaders={importTemplate.importHeaders}
      importExampleRow={importTemplate.importExampleRow}
      importColumnOptions={importTemplate.importColumnOptions}
      importFieldMap={importTemplate.importHeaderMap}
      importTemplateName={t('app.kuaioa.minimumWage.exportFileName')}
    />
  );
};

export default MinimumWagePage;
