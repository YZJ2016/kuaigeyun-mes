import React, { useMemo, useState } from 'react';
import { MobileOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Dropdown, Spin, Tooltip, Typography, theme } from 'antd';
import { QRCodeSVG } from 'qrcode.react';
import { useTranslation } from 'react-i18next';
import { useCurrentUser } from '../../hooks/useCurrentUser';

import {
  getClientDownloadQrOrigin,
  getTenantClientDownloads,
  getTenantHeaderMiniprogramQr,
  type TenantClientDownload,
} from '../../services/clientRelease';
import { normalizeFilePreviewUrl } from '../../services/file';
import { getTenantId } from '../../utils/auth';
import {
  isLoopbackDownloadUrl,
  isPageLoopback,
  resolvePublicDownloadUrl,
} from '../../utils/resolvePublicDownloadUrl';

const { Text } = Typography;

const QR_SIZE = 136;
const TITLE_MIN_HEIGHT = 20;
const FOOTER_MIN_HEIGHT = 36;

function formatFileSize(bytes?: number | null): string {
  if (bytes == null || bytes <= 0) return '';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function QrCodeColumn({
  title,
  hint,
  footerExtra,
  children,
}: {
  title: React.ReactNode;
  hint?: React.ReactNode;
  footerExtra?: React.ReactNode;
  children: React.ReactNode;
}) {
  const { token } = theme.useToken();

  return (
    <div
      style={{
        flex: '1 1 0',
        minWidth: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'stretch',
        padding: '0 6px',
      }}
    >
      <Text
        strong
        style={{
          display: 'block',
          textAlign: 'center',
          fontSize: 13,
          lineHeight: `${TITLE_MIN_HEIGHT}px`,
          minHeight: TITLE_MIN_HEIGHT,
        }}
      >
        {title}
      </Text>
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          marginTop: 10,
          background: token.colorBgContainer,
          padding: 10,
          borderRadius: token.borderRadius,
          border: `1px solid ${token.colorBorderSecondary}`,
          minHeight: QR_SIZE + 20,
        }}
      >
        {children}
      </div>
      <div
        style={{
          minHeight: FOOTER_MIN_HEIGHT,
          marginTop: 8,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'flex-start',
          gap: 2,
        }}
      >
        {hint ? (
          <Text type="secondary" style={{ textAlign: 'center', fontSize: 11, lineHeight: 1.45 }}>
            {hint}
          </Text>
        ) : null}
        {footerExtra ? (
          <Text type="secondary" style={{ textAlign: 'center', fontSize: 11, lineHeight: 1.45 }}>
            {footerExtra}
          </Text>
        ) : null}
      </div>
    </div>
  );
}

function MiniprogramQrColumn({ imageUrl }: { imageUrl: string }) {
  const { t } = useTranslation();

  return (
    <QrCodeColumn title={t('ui.header.miniprogramQr.title')} hint={t('ui.header.miniprogramQr.hint')}>
      <img
        src={imageUrl}
        alt={t('ui.header.miniprogramQr.title')}
        width={QR_SIZE}
        height={QR_SIZE}
        style={{ objectFit: 'contain', display: 'block' }}
      />
    </QrCodeColumn>
  );
}

function DownloadQrColumn({
  item,
  qrOrigin,
  originLoading,
}: {
  item: TenantClientDownload;
  qrOrigin?: string;
  originLoading: boolean;
}) {
  const { t } = useTranslation();
  const downloadUrl = resolvePublicDownloadUrl(item.url, qrOrigin);
  const sizeLabel = formatFileSize(item.size_bytes);
  const footerExtra = sizeLabel ? `v${item.app_version}，${sizeLabel}` : `v${item.app_version}`;
  const blocked = isPageLoopback() && !qrOrigin && !originLoading;
  const showQr = !originLoading && !blocked && !isLoopbackDownloadUrl(downloadUrl);

  return (
    <QrCodeColumn
      title={item.display_name}
      hint={showQr ? t('ui.header.clientDownload.hint') : undefined}
      footerExtra={showQr ? footerExtra : undefined}
    >
      {originLoading ? (
        <Spin size="small" />
      ) : blocked ? (
        <Alert type="warning" showIcon title={t('ui.header.clientDownload.lanOriginFailed')} />
      ) : showQr ? (
        <QRCodeSVG value={downloadUrl} size={QR_SIZE} />
      ) : (
        <Alert type="error" showIcon title={t('ui.header.clientDownload.loopbackBlocked')} />
      )}
    </QrCodeColumn>
  );
}

