import React from 'react';
import { Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { MarkerTag } from '../../../constants/statusBadges';
import type { BomCollabCapabilities } from '../services/bom-collaboration';

type Props = {
  capabilities?: BomCollabCapabilities | null;
};

const CapItem: React.FC<{ ok: boolean; label: string }> = ({ ok, label }) => (
  <MarkerTag variant="filled" color={ok ? 'success' : 'default'}>
    {label}
  </MarkerTag>
);

export const BomCollabCapabilitiesTags: React.FC<Props> = ({ capabilities }) => {
  const { t } = useTranslation();
  if (!capabilities) return null;
  return (
    <Space size={4} wrap>
      <CapItem
        ok={Boolean(capabilities.electronics_ready)}
        label={t('app.kuaiplm.bomCollab.capabilities.electronicsReady')}
      />
      <CapItem
        ok={Boolean(capabilities.structure_ready)}
        label={t('app.kuaiplm.bomCollab.capabilities.structureReady')}
      />
      <CapItem
        ok={Boolean(capabilities.approved)}
        label={t('app.kuaiplm.bomCollab.capabilities.approved')}
      />
      <CapItem
        ok={Boolean(capabilities.clerk_entered)}
        label={t('app.kuaiplm.bomCollab.capabilities.clerkEntered')}
      />
    </Space>
  );
};
