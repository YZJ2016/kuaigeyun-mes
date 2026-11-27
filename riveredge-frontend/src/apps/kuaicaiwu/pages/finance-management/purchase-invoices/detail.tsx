import React, { useEffect, useMemo, useState } from 'react';
import { ProDescriptions } from '@ant-design/pro-components';
import { App, Button, Spin, Empty, Typography, Timeline, Space, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { purchaseInvoiceService } from '../../../services/finance/purchase-invoice';
import { PurchaseInvoice, PurchaseInvoiceLine } from '../../../types/finance/purchase-invoice';
import { formatAmount } from '../../../../../utils/format';
import { UniWorkflowActions } from '../../../../../components/uni-workflow-actions';
import { UniLifecycle } from '../../../../../components/uni-lifecycle';
import {
  DetailDrawerSection,
  DOCUMENT_DETAIL_PAGE_HEADER_STYLE,
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  uniTabsChildPageVerticalInsetStyle,
} from '../../../../../components/layout-templates';
import { getChineseInvoiceLifecycle } from '../../../utils/financeLifecycle';
import { formatChineseInvoiceType } from '../../../utils/financeSharedOptions';
import { canDeletePurchaseInvoice } from '../../../utils/purchaseInvoiceUi';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { formatApiErrorDetail } from '../../../../../services/api';

const P = 'app.kuaicaiwu.purchaseInvoice';
const LINE = 'app.kuaicaiwu.salesInvoice';
const PURCHASE_INVOICE_RESOURCE = 'kuaicaiwu:purchase-invoice';

function moneyCell(v: string | number | undefined | null) {
  const n = Number(v ?? 0);
  const abs = formatAmount(Math.abs(n));
  return n < 0 ? `-${abs}` : abs;
}

function formatPurchaseInvoiceLedgerPostingMode(
  mode: string | null | undefined,
  t: (key: string) => string,
): string {
  return mode === 'by_invoice'
    ? t('app.kuaicaiwu.partnerStatement.ledgerPostingMode.byInvoice')
    : t('app.kuaicaiwu.partnerStatement.ledgerPostingMode.immediate');
}

function formatInvoiceLineSourceTrace(row: PurchaseInvoiceLine): string {
  const docType = String(row.source_doc_type ?? '').trim();
  const docId = Number(row.source_doc_id ?? 0);
  const lineId = Number(row.source_line_id ?? 0);
  if (!docType || docId <= 0) {
    return '—';
  }
  return lineId > 0 ? `${docType} ${docId} / ${lineId}` : `${docType} ${docId}`;
}

const PurchaseInvoiceDetail: React.FC = () => {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const invoiceListBase = location.pathname.includes('/purchase-detail-invoices')
    ? '/apps/kuaicaiwu/finance-management/purchase-detail-invoices'
    : '/apps/kuaicaiwu/finance-management/purchase-invoices';
  const [data, setData] = useState<PurchaseInvoice>();
  const [loading, setLoading] = useState(false);
  const purchaseInvoicePerms = useResourcePermissions(PURCHASE_INVOICE_RESOURCE);

  const pageTitle = useMemo(() => {
    const num = String(data?.invoice_number ?? '').trim();
    return num ? t(`${P}.detailTitleWithNumber`, { number: num }) : t(`${P}.detailTitle`);
  }, [data?.invoice_number, t]);

  const tabTitle = useMemo(() => {
    const num = String(data?.invoice_number ?? '').trim();
    return num || t(`${P}.detailTitle`);
  }, [data?.invoice_number, t]);

  useEffect(() => {
    if (!data) return;
    const tabKey = location.pathname + location.search;
    window.dispatchEvent(
      new CustomEvent('riveredge:update-tab-title', {
        detail: { key: tabKey, title: tabTitle },
      }),
    );
  }, [data, tabTitle, location.pathname, location.search]);

  const loadData = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const res = await purchaseInvoiceService.get(Number(id));
      setData(res);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [id]);

  const remove = () => {
    if (!id || !data) return;
    modal.confirm({
      title: t(`${P}.deleteTitle`),
      content: t(`${P}.deleteConfirm`),
      okType: 'danger',
      onOk: async () => {
        try {
          await purchaseInvoiceService.delete(Number(id));
          message.success(t('common.deleteSuccess'));
          navigate(invoiceListBase);
        } catch (e: unknown) {
          const err = e as { response?: { data?: { detail?: unknown } }; message?: string };
          message.error(
            formatApiErrorDetail(err?.response?.data?.detail)
              || err?.message
              || t('common.operationFailed'),
          );
          throw e;
        }
      },
    });
  };

  const pageActions = data ? (
    <>
      <Button onClick={() => navigate(-1)}>{t('common.back')}</Button>
      <UniWorkflowActions
        record={data}
        apiPrefix="/apps/kuaicaiwu/purchase-invoices"
        entityType="purchase_invoice"
        entityName={t(`${P}.entityName`)}
        statusField="status"
        reviewStatusField="review_status"
        draftStatuses={['草稿', 'draft']}
        pendingStatuses={['待审核']}
        approvedStatuses={['已审核']}
        rejectedStatuses={['已驳回', '驳回']}
        theme="default"
        onSuccess={loadData}
      />
      {canDeletePurchaseInvoice(data) && purchaseInvoicePerms.canDelete ? (
        <Button danger onClick={remove}>
          {t('common.delete')}
        </Button>
      ) : null}
    </>
  ) : null;

  const lineColumns: ColumnsType<PurchaseInvoiceLine> = useMemo(
    () => [
      { title: t('app.kuaicaiwu.invoice.line.itemName'), dataIndex: 'item_name', width: 200 },
      { title: t('app.kuaicaiwu.invoice.line.specModel'), dataIndex: 'spec_model', width: 120 },
      {
        title: t('app.kuaicaiwu.invoice.line.invoiceNumber'),
        dataIndex: 'invoice_number',
        width: 128,
        ellipsis: true,
        render: (v) => {
          const line = String(v ?? '').trim();
          if (line) return line;
          const header = String(data?.invoice_number ?? '').trim();
          return header || '—';
        },
      },
      { title: t('common.unit'), dataIndex: 'unit', width: 72 },
      {
        title: t('common.quantity'),
        dataIndex: 'quantity',
        width: 88,
        align: 'right',
        render: (v) => (v == null || v === '' ? '—' : String(v)),
      },
      {
        title: t(`${LINE}.line.unitPriceExcl`),
        dataIndex: 'unit_price',
        width: 110,
        align: 'right',
        render: (v) => (v == null || v === '' ? '—' : moneyCell(v)),
      },
      {
        title: t('app.kuaicaiwu.invoice.line.taxRate'),
        dataIndex: 'tax_rate',
        width: 72,
        align: 'right',
        render: (_, r) => {
          const n = Number(r.tax_rate);
          const pct = !Number.isFinite(n) || n <= 0 ? 0 : n < 1 ? n * 100 : n;
          return `${pct.toFixed(2)}%`;
        },
      },
      {
        title: t(`${LINE}.line.amountExcl`),
        dataIndex: 'amount',
        width: 120,
        align: 'right',
        render: (_, r) => moneyCell(r.amount),
      },
      {
        title: t('app.kuaicaiwu.invoice.line.taxAmount'),
        dataIndex: 'tax_amount',
        width: 100,
        align: 'right',
        render: (_, r) => moneyCell(r.tax_amount),
      },
      {
        title: t('app.kuaicaiwu.invoice.line.sourceTrace'),
        key: 'source_trace',
        width: 160,
        ellipsis: true,
        render: (_, r) => formatInvoiceLineSourceTrace(r),
      },
    ],
    [t, data?.invoice_number],
  );

  const renderShell = (body: React.ReactNode) => (
    <div style={uniTabsChildPageVerticalInsetStyle()}>
      <div style={DOCUMENT_DETAIL_PAGE_HEADER_STYLE}>
        <Typography.Title level={4} style={DOCUMENT_DETAIL_PAGE_TITLE_STYLE}>
          {pageTitle}
        </Typography.Title>
        {pageActions ? <Space wrap size={8}>{pageActions}</Space> : null}
      </div>
      {body}
    </div>
  );

  if (!id) return null;

  if (loading && !data) {
    return renderShell(
      <div style={{ padding: '48px 0', textAlign: 'center' }}>
        <Spin size="large" />
      </div>,
    );
  }

  if (!data) {
    return renderShell(<Empty description={t(`${P}.detailNotFound`)} />);
  }

  const lc = getChineseInvoiceLifecycle(data as unknown as Record<string, unknown>, t);

  return renderShell(
    <>
      <DetailDrawerSection title={t('app.uniDetail.sectionBasic')}>
        <ProDescriptions column={3} dataSource={data as unknown as Record<string, unknown>} loading={loading}>
          <ProDescriptions.Item label={t(`${P}.col.purchaseOrder`)}>{data.purchase_order_code || '-'}</ProDescriptions.Item>
          <ProDescriptions.Item label={t('app.kuaicaiwu.common.supplier')}>{data.supplier_name}</ProDescriptions.Item>
          <ProDescriptions.Item label={t(`${P}.col.invoiceNumber`)}>{data.invoice_number || '-'}</ProDescriptions.Item>
          <ProDescriptions.Item label={t('app.kuaicaiwu.common.invoiceDate')}>{data.invoice_date}</ProDescriptions.Item>
          <ProDescriptions.Item label={t(`${P}.col.settlementClosingDate`)}>
            {data.settlement_closing_date || '—'}
          </ProDescriptions.Item>
          <ProDescriptions.Item label={t('app.kuaizhizao.purchase.field.department')}>
            {data.department_name || '—'}
          </ProDescriptions.Item>
          <ProDescriptions.Item label={t('app.kuaicaiwu.partnerStatement.ledgerPostingMode')}>
            {formatPurchaseInvoiceLedgerPostingMode(data.ledger_posting_mode, t)}
          </ProDescriptions.Item>
          <ProDescriptions.Item label={t(`${P}.col.invoiceType`)}>{formatChineseInvoiceType(data.invoice_type, t)}</ProDescriptions.Item>
          <ProDescriptions.Item label={t(`${P}.col.invoiceAmount`)}>{data.invoice_amount}</ProDescriptions.Item>
          <ProDescriptions.Item label={t(`${P}.col.taxAmount`)}>{data.tax_amount}</ProDescriptions.Item>
          <ProDescriptions.Item label={t(`${P}.col.totalAmount`)}>{data.total_amount}</ProDescriptions.Item>
          <ProDescriptions.Item label={t(`${P}.col.discountAmount`)}>
            {data.discount_amount ?? 0}
          </ProDescriptions.Item>
          <ProDescriptions.Item label={t(`${P}.col.taxRate`)}>{data.tax_rate}%</ProDescriptions.Item>
          <ProDescriptions.Item label={t('app.kuaicaiwu.common.businessStatus')}>{data.status}</ProDescriptions.Item>
          <ProDescriptions.Item label={t('app.kuaicaiwu.common.reviewStatus')}>{data.review_status}</ProDescriptions.Item>
          <ProDescriptions.Item label={t(`${P}.col.linkedPayable`)}>{data.payable_code || '-'}</ProDescriptions.Item>
          <ProDescriptions.Item label={t('common.remark')} span={3}>
            {data.notes || '-'}
          </ProDescriptions.Item>
        </ProDescriptions>
      </DetailDrawerSection>

      <DetailDrawerSection title={t('app.uniDetail.sectionCollaboration')}>
        <UniLifecycle
          percent={lc.percent}
          stageName={lc.stageName}
          status={lc.status}
          subStages={lc.subStages}
          showLabel
          size="small"
          showCircleTooltip={false}
        />
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          {t(`${P}.lifecycleHint`)}
        </Typography.Paragraph>
      </DetailDrawerSection>

      <DetailDrawerSection title={t('app.uniDetail.sectionLines')}>
        <Table<PurchaseInvoiceLine>
          size="small"
          rowKey="id"
          pagination={false}
          columns={lineColumns}
          dataSource={data.items || []}
          locale={{ emptyText: t(`${P}.noLines`) }}
          scroll={{ x: 1000 }}
        />
      </DetailDrawerSection>

      <DetailDrawerSection title={t('app.uniDetail.sectionTimeline')} marginBottom={0}>
        <Timeline
          items={[
            { color: 'green', children: t(`${P}.activityCreated`, { time: data.created_at }) },
            ...(data.updated_at && data.updated_at !== data.created_at
              ? [{ color: 'blue', children: t(`${P}.activityUpdated`, { time: data.updated_at }) }]
              : []),
          ]}
        />
      </DetailDrawerSection>
    </>,
  );
};

export default PurchaseInvoiceDetail;
