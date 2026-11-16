import { apiRequest } from '../../../services/api';
import type { MaterialLineAttachmentSource } from '../utils/documentAttachments';

type ApiItem = {
  key: string;
  source: 'material_image' | 'engineering_drawing';
  file_uuid: string;
  name: string;
  content_type?: string | null;
  drawing_code?: string | null;
  drawing_revision?: string | null;
};

export async function fetchMaterialLineAttachmentSources(
  materialId: number,
): Promise<MaterialLineAttachmentSource[]> {
  const res = await apiRequest<{ items: ApiItem[] }>(
    '/apps/kuaizhizao/document-relations/material-line-attachment-sources',
    { method: 'GET', params: { material_id: materialId } },
  );
  return (res.items ?? []).map((row) => ({
    key: row.key,
    source: row.source,
    fileUuid: row.file_uuid,
    name: row.name,
    contentType: row.content_type,
    drawingCode: row.drawing_code,
    drawingRevision: row.drawing_revision,
  }));
}
