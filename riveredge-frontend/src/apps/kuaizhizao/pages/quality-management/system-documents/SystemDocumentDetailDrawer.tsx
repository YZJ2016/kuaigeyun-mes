/**
 * 体系文件详情抽屉：基本信息 + 附件只读预览（查看文件）。
 * 单一 DetailDrawerTemplate 壳；加载/失败/有数据不切换双树。
 */
import React, { useMemo } from 'react';
import type { ProDescriptionsItemProps } from '@ant-design/pro-components';
import { Button, Descriptions, Result, Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  DetailDrawerTemplate,
  DRAWER_CONFIG,
  detailDrawerBasicColumn,
  useDetailDrawerDescriptionItems,
} from '../../../../../components/layout-templates';
import { rowActionKind } from '../../../../../components/uni-action';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { renderDocumentStatusTag } from '../../../../../utils/documentLifecycleStatusTag';
import { formatDateTimeBySiteSetting } from '../../../../../utils/format';
import {
  DocumentAttachmentsReadonly,
  documentAttachmentsFromRecord,
} from '../../../components/DocumentAttachmentsReadonly';
import {
  alignDescriptionColumns,
  GLOBAL_DOC_DETAIL_BASIC_FIELD_RANK,
} from '../../sales-management/shared/documentFieldAlignment';
import type { QmsSystemDocument } from '../../../services/quality-qms';
import { QMS_DOC_STATUS_OPTIONS, QMS_DOC_TYPE_OPTIONS } from '../qms/qmsMeta';
import {
  CustomFieldsDetailSection,
  hasCustomFieldsDetailContent,
} from '../../../../../components/custom-fields';
import type { CustomField } from '../../../../../services/customField';

export type SystemDocumentDetailDrawerProps = {
  open: boolean;
  document: QmsSystemDocument | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  onClose: () => void;
  canUpdate?: boolean;
  onEdit?: (doc: QmsSystemDocument) => void;
  standardLabel?: (standardId: number | null | undefined) => string;
  customFields?: CustomField[];
  customFieldValues?: Record<string, any>;
};

