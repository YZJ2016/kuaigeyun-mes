import React, { useCallback, useRef, useState, type CSSProperties } from 'react';
import { App, Col, InputNumber, Modal, Row } from 'antd';
import { ProFormDependency, ProFormDigit, ProFormItem, type ProFormInstance } from '@ant-design/pro-components';
import { theme } from 'antd';
import { useTranslation } from 'react-i18next';
import { UniDropdown } from '../../../components/uni-dropdown';
import {
  formatPaymentMethodMixLabel,
  isMixedPaymentMethodCode,
  isPartnerEmployeeAdvancePaymentMethod,
  validatePaymentMethodMix,
} from '../../master-data/utils/paymentMethodMix';
import {
  PartnerPaymentAdvancePayeeField,
  type PartnerPaymentAdvancePayeeFieldHandle,
} from './PartnerPaymentAdvancePayeeField';
import { partnerDefaultPaymentMethodLabel } from '../../master-data/utils/partner-static-labels';
import {
  PartnerPaymentMethodFieldLabel,
  PartnerPaymentMethodLabelAddons,
} from './PartnerPaymentMethodLabelAddons';

type Props = {
  formRef: React.MutableRefObject<ProFormInstance | undefined>;
  options: Array<{ label: string; value: string }>;
  methodLabel: string;
  methodPlaceholder?: string;
  wireField?: string;
  acceptanceField?: string;
  methodField?: string;
  advancePayeeIdField?: string;
  advancePayeeNameField?: string;
  /** 单据支持员工垫付+领款人时开启；主数据/销售侧仅组合比例 */
  enableEmployeeAdvance?: boolean;
};

