import type { TFunction } from 'i18next';

/** 工装台账状态展示（canonical + 历史别名） */
export function toolStatusTag(
  status: string | undefined,
  t: TFunction,
): { text: string; color: string } {
  const statusMap: Record<string, { text: string; color: string }> = {
    待启用: { text: t('app.kuaizhizao.toolLedger.statusPendingActivation'), color: 'default' },
    待用: { text: t('app.kuaizhizao.toolLedger.statusNormal'), color: 'success' },
    正常: { text: t('app.kuaizhizao.toolLedger.statusNormal'), color: 'success' },
    在用: { text: t('app.kuaizhizao.toolLedger.statusInUse'), color: 'processing' },
    领用中: { text: t('app.kuaizhizao.toolLedger.statusCheckedOut'), color: 'processing' },
    保养中: { text: t('app.kuaizhizao.toolLedger.statusMaintaining'), color: 'warning' },
    维修中: { text: t('app.kuaizhizao.toolLedger.statusRepairing'), color: 'warning' },
    校验中: { text: t('app.kuaizhizao.toolLedger.statusCalibrating'), color: 'warning' },
    停用: { text: t('app.kuaizhizao.toolLedger.statusDisabled'), color: 'default' },
    报废: { text: t('app.kuaizhizao.toolLedger.statusScrapped'), color: 'error' },
  };
  return statusMap[status ?? ''] ?? { text: status ?? '-', color: 'default' };
}

/** 高级搜索 / 筛选 valueEnum（键为后端 canonical 值） */
export function buildToolStatusValueEnum(t: TFunction): Record<string, { text: string }> {
  return {
    待启用: { text: t('app.kuaizhizao.toolLedger.statusPendingActivation') },
    待用: { text: t('app.kuaizhizao.toolLedger.statusNormal') },
    在用: { text: t('app.kuaizhizao.toolLedger.statusInUse') },
    保养中: { text: t('app.kuaizhizao.toolLedger.statusMaintaining') },
    维修中: { text: t('app.kuaizhizao.toolLedger.statusRepairing') },
    校验中: { text: t('app.kuaizhizao.toolLedger.statusCalibrating') },
    停用: { text: t('app.kuaizhizao.toolLedger.statusDisabled') },
    报废: { text: t('app.kuaizhizao.toolLedger.statusScrapped') },
  };
}
