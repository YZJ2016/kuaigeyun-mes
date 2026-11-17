import React, { useState } from 'react';
import { Button, Space } from 'antd';
import { FolderOpenOutlined, PaperClipOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import LineAttachmentsUpload from './LineAttachmentsUpload';
import { DocumentAttachmentsReadonly, hasDocumentAttachments } from './DocumentAttachmentsReadonly';
import MaterialAttachmentsPickerModal from './MaterialAttachmentsPickerModal';
import {
  mergeMaterialSourcesIntoLineAttachments,
  type DocumentAttachmentFile,
  type MaterialLineAttachmentSource,
} from '../utils/documentAttachments';

export type DocumentLineAttachmentsCellProps = {
  value?: DocumentAttachmentFile[] | null;
  onChange?: (next: DocumentAttachmentFile[]) => void;
  materialId?: number;
  category: string;
  readOnly?: boolean;
  disabled?: boolean;
  maxCount?: number;
};

export const DocumentLineAttachmentsCell: React.FC<DocumentLineAttachmentsCellProps> = ({
  value,
  onChange,
  materialId,
  category,
  readOnly,
  disabled,
  maxCount = 4,
}) => {
  const { t } = useTranslation();
  const [materialOpen, setMaterialOpen] = useState(false);
  const mid = Number(materialId);
  const hasMaterial = Number.isFinite(mid) && mid > 0;

  if (readOnly) {
    return (
      <Space size={4} wrap>
        <DocumentAttachmentsReadonly attachments={value} variant="count" />
        {hasMaterial ? (
          <Button
            type="link"
            size="small"
            icon={<FolderOpenOutlined />}
            onClick={() => setMaterialOpen(true)}
          >
            {t('app.kuaizhizao.documentLineAttachments.materialShort')}
          </Button>
        ) : null}
        <MaterialAttachmentsPickerModal
          open={materialOpen}
          materialId={mid}
          readOnly
          onClose={() => setMaterialOpen(false)}
        />
      </Space>
    );
  }

  return (
    <Space orientation="vertical" size={4} style={{ width: '100%' }}>
      <LineAttachmentsUpload
        value={value}
        onChange={onChange}
        category={category}
        maxCount={maxCount}
        disabled={disabled}
      />
      <Space size={4} wrap>
        {hasDocumentAttachments(value) ? (
          <span style={{ fontSize: 12, color: 'rgba(0,0,0,0.45)' }}>
            <PaperClipOutlined /> {t('app.kuaizhizao.documentLineAttachments.lineCountHint')}
          </span>
        ) : null}
        <Button
          type="link"
          size="small"
          icon={<FolderOpenOutlined />}
          disabled={disabled || !hasMaterial}
          onClick={() => setMaterialOpen(true)}
        >
          {t('app.kuaizhizao.documentLineAttachments.materialShort')}
        </Button>
      </Space>
      <MaterialAttachmentsPickerModal
        open={materialOpen}
        materialId={mid}
        onClose={() => setMaterialOpen(false)}
        onConfirm={(picked: MaterialLineAttachmentSource[]) => {
          onChange?.(mergeMaterialSourcesIntoLineAttachments(value, picked));
        }}
      />
    </Space>
  );
};

export default DocumentLineAttachmentsCell;
