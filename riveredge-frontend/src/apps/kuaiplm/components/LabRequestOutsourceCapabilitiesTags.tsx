import React from 'react';
import { Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { MarkerTag } from '../../../constants/statusBadges';

export type LabRequestOutsourceCapabilities = {
  filled?: boolean;
  dept_approved?: boolean;
  price_filled?: boolean;
  lab_accepted?: boolean;
};

type Props = {
  capabilities?: LabRequestOutsourceCapabilities | null;
  businessType?: string | null;
};

const CapItem: React.FC<{ ok: boolean; label: string }> = ({ ok, label }) => (
  <MarkerTag variant="filled" color={ok ? 'success' : 'default'}>
    {label}
  </MarkerTag>
);

export const LabRequestOutsourceCapabilitiesTags: React.FC<Props> = ({
  capabilities,
  businessType,
}) => {
  const { t } = useTranslation();
  if ((businessType || '').trim().toLowerCase() !== 'outsource' || !capabilities) {
    return null;
  }
  return (
    <Space size={4} wrap>
      <CapItem ok={Boolean(capabilities.filled)} label={t('app.kuaiplm.labRequest.capabilities.filled')} />
      <CapItem
        ok={Boolean(capabilities.dept_approved)}
        label={t('app.kuaiplm.labRequest.capabilities.deptApproved')}
      />
      <CapItem
        ok={Boolean(capabilities.price_filled)}
        label={t('app.kuaiplm.labRequest.capabilities.priceFilled')}
      />
      <CapItem
        ok={Boolean(capabilities.lab_accepted)}
        label={t('app.kuaiplm.labRequest.capabilities.labAccepted')}
      />
    </Space>
  );
};
