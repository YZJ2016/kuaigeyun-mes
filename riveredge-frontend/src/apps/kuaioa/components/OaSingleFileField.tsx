/**
 * 轻办公单文件字段：上传后存 file_uuid
 * 外观统一走平台 FileUploadComponent。
 */
import React, { useEffect, useState } from 'react';
import type { UploadFile } from 'antd/es/upload/interface';
import {
  customFieldFileValueToUploadFiles,
  extractUploadFileUuids,
  normalizeUploadFileList,
} from '../../../components/custom-fields/customFieldFileUtils';
import FileUploadComponent from '../../../components/file-upload';

const EMPLOYEE_DOC_ACCEPT =
  '.pdf,.jpg,.jpeg,.png,.gif,.webp,.doc,.docx,.xls,.xlsx,.zip,.rar';

type Props = {
  value?: string | UploadFile[] | null;
  onChange?: (value: UploadFile[]) => void;
  disabled?: boolean;
  /** 文件管理分类 */
  category?: string;
  accept?: string;
};

const OaSingleFileField: React.FC<Props> = ({
  value,
  onChange,
  disabled,
  category = 'kuaioa_employee_attachments',
  accept = EMPLOYEE_DOC_ACCEPT,
}) => {
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const list = normalizeUploadFileList(value);
      if (list.length) {
        if (!cancelled) setFileList(list.slice(0, 1));
        return;
      }
      const files = await customFieldFileValueToUploadFiles(value);
      if (!cancelled) setFileList(files.slice(0, 1));
    })();
    return () => {
      cancelled = true;
    };
  }, [value]);

  return (
    <FileUploadComponent
      category={category}
      multiple={false}
      maxCount={1}
      accept={accept}
      disabled={disabled}
      value={fileList}
      onChange={(next) => {
        const trimmed = next.slice(-1);
        setFileList(trimmed);
        onChange?.(trimmed);
      }}
    />
  );
};

export function extractOaSingleFileUuid(value: unknown): string | null {
  const uuids = extractUploadFileUuids(normalizeUploadFileList(value));
  return uuids[0] ?? null;
}

export default OaSingleFileField;
