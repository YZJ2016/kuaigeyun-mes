import React from 'react';
import { useTranslation } from 'react-i18next';
import { Space } from 'antd';
import { CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { MarkerTag } from '../../../constants/statusBadges';
import type { FormRequestCapabilities } from '../services/forms';

type Props = {
  capabilities?: FormRequestCapabilities | null;
  /** L55 确认书展示「回答」勾选 */
  showResponded?: boolean;
  /** L56 评审单展示「会签对象」勾选 */
  showCountersignSelected?: boolean;
};

const CapItem: React.FC<{ ok: boolean; label: string }> = ({ ok, label }) => (
  <MarkerTag color={ok ? 'success' : 'default'} variant="filled">
    {ok ? <CheckOutlined /> : <CloseOutlined />} {label}
  </MarkerTag>
);

export const FormRequestCapabilitiesTags: React.FC<Props> = ({
  capabilities,
  showResponded = false,
  showCountersignSelected = false,
}) => {
  const { t } = useTranslation();
  if (!capabilities) return null;
  return (
    <Space size={4} wrap>
      <CapItem ok={capabilities.uploaded} label={t('app.kuaioa.formRequest.capabilities.uploaded')} />
      <CapItem ok={capabilities.approved} label={t('app.kuaioa.formRequest.capabilities.approved')} />
      <CapItem ok={capabilities.issued} label={t('app.kuaioa.formRequest.capabilities.issued')} />
      <CapItem
        ok={capabilities.can_download}
        label={t('app.kuaioa.formRequest.capabilities.canDownload')}
      />
      {showResponded ? (
        <CapItem
          ok={Boolean(capabilities.responded)}
          label={t('app.kuaioa.formRequest.capabilities.responded')}
        />
      ) : null}
      {showCountersignSelected ? (
        <CapItem
          ok={Boolean(capabilities.countersign_selected)}
          label={t('app.kuaioa.formRequest.capabilities.countersignSelected')}
        />
      ) : null}
    </Space>
  );
};
