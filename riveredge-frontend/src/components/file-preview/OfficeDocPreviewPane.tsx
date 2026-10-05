import React, { useMemo } from 'react';
import { Alert } from 'antd';
import { useTranslation } from 'react-i18next';
import DocViewer, { MSDocRenderer } from '@cyntler/react-doc-viewer';
import '@cyntler/react-doc-viewer/dist/index.css';
import { getFileExt, type FilePreviewSource } from '../../utils/filePreviewKind';

export interface OfficeDocPreviewPaneProps {
  fileUrl: string;
  fileUuid?: string;
  fileSource: FilePreviewSource;
  height?: string | number;
}

const OFFICE_MIME_BY_EXT: Record<string, string> = {
  doc: 'application/msword',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  ppt: 'application/vnd.ms-powerpoint',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
};

/** 相对预览链转为绝对地址，供微软 Office Online 拉取 */
function toAbsoluteFileUri(uri: string): string {
  const trimmed = (uri || '').trim();
  if (!trimmed) return '';
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  if (typeof window === 'undefined') return trimmed;
  return new URL(trimmed, window.location.origin).href;
}

/** 微软服务器无法访问的本机 / 内网地址 */
function isUnreachableByOfficeOnline(absoluteUri: string): boolean {
  try {
    const host = new URL(absoluteUri).hostname.toLowerCase();
    if (
      host === 'localhost'
      || host === '127.0.0.1'
      || host === '0.0.0.0'
      || host === '::1'
      || host.endsWith('.local')
      || host.endsWith('.lan')
    ) {
      return true;
    }
    if (/^10\.\d+\.\d+\.\d+$/.test(host)) return true;
    if (/^192\.168\.\d+\.\d+$/.test(host)) return true;
    if (/^172\.(1[6-9]|2\d|3[01])\.\d+\.\d+$/.test(host)) return true;
    return false;
  } catch {
    return true;
  }
}

export const OfficeDocPreviewPane: React.FC<OfficeDocPreviewPaneProps> = ({
  fileUrl,
  fileSource,
  height = '72vh',
}) => {
  const { t } = useTranslation();
  const resolvedHeight = typeof height === 'number' ? `${height}px` : height;

  const absoluteUri = useMemo(() => toAbsoluteFileUri(fileUrl), [fileUrl]);
  const unreachable = useMemo(
    () => (absoluteUri ? isUnreachableByOfficeOnline(absoluteUri) : true),
    [absoluteUri],
  );

  const documents = useMemo(() => {
    if (!absoluteUri) return [];
    const ext = getFileExt(fileSource);
    const fileType =
      (fileSource.fileType || '').trim()
      || OFFICE_MIME_BY_EXT[ext]
      || undefined;
    return [
      {
        uri: absoluteUri,
        fileName: fileSource.fileName,
        fileType,
      },
    ];
  }, [absoluteUri, fileSource]);

  if (!absoluteUri || documents.length === 0) {
    return (
      <Alert
        type="error"
        showIcon
        title={t('pages.system.files.previewLoadFailed')}
        style={{ margin: 16 }}
      />
    );
  }

  return (
    <div
      style={{
        height: resolvedHeight,
        minHeight: resolvedHeight,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {unreachable ? (
        <Alert
          type="warning"
          showIcon
          title={t('pages.system.files.previewOfficePublicUrlRequired')}
          style={{ margin: 12, marginBottom: 0, flexShrink: 0 }}
        />
      ) : null}
      <div style={{ flex: 1, minHeight: 0 }}>
        <DocViewer
          documents={documents}
          pluginRenderers={[MSDocRenderer]}
          config={{
            header: {
              disableHeader: true,
              disableFileName: true,
              retainURLParams: true,
            },
          }}
          style={{ height: '100%', width: '100%' }}
        />
      </div>
    </div>
  );
};
