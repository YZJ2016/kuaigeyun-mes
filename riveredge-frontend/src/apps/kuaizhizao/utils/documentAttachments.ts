import type { UploadFile, UploadProps } from 'antd/es/upload/interface';
import { getFileDownloadUrl, getFileDownloadUrlWithToken } from '../../../services/file';

export type DocumentAttachmentFile = {
  uid?: string;
  name?: string;
  status?: string;
  url?: string;
  kind?: string;
  source?: string;
  supplier_id?: number;
  response?: { uuid?: string; original_name?: string } | Array<{ uuid?: string; original_name?: string }>;
};

export function isSystemDocumentAttachment(
  file: Pick<DocumentAttachmentFile, 'kind' | 'source'> | null | undefined,
): boolean {
  if (!file) return false;
  const kind = String(file.kind || '').trim();
  const source = String(file.source || '').trim();
  return kind === 'system' || source === 'purchase_inquiry_vendor';
}

/** 从 Upload 条目或后端 attachments JSON 解析文件 UUID */
export function resolveDocumentAttachmentFileUuid(
  file: Pick<DocumentAttachmentFile, 'uid' | 'response'> | UploadFile,
): string | undefined {
  const response = (file as DocumentAttachmentFile).response;
  if (response) {
    if (Array.isArray(response) && response.length > 0 && response[0]?.uuid) {
      return String(response[0].uuid).trim() || undefined;
    }
    if (!Array.isArray(response) && response.uuid) {
      return String(response.uuid).trim() || undefined;
    }
  }
  const uid = String(file.uid ?? '').trim();
  return uid || undefined;
}

/** 鉴权打开附件（禁止裸 /download URL，浏览器无法带租户头） */
export async function openDocumentAttachment(
  file: Pick<DocumentAttachmentFile, 'uid' | 'response'> | UploadFile,
): Promise<void> {
  const fileUuid = resolveDocumentAttachmentFileUuid(file);
  if (!fileUuid) return;
  const url = await getFileDownloadUrlWithToken(fileUuid);
  window.open(url, '_blank', 'noopener,noreferrer');
}

/** 鉴权下载附件到本地（带 token 的 blob URL） */
export async function downloadDocumentAttachment(
  file: Pick<DocumentAttachmentFile, 'uid' | 'name' | 'response'> | UploadFile,
): Promise<void> {
  const fileUuid = resolveDocumentAttachmentFileUuid(file);
  if (!fileUuid) return;
  const url = await getFileDownloadUrlWithToken(fileUuid);
  const name =
    String((file as DocumentAttachmentFile).name || '').trim() ||
    `${fileUuid}.bin`;
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

/** ProFormUploadDragger / Upload 共用：预览与下载均走带 token 的 URL */
export function buildDocumentAttachmentUploadHandlers(handlers?: {
  onOpenFailed?: () => void;
}): Pick<UploadProps, 'onPreview' | 'onDownload'> {
  const open = (file: UploadFile) => {
    void openDocumentAttachment(file).catch(() => {
      handlers?.onOpenFailed?.();
    });
  };
  return {
    onPreview: open,
    onDownload: open,
  };
}

/** 编辑回填：后端 attachments → Upload fileList */
export function mapAttachmentsToUploadList(attachments?: DocumentAttachmentFile[] | null) {
  return (attachments ?? []).map((file) => ({
    uid: file.uid ?? file.name ?? String(Math.random()),
    name: file.name ?? '附件',
    status: 'done' as const,
    url: file.url ?? (file.uid ? getFileDownloadUrl(file.uid) : undefined),
  }));
}

/** 提交前：Upload fileList → 后端 attachments JSON */
export type MaterialLineAttachmentSource = {
  key: string;
  source: 'material_image' | 'engineering_drawing';
  fileUuid: string;
  name: string;
  contentType?: string | null;
  drawingCode?: string | null;
  drawingRevision?: string | null;
};

export function materialLineSourceToDocumentAttachment(
  item: MaterialLineAttachmentSource,
): DocumentAttachmentFile {
  return {
    uid: item.fileUuid,
    uuid: item.fileUuid,
    name: item.name,
    status: 'done',
    source: item.source,
  };
}

/** 从物料附件弹窗勾选合并进行附件（按 UUID 去重，不改主数据） */
export function mergeMaterialSourcesIntoLineAttachments(
  current: DocumentAttachmentFile[] | null | undefined,
  picked: MaterialLineAttachmentSource[],
): DocumentAttachmentFile[] {
  const next = normalizeDocumentAttachments(current);
  const seen = new Set(
    next.map((f) => resolveDocumentAttachmentFileUuid(f)).filter(Boolean) as string[],
  );
  for (const item of picked) {
    const uuid = String(item.fileUuid || '').trim();
    if (!uuid || seen.has(uuid)) continue;
    seen.add(uuid);
    next.push(materialLineSourceToDocumentAttachment(item));
  }
  return next;
}

export function normalizeDocumentAttachments(list?: DocumentAttachmentFile[] | null) {
  return (list ?? []).map((file) => {
    const meta: Pick<DocumentAttachmentFile, 'kind' | 'source' | 'supplier_id'> = {};
    if (file.kind) meta.kind = file.kind;
    if (file.source) meta.source = file.source;
    if (file.supplier_id != null) meta.supplier_id = file.supplier_id;

    if (file.response) {
      if (Array.isArray(file.response) && file.response.length > 0) {
        const res = file.response[0];
        return {
          uid: res.uuid,
          name: res.original_name,
          status: 'done',
          url: getFileDownloadUrl(res.uuid!),
          ...meta,
        };
      }
      if (file.response.uuid) {
        return {
          uid: file.response.uuid,
          name: file.response.original_name,
          status: 'done',
          url: getFileDownloadUrl(file.response.uuid),
          ...meta,
        };
      }
    }
    return {
      uid: file.uid,
      name: file.name,
      status: 'done',
      url: file.url,
      ...meta,
    };
  });
}
