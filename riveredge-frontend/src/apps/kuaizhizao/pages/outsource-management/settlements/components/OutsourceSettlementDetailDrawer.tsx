import React, { useMemo } from 'react';
import { Empty, Result, Spin, Table, Tabs } from 'antd';
import { useTranslation } from 'react-i18next';
import type { ProDescriptionsItemProps } from '@ant-design/pro-components';
import { DetailDrawerTemplate } from '../../../../../../components/layout-templates';
import { formatBusinessDateOnly } from '../../../../../../utils/format';
import { MarkerTag, StatusTag } from '../../../../../../constants/statusBadges';
import type { OutsourceSettlement } from '../../../../services/outsource-settlement';

const REVIEW_STATUS_COLOR: Record<string, string> = {
  草稿: 'default',
  待审核: 'processing',
  已审核: 'success',
};

export type OutsourceSettlementDetailDrawerProps = {
  open: boolean;
  onClose: () => void;
  record: OutsourceSettlement | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  extra?: React.ReactNode;
};

export const OutsourceSettlementDetailDrawer: React.FC<OutsourceSettlementDetailDrawerProps> = ({
  open,
  onClose,
  record,
  loading,
  error,
  onRetry,
  extra,
}) => {
  const { t } = useTranslation();

  const columns = useMemo(
    () =>
      [
        {
          title: t('app.kuaizhizao.outsourceManagement.settlement.field.settlementCode'),
          dataIndex: 'settlement_code',
        },
        {
          title: t('app.kuaizhizao.outsourceManagement.settlement.field.supplierName'),
          dataIndex: 'supplier_name',
        },
        {
          title: t('app.kuaizhizao.outsourceManagement.settlement.field.businessDate'),
          dataIndex: 'business_date',
          render: (_, row) =>
            row.business_date ? formatBusinessDateOnly(String(row.business_date)) : '-',
        },
        {
          title: t('app.kuaizhizao.outsourceManagement.settlement.field.settlementKind'),
          dataIndex: 'settlement_kind',
          render: (_, row) =>
            row.settlement_kind === 'credit'
              ? t('app.kuaizhizao.outsourceManagement.settlement.kindCredit')
              : t('app.kuaizhizao.outsourceManagement.settlement.kindNormal'),
        },
        {
          title: t('app.kuaizhizao.outsourceManagement.settlement.field.totalAmount'),
          dataIndex: 'total_amount',
        },
        {
          title: t('app.kuaizhizao.outsourceManagement.settlement.field.invoiceStatus'),
          dataIndex: 'invoice_status',
        },
        {
          title: t('app.kuaizhizao.outsourceManagement.settlement.field.payableCode'),
          dataIndex: 'payable_code',
        },
        {
          title: t('app.kuaizhizao.outsourceManagement.settlement.field.reviewerName'),
          dataIndex: 'reviewer_name',
        },
        {
          title: t('app.kuaizhizao.outsourceManagement.settlement.field.reviewedAt'),
          dataIndex: 'reviewed_at',
        },
        {
          title: t('common.status'),
          dataIndex: 'status',
          render: (_, row) => <StatusTag color={REVIEW_STATUS_COLOR[row.status] ?? 'default'}>{row.status}</StatusTag>,
        },
        {
          title: t('app.kuaizhizao.outsourceManagement.settlement.field.reviewRemarks'),
          dataIndex: 'review_remarks',
          span: 2,
        },
        {
          title: t('common.remark'),
          dataIndex: 'notes',
          span: 2,
        },
      ] as ProDescriptionsItemProps<OutsourceSettlement>[],
    [t],
  );

  const code = String(record?.settlement_code ?? '').trim();
  const title = `${t('app.kuaizhizao.outsourceManagement.settlement.detailTitle')}${code ? ` - ${code}` : ''}`;
  const items = record?.items ?? [];
  const payables = record?.payables ?? [];

  const lineTypeLabel = (lineType?: string) => {
    if (lineType === 'material_deduction') {
      return t('app.kuaizhizao.outsourceManagement.settlement.lineTypeDeduction');
    }
    if (lineType === 'return_credit') {
      return t('app.kuaizhizao.outsourceManagement.settlement.lineTypeReturnCredit');
    }
    return t('app.kuaizhizao.outsourceManagement.settlement.lineTypeProcessing');
  };

  return (
    <DetailDrawerTemplate
      open={open}
      onClose={onClose}
      title={title}
      loading={loading && !error}
      extra={extra}
      dataSource={record ?? undefined}
      columns={columns}
      plainBody={
        error ? (
          <Result
            status="error"
            title={t('common.loadFailed')}
            subTitle={error}
            extra={
              onRetry ? (
                <a onClick={onRetry}>{t('common.retry')}</a>
              ) : undefined
            }
          />
        ) : loading && !record ? (
          <Spin />
        ) : undefined
      }
      lines={
        <Tabs
          items={[
            {
              key: 'items',
              label: t('app.kuaizhizao.outsourceManagement.settlement.itemsTitle'),
              children:
                items.length > 0 ? (
                  <Table
                    size="small"
                    rowKey={(r) => String(r.id ?? `${r.line_type}-${r.outsource_material_receipt_id}`)}
                    pagination={false}
                    dataSource={items}
                    columns={[
                      {
                        title: t('app.kuaizhizao.outsourceManagement.settlement.field.lineType'),
                        dataIndex: 'line_type',
                        render: (v: string) => <MarkerTag>{lineTypeLabel(v)}</MarkerTag>,
                      },
                      {
                        title: t('app.kuaizhizao.outsourceManagement.settlement.field.receiptCode'),
                        dataIndex: 'receipt_code',
                      },
                      {
                        title: t('app.kuaizhizao.outsourceManagement.settlement.field.workOrderCode'),
                        dataIndex: 'outsource_work_order_code',
                      },
                      {
                        title: t('app.kuaizhizao.outsourceManagement.settlement.field.productName'),
                        dataIndex: 'product_name',
                        ellipsis: true,
                      },
                      {
                        title: t('app.kuaizhizao.outsourceManagement.settlement.field.settlementQuantity'),
                        dataIndex: 'settlement_quantity',
                        align: 'right',
                      },
                      {
                        title: t('app.kuaizhizao.outsourceManagement.settlement.field.unitPrice'),
                        dataIndex: 'unit_price',
                        align: 'right',
                      },
                      {
                        title: t('app.kuaizhizao.outsourceManagement.settlement.field.lineAmount'),
                        dataIndex: 'amount',
                        align: 'right',
                      },
                    ]}
                  />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />
                ),
            },
            {
              key: 'payables',
              label: t('app.kuaizhizao.outsourceManagement.settlement.payablesTitle'),
              children:
                payables.length > 0 ? (
                  <Table
                    size="small"
                    rowKey={(r) => String(r.payable_id)}
                    pagination={false}
                    dataSource={payables}
                    columns={[
                      {
                        title: t('app.kuaizhizao.outsourceManagement.settlement.field.payableCode'),
                        dataIndex: 'payable_code',
                      },
                      { title: t('app.kuaizhizao.outsourceManagement.settlement.field.sourceType'), dataIndex: 'source_type' },
                      {
                        title: t('app.kuaizhizao.outsourceManagement.settlement.field.totalAmount'),
                        dataIndex: 'total_amount',
                        align: 'right',
                      },
                      {
                        title: t('app.kuaizhizao.outsourceManagement.settlement.field.invoiceStatus'),
                        dataIndex: 'invoice_status',
                      },
                    ]}
                  />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />
                ),
            },
          ]}
        />
      }
      linesTitle={t('app.kuaizhizao.outsourceManagement.settlement.detailTabsTitle')}
    />
  );
};