export const PaymentMethodWithMixFormItems: React.FC<Props> = ({
  formRef,
  options,
  methodLabel,
  methodPlaceholder,
  wireField = 'payment_wire_percent',
  acceptanceField = 'payment_acceptance_percent',
  methodField = 'payment_method_code',
  advancePayeeIdField = 'advance_payee_id',
  advancePayeeNameField = 'advance_payee_name',
  enableEmployeeAdvance = true,
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const [mixOpen, setMixOpen] = useState(false);
  const [draftWire, setDraftWire] = useState<number | null>(null);
  const [draftAcceptance, setDraftAcceptance] = useState<number | null>(null);
  const advancePayeeRef = useRef<PartnerPaymentAdvancePayeeFieldHandle>(null);

  const openMixModal = useCallback(() => {
    const form = formRef.current;
    const wire = form?.getFieldValue(wireField);
    const acceptance = form?.getFieldValue(acceptanceField);
    setDraftWire(wire != null ? Number(wire) : null);
    setDraftAcceptance(acceptance != null ? Number(acceptance) : null);
    setMixOpen(true);
  }, [acceptanceField, formRef, wireField]);

  const confirmMixModal = useCallback(() => {
    const err = validatePaymentMethodMix('bank_transfer_and_acceptance', draftWire, draftAcceptance);
    if (err) {
      message.error(err);
      return;
    }
    formRef.current?.setFieldsValue({
      [wireField]: draftWire ?? undefined,
      [acceptanceField]: draftAcceptance ?? undefined,
    });
    setMixOpen(false);
  }, [acceptanceField, draftAcceptance, draftWire, formRef, message, wireField]);

  const buildMethodFieldExtra = useCallback(
    (dep: Record<string, unknown> | undefined) => {
      const code = dep?.[methodField] as string | undefined;
      const hintStyle: CSSProperties = {
        fontSize: 12,
        lineHeight: '20px',
        cursor: 'pointer',
      };

      if (isMixedPaymentMethodCode(code)) {
        const mixLabel = formatPaymentMethodMixLabel(
          dep?.[wireField] as number | string | null | undefined,
          dep?.[acceptanceField] as number | string | null | undefined,
        );
        if (mixLabel) return undefined;
        return (
          <span
            role="button"
            tabIndex={0}
            onClick={openMixModal}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') openMixModal();
            }}
            style={{
              ...hintStyle,
              color: token.colorTextSecondary,
            }}
          >
            {t('field.partner.paymentMix.configureHint')}
          </span>
        );
      }

      if (enableEmployeeAdvance && isPartnerEmployeeAdvancePaymentMethod(code)) {
        const storedName = String(dep?.[advancePayeeNameField] ?? '').trim();
        const payeeId = dep?.[advancePayeeIdField];
        if (storedName || (payeeId != null && payeeId !== '')) {
          return undefined;
        }
        return (
          <span
            role="button"
            tabIndex={0}
            onClick={() => advancePayeeRef.current?.open()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') advancePayeeRef.current?.open();
            }}
            style={{ ...hintStyle, color: token.colorTextSecondary }}
          >
            {t('field.partner.paymentAdvance.configureHint')}
          </span>
        );
      }

      return undefined;
    },
    [
      acceptanceField,
      advancePayeeIdField,
      advancePayeeNameField,
      enableEmployeeAdvance,
      methodField,
      openMixModal,
      t,
      token.colorTextSecondary,
      wireField,
    ],
  );

  const onMethodChange = useCallback(
    (next: string | undefined) => {
      const form = formRef.current;
      if (!form) return;
      if (!isMixedPaymentMethodCode(next)) {
        form.setFieldsValue({
          [wireField]: undefined,
          [acceptanceField]: undefined,
        });
      }
      if (enableEmployeeAdvance) {
        if (!isPartnerEmployeeAdvancePaymentMethod(next)) {
          form.setFieldsValue({
            [advancePayeeIdField]: undefined,
            [advancePayeeNameField]: undefined,
          });
        } else {
          advancePayeeRef.current?.openIfNeeded();
        }
      }
      if (!isMixedPaymentMethodCode(next)) {
        return;
      }
      const wire = form.getFieldValue(wireField);
      const acceptance = form.getFieldValue(acceptanceField);
      const err = validatePaymentMethodMix(next, wire, acceptance);
      if (err) {
        openMixModal();
      }
    },
    [acceptanceField, advancePayeeIdField, advancePayeeNameField, enableEmployeeAdvance, formRef, openMixModal, wireField],
  );

  return (
    <>
      <ProFormDigit name={wireField} hidden />
      <ProFormDigit name={acceptanceField} hidden />
      <ProFormDependency
        name={[
          methodField,
          wireField,
          acceptanceField,
          ...(enableEmployeeAdvance ? [advancePayeeIdField, advancePayeeNameField] : []),
        ]}
      >
        {(dep) => (
          <ProFormItem
            name={methodField}
            label={
              <PartnerPaymentMethodFieldLabel title={methodLabel}>
                <PartnerPaymentMethodLabelAddons
                  t={t}
                  methodCode={dep?.[methodField] as string | undefined}
                  mixWire={dep?.[wireField] as number | string | null | undefined}
                  mixAcceptance={dep?.[acceptanceField] as number | string | null | undefined}
                  advancePayeeName={
                    enableEmployeeAdvance
                      ? (dep?.[advancePayeeNameField] as string | undefined)
                      : undefined
                  }
                  onAdvancePayeeClick={
                    enableEmployeeAdvance ? () => advancePayeeRef.current?.open() : undefined
                  }
                  onMixClick={openMixModal}
                />
              </PartnerPaymentMethodFieldLabel>
            }
            extra={buildMethodFieldExtra(dep)}
          >
            <UniDropdown
              allowClear
              showSearch
              optionFilterProp="label"
              options={options}
              placeholder={methodPlaceholder}
              style={{ width: '100%' }}
              onChange={(v) => onMethodChange(v as string | undefined)}
            />
          </ProFormItem>
        )}
      </ProFormDependency>
      {enableEmployeeAdvance ? (
        <PartnerPaymentAdvancePayeeField
          ref={advancePayeeRef}
          formRef={formRef}
          methodField={methodField}
          payeeIdField={advancePayeeIdField}
          payeeNameField={advancePayeeNameField}
        />
      ) : null}
      <Modal
        title={t('field.partner.paymentMix.modalTitle')}
        open={mixOpen}
        onOk={confirmMixModal}
        onCancel={() => setMixOpen(false)}
        destroyOnHidden
        width={400}
      >
        <Row gutter={16}>
          <Col span={12}>
            <div style={{ marginBottom: 4 }}>{t('field.partner.paymentMix.wirePercent')}</div>
            <InputNumber
              min={0}
              max={100}
              precision={2}
              addonAfter="%"
              style={{ width: '100%' }}
              value={draftWire ?? undefined}
              onChange={(v) => setDraftWire(v == null ? null : Number(v))}
            />
          </Col>
          <Col span={12}>
            <div style={{ marginBottom: 4 }}>{t('field.partner.paymentMix.acceptancePercent')}</div>
            <InputNumber
              min={0}
              max={100}
              precision={2}
              addonAfter="%"
              style={{ width: '100%' }}
              value={draftAcceptance ?? undefined}
              onChange={(v) => setDraftAcceptance(v == null ? null : Number(v))}
            />
          </Col>
        </Row>
      </Modal>
    </>
  );
};

export function renderDocumentPaymentMethodDisplay(
  t: (key: string) => string,
  record: {
    payment_method_code?: string | null;
    payment_wire_percent?: number | string | null;
    payment_acceptance_percent?: number | string | null;
    payment_terms?: string | null;
  },
): string {
  const code = record.payment_method_code;
  const base = partnerDefaultPaymentMethodLabel(t, code) || code || '';
  if (isMixedPaymentMethodCode(code)) {
    const w = record.payment_wire_percent;
    const a = record.payment_acceptance_percent;
    if (w != null && a != null) {
      return `${base}（电汇${w}% 承兑${a}%）`;
    }
  }
  if (base) return base;
  return record.payment_terms?.trim() || '—';
}