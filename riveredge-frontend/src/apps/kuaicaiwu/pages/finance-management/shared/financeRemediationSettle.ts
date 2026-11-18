/** 补救核销：是否可按付款单/收款单上已记录的来源直接核销（无需再选手工匹配）。 */

export type PullLineSourceHint = {
  source_type?: string | null;
};

export function paymentHasLinkedAutoSettleSource(
  pullLines?: PullLineSourceHint[] | null,
): boolean {
  if (!pullLines?.length) {
    return false;
  }
  return pullLines.every((line) => {
    const st = String(line.source_type || '').trim();
    return st === 'payable' || st === 'payment_application';
  });
}

/** 补核销失败时：仅「从未关联清账来源」才打开选手工单弹窗，勿把「已有来源但核销失败」误当成手工匹配。 */
export function shouldOpenManualRemediationAfterRepairFailure(
  apiMessage: string,
  side: 'payment' | 'receipt',
): boolean {
  const msg = String(apiMessage || '').trim();
  if (!msg) return false;
  if (side === 'payment') {
    return msg.includes('须指定清账来源');
  }
  return msg.includes('须从应收单加载创建并关联应收后再确认');
}
