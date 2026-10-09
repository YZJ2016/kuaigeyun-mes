import React from 'react';
import { Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { MarkerTag } from '../../../constants/statusBadges';

export type EcnCapabilities = {
  is_design_change_request?: boolean;
  request_ready?: boolean;
  issued_to_rd?: boolean;
  rd_ready?: boolean;
  signoffs_done?: boolean;
  approved?: boolean;
  erp_closed?: boolean;
};

type Props = {
  capabilities?: EcnCapabilities | null;
};

const CapItem: React.FC<{ ok: boolean; label: string }> = ({ ok, label }) => (
  <MarkerTag variant="filled" color={ok ? 'success' : 'default'}>
    {label}
  </MarkerTag>
);

export const EcnCapabilitiesTags: React.FC<Props> = ({ capabilities }) => {
  const { t } = useTranslation();
  if (!capabilities) {
    return null;
  }
  if (capabilities.is_design_change_request) {
    return (
      <Space size={4} wrap>
        <CapItem
          ok={Boolean(capabilities.request_ready)}
          label={t('app.kuaiplm.designChangeRequest.capabilities.requestReady')}
        />
        <CapItem
          ok={Boolean(capabilities.approved)}
          label={t('app.kuaiplm.designChangeRequest.capabilities.approved')}
        />
        <CapItem
          ok={Boolean(capabilities.issued_to_rd)}
          label={t('app.kuaiplm.designChangeRequest.capabilities.issuedToRd')}
        />
        {capabilities.issued_to_rd ? (
          <>
            <CapItem
              ok={Boolean(capabilities.rd_ready)}
              label={t('app.kuaiplm.ecn.capabilities.rdReady')}
            />
            <CapItem
              ok={Boolean(capabilities.signoffs_done)}
              label={t('app.kuaiplm.ecn.capabilities.signoffsDone')}
            />
            <CapItem
              ok={Boolean(capabilities.erp_closed)}
              label={t('app.kuaiplm.ecn.capabilities.erpClosed')}
            />
          </>
        ) : null}
      </Space>
    );
  }
  return (
    <Space size={4} wrap>
      <CapItem ok={Boolean(capabilities.rd_ready)} label={t('app.kuaiplm.ecn.capabilities.rdReady')} />
      <CapItem
        ok={Boolean(capabilities.signoffs_done)}
        label={t('app.kuaiplm.ecn.capabilities.signoffsDone')}
      />
      <CapItem ok={Boolean(capabilities.approved)} label={t('app.kuaiplm.ecn.capabilities.approved')} />
      <CapItem ok={Boolean(capabilities.erp_closed)} label={t('app.kuaiplm.ecn.capabilities.erpClosed')} />
    </Space>
  );
};
