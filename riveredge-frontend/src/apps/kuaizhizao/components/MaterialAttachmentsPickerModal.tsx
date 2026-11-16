import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { App, Button, Empty, Modal, Space, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from 'react-i18next';
import FilePreviewModal from '../../../components/file-preview';
import { getFileExt } from '../../../utils/filePreviewKind';
import { fetchMaterialLineAttachmentSources } from '../services/documentLineMaterialAttachments';
import type { MaterialLineAttachmentSource } from '../utils/documentAttachments';

export type MaterialAttachmentsPickerModalProps = {
  open: boolean;
  materialId?: number;
  onClose: () => void;
  onConfirm?: (picked: MaterialLineAttachmentSource[]) => void;
  /** 只读：仅预览，无勾选确认 */
  readOnly?: boolean;
};

export const MaterialAttachmentsPickerModal: React.FC<MaterialAttachmentsPickerModalProps> = ({
  open,
  materialId,
  onClose,
  onConfirm,
  readOnly,
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<MaterialLineAttachmentSource[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewUuid, setPreviewUuid] = useState<string | undefined>();
  const [previewName, setPreviewName] = useState<string | undefined>();

  const load = useCallback(async () => {
    const mid = Number(materialId);
    if (!Number.isFinite(mid) || mid <= 0) {
      setRows([]);
      return;
    }
    setLoading(true);
    try {
      const items = await fetchMaterialLineAttachmentSources(mid);
      setRows(items);
      setSelectedKeys([]);
    } catch {
      message.error(t('app.kuaizhizao.documentLineAttachments.materialSourcesLoadFailed'));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [materialId, message, t]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const columns: ColumnsType<MaterialLineAttachmentSource> = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.documentLineAttachments.colName'),
        dataIndex: 'name',
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.documentLineAttachments.colSource'),
        dataIndex: 'source',
        width: 120,
        render: (v: MaterialLineAttachmentSource['source']) =>
          v === 'engineering_drawing'
            ? t('app.kuaizhizao.documentLineAttachments.sourceDrawing')
            : t('app.kuaizhizao.documentLineAttachments.sourceMaterialImage'),
      },
      {
        title: t('common.action'),
        key: 'action',
        width: 88,
        render: (_, row) => (
          <Button
            type="link"
            size="small"
            onClick={() => {
              setPreviewUuid(row.fileUuid);
              setPreviewName(row.name);
              setPreviewOpen(true);
            }}
          >
            {t('common.preview')}
          </Button>
        ),
      },
    ],
    [t],
  );

  const picked = useMemo(
    () => rows.filter((r) => selectedKeys.includes(r.key)),
    [rows, selectedKeys],
  );

  return (
    <>
      <Modal
        open={open}
        title={t('app.kuaizhizao.documentLineAttachments.materialPickerTitle')}
        width={720}
        destroyOnHidden
        onCancel={onClose}
        footer={
          readOnly ? (
            <Button onClick={onClose}>{t('common.close')}</Button>
          ) : (
            <Space>
              <Button onClick={onClose}>{t('common.cancel')}</Button>
              <Button
                type="primary"
                disabled={!picked.length}
                onClick={() => {
                  onConfirm?.(picked);
                  onClose();
                }}
              >
                {t('app.kuaizhizao.documentLineAttachments.copyToLine', { count: picked.length })}
              </Button>
            </Space>
          )
        }
      >
        {!materialId ? (
          <Typography.Text type="secondary">
            {t('app.kuaizhizao.documentLineAttachments.selectMaterialFirst')}
          </Typography.Text>
        ) : rows.length === 0 && !loading ? (
          <Empty description={t('app.kuaizhizao.documentLineAttachments.materialSourcesEmpty')} />
        ) : (
          <Table
            size="small"
            rowKey="key"
            loading={loading}
            pagination={false}
            dataSource={rows}
            columns={columns}
            rowSelection={
              readOnly
                ? undefined
                : {
                    selectedRowKeys: selectedKeys,
                    onChange: (keys) => setSelectedKeys(keys),
                  }
            }
            scroll={{ y: 360 }}
          />
        )}
      </Modal>
      <FilePreviewModal
        open={previewOpen}
        onClose={() => {
          setPreviewOpen(false);
          setPreviewUuid(undefined);
          setPreviewName(undefined);
        }}
        fileUuid={previewUuid}
        fileName={previewName}
        fileExtension={previewName ? getFileExt({ fileName: previewName }) : undefined}
        title={previewName}
      />
    </>
  );
};

export default MaterialAttachmentsPickerModal;
