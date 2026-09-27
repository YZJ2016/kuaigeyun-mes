/**
 * 客户跟进附件：上传 / 列表点击预览（FilePreviewModal）
 */

import React, { useCallback, useEffect, useState } from 'react';
import { App, Button, Space, Typography, Upload } from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';
import { useTranslation } from 'react-i18next';
import FilePreviewModal from '../../../components/file-preview';
import { getFileByUuid, uploadFile } from '../../../services/file';
import { getFileExt } from '../../../utils/filePreviewKind';

const ATTACHMENT_CATEGORY = 'customer_follow_up_attachments';

export interface CustomerFollowUpAttachmentsProps {
  uuids: string[];
  /** 可编辑时展示上传；只读时仅列表预览 */
  editable?: boolean;
  onChange?: (uuids: string[]) => void;
}

export const CustomerFollowUpAttachments: React.FC<CustomerFollowUpAttachmentsProps> = ({
  uuids,
  editable = false,
  onChange,
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [nameMap, setNameMap] = useState<Record<string, string>>({});
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewUuid, setPreviewUuid] = useState<string | undefined>();
  const [previewName, setPreviewName] = useState<string | undefined>();

  useEffect(() => {
    let cancelled = false;
    const missing = uuids.filter((u) => u && !nameMap[u]);
    if (missing.length === 0) return;
    void (async () => {
      const next: Record<string, string> = {};
      await Promise.all(
        missing.map(async (uuid) => {
          try {
            const file = await getFileByUuid(uuid);
            next[uuid] = String(file.original_name || file.name || uuid).trim() || uuid;
          } catch {
            next[uuid] = uuid.slice(0, 8);
          }
        }),
      );
      if (!cancelled) {
        setNameMap((prev) => ({ ...prev, ...next }));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [uuids, nameMap]);

  const openPreview = useCallback(
    (uuid: string) => {
      setPreviewUuid(uuid);
      setPreviewName(nameMap[uuid] || uuid);
      setPreviewOpen(true);
    },
    [nameMap],
  );

  const fileList: UploadFile[] = uuids.map((uid) => ({
    uid,
    name: nameMap[uid] || uid.slice(0, 8),
    status: 'done' as const,
  }));

  if (!editable && uuids.length === 0) {
    return <Typography.Text type="secondary">—</Typography.Text>;
  }

  return (
    <>
      {editable ? (
        <Upload
          multiple
          fileList={fileList}
          onPreview={(file) => {
            const uuid = String(file.uid || '').trim();
            if (uuid) openPreview(uuid);
          }}
          customRequest={async (options) => {
            const file = options.file as File;
            try {
              const res = await uploadFile(file, { category: ATTACHMENT_CATEGORY });
              const uuid = String(res?.uuid || '').trim();
              if (!uuid) throw new Error('missing uuid');
              const displayName = String(res.original_name || res.name || file.name || uuid).trim();
              setNameMap((prev) => ({ ...prev, [uuid]: displayName }));
              onChange?.(uuids.includes(uuid) ? uuids : [...uuids, uuid]);
              options.onSuccess?.(res);
            } catch (err) {
              options.onError?.(err as Error);
              message.error(t('components.fileUpload.uploadFailed'));
            }
          }}
          onRemove={(file) => {
            onChange?.(uuids.filter((u) => u !== file.uid));
            return true;
          }}
        >
          <Button size="small">{t('common.upload')}</Button>
        </Upload>
      ) : (
        <Space orientation="vertical" size={4} style={{ width: '100%' }}>
          {uuids.map((uuid) => (
            <Button
              key={uuid}
              type="link"
              size="small"
              style={{ padding: 0, height: 'auto', textAlign: 'left' }}
              onClick={() => openPreview(uuid)}
            >
              {nameMap[uuid] || uuid.slice(0, 8)}
            </Button>
          ))}
        </Space>
      )}
      <FilePreviewModal
        open={previewOpen}
        onClose={() => {
          setPreviewOpen(false);
          setPreviewUuid(undefined);
          setPreviewName(undefined);
        }}
        fileUuid={previewUuid}
        fileName={previewName}
        fileExtension={previewName ? getFileExt(previewName) : undefined}
        title={previewName}
      />
    </>
  );
};
