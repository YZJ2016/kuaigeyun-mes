import type { TFunction } from 'i18next';
import type { ActionCapability } from '../../../../../hooks/useDocumentCapabilities';
import { qualityInspectionCapabilityReasonMessage } from '../../../../../hooks/useDocumentCapabilities';

export type QualityInspectionRecordWithCaps = {
  id?: number | null;
  inspection_code?: string | null;
  capabilities?: {
    delete?: ActionCapability;
    revoke_conduct?: ActionCapability;
  } | null;
};

export function filterDeletableQualityInspectionRecords<T extends QualityInspectionRecordWithCaps>(
  records: T[],
): T[] {
  return records.filter((row) => row.capabilities?.delete?.allowed);
}

export function filterRevokeConductQualityInspectionRecords<T extends QualityInspectionRecordWithCaps>(
  records: T[],
): T[] {
  return records.filter((row) => row.capabilities?.revoke_conduct?.allowed);
}

/** 批量撤回无可执行目标时：优先展示首条单据的 capabilities 原因 */
export function resolveRevokeConductBatchBlockedMessage<T extends QualityInspectionRecordWithCaps>(
  records: T[],
  t: TFunction,
): string {
  const blocked = records.find((row) => row.capabilities?.revoke_conduct?.allowed !== true);
  const reason = blocked?.capabilities?.revoke_conduct?.reason;
  return (
    qualityInspectionCapabilityReasonMessage(reason, t) ||
    t('app.kuaizhizao.quality.common.messages.revokeConductBatchEmpty', {
      defaultValue: '所选记录均不可撤回检验',
    })
  );
}
