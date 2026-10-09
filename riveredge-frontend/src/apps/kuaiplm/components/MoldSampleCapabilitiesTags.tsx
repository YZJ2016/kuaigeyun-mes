import React from 'react';
import { Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { MarkerTag } from '../../../constants/statusBadges';

export type MoldSampleCapabilities = {
  file_uploaded?: boolean;
  submitted?: boolean;
  approved?: boolean;
  sealed?: boolean;
  archived?: boolean;
};

type Props = {
  capabilities?: MoldSampleCapabilities | null;
};

const CapItem: React.FC<{ ok: boolean; label: string }> = ({ ok, label }) => (
  <MarkerTag variant="filled" color={ok ? 'success' : 'default'}>
    {label}
  </MarkerTag>
);

export const MoldSampleCapabilitiesTags: React.FC<Props> = ({ capabilities }) => {
  const { t } = useTranslation();
  if (!capabilities) {
    return null;
  }
  return (
    <Space size={4} wrap>
      <CapItem
        ok={Boolean(capabilities.file_uploaded)}
        label={t('app.kuaiplm.moldSample.capabilities.fileUploaded')}
      />
      <CapItem
        ok={Boolean(capabilities.approved)}
        label={t('app.kuaiplm.moldSample.capabilities.approved')}
      />
      <CapItem
        ok={Boolean(capabilities.sealed)}
        label={t('app.kuaiplm.moldSample.capabilities.sealed')}
      />
      <CapItem
        ok={Boolean(capabilities.archived)}
        label={t('app.kuaiplm.moldSample.capabilities.archived')}
      />
    </Space>
  );
};
