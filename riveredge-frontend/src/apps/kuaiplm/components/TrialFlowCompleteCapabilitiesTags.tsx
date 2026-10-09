import React from 'react';
import { Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { MarkerTag } from '../../../constants/statusBadges';

export type TrialFlowCompleteCapabilities = {
  filled?: boolean;
  dept_approved?: boolean;
  results_done?: boolean;
  conclusions_done?: boolean;
  archived?: boolean;
};

type Props = {
  capabilities?: TrialFlowCompleteCapabilities | null;
  businessType?: string | null;
};

const CapItem: React.FC<{ ok: boolean; label: string }> = ({ ok, label }) => (
  <MarkerTag variant="filled" color={ok ? 'success' : 'default'}>
    {label}
  </MarkerTag>
);

export const TrialFlowCompleteCapabilitiesTags: React.FC<Props> = ({
  capabilities,
  businessType,
}) => {
  const { t } = useTranslation();
  if ((businessType || '').trim().toLowerCase() !== 'complete' || !capabilities) {
    return null;
  }
  return (
    <Space size={4} wrap>
      <CapItem ok={Boolean(capabilities.filled)} label={t('app.kuaiplm.trialFlow.capabilities.filled')} />
      <CapItem
        ok={Boolean(capabilities.dept_approved)}
        label={t('app.kuaiplm.trialFlow.capabilities.deptApproved')}
      />
      <CapItem
        ok={Boolean(capabilities.results_done)}
        label={t('app.kuaiplm.trialFlow.capabilities.resultsDone')}
      />
      <CapItem
        ok={Boolean(capabilities.conclusions_done)}
        label={t('app.kuaiplm.trialFlow.capabilities.conclusionsDone')}
      />
      <CapItem
        ok={Boolean(capabilities.archived)}
        label={t('app.kuaiplm.trialFlow.capabilities.archived')}
      />
    </Space>
  );
};
