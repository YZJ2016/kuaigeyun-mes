import React, { useContext, useEffect, useRef, useState } from 'react';
import { Form } from 'antd';
import type { DocumentLineMaterialPreviewItem } from '../../../../../components/document-line-materials-preview';
import { normalizeFormListItems } from '../../../../../utils/formListItems';
import {
  collectPayableIdsNeedingMaterialPreview,
  fetchPayableLineMaterialPreviewItems,
} from './paymentApplicationLineMaterialsPreview';

const PaymentApplicationPayablePreviewContext = React.createContext<
  Record<number, DocumentLineMaterialPreviewItem[]>
>({});

export function usePaymentApplicationPayableMaterialPreviewMap() {
  return useContext(PaymentApplicationPayablePreviewContext);
}

export function PaymentApplicationFormPayableMaterialPreviewsProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const items = Form.useWatch('items');
  const [payablePreviewByPayableId, setPayablePreviewByPayableId] = useState<
    Record<number, DocumentLineMaterialPreviewItem[]>
  >({});
  const cacheRef = useRef<Record<number, DocumentLineMaterialPreviewItem[]>>({});
  const inflightRef = useRef(new Set<number>());

  useEffect(() => {
    const payableIds = collectPayableIdsNeedingMaterialPreview(items);
    const missing = payableIds.filter(
      (id) => !cacheRef.current[id]?.length && !inflightRef.current.has(id),
    );
    if (!missing.length) {
      return;
    }
    let cancelled = false;
    for (const id of missing) {
      inflightRef.current.add(id);
    }
    void (async () => {
      const fetched: Record<number, DocumentLineMaterialPreviewItem[]> = {};
      await Promise.all(
        missing.map(async (payableId) => {
          try {
            const preview = await fetchPayableLineMaterialPreviewItems(payableId);
            if (preview.length) {
              fetched[payableId] = preview;
            }
          } finally {
            inflightRef.current.delete(payableId);
          }
        }),
      );
      if (cancelled || !Object.keys(fetched).length) {
        return;
      }
      cacheRef.current = { ...cacheRef.current, ...fetched };
      setPayablePreviewByPayableId((prev) => ({ ...prev, ...fetched }));
    })();
    return () => {
      cancelled = true;
    };
  }, [items]);

  return (
    <PaymentApplicationPayablePreviewContext.Provider value={payablePreviewByPayableId}>
      {children}
    </PaymentApplicationPayablePreviewContext.Provider>
  );
}

export function resolveFormPaymentApplicationLineRow(
  items: unknown,
  fieldIndex: number,
): Record<string, unknown> {
  return normalizeFormListItems<Record<string, unknown>>(items)[fieldIndex] ?? {};
}