export const HeaderClientDownloadButton: React.FC = () => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const currentUser = useCurrentUser();
  const tenantId =
    getTenantId() ??
    (currentUser?.tenant_id != null ? Number(currentUser.tenant_id) : null) ??
    (currentUser?.tenantId != null ? Number(currentUser.tenantId) : null);
  const [open, setOpen] = useState(false);
  const frontendPort = window.location.port ? Number(window.location.port) : undefined;

  const {
    data: downloads = [],
    isLoading: downloadsLoading,
    isFetching: downloadsFetching,
    refetch: refetchDownloads,
  } = useQuery({
    queryKey: ['tenantClientDownloads', tenantId],
    queryFn: getTenantClientDownloads,
    enabled: tenantId != null,
    staleTime: 60_000,
    retry: 1,
  });

  const {
    data: miniprogram,
    isLoading: miniprogramLoading,
    isFetching: miniprogramFetching,
    refetch: refetchMiniprogram,
  } = useQuery({
    queryKey: ['tenantHeaderMiniprogramQr', tenantId],
    queryFn: getTenantHeaderMiniprogramQr,
    enabled: tenantId != null,
    staleTime: 60_000,
    retry: 1,
  });

  const { data: qrOrigin, isLoading: originLoading, refetch: refetchOrigin } = useQuery({
    queryKey: ['clientDownloadQrOrigin', tenantId, frontendPort],
    queryFn: async () => {
      const origin = await getClientDownloadQrOrigin(frontendPort);
      try {
        const host = new URL(origin).hostname;
        if (host && !/^(localhost|127\.0\.0\.1|::1)$/i.test(host)) {
          localStorage.setItem('client_download_public_host', host);
        }
      } catch {
        /* ignore */
      }
      return origin;
    },
    enabled: tenantId != null && open,
    staleTime: 300_000,
    retry: 1,
  });

  const visibleDownloads = useMemo(
    () => downloads.filter((item) => Boolean(item.url)),
    [downloads],
  );

  const miniprogramImageUrl = miniprogram?.image_url
    ? normalizeFilePreviewUrl(miniprogram.image_url)
    : null;
  const showMiniprogram = Boolean(miniprogram?.enabled && miniprogramImageUrl);
  const showDownloads = visibleDownloads.length > 0;
  const initialLoading = downloadsLoading || miniprogramLoading;
  const columnCount = (showMiniprogram ? 1 : 0) + visibleDownloads.length;
  const popupWidth = columnCount <= 1 ? 260 : Math.min(520, columnCount * 240 + 32);

  if (!tenantId || initialLoading || (!showMiniprogram && !showDownloads)) {
    return null;
  }

  const loading = miniprogramFetching || downloadsLoading || downloadsFetching;

  const popup = (
    <div
      style={{
        width: popupWidth,
        backgroundColor: token.colorBgElevated,
        borderRadius: token.borderRadiusLG,
        boxShadow: token.boxShadowSecondary,
        padding: '14px 16px',
      }}
    >
      {loading ? (
        <div style={{ padding: '32px 0', textAlign: 'center' }}>
          <Spin />
        </div>
      ) : (
        <div
          style={{
            display: 'flex',
            flexDirection: 'row',
            alignItems: 'flex-start',
            gap: 12,
          }}
        >
          {showMiniprogram && miniprogramImageUrl ? (
            <MiniprogramQrColumn imageUrl={miniprogramImageUrl} />
          ) : null}
          {showDownloads
            ? visibleDownloads.map((item) => (
                <DownloadQrColumn
                  key={item.client_key}
                  item={item}
                  qrOrigin={qrOrigin}
                  originLoading={originLoading}
                />
              ))
            : null}
        </div>
      )}
    </div>
  );

  return (
    <Dropdown
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          void refetchDownloads();
          void refetchMiniprogram();
          if (showDownloads) {
            void refetchOrigin();
          }
        }
      }}
      popupRender={() => popup}
      trigger={['click']}
      placement="bottomRight"
      arrow={false}
      classNames={{ root: 'header-actions-dropdown' }}
    >
      <Tooltip title={t('ui.header.clientDownload.tooltip')} open={open ? false : undefined}>
        <Button type="text" size="small" icon={<MobileOutlined />} />
      </Tooltip>
    </Dropdown>
  );
};
