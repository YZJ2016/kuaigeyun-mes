import {
  extractUploadFileUuids,
  normalizeUploadFileList,
} from '../../../components/custom-fields/customFieldFileUtils';
import type { RefObject } from 'react';
import type { ProFormInstance } from '@ant-design/pro-components';
import { needsMaterialCode, needsProjectCodeWithoutProject } from './rdDeliverableTypes';

export function sanitizeRdDeliverableProjectId(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function buildRdDeliverablePayload(
  values: Record<string, unknown>,
  options: {
    formRef?: RefObject<ProFormInstance | undefined>;
  } = {},
): {
  name: string;
  deliverable_type?: string;
  status: string;
  description?: string;
  file_uuid?: string;
  file_name?: string;
  material_code?: string;
  legacy_material_code?: string;
  project_id: number | null;
  project_code?: string;
  gate_id?: number;
} {
  const formRef = options.formRef;
  const formUpload = formRef?.current?.getFieldValue?.('file_upload');
  const uploadList = normalizeUploadFileList(formUpload ?? values.file_upload);
  const uploadedUuids = extractUploadFileUuids(uploadList);
  const fileUuid =
    uploadedUuids[0] ||
    String(formRef?.current?.getFieldValue?.('file_uuid') ?? values.file_uuid ?? '').trim() ||
    undefined;
  const fileName =
    String(formRef?.current?.getFieldValue?.('file_name') ?? values.file_name ?? '').trim() ||
    (uploadList[0]?.name as string | undefined) ||
    undefined;
  const dtype = String(values.deliverable_type || '').trim() || undefined;
  const projectId = sanitizeRdDeliverableProjectId(values.project_id);
  return {
    name: String(values.name || '').trim(),
    deliverable_type: dtype,
    status: String(values.status || 'PENDING'),
    description: values.description ? String(values.description) : undefined,
    file_uuid: fileUuid,
    file_name: fileName,
    material_code: needsMaterialCode(dtype)
      ? String(values.material_code || '').trim() || undefined
      : values.material_code
        ? String(values.material_code).trim() || undefined
        : undefined,
    legacy_material_code: values.legacy_material_code
      ? String(values.legacy_material_code).trim() || undefined
      : undefined,
    project_id: projectId,
    project_code:
      projectId == null && values.project_code
        ? String(values.project_code).trim() || undefined
        : undefined,
    gate_id:
      values.gate_id != null && values.gate_id !== ''
        ? Number(values.gate_id)
        : undefined,
  };
}

export function validateRdDeliverablePayloadClient(
  payload: ReturnType<typeof buildRdDeliverablePayload>,
  t: (key: string) => string,
): string | null {
  const dtype = payload.deliverable_type;
  if (needsMaterialCode(dtype) && !payload.material_code) {
    return t('app.kuaiplm.rdProjects.detail.deliverable.materialCodeRequired');
  }
  if (needsProjectCodeWithoutProject(dtype, payload.project_id) && !payload.project_code) {
    return t('app.kuaiplm.rdDeliverables.form.projectCodeRequired');
  }
  return null;
}
