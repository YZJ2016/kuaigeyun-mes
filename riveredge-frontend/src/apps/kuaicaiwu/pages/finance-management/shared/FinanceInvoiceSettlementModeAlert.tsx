/**
 * 组织「发票开立粒度」与当前列表页（汇总 / 明细）不一致时：整页工作区遮罩 + 引导至对应菜单。
 */
import React, { useMemo } from 'react';
import { Button, Result, theme } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { getBusinessConfig } from '../../../../../services/businessConfig';
import { orgFinanceInvoiceSettlementMode } from '../../../../../utils/documentLedgerRecognition';
import './financeInvoiceSettlementModeGuard.less';

export type FinanceInvoiceSettlementPageKind = 'sales' | 'purchase';

export const LIST_PATHS: Record<
  FinanceInvoiceSettlementPageKind,
  { summary: string; detail: string; summaryMenuKey: string; detailMenuKey: string }
> = {
  sales: {
    summary: '/apps/kuaicaiwu/finance-management/sales-invoices',
    detail: '/apps/kuaicaiwu/finance-management/sales-detail-invoices',
    summaryMenuKey: 'app.kuaicaiwu.menu.finance-management.sales-invoices',
    detailMenuKey: 'app.kuaicaiwu.menu.finance-management.sales-detail-invoices',
  },
  purchase: {
    summary: '/apps/kuaicaiwu/finance-management/purchase-invoices',
    detail: '/apps/kuaicaiwu/finance-management/purchase-detail-invoices',
    summaryMenuKey: 'app.kuaicaiwu.menu.finance-management.purchase-invoices',
    detailMenuKey: 'app.kuaicaiwu.menu.finance-management.purchase-detail-invoices',
  },
};

export type FinanceInvoiceSettlementModeAlertProps = {
  /** 本页固定粒度 */
  pageMode: 'summary' | 'detail';
  kind: FinanceInvoiceSettlementPageKind;
  children: React.ReactNode;
};

export const FinanceInvoiceSettlementModeAlert: React.FC<FinanceInvoiceSettlementModeAlertProps> = ({
  pageMode,
  kind,
  children,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const { data: businessConfig } = useQuery({
    queryKey: ['businessConfig', 'finance', 'invoice_settlement_mode'],
    queryFn: getBusinessConfig,
    staleTime: 60_000,
  });

  const orgMode = orgFinanceInvoiceSettlementMode(businessConfig);
  const paths = LIST_PATHS[kind];

  const mismatch = useMemo(() => {
    if (!businessConfig) return false;
    return orgMode !== pageMode;
  }, [businessConfig, orgMode, pageMode]);

  if (!mismatch) {
    return <>{children}</>;
  }

  const useDetailMenu = orgMode === 'detail';
  const targetPath = useDetailMenu ? paths.detail : paths.summary;
  const targetMenuLabel = t(useDetailMenu ? paths.detailMenuKey : paths.summaryMenuKey);
  const title = useDetailMenu
    ? t('app.kuaicaiwu.finance.invoiceSettlementUseDetailMenuAlert', { menu: targetMenuLabel })
    : t('app.kuaicaiwu.finance.invoiceSettlementUseSummaryMenuAlert', { menu: targetMenuLabel });

  return (
    <div className="finance-invoice-settlement-mode-guard">
      <div className="finance-invoice-settlement-mode-guard__content" aria-hidden>
        {children}
      </div>
      <div
        className="finance-invoice-settlement-mode-guard__overlay"
        style={{ background: token.colorBgMask }}
        role="alertdialog"
        aria-modal
        aria-labelledby="finance-invoice-settlement-mode-guard-title"
      >
        <Result
          className="finance-invoice-settlement-mode-guard__result"
          style={{
            background: token.colorBgContainer,
            borderRadius: token.borderRadiusLG,
            boxShadow: token.boxShadowSecondary,
          }}
          status="warning"
          title={<span id="finance-invoice-settlement-mode-guard-title">{title}</span>}
          extra={
            <Button type="primary" onClick={() => navigate(targetPath)}>
              {t('app.kuaicaiwu.finance.invoiceSettlementGoMenu', { menu: targetMenuLabel })}
            </Button>
          }
        />
      </div>
    </div>
  );
};

/**
 * 按组织「发票开立粒度」解析汇总/明细列表路由。
 * 推单入口（应付/应收/对账单 → 开票列表）须跳转到与组织粒度一致的页面，
 * 否则落入遮罩页并丢失拉单上下文。
 */
export const useOrgInvoiceListPath = (
  kind: FinanceInvoiceSettlementPageKind,
): string => {
  const { data: businessConfig } = useQuery({
    queryKey: ['businessConfig', 'finance', 'invoice_settlement_mode'],
    queryFn: getBusinessConfig,
    staleTime: 60_000,
  });
  const paths = LIST_PATHS[kind];
  return orgFinanceInvoiceSettlementMode(businessConfig) === 'detail'
    ? paths.detail
    : paths.summary;
};

export default FinanceInvoiceSettlementModeAlert;