import { apiRequest } from '../../../services/api';
import type { MaterialLineAttachmentSource } from '../utils/documentAttachments';

type ApiItem = {
  key: string;
  source: 'material_image' | 'engineering_drawing';
  file_uuid?: string;
  fileUuid?: string;
  name: string;
  content_type?: string | null;
  contentType?: string | null;
  drawing_code?: string | null;
  drawingCode?: string | null;
  drawing_revision?: string | null;
  drawingRevision?: string | null;
};

function normalizeMaterialLineAttachmentSource(row: ApiItem): MaterialLineAttachmentSource {
  return {
    key: row.key,
    source: row.source,
    fileUuid: String(row.file_uuid ?? row.fileUuid ?? '').trim(),
    name: row.name,
    contentType: row.content_type ?? row.contentType ?? undefined,
    drawingCode: row.drawing_code ?? row.drawingCode ?? undefined,
    drawingRevision: row.drawing_revision ?? row.drawingRevision ?? undefined,
  };
}

export async function fetchMaterialLineAttachmentSources(
  materialId: number,
): Promise<MaterialLineAttachmentSource[]> {
  const res = await apiRequest<{ items?: ApiItem[] }>(
    '/apps/kuaizhizao/document-relations/material-line-attachment-sources',
    {
      method: 'GET',
      params: { material_id: materialId },
      suppressErrorToast: true,
    },
  );
  const items = Array.isArray(res?.items) ? res.items : [];
  return items.map(normalizeMaterialLineAttachmentSource);
}
