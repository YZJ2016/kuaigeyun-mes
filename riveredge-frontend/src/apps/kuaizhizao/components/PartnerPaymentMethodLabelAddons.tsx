import React, { type ReactNode } from 'react';
import { UserOutlined } from '@ant-design/icons';
import type { TFunction } from 'i18next';
import {
  formatPaymentMethodMixLabel,
  isMixedPaymentMethodCode,
  isPartnerEmployeeAdvancePaymentMethod,
} from '../../master-data/utils/paymentMethodMix';

const FIELD_LABEL_ROW_STYLE: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'baseline',
  flexWrap: 'wrap',
  columnGap: 8,
  rowGap: 4,
  maxWidth: '100%',
  lineHeight: '22px',
};

const FIELD_TITLE_STYLE: React.CSSProperties = {
  flexShrink: 0,
  whiteSpace: 'nowrap',
};

const ADDON_CLUSTER_STYLE: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'baseline',
  flexWrap: 'wrap',
  columnGap: 10,
  rowGap: 2,
  fontSize: 12,
  fontWeight: 'normal',
  lineHeight: '20px',
};

const ADDON_CLICKABLE_STYLE: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  cursor: 'pointer',
};

type FieldLabelProps = {
  title: ReactNode;
  children?: ReactNode;
};

/** 付款方式表单项标签行：标题与附属说明分列对齐 */
export function PartnerPaymentMethodFieldLabel({ title, children }: FieldLabelProps) {
  return (
    <span style={FIELD_LABEL_ROW_STYLE}>
      <span style={FIELD_TITLE_STYLE}>{title}</span>
      {children ? <span style={ADDON_CLUSTER_STYLE}>{children}</span> : null}
    </span>
  );
}

type Props = {
  t: TFunction;
  methodCode?: string | null;
  mixWire?: number | string | null;
  mixAcceptance?: number | string | null;
  advancePayeeName?: string | null;
  onAdvancePayeeClick?: () => void;
  onMixClick?: () => void;
};

/** 领款人 / 组合比例纯文字（无徽章；人名不加框） */
export function PartnerPaymentMethodLabelAddons({
  t,
  methodCode,
  mixWire,
  mixAcceptance,
  advancePayeeName,
  onAdvancePayeeClick,
  onMixClick,
}: Props) {
  const code = String(methodCode ?? '').trim();
  if (!code) return null;

  const payeeName = String(advancePayeeName ?? '').trim();
  const mixLabel = isMixedPaymentMethodCode(code)
    ? formatPaymentMethodMixLabel(mixWire, mixAcceptance)
    : undefined;

  const showPayee = isPartnerEmployeeAdvancePaymentMethod(code) && payeeName;
  const showMix = Boolean(mixLabel);

  if (!showPayee && !showMix) return null;

  return (
    <>
      {showMix && mixLabel ? (
        <span
          role="button"
          tabIndex={0}
          onClick={onMixClick}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') onMixClick?.();
          }}
          style={{
            ...ADDON_CLICKABLE_STYLE,
            color: 'var(--ant-color-text)',
          }}
        >
          {mixLabel}
        </span>
      ) : null}
      {showPayee ? (
        <span
          role="button"
          tabIndex={0}
          onClick={onAdvancePayeeClick}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') onAdvancePayeeClick?.();
          }}
          style={{
            ...ADDON_CLICKABLE_STYLE,
            color: 'var(--ant-color-text-secondary)',
          }}
        >
          <UserOutlined />
          <span>
            {t('app.kuaicaiwu.payment.advancePayee')} {payeeName}
          </span>
        </span>
      ) : null}
    </>
  );
}