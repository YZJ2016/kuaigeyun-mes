/**
 * 检验四单据详情：附件补充（与 conduct 解耦）。检验方案切换在检验 Modal 内。
 */

import React, { useEffect, useState } from 'react';
import { App, Button, Typography } from 'antd';
import { ProForm } from '@ant-design/pro-components';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { DetailDrawerSection } from '../../../../../components/layout-templates';
import { MarkerTag } from '../../../../../constants/statusBadges';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import {
  DocumentAttachmentsReadonly,
  documentAttachmentsFromRecord,
  hasDocumentAttachments,
} from '../../../components/DocumentAttachmentsReadonly';
import {
  mapAttachmentsToUploadList,
  normalizeDocumentAttachments,
} from '../../../utils/documentAttachments';
import type { CapabilityActionView } from '../../../../../hooks/useDocumentCapabilities';
import {
  getInspectionPlanNameAndCode,
  getInspectionTemplateSource,
  hasInspectionPlanSteps,
} from './inspectionTemplateUtils';
import { resolveQualityInspectionKindMarkerColor } from './qualityMeta';

export type InspectionPlanType = 'incoming' | 'process' | 'finished' | 'outbound';

export type QualityInspectionDetailSupplementProps = {
  inspection: Record<string, unknown>;
  attachmentCategory: string;
  updateAttachmentsGate: CapabilityActionView;
  onSaveAttachments: (attachments: ReturnType<typeof normalizeDocumentAttachments>) => Promise<void>;
};

export function renderQualityInspectionPlanSummary(
  record: Record<string, unknown> | null | undefined,
  t: TFunction,
): React.ReactNode {
  if (!record) return '—';
  const isPlan = hasInspectionPlanSteps(getInspectionTemplateSource(record));
  if (!isPlan) {
    return (
      <MarkerTag color={resolveQualityInspectionKindMarkerColor(false)}>
        {t('app.kuaizhizao.quality.common.inspectionKind.simple')}
      </MarkerTag>
    );
  }
  const { name, code } = getInspectionPlanNameAndCode(record);
  if (!name && !code) {
    return (
      <MarkerTag color={resolveQualityInspectionKindMarkerColor(true)}>
        {t('app.kuaizhizao.quality.common.inspectionKind.plan')}
      </MarkerTag>
    );
  }
  const label = name && code ? `${name} (${code})` : name || code;
  return <Typography.Text>{label}</Typography.Text>;
}

export function QualityInspectionDetailSupplement({
  inspection,
  attachmentCategory,
  updateAttachmentsGate,
  onSaveAttachments,
}: QualityInspectionDetailSupplementProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [attachmentForm] = ProForm.useForm();
  const [attachmentsSaving, setAttachmentsSaving] = useState(false);

  const attachments = documentAttachmentsFromRecord(inspection);
  const attachmentsEditable = updateAttachmentsGate.allowed && !updateAttachmentsGate.disabled;

  useEffect(() => {
    attachmentForm.setFieldsValue({
      attachments: mapAttachmentsToUploadList(attachments),
    });
  }, [attachmentForm, inspection, attachments]);

  const handleSaveAttachments = async () => {
    try {
      const values = await attachmentForm.validateFields();
      setAttachmentsSaving(true);
      await onSaveAttachments(normalizeDocumentAttachments(values.attachments));
      message.success(t('app.kuaizhizao.quality.common.messages.attachmentsSaved'));
    } catch (e: unknown) {
      if ((e as { errorFields?: unknown })?.errorFields) return;
      message.error((e as Error)?.message || t('common.saveFailed'));
    } finally {
      setAttachmentsSaving(false);
    }
  };

  return (
    <DetailDrawerSection title={t('components.documentAttachments.label')}>
      {attachmentsEditable ? (
        <ProForm form={attachmentForm} submitter={false} layout="vertical">
          <DocumentAttachmentsField category={attachmentCategory} label={false} />
          <Button
            type="primary"
            loading={attachmentsSaving}
            disabled={updateAttachmentsGate.disabled}
            title={updateAttachmentsGate.title}
            onClick={() => void handleSaveAttachments()}
          >
            {t('app.kuaizhizao.quality.common.actions.saveAttachments')}
          </Button>
        </ProForm>
      ) : hasDocumentAttachments(attachments) ? (
        <DocumentAttachmentsReadonly attachments={attachments} />
      ) : updateAttachmentsGate.title ? (
        <Typography.Text type="secondary">{updateAttachmentsGate.title}</Typography.Text>
      ) : (
        <Typography.Text type="secondary">—</Typography.Text>
      )}
    </DetailDrawerSection>
  );
}

/** 列表页详情抽屉：附件补充区 */
export function buildQualityInspectionDetailSupplementNode(options: {
  inspection: Record<string, unknown> | null | undefined;
  attachmentCategory: string;
  updateAttachmentsGate: CapabilityActionView;
  patchAttachments: (attachments: ReturnType<typeof normalizeDocumentAttachments>) => Promise<unknown>;
  onUpdated: (record: unknown) => void;
}): React.ReactNode {
  const { inspection, attachmentCategory, updateAttachmentsGate, patchAttachments, onUpdated } = options;
  if (!inspection) return null;
  return (
    <QualityInspectionDetailSupplement
      inspection={inspection}
      attachmentCategory={attachmentCategory}
      updateAttachmentsGate={updateAttachmentsGate}
      onSaveAttachments={async (attachments) => {
        const updated = await patchAttachments(attachments);
        onUpdated(updated);
      }}
    />
  );
}
