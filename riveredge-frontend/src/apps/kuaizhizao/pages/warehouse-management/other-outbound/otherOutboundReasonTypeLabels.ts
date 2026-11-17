/** 其他出库原因类型展示：字典值为中文；历史/对接数据可能存英文码（与 i18n key 后缀一致）。 */
export const OTHER_OUTBOUND_REASON_TYPE_I18N: Record<string, string> = {
  盘亏: 'app.kuaizhizao.otherOutbound.reason.loss',
  样品: 'app.kuaizhizao.otherOutbound.reason.sample',
  报废: 'app.kuaizhizao.otherOutbound.reason.scrap',
  其他: 'app.kuaizhizao.otherOutbound.reason.other',
  loss: 'app.kuaizhizao.otherOutbound.reason.loss',
  sample: 'app.kuaizhizao.otherOutbound.reason.sample',
  scrap: 'app.kuaizhizao.otherOutbound.reason.scrap',
  other: 'app.kuaizhizao.otherOutbound.reason.other',
};

export function translateOtherOutboundReasonTypeLabel(
  t: (key: string) => string,
  value: string | undefined,
  options?: Array<{ label: string; value: string }>,
): string {
  if (!value) return '-';
  const fromDict = options?.find((o) => o.value === value);
  if (fromDict?.label) return fromDict.label;
  const key = OTHER_OUTBOUND_REASON_TYPE_I18N[value];
  return key ? t(key) : value;
}

export function mapOtherOutboundReasonTypeOptions(
  items: Array<{ label: string; value: string }>,
  t: (key: string) => string,
): Array<{ label: string; value: string }> {
  return items.map(({ value, label }) => ({
    value,
    label: OTHER_OUTBOUND_REASON_TYPE_I18N[value] ? t(OTHER_OUTBOUND_REASON_TYPE_I18N[value]) : label,
  }));
}
