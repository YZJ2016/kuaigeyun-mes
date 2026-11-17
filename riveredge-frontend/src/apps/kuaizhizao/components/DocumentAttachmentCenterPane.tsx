/**
 * 详情抽屉「附件中心」Tab 面板：聚合本单 + 全链路关联单据附件。
 * 预览走 FilePreviewModal；下载走带 token URL；本单附件可上传/删除（由宿主回调写回单据）。
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { App, Button, Collapse, Empty, Popconfirm, Result, Spin, Typography, Upload } from 'antd';
import {
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  PaperClipOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { ProForm } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { SecureImage } from '../../../components/secure-image';
import FilePreviewModal from '../../../components/file-preview';
import { getFileExt } from '../../../utils/filePreviewKind';
import { getFileDownloadUrl, uploadMultipleFiles } from '../../../services/file';
import {
  getDocumentAttachmentCenter,
  type DocumentAttachmentCenterData,
  type DocumentAttachmentCenterGroup,
} from '../services/document-relation';
import DocumentAttachmentsField from './DocumentAttachmentsField';
import {
  downloadDocumentAttachment,
  isSystemDocumentAttachment,
  mapAttachmentsToUploadList,
  normalizeDocumentAttachments,
  type DocumentAttachmentFile,
} from '../utils/documentAttachments';
import { getApiErrorMessage } from '../../../utils/errorHandler';

const IMAGE_EXT_RE = /\.(png|jpe?g|gif|webp|bmp|svg)$/i;

function looksLikeImage(name?: string): boolean {
  const n = String(name || '').trim();
  if (!n) return true;
  if (!n.includes('.')) return true;
  return IMAGE_EXT_RE.test(n);
}

export type DocumentAttachmentCenterHostUpload = {
  category: string;
  allowed: boolean;
  disabledReason?: string | null;
  initialAttachments?: DocumentAttachmentFile[] | null;
  onSave: (attachments: ReturnType<typeof normalizeDocumentAttachments>) => Promise<void>;
};

export type DocumentAttachmentCenterPaneProps = {
  documentType: string;
  documentId: number;
  /** 抽屉打开且 Tab 激活 */
  active?: boolean;
  /** 上传分类；与 canManage + onAdd 同时有值时显示上传 */
  attachmentCategory?: string;
  /** 是否允许上传/删除本单（is_self）附件 */
  canManageSelfAttachments?: boolean;
  /** 删除本单附件；成功后本面板会 reload */
  onDeleteSelfAttachment?: (fileUid: string) => Promise<void>;
  /** 上传成功后追加本单附件 */
  onAddSelfAttachments?: (files: DocumentAttachmentFile[]) => Promise<void>;
  /** 本单附件补充（已审核后仍可用时由单据页传入） */
  hostUpload?: DocumentAttachmentCenterHostUpload | null;
};

