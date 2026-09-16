import React, { useMemo } from 'react';
import KuaioaCrudListPage from '../../../components/KuaioaCrudListPage';
import {
  createMinimumWageConfig,
  deleteMinimumWageConfig,
  getMinimumWageConfig,
  listMinimumWageConfigs,
  updateMinimumWageConfig,
} from '../../../services/minimumWage';

const MinimumWagePage: React.FC = () => {
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

  return (
    <KuaioaCrudListPage
      createButtonKey="app.kuaioa.minimumWage.createButton"
      resource="kuaioa:minimum-wage"
      codeField="id"
      nameField="amount"
      statusPresentation="marker"
      detailVariant="master"
      getDetailFn={getMinimumWageConfig}
      columnPersistenceId="apps.kuaioa.minimum-wage.list-v1"
      fields={fields}
      listFn={listMinimumWageConfigs}
      createFn={createMinimumWageConfig}
      updateFn={updateMinimumWageConfig}
      deleteFn={deleteMinimumWageConfig}
    />
  );
};

export default MinimumWagePage;
