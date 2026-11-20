/**
 * 快制造统一打印弹窗状态
 */

import { useCallback, useMemo, useState } from 'react';
import KuaizhizaoDocumentPrintModal from '../components/KuaizhizaoDocumentPrintModal';
import {
  buildKuaizhizaoPrintApiPath,
  getKuaizhizaoPrintTitle,
  type KuaizhizaoPrintDocumentType,
} from '../utils/kuaizhizaoPrintConfig';

export interface KuaizhizaoPrintTarget {
  documentType: KuaizhizaoPrintDocumentType | string;
  documentId: number;
  /**
   * 多单批量打印：预览内按单据分别成页展示。
   * 有值时以本数组为准；documentId 可填首个 id。
   */
  documentIds?: number[];
  title?: string;
  printApiPath?: string;
  /** 合并进打印预览/PDF 请求的额外 query（如设备卡批量 uuids） */
  printApiParams?: Record<string, string | number | boolean | Array<string | number>>;
  pdfDownloadFilename?: string;
}

export function useKuaizhizaoPrintModal(options?: {
  onAfterPrint?: (target: KuaizhizaoPrintTarget) => void | Promise<void>;
}) {
  const [target, setTarget] = useState<KuaizhizaoPrintTarget | null>(null);

  const openPrint = useCallback((next: KuaizhizaoPrintTarget) => {
    const batchIds = (next.documentIds ?? [])
      .map((id) => Number(id))
      .filter((id) => Number.isFinite(id) && id > 0);
    if (batchIds.length > 0) {
      setTarget({
        ...next,
        documentId: next.documentId > 0 ? next.documentId : batchIds[0],
        documentIds: batchIds,
      });
      return;
    }
    if (!next.documentId) return;
    setTarget(next);
  }, []);

  const closePrint = useCallback(() => setTarget(null), []);

  const PrintModal = useMemo(
    () => (
      <KuaizhizaoDocumentPrintModal
        open={!!target}
        onClose={closePrint}
        documentType={target?.documentType ?? ''}
        documentId={target?.documentId ?? null}
        documentIds={target?.documentIds}
        printApiPath={
          target
            ? target.printApiPath ?? buildKuaizhizaoPrintApiPath(target.documentType, target.documentId)
            : ''
        }
        printApiParams={target?.printApiParams}
        title={target?.title ?? (target ? getKuaizhizaoPrintTitle(target.documentType) : '打印预览')}
        pdfDownloadFilename={target?.pdfDownloadFilename}
        onAfterPrint={target && options?.onAfterPrint ? () => options.onAfterPrint!(target) : undefined}
      />
    ),
    [target, closePrint, options?.onAfterPrint],
  );

  return { openPrint, closePrint, printTarget: target, PrintModal };
}
