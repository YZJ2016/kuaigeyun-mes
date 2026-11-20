/**
 * 新建单据：supplier_id / customer_id 已预填但未点选客商时，从引用展示补全头字段（含立账策略）。
 */
import type { ProFormInstance } from '@ant-design/pro-components';
import { useEffect, useRef } from 'react';
import { applyCustomerFormFields } from '../apps/kuaizhizao/pages/sales-management/shared/applyCustomerFormFields';
import { applySupplierFormFields } from '../apps/kuaizhizao/pages/purchase-management/shared/applySupplierFormFields';
import { mapPartnerReferenceDisplayItem, resolveReferenceDisplay } from './referenceDisplay';

type FormRef = React.RefObject<ProFormInstance | undefined | null>;

export function useHydrateSupplierOnCreatePrefill(options: {
  enabled: boolean;
  formRef: FormRef;
  supplierId?: number | null;
  supplierList: Array<Record<string, unknown>>;
  users?: Array<{ id: number | string; [key: string]: unknown }>;
  orgPayableDefault: string;
  defaultCurrency: string;
  hostResource?: string;
}) {
  const lastHydratedRef = useRef<number | null>(null);

  useEffect(() => {
    if (!options.enabled) {
      lastHydratedRef.current = null;
      return;
    }
    const raw =
      options.supplierId != null
        ? options.supplierId
        : options.formRef.current?.getFieldValue('supplier_id');
    const sid = raw != null ? Number(raw) : NaN;
    if (!Number.isFinite(sid) || sid <= 0) {
      lastHydratedRef.current = null;
      return;
    }
    if (lastHydratedRef.current === sid) return;

    const fromList = options.supplierList.find(
      (x) => Number(x.id ?? x.supplier_id) === sid,
    );
    if (fromList) {
      applySupplierFormFields(options.formRef, fromList, {
        users: options.users,
        supplierList: options.supplierList,
        orgPayableDefault: options.orgPayableDefault,
        defaultCurrency: options.defaultCurrency,
      });
      lastHydratedRef.current = sid;
      return;
    }

    let cancelled = false;
    void resolveReferenceDisplay({
      resource: 'master-data:supply-chain:supplier',
      recordIds: [sid],
      hostResource: options.hostResource,
    })
      .then((items) => {
        if (cancelled || !items.length) return;
        const mapped = mapPartnerReferenceDisplayItem(items[0]);
        applySupplierFormFields(options.formRef, mapped as Record<string, unknown>, {
          users: options.users,
          orgPayableDefault: options.orgPayableDefault,
          defaultCurrency: options.defaultCurrency,
        });
        lastHydratedRef.current = sid;
      })
      .catch(() => {
        /* 权限或网络失败时保留组织默认，不阻塞建单 */
      });

    return () => {
      cancelled = true;
    };
  }, [
    options.enabled,
    options.supplierId,
    options.supplierList,
    options.users,
    options.orgPayableDefault,
    options.defaultCurrency,
    options.hostResource,
    options.formRef,
  ]);

  return {
    markSupplierHydrated: (id: number | null | undefined) => {
      const n = id != null ? Number(id) : NaN;
      lastHydratedRef.current = Number.isFinite(n) && n > 0 ? n : null;
    },
  };
}

export function useHydrateCustomerOnCreatePrefill(options: {
  enabled: boolean;
  formRef: FormRef;
  customerId?: number | null;
  customerList: Array<Record<string, unknown>>;
  users?: Array<{ id: number | string; [key: string]: unknown }>;
  orgRevenueRecognitionDefault: string;
  hostResource?: string;
}) {
  const lastHydratedRef = useRef<number | null>(null);

  useEffect(() => {
    if (!options.enabled) {
      lastHydratedRef.current = null;
      return;
    }
    const raw =
      options.customerId != null
        ? options.customerId
        : options.formRef.current?.getFieldValue('customer_id');
    const cid = raw != null ? Number(raw) : NaN;
    if (!Number.isFinite(cid) || cid <= 0) {
      lastHydratedRef.current = null;
      return;
    }
    if (lastHydratedRef.current === cid) return;

    const fromList = options.customerList.find(
      (x) => Number(x.id ?? x.customer_id) === cid,
    );
    if (fromList) {
      applyCustomerFormFields(options.formRef, fromList, {
        users: options.users,
        customerList: options.customerList,
        orgRevenueRecognitionDefault: options.orgRevenueRecognitionDefault,
      });
      lastHydratedRef.current = cid;
      return;
    }

    let cancelled = false;
    void resolveReferenceDisplay({
      resource: 'master-data:supply-chain:customer',
      recordIds: [cid],
      hostResource: options.hostResource,
    })
      .then((items) => {
        if (cancelled || !items.length) return;
        const mapped = mapPartnerReferenceDisplayItem(items[0]);
        applyCustomerFormFields(options.formRef, mapped as Record<string, unknown>, {
          users: options.users,
          orgRevenueRecognitionDefault: options.orgRevenueRecognitionDefault,
        });
        lastHydratedRef.current = cid;
      })
      .catch(() => {
        /* 权限或网络失败时保留组织默认 */
      });

    return () => {
      cancelled = true;
    };
  }, [
    options.enabled,
    options.customerId,
    options.customerList,
    options.users,
    options.orgRevenueRecognitionDefault,
    options.hostResource,
    options.formRef,
  ]);

  return {
    markCustomerHydrated: (id: number | null | undefined) => {
      const n = id != null ? Number(id) : NaN;
      lastHydratedRef.current = Number.isFinite(n) && n > 0 ? n : null;
    },
  };
}