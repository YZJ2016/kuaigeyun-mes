import React, { useMemo, useState } from 'react';
import { Button, Space } from 'antd';
import { FolderOpenOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import LineAttachmentsUpload from './LineAttachmentsUpload';
import MaterialAttachmentsPickerModal from './MaterialAttachmentsPickerModal';
import {
  mapAttachmentsToUploadList,
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
  const lineCount = useMemo(() => mapAttachmentsToUploadList(value).length, [value]);

  const materialButtonLabel =
    lineCount > 0
      ? `${t('app.kuaizhizao.documentLineAttachments.materialShort')} (${lineCount})`
      : t('app.kuaizhizao.documentLineAttachments.materialShort');

  if (readOnly) {
    return (
      <>
        <Button
          type="link"
          size="small"
          icon={<FolderOpenOutlined />}
          onClick={() => setMaterialOpen(true)}
        >
          {materialButtonLabel}
        </Button>
        <MaterialAttachmentsPickerModal
          open={materialOpen}
          materialId={hasMaterial ? mid : undefined}
          readOnly
          lineAttachments={value}
          uploadCategory={category}
          onClose={() => setMaterialOpen(false)}
        />
      </>
    );
  }

  return (
    <Space size={8} align="center" style={{ whiteSpace: 'nowrap' }}>
      <LineAttachmentsUpload
        variant="inline"
        value={value}
        onChange={onChange}
        category={category}
        maxCount={maxCount}
        disabled={disabled}
      />
      <Button
        type="link"
        size="small"
        icon={<FolderOpenOutlined />}
        disabled={disabled}
        style={{ display: 'inline-flex', alignItems: 'center' }}
        onClick={() => setMaterialOpen(true)}
      >
        {materialButtonLabel}
      </Button>
      <MaterialAttachmentsPickerModal
        open={materialOpen}
        materialId={hasMaterial ? mid : undefined}
        lineAttachments={value}
        onLineAttachmentsChange={onChange}
        uploadCategory={category}
        maxUploadCount={maxCount}
        uploadDisabled={disabled}
        onClose={() => setMaterialOpen(false)}
        onConfirm={(picked: MaterialLineAttachmentSource[]) => {
          onChange?.(mergeMaterialSourcesIntoLineAttachments(value, picked));
        }}
      />
    </Space>
  );
};

export default DocumentLineAttachmentsCell;