export const DocumentAttachmentCenterPane: React.FC<DocumentAttachmentCenterPaneProps> = ({
  documentType,
  documentId,
  active = true,
  attachmentCategory,
  canManageSelfAttachments = false,
  onDeleteSelfAttachment,
  onAddSelfAttachments,
  hostUpload = null,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<DocumentAttachmentCenterData | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewFile, setPreviewFile] = useState<{ uuid: string; name: string } | null>(null);
  const [deletingUid, setDeletingUid] = useState<string | null>(null);
  const uploadChainRef = useRef(Promise.resolve());
  const [attachmentForm] = ProForm.useForm();
  const [attachmentsSaving, setAttachmentsSaving] = useState(false);

  const canUpload =
    Boolean(canManageSelfAttachments) &&
    Boolean(attachmentCategory) &&
    typeof onAddSelfAttachments === 'function';

  const load = useCallback(async () => {
    if (!documentType || !documentId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getDocumentAttachmentCenter(documentType, documentId);
      setData(res);
    } catch (err: unknown) {
      const msg =
        err && typeof err === 'object' && 'message' in err
          ? String((err as { message?: string }).message || '')
          : '';
      setError(msg || t('app.uniDetail.attachmentCenter.loadFailed'));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [documentId, documentType, t]);

  useEffect(() => {
    if (!active) return;
    void load();
  }, [active, load]);

  const hostAttachmentsEditable = Boolean(hostUpload?.allowed);

  useEffect(() => {
    if (!hostAttachmentsEditable || !hostUpload) return;
    const fromCenter = data?.groups?.find((g) => g.is_self)?.attachments;
    const initial =
      (fromCenter && fromCenter.length > 0 ? fromCenter : null) ||
      hostUpload.initialAttachments ||
      [];
    attachmentForm.setFieldsValue({
      attachments: mapAttachmentsToUploadList(initial as DocumentAttachmentFile[]),
    });
  }, [
    attachmentForm,
    data?.groups,
    hostAttachmentsEditable,
    hostUpload,
    hostUpload?.initialAttachments,
  ]);

  const handleSaveHostAttachments = useCallback(async () => {
    if (!hostUpload) return;
    try {
      const values = await attachmentForm.validateFields();
      setAttachmentsSaving(true);
      await hostUpload.onSave(normalizeDocumentAttachments(values.attachments));
      messageApi.success(t('app.uniDetail.attachmentCenter.attachmentsSaved'));
      await load();
    } catch (e: unknown) {
      if ((e as { errorFields?: unknown })?.errorFields) return;
      messageApi.error((e as Error)?.message || t('common.saveFailed'));
    } finally {
      setAttachmentsSaving(false);
    }
  }, [attachmentForm, hostUpload, load, messageApi, t]);

  const openPreview = useCallback((uuid: string, name: string) => {
    const id = String(uuid || '').trim();
    if (!id) {
      void messageApi.error(t('app.uniDetail.attachmentCenter.previewMissingUuid'));
      return;
    }
    setPreviewFile({ uuid: id, name: name || t('components.documentAttachments.label') });
    setPreviewOpen(true);
  }, [messageApi, t]);

  const handleDownload = useCallback(
    async (uuid: string, name: string) => {
      try {
        await downloadDocumentAttachment({ uid: uuid, name });
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('app.uniDetail.attachmentCenter.downloadFailed')));
      }
    },
    [messageApi, t],
  );

  const handleDelete = useCallback(
    async (uuid: string) => {
      if (!onDeleteSelfAttachment) return;
      setDeletingUid(uuid);
      try {
        await onDeleteSelfAttachment(uuid);
        messageApi.success(t('common.deleteSuccess'));
        await load();
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('common.deleteFailed')));
      } finally {
        setDeletingUid(null);
      }
    },
    [load, messageApi, onDeleteSelfAttachment, t],
  );

  const handleUploadFiles = useCallback(
    async (fileList: File[]) => {
      if (!canUpload || !attachmentCategory || !onAddSelfAttachments) return;
      if (fileList.length === 0) return;
      setUploading(true);
      try {
        const uploaded = await uploadMultipleFiles(fileList, { category: attachmentCategory });
        const asUploadList: DocumentAttachmentFile[] = uploaded.map((f) => ({
          uid: f.uuid,
          name: f.original_name || f.uuid,
          status: 'done',
          url: getFileDownloadUrl(f.uuid),
          response: { uuid: f.uuid, original_name: f.original_name },
        }));
        const normalized = normalizeDocumentAttachments(asUploadList);
        await onAddSelfAttachments(normalized);
        messageApi.success(t('components.fileUpload.uploadMultiSuccess', { count: normalized.length }));
        await load();
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('app.uniDetail.attachmentCenter.uploadFailed')));
      } finally {
        setUploading(false);
      }
    },
    [attachmentCategory, canUpload, load, messageApi, onAddSelfAttachments, t],
  );

  const resolveDocTypeLabel = useCallback(
    (type: string) =>
      t(`components.documentTrackingPanel.docType.${type}`, {
        defaultValue: type,
      }),
    [t],
  );

  const uploadButton = canUpload ? (
    <Upload
      multiple
      showUploadList={false}
      disabled={uploading}
      customRequest={(options) => {
        const run = async () => {
          try {
            await handleUploadFiles([options.file as File]);
            options.onSuccess?.({}, options.file as any);
          } catch (err) {
            options.onError?.(err as Error);
          }
        };
        uploadChainRef.current = uploadChainRef.current.then(run, run);
        return uploadChainRef.current;
      }}
    >
      <Button type="primary" icon={<UploadOutlined />} loading={uploading}>
        {t('app.uniDetail.attachmentCenter.upload')}
      </Button>
    </Upload>
  ) : null;

  const collapseItems = useMemo(() => {
    const groups = data?.groups ?? [];
    return groups.map((group: DocumentAttachmentCenterGroup) => {
      const typeLabel = resolveDocTypeLabel(group.document_type);
      const code = String(group.document_code || '').trim();
      const canDeleteBase =
        Boolean(group.is_self) && canManageSelfAttachments && typeof onDeleteSelfAttachment === 'function';
      const header = (
        <span style={{ display: 'inline-flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
          <Typography.Text strong>
            {typeLabel}
            {code ? ` ${code}` : ''}
          </Typography.Text>
          {group.is_self ? (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('app.uniDetail.attachmentCenter.selfBadge')}
            </Typography.Text>
          ) : null}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {t('app.uniDetail.attachmentCenter.fileCount', { count: group.attachments.length })}
          </Typography.Text>
        </span>
      );

      const actionButtons = (uid: string, name: string, isSystem: boolean) => (
        <>
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => openPreview(uid, name)}
          >
            {t('app.uniDetail.attachmentCenter.preview')}
          </Button>
          <Button
            type="link"
            size="small"
            icon={<DownloadOutlined />}
            onClick={() => void handleDownload(uid, name)}
          >
            {t('app.uniDetail.attachmentCenter.download')}
          </Button>
          {canDeleteBase && !isSystem ? (
            <Popconfirm
              title={t('app.uniDetail.attachmentCenter.confirmDelete')}
              onConfirm={() => void handleDelete(uid)}
            >
              <Button
                type="link"
                size="small"
                danger
                icon={<DeleteOutlined />}
                loading={deletingUid === uid}
              >
                {t('common.delete')}
              </Button>
            </Popconfirm>
          ) : null}
        </>
      );

      const body =
        group.attachments.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {group.attachments.map((file) => {
              const uid = String(file.uid || '').trim();
              if (!uid) return null;
              const name = file.name || t('components.documentAttachments.label');
              const isSystem = isSystemDocumentAttachment(file);
              const nameNode = (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0, flex: 1 }}>
                  <Typography.Text ellipsis style={{ flex: 1, minWidth: 0 }}>
                    {name}
                  </Typography.Text>
                  {isSystem ? (
                    <Typography.Text type="secondary" style={{ fontSize: 12, flexShrink: 0 }}>
                      {t('app.uniDetail.attachmentCenter.systemBadge')}
                    </Typography.Text>
                  ) : null}
                </span>
              );
              if (looksLikeImage(name)) {
                return (
                  <div
                    key={`${group.document_type}-${group.document_id}-${uid}`}
                    style={{ display: 'flex', alignItems: 'center', gap: 12 }}
                  >
                    <button
                      type="button"
                      onClick={() => openPreview(uid, name)}
                      style={{
                        padding: 0,
                        border: 'none',
                        background: 'transparent',
                        cursor: 'pointer',
                      }}
                    >
                      <SecureImage
                        fileUuid={uid}
                        alt={name}
                        width={64}
                        height={64}
                        thumbSize={128}
                        previewSize={512}
                        style={{ objectFit: 'cover', borderRadius: 4 }}
                      />
                    </button>
                    {nameNode}
                    {actionButtons(uid, name, isSystem)}
                  </div>
                );
              }
              return (
                <div
                  key={`${group.document_type}-${group.document_id}-${uid}`}
                  style={{ display: 'flex', alignItems: 'center', gap: 8 }}
                >
                  <PaperClipOutlined />
                  {nameNode}
                  {actionButtons(uid, name, isSystem)}
                </div>
              );
            })}
          </div>
        ) : (
          <Typography.Text type="secondary">{t('app.uniDetail.attachmentCenter.groupEmpty')}</Typography.Text>
        );

      return {
        key: `${group.document_type}-${group.document_id}`,
        label: header,
        children: body,
      };
    });
  }, [
    canManageSelfAttachments,
    data?.groups,
    deletingUid,
    handleDelete,
    handleDownload,
    onDeleteSelfAttachment,
    openPreview,
    resolveDocTypeLabel,
    t,
  ]);

  const defaultActiveKeys = useMemo(() => {
    const groups = data?.groups ?? [];
    const withFiles = groups.filter((g) => g.attachments.length > 0);
    if (withFiles.length > 0) {
      return withFiles.map((g) => `${g.document_type}-${g.document_id}`);
    }
    const self = groups.find((g) => g.is_self);
    if (self) return [`${self.document_type}-${self.document_id}`];
    return groups.slice(0, 1).map((g) => `${g.document_type}-${g.document_id}`);
  }, [data?.groups]);

  const totalFiles = useMemo(
    () => (data?.groups ?? []).reduce((sum, g) => sum + g.attachments.length, 0),
    [data?.groups],
  );

  const hostUploadPanel = hostAttachmentsEditable && hostUpload ? (
    <div style={{ marginBottom: 16 }}>
      <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
        {t('app.uniDetail.attachmentCenter.hostUploadTitle')}
      </Typography.Text>
      <ProForm form={attachmentForm} submitter={false} layout="vertical">
        <DocumentAttachmentsField category={hostUpload.category} label={false} />
        <Button
          type="primary"
          loading={attachmentsSaving}
          title={hostUpload.disabledReason || undefined}
          onClick={() => void handleSaveHostAttachments()}
        >
          {t('app.uniDetail.attachmentCenter.saveAttachments')}
        </Button>
      </ProForm>
    </div>
  ) : hostUpload && !hostUpload.allowed && hostUpload.disabledReason ? (
    <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
      {hostUpload.disabledReason}
    </Typography.Text>
  ) : null;

  const previewModal = (
    <FilePreviewModal
      open={previewOpen}
      onClose={() => {
        setPreviewOpen(false);
        setPreviewFile(null);
      }}
      fileUuid={previewFile?.uuid}
      fileName={previewFile?.name}
      fileExtension={previewFile?.name ? getFileExt(previewFile.name) : undefined}
      title={previewFile?.name}
    />
  );

  if (!active) return null;

  if (loading && !data) {
    return (
      <div style={{ minHeight: 160, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin />
      </div>
    );
  }

  if (error && !data) {
    return (
      <Result
        status="error"
        title={error}
        extra={
          <Button type="primary" onClick={() => void load()}>
            {t('common.retry', { defaultValue: '重试' })}
          </Button>
        }
      />
    );
  }

  if (!data || totalFiles === 0) {
    return (
      <>
        {hostUploadPanel}
        <div
          style={{
            minHeight: 160,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 16,
          }}
        >
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              canUpload
                ? t('app.uniDetail.attachmentCenter.emptyUploadHint')
                : hostAttachmentsEditable
                  ? t('app.uniDetail.attachmentCenter.emptyHintUpload')
                  : t('app.uniDetail.attachmentCenter.empty')
            }
          />
          {uploadButton}
        </div>
        {previewModal}
      </>
    );
  }

  return (
    <>
      {hostUploadPanel}
      {canUpload ? (
        <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'flex-end' }}>{uploadButton}</div>
      ) : null}
      <Collapse
        size="small"
        defaultActiveKey={defaultActiveKeys}
        items={collapseItems}
      />
      <FilePreviewModal
        open={previewOpen}
        onClose={() => {
          setPreviewOpen(false);
          setPreviewFile(null);
        }}
        fileUuid={previewFile?.uuid}
        fileName={previewFile?.name}
        fileExtension={previewFile?.name ? getFileExt({ fileName: previewFile.name }) : undefined}
        title={previewFile?.name}
      />
    </>
  );
};

export default DocumentAttachmentCenterPane;
