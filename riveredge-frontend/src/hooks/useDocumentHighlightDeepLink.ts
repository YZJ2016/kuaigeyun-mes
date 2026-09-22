import { useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * 列表页 ?highlight={id} 深链：打开指定单据详情（与收货通知等页契约一致）。
 */
export function useDocumentHighlightDeepLink(
  openById: (id: number) => void | Promise<void>,
): void {
  const [searchParams] = useSearchParams();
  const openedRef = useRef(false);

  useEffect(() => {
    const highlightRaw = searchParams.get('highlight')?.trim();
    if (!highlightRaw) {
      openedRef.current = false;
      return;
    }
    if (openedRef.current) {
      return;
    }
    openedRef.current = true;
    const id = Number(highlightRaw);
    if (Number.isFinite(id) && id > 0) {
      void openById(id);
    }
  }, [openById, searchParams]);
}
