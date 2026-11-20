/**
 * 往来对账单：立账方式 + 金额口径（新建预览区与详情编辑区共用）
 */
import React from 'react';
import { Space, Tooltip, Typography, message } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ThemedSegmented } from '../../../../../components/themed-segmented';
import type { PartnerStatementAmountBasis } from '../../../services/finance/partnerStatement';

const PS = 'app.kuaicaiwu.partnerStatement';

function PartnerStatementSettingLabel({ label, hint }: { label: string; hint: string }) {
  return (
    <Space size={4} align="center">
      <Typography.Text>{label}</Typography.Text>
      <Tooltip title={hint}>
        <QuestionCircleOutlined
          aria-label={hint}
          style={{ color: 'var(--ant-color-text-tertiary)', fontSize: 12, cursor: 'help' }}
        />
      </Tooltip>
    </Space>
  );
}

export type PartnerStatementSettingsBarProps = {
  showLedger: boolean;
  ledgerMode: 'immediate' | 'by_invoice';
  amountBasis: PartnerStatementAmountBasis;
  headerBusy?: boolean;
  /** 详情：有未保存明细时禁止改口径 */
  blockAmountBasisChange?: boolean;
  onLedgerChange: (mode: 'immediate' | 'by_invoice') => void;
  onAmountBasisChange: (basis: PartnerStatementAmountBasis) => void;
};

export function PartnerStatementSettingsBar({
  showLedger,
  ledgerMode,
  amountBasis,
  headerBusy = false,
  blockAmountBasisChange = false,
  onLedgerChange,
  onAmountBasisChange,
}: PartnerStatementSettingsBarProps) {
  const { t } = useTranslation();

  return (
    <div
      style={{
        marginBottom: 16,
        border: '1px solid rgba(0, 0, 0, 0.06)',
        borderRadius: 6,
        padding: '10px 16px',
        background: '#fafafa',
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: '12px 24px',
      }}
    >
      {showLedger ? (
        <Space wrap size={8} align="center">
          <PartnerStatementSettingLabel
            label={t(`${PS}.ledgerPostingMode`)}
            hint={t(`${PS}.ledgerPostingModeHint`)}
          />
          <ThemedSegmented
            surfaceBackground
            disabled={headerBusy}
            value={ledgerMode}
            onChange={(value) => onLedgerChange(value as 'immediate' | 'by_invoice')}
            options={[
              { label: t(`${PS}.ledgerPostingMode.immediate`), value: 'immediate' },
              { label: t(`${PS}.ledgerPostingMode.byInvoice`), value: 'by_invoice' },
            ]}
          />
        </Space>
      ) : null}
      <Space wrap size={8} align="center">
        <PartnerStatementSettingLabel label={t(`${PS}.amountBasis`)} hint={t(`${PS}.amountBasisHint`)} />
        <ThemedSegmented
          surfaceBackground
          disabled={headerBusy}
          value={amountBasis}
          onChange={(value) => {
            const next = value as PartnerStatementAmountBasis;
            if (next === amountBasis) {
              return;
            }
            if (blockAmountBasisChange) {
              message.warning(t(`${PS}.detail.saveLinesBeforeAmountBasis`));
              return;
            }
            onAmountBasisChange(next);
          }}
          options={[
            { label: t(`${PS}.amountBasis.taxInclusive`), value: 'tax_inclusive' },
            { label: t(`${PS}.amountBasis.taxExclusive`), value: 'tax_exclusive' },
          ]}
        />
      </Space>
    </div>
  );
}