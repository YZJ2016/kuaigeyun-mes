/**
 * 关联单据详情抽屉（当前页嵌套打开，不跳转列表）。
 * 唯一入口：openLinkedDocumentDetail(type, id, options?)。
 * 内容：各单据原版 DetailDrawerTemplate 插槽壳（禁止 Brief / plainBody 另写）。
 */

import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { DrawerProps } from 'antd';
import { theme } from 'antd';
import { useNavigate } from 'react-router-dom';
import {
  canOpenLinkedDocumentDetail,
  normalizeLinkedDocumentType,
} from '../../apps/kuaizhizao/utils/linkedDocumentDetail';
import { DetailDrawerChromeProvider } from '../layout-templates';
import { SalesOrderLinkedDetailDrawer } from './drawers/SalesOrderLinkedDetailDrawer';
import { PurchaseOrderLinkedDetailDrawer } from './drawers/PurchaseOrderLinkedDetailDrawer';
import { QuotationLinkedDetailDrawer } from './drawers/QuotationLinkedDetailDrawer';
import { SalesDeliveryLinkedDetailDrawer } from './drawers/SalesDeliveryLinkedDetailDrawer';
import { PurchaseReceiptLinkedDetailDrawer } from './drawers/PurchaseReceiptLinkedDetailDrawer';
import { SalesForecastLinkedDetailDrawer } from './drawers/SalesForecastLinkedDetailDrawer';
import { DemandLinkedDetailDrawer } from './drawers/DemandLinkedDetailDrawer';
import { PurchaseRequisitionLinkedDetailDrawer } from './drawers/PurchaseRequisitionLinkedDetailDrawer';
import { DemandComputationLinkedDetailDrawer } from './drawers/DemandComputationLinkedDetailDrawer';
import { WorkOrderLinkedDetailDrawer } from './drawers/WorkOrderLinkedDetailDrawer';
import { FreightOrderLinkedDetailDrawer } from './drawers/FreightOrderLinkedDetailDrawer';
import { ReportingRecordLinkedDetailDrawer } from './drawers/ReportingRecordLinkedDetailDrawer';
import { PerformanceSummaryLinkedDetailDrawer } from './drawers/PerformanceSummaryLinkedDetailDrawer';
import { AfterSalesLinkedDetailDrawer } from './drawers/AfterSalesLinkedDetailDrawer';

/** 高于列表详情抽屉、报价内嵌关联，以及在线消息壳（z-index 1050） */
const LINKED_DRAWER_Z_OFFSET = 80;
/** 在线消息右下角壳层，关联抽屉须压过它 */
const UNI_IM_SHELL_Z_INDEX = 1050;

export type OpenLinkedDocumentDetailOptions = {
  /** 停靠侧；在线消息等从右侧浮层打开时传 left，避免挡住聊天窗 */
  placement?: DrawerProps['placement'];
};

type OpenFn = (
  documentType: string,
  documentId: number,
  options?: OpenLinkedDocumentDetailOptions,
) => boolean;

type CtxValue = {
  openLinkedDocumentDetail: OpenFn;
};

const LinkedDocumentDetailContext = createContext<CtxValue | null>(null);

export function useLinkedDocumentDetail(): CtxValue {
  const ctx = useContext(LinkedDocumentDetailContext);
  if (!ctx) {
    throw new Error('useLinkedDocumentDetail must be used within LinkedDocumentDetailProvider');
  }
  return ctx;
}

/** 无 Provider 时不抛错（如单测）；有则打开抽屉 */
export function useOptionalLinkedDocumentDetail(): CtxValue | null {
  return useContext(LinkedDocumentDetailContext);
}

type Target = {
  documentType: string;
  documentId: number;
  placement?: DrawerProps['placement'];
};

function LinkedDocumentDetailHost({
  target,
  onClose,
}: {
  target: Target | null;
  onClose: () => void;
}) {
  const { token } = theme.useToken();
  const zIndex = Math.max(
    token.zIndexPopupBase + LINKED_DRAWER_Z_OFFSET,
    UNI_IM_SHELL_Z_INDEX + 10,
  );
  const open = Boolean(target);
  const documentType = target?.documentType ?? '';
  const documentId = target?.documentId ?? 0;
  const chrome = useMemo(
    () => ({
      placement: target?.placement ?? 'right',
      zIndex,
    }),
    [target?.placement, zIndex],
  );

  if (!open || documentId <= 0) return null;

  let drawer: React.ReactNode = null;
  switch (documentType) {
    case 'sales_order':
      drawer = (
        <SalesOrderLinkedDetailDrawer
          open
          documentId={documentId}
          onClose={onClose}
          zIndex={zIndex}
        />
      );
      break;
    case 'purchase_order':
      drawer = (
        <PurchaseOrderLinkedDetailDrawer
          open
          documentId={documentId}
          onClose={onClose}
          zIndex={zIndex}
        />
      );
      break;
    case 'quotation':
      drawer = (
        <QuotationLinkedDetailDrawer
          open
          documentId={documentId}
          onClose={onClose}
          zIndex={zIndex}
        />
      );
      break;
    case 'sales_delivery':
      drawer = (
        <SalesDeliveryLinkedDetailDrawer
          open
          documentId={documentId}
          onClose={onClose}
          zIndex={zIndex}
        />
      );
      break;
    case 'purchase_receipt':
      drawer = (
        <PurchaseReceiptLinkedDetailDrawer
          open
          documentId={documentId}
          onClose={onClose}
          zIndex={zIndex}
        />
      );
      break;
    case 'sales_forecast':
      drawer = (
        <SalesForecastLinkedDetailDrawer
          open
          documentId={documentId}
          onClose={onClose}
          zIndex={zIndex}
        />
      );
      break;
    case 'demand':
      drawer = (
        <DemandLinkedDetailDrawer
          open
          documentId={documentId}
          onClose={onClose}
          zIndex={zIndex}
        />
      );
      break;
    case 'purchase_requisition':
      drawer = (
        <PurchaseRequisitionLinkedDetailDrawer
          open
          documentId={documentId}
          onClose={onClose}
          zIndex={zIndex}
        />
      );
      break;
    case 'demand_computation':
      drawer = (
        <DemandComputationLinkedDetailDrawer
          open
          documentId={documentId}
          onClose={onClose}
          zIndex={zIndex}
        />
      );
      break;
    case 'work_order':
      drawer = (
        <WorkOrderLinkedDetailDrawer
          open
          documentId={documentId}
          onClose={onClose}
          zIndex={zIndex}
        />
      );
      break;
    case 'freight_order':
      drawer = (
        <FreightOrderLinkedDetailDrawer
          open
          documentId={documentId}
          onClose={onClose}
          zIndex={zIndex}
        />
      );
      break;
    case 'reporting_record':
      drawer = (
        <ReportingRecordLinkedDetailDrawer
          open
          documentId={documentId}
          onClose={onClose}
          zIndex={zIndex}
        />
      );
      break;
    case 'performance_summary':
      drawer = (
        <PerformanceSummaryLinkedDetailDrawer
          open
          documentId={documentId}
          onClose={onClose}
          zIndex={zIndex}
        />
      );
      break;
    case 'after_sales_ticket':
    case 'install_execution':
    case 'service_asset':
    case 'repair_order':
    case 'service_dispatch':
    case 'spare_part_requisition':
    case 'service_settlement':
    case 'customer_return_visit':
      drawer = (
        <AfterSalesLinkedDetailDrawer
          open
          documentType={documentType}
          documentId={documentId}
          onClose={onClose}
          zIndex={zIndex}
        />
      );
      break;
    default:
      return null;
  }

  return <DetailDrawerChromeProvider value={chrome}>{drawer}</DetailDrawerChromeProvider>;
}

export function LinkedDocumentDetailProvider({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const [target, setTarget] = useState<Target | null>(null);

  const openLinkedDocumentDetail = useCallback<OpenFn>(
    (documentType, documentId, options) => {
      const type = normalizeLinkedDocumentType(documentType);
      const id = Number(documentId);
      if (!canOpenLinkedDocumentDetail(type) || !Number.isFinite(id) || id <= 0) return false;
      if (type === 'delivery_project') {
        navigate(`/apps/kuaizhizao/delivery-project/projects/${id}`);
        return true;
      }
      setTarget({
        documentType: type,
        documentId: id,
        placement: options?.placement,
      });
      return true;
    },
    [navigate],
  );

  const onClose = useCallback(() => setTarget(null), []);

  const value = useMemo(() => ({ openLinkedDocumentDetail }), [openLinkedDocumentDetail]);

  return (
    <LinkedDocumentDetailContext.Provider value={value}>
      {children}
      <LinkedDocumentDetailHost target={target} onClose={onClose} />
    </LinkedDocumentDetailContext.Provider>
  );
}

/** 供非 React 点击处复用：优先抽屉，无 Provider 时返回 false */
export function openLinkedDocumentDetailOrFalse(
  ctx: CtxValue | null,
  documentType: string,
  documentId: number,
  options?: OpenLinkedDocumentDetailOptions,
): boolean {
  if (!ctx) return false;
  return ctx.openLinkedDocumentDetail(documentType, documentId, options);
}
