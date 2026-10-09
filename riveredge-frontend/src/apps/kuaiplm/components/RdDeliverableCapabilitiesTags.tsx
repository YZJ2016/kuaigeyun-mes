import React from 'react';
import { useTranslation } from 'react-i18next';
import { Space } from 'antd';
import { CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { MarkerTag } from '../../../constants/statusBadges';
import type { RdProjectDeliverableCapabilities } from '../services/rd-project';

type Props = {
  capabilities?: RdProjectDeliverableCapabilities | null;
};

const CapItem: React.FC<{ ok: boolean; label: string }> = ({ ok, label }) => (
  <MarkerTag color={ok ? 'success' : 'default'} variant="filled">
    {ok ? <CheckOutlined /> : <CloseOutlined />} {label}
  </MarkerTag>
);

export const RdDeliverableCapabilitiesTags: React.FC<Props> = ({ capabilities }) => {
  const { t } = useTranslation();
  if (!capabilities) return null;
  return (
    <Space size={4} wrap>
      <CapItem
        ok={capabilities.uploaded}
        label={t('app.kuaiplm.rdDeliverables.capabilities.uploaded')}
      />
      <CapItem
        ok={capabilities.approved}
        label={t('app.kuaiplm.rdDeliverables.capabilities.approved')}
      />
      <CapItem
        ok={capabilities.issued}
        label={t('app.kuaiplm.rdDeliverables.capabilities.issued')}
      />
      <CapItem
        ok={capabilities.can_download}
        label={t('app.kuaiplm.rdDeliverables.capabilities.canDownload')}
      />
    </Space>
  );
};