const SystemDocumentDetailDrawer: React.FC<SystemDocumentDetailDrawerProps> = ({
  open,
  document,
  loading = false,
  error = null,
  onRetry,
  onClose,
  canUpdate = false,
  onEdit,
  standardLabel,
  customFields = [],
  customFieldValues = {},
}) => {
  const { t } = useTranslation();

  const statusEnum = useMemo(
    () =>
      Object.fromEntries(
        QMS_DOC_STATUS_OPTIONS.map((o) => [o.value, { text: t(o.labelKey) }]),
      ),
    [t],
  );
  const typeEnum = useMemo(
    () => Object.fromEntries(QMS_DOC_TYPE_OPTIONS.map((o) => [o.value, { text: t(o.labelKey) }])),
    [t],
  );

  const detailColumns = useMemo(
    () =>
      alignDescriptionColumns<QmsSystemDocument>(
        [
          {
            title: t('app.kuaizhizao.quality.qms.documentCode'),
            dataIndex: 'document_code',
            copyable: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.title'),
            dataIndex: 'title',
          },
          {
            title: t('app.kuaizhizao.quality.qms.docTypeLabel'),
            dataIndex: 'doc_type',
            key: 'qms_system_doc_type',
            render: (_, row) => {
              const text = typeEnum[row.doc_type]?.text || row.doc_type;
              return text ? <MarkerTag color="geekblue">{text}</MarkerTag> : '-';
            },
          },
          {
            title: t('app.kuaizhizao.quality.qms.version'),
            dataIndex: 'version',
            key: 'qms_system_version',
          },
          {
            title: t('app.kuaizhizao.quality.qms.applicableStandard'),
            dataIndex: 'standard_id',
            key: 'qms_system_standard',
            render: (_, row) => standardLabel?.(row.standard_id) || '-',
          },
          {
            title: t('app.kuaizhizao.quality.qms.clauseLabel'),
            dataIndex: 'clause_labels',
            key: 'qms_system_clause_labels',
            span: 2,
            render: (_, row) => {
              const labels = row.clause_labels;
              if (!labels?.length) return '-';
              return labels.join('、');
            },
          },
          {
            title: t('app.kuaizhizao.quality.qms.ownerName'),
            dataIndex: 'owner_name',
            render: (_, row) => row.owner_name || '-',
          },
          {
            title: t('app.kuaizhizao.quality.qms.nextReviewAt'),
            dataIndex: 'next_review_at',
            key: 'qms_system_next_review_at',
            render: (_, row) => formatDateTimeBySiteSetting(row.next_review_at) || '-',
          },
          {
            title: t('app.kuaizhizao.quality.qms.effectiveAt'),
            dataIndex: 'effective_at',
            key: 'qms_system_effective_at',
            render: (_, row) => formatDateTimeBySiteSetting(row.effective_at) || '-',
          },
          {
            title: t('app.kuaizhizao.quality.qms.fileUrl'),
            dataIndex: 'file_url',
            key: 'qms_system_file_url',
            span: 2,
            render: (_, row) => {
              const url = (row.file_url || '').trim();
              if (!url) return '-';
              return (
                <Typography.Link href={url} target="_blank" rel="noopener noreferrer">
                  {url}
                </Typography.Link>
              );
            },
          },
          {
            title: t('app.kuaizhizao.quality.qms.content'),
            dataIndex: 'content',
            span: 2,
            render: (_, row) => row.content || '-',
          },
          {
            title: t('common.remark'),
            dataIndex: 'remarks',
            span: 2,
            render: (_, row) => row.remarks || '-',
          },
          {
            title: t('common.status'),
            dataIndex: 'status',
            render: (_, row) =>
              renderDocumentStatusTag(
                statusEnum[row.status]?.text || row.status || '-',
                row.status || undefined,
              ),
          },
        ] as ProDescriptionsItemProps<QmsSystemDocument>[],
        GLOBAL_DOC_DETAIL_BASIC_FIELD_RANK,
      ),
    [standardLabel, statusEnum, t, typeEnum],
  );

  const detailItems = useDetailDrawerDescriptionItems(detailColumns, document, 'qms_system_document');
  const attachments = documentAttachmentsFromRecord(document);
  const contentReady = Boolean(document);
  const showError = Boolean(error) && !contentReady && !loading;
  const showLoading = loading || (!contentReady && !showError);

  if (!open) return null;

  const titleNode = contentReady ? (
    <Space size={4}>
      <span>{t('app.kuaizhizao.menu.quality-management.system-documents')}</span>
      <Typography.Text type="secondary" copyable>
        {document!.document_code}
      </Typography.Text>
    </Space>
  ) : (
    t('app.kuaizhizao.menu.quality-management.system-documents')
  );

  return (
    <DetailDrawerTemplate
      open={open}
      onClose={onClose}
      loading={showLoading}
      size={DRAWER_CONFIG.HALF_WIDTH}
      title={titleNode}
      extra={
        contentReady && canUpdate && onEdit ? (
          <Button
            {...rowActionKind('update')}
            size="small"
            onClick={() => onEdit(document!)}
          />
        ) : null
      }
      plainBody={
        showError ? (
          <Result
            status="error"
            title={t('common.loadFailed')}
            subTitle={error || undefined}
            extra={
              onRetry ? (
                <Button type="primary" onClick={onRetry}>
                  {t('common.retry')}
                </Button>
              ) : null
            }
          />
        ) : undefined
      }
      basic={
        contentReady ? (
          <>
            <Descriptions
              column={detailDrawerBasicColumn(false)}
              size="small"
              items={detailItems}
            />
            {hasCustomFieldsDetailContent(customFields, customFieldValues) ? (
              <div style={{ marginTop: 16 }}>
                <CustomFieldsDetailSection
                  customFields={customFields}
                  customFieldValues={customFieldValues}
                />
              </div>
            ) : null}
          </>
        ) : undefined
      }
      afterBasicTitle={t('components.documentAttachments.label')}
      afterBasicVisible={contentReady}
      afterBasic={
        contentReady ? (
          <DocumentAttachmentsReadonly attachments={attachments} showEmpty />
        ) : undefined
      }
    />
  );
};

export default SystemDocumentDetailDrawer;
