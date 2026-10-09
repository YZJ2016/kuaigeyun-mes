import React from 'react';
import { Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { MarkerTag } from '../../../constants/statusBadges';

export type PrototypeBuildCapabilities = {
  project_ready?: boolean;
  electronics_ready?: boolean;
  structure_ready?: boolean;
  approved?: boolean;
  issued?: boolean;
  signoffs_done?: boolean;
  closed?: boolean;
};

type Props = {
  capabilities?: PrototypeBuildCapabilities | null;
};

const CapItem: React.FC<{ ok: boolean; label: string }> = ({ ok, label }) => (
  <MarkerTag variant="filled" color={ok ? 'success' : 'default'}>
    {label}
  </MarkerTag>
);

export const PrototypeBuildCapabilitiesTags: React.FC<Props> = ({ capabilities }) => {
  const { t } = useTranslation();
  if (!capabilities) {
    return null;
  }
  return (
    <Space size={4} wrap>
      <CapItem
        ok={Boolean(capabilities.project_ready)}
        label={t('app.kuaiplm.prototypeBuildSheet.capabilities.projectReady')}
      />
      <CapItem
        ok={Boolean(capabilities.electronics_ready)}
        label={t('app.kuaiplm.prototypeBuildSheet.capabilities.electronicsReady')}
      />
      <CapItem
        ok={Boolean(capabilities.structure_ready)}
        label={t('app.kuaiplm.prototypeBuildSheet.capabilities.structureReady')}
      />
      <CapItem
        ok={Boolean(capabilities.approved)}
        label={t('app.kuaiplm.prototypeBuildSheet.capabilities.approved')}
      />
      <CapItem
        ok={Boolean(capabilities.issued)}
        label={t('app.kuaiplm.prototypeBuildSheet.capabilities.issued')}
      />
      <CapItem
        ok={Boolean(capabilities.signoffs_done)}
        label={t('app.kuaiplm.prototypeBuildSheet.capabilities.signoffsDone')}
      />
    </Space>
  );
};
