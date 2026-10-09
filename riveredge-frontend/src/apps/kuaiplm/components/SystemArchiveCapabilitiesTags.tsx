import React from 'react';
import { Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { MarkerTag } from '../../../constants/statusBadges';

export type SystemArchiveCapabilities = {
  checklist_ready?: boolean;
  upload_link_started?: boolean;
  checklist_complete?: boolean;
  all_accepted?: boolean;
};

type Props = {
  capabilities?: SystemArchiveCapabilities | null;
  /** 列表窄列可只显示分数 */
  compact?: boolean;
  filled?: number;
  total?: number;
};

const CapItem: React.FC<{ ok: boolean; label: string }> = ({ ok, label }) => (
  <MarkerTag variant="filled" color={ok ? 'success' : 'default'}>
    {label}
  </MarkerTag>
);

export const SystemArchiveCapabilitiesTags: React.FC<Props> = ({
  capabilities,
  compact,
  filled,
  total,
}) => {
  const { t } = useTranslation();
  if (!capabilities) {
    if (compact && total != null && filled != null) {
      return (
        <span>
          {t('app.kuaiplm.rdProjects.systemArchive.listCell', { filled, total })}
        </span>
      );
    }
    return null;
  }
  if (compact) {
    return (
      <Space size={4} wrap direction="vertical" style={{ lineHeight: 1.3 }}>
        <span>
          {t('app.kuaiplm.rdProjects.systemArchive.listCell', {
            filled: filled ?? 0,
            total: total ?? 0,
          })}
        </span>
        <Space size={4} wrap>
          <CapItem
            ok={Boolean(capabilities.checklist_complete)}
            label={t('app.kuaiplm.rdProjects.systemArchive.capabilities.checklistComplete')}
          />
          <CapItem
            ok={Boolean(capabilities.all_accepted)}
            label={t('app.kuaiplm.rdProjects.systemArchive.capabilities.allAccepted')}
          />
        </Space>
      </Space>
    );
  }
  return (
    <Space size={4} wrap>
      <CapItem
        ok={Boolean(capabilities.checklist_ready)}
        label={t('app.kuaiplm.rdProjects.systemArchive.capabilities.checklistReady')}
      />
      <CapItem
        ok={Boolean(capabilities.upload_link_started)}
        label={t('app.kuaiplm.rdProjects.systemArchive.capabilities.uploadLinkStarted')}
      />
      <CapItem
        ok={Boolean(capabilities.checklist_complete)}
        label={t('app.kuaiplm.rdProjects.systemArchive.capabilities.checklistComplete')}
      />
      <CapItem
        ok={Boolean(capabilities.all_accepted)}
        label={t('app.kuaiplm.rdProjects.systemArchive.capabilities.allAccepted')}
      />
    </Space>
  );
};
