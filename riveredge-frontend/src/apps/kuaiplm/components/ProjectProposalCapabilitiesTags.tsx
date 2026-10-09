import React from 'react';
import { Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { MarkerTag } from '../../../constants/statusBadges';

export type ProjectProposalCapabilities = {
  sales_ready?: boolean;
  supplier_filled?: boolean;
  approved?: boolean;
  issued?: boolean;
};

type Props = {
  capabilities?: ProjectProposalCapabilities | null;
};

const CapItem: React.FC<{ ok: boolean; label: string }> = ({ ok, label }) => (
  <MarkerTag variant="filled" color={ok ? 'success' : 'default'}>
    {label}
  </MarkerTag>
);

export const ProjectProposalCapabilitiesTags: React.FC<Props> = ({ capabilities }) => {
  const { t } = useTranslation();
  if (!capabilities) {
    return null;
  }
  return (
    <Space size={4} wrap>
      <CapItem
        ok={Boolean(capabilities.sales_ready)}
        label={t('app.kuaiplm.projectProposal.capabilities.salesReady')}
      />
      <CapItem
        ok={Boolean(capabilities.supplier_filled)}
        label={t('app.kuaiplm.projectProposal.capabilities.supplierFilled')}
      />
      <CapItem
        ok={Boolean(capabilities.approved)}
        label={t('app.kuaiplm.projectProposal.capabilities.approved')}
      />
      <CapItem
        ok={Boolean(capabilities.issued)}
        label={t('app.kuaiplm.projectProposal.capabilities.issued')}
      />
    </Space>
  );
};
