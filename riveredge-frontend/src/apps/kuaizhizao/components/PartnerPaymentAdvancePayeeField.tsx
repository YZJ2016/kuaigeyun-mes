import React, {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useMemo,
  useState,
} from 'react';
import { App, Modal } from 'antd';
import { ProFormDigit, ProFormText, type ProFormInstance } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { UniDropdown } from '../../../components/uni-dropdown';
import { isPartnerEmployeeAdvancePaymentMethod } from '../../master-data/utils/paymentMethodMix';
import { loadUserFormReferenceOptions } from '../../../utils/documentFormReferenceLoad';

export type PartnerPaymentAdvancePayeeFieldHandle = {
  openIfNeeded: () => void;
  open: () => void;
};

type PartnerPaymentAdvancePayeeFieldProps = {
  formRef: React.MutableRefObject<ProFormInstance | undefined>;
  methodField?: string;
  payeeIdField?: string;
  payeeNameField?: string;
};

/** 员工垫付：付款方式下方可点文案 + 弹窗选领款人（与电汇+承兑组合付款交互一致） */
export const PartnerPaymentAdvancePayeeField = forwardRef<
  PartnerPaymentAdvancePayeeFieldHandle,
  PartnerPaymentAdvancePayeeFieldProps
>(function PartnerPaymentAdvancePayeeField(
  {
    formRef,
    methodField = 'payment_method_code',
    payeeIdField = 'advance_payee_id',
    payeeNameField = 'advance_payee_name',
  },
  ref,
) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
  const [draftPayeeId, setDraftPayeeId] = useState<number | undefined>(undefined);

  const { data: userOptions = [] } = useQuery({
    queryKey: ['partner-payment-advance-payee-users'],
    queryFn: () => loadUserFormReferenceOptions(),
    staleTime: 60_000,
  });
  const options = useMemo(
    () => userOptions.map((o) => ({ label: o.label, value: o.value })),
    [userOptions],
  );

  const openModal = useCallback(() => {
    const form = formRef.current;
    const current = form?.getFieldValue(payeeIdField);
    const id = current != null && current !== '' ? Number(current) : undefined;
    setDraftPayeeId(Number.isFinite(id) && id! > 0 ? id : undefined);
    setOpen(true);
  }, [formRef, payeeIdField]);

  useImperativeHandle(
    ref,
    () => ({
      open: openModal,
      openIfNeeded: () => {
        const form = formRef.current;
        const code = form?.getFieldValue(methodField);
        if (!isPartnerEmployeeAdvancePaymentMethod(code)) return;
        const payeeId = form?.getFieldValue(payeeIdField);
        if (payeeId == null || payeeId === '') {
          openModal();
        }
      },
    }),
    [formRef, methodField, openModal, payeeIdField],
  );

  const confirmModal = useCallback(() => {
    const id = draftPayeeId != null ? Number(draftPayeeId) : NaN;
    if (!Number.isFinite(id) || id <= 0) {
      message.error(t('app.kuaicaiwu.payment.advancePayeeRequired'));
      return;
    }
    const name = resolvePartnerAdvancePayeeName(id, options);
    if (!name) {
      message.error(t('app.kuaicaiwu.payment.advancePayeeRequired'));
      return;
    }
    formRef.current?.setFieldsValue({
      [payeeIdField]: id,
      [payeeNameField]: name,
    });
    setOpen(false);
  }, [draftPayeeId, formRef, message, options, payeeIdField, payeeNameField, t]);

  return (
    <>
      <ProFormDigit name={payeeIdField} hidden />
      <ProFormText name={payeeNameField} hidden />
      <Modal
        title={t('field.partner.paymentAdvance.payeeModalTitle')}
        open={open}
        onOk={confirmModal}
        onCancel={() => setOpen(false)}
        destroyOnHidden
        width={400}
      >
        <div style={{ marginBottom: 8 }}>{t('app.kuaicaiwu.payment.advancePayee')}</div>
        <UniDropdown
          allowClear
          showSearch
          optionFilterProp="label"
          options={options}
          placeholder={t('common.pleaseSelect')}
          style={{ width: '100%' }}
          value={draftPayeeId}
          onChange={(v) => {
            const id = v != null && v !== '' ? Number(v) : undefined;
            setDraftPayeeId(Number.isFinite(id) && id! > 0 ? id : undefined);
          }}
        />
      </Modal>
    </>
  );
});

export function resolvePartnerAdvancePayeeName(
  payeeId: unknown,
  userOptions: Array<{ label: string; value: number | string }>,
): string | undefined {
  if (payeeId == null || payeeId === '') {
    return undefined;
  }
  const label = userOptions.find((o) => String(o.value) === String(payeeId))?.label;
  return label ? String(label).trim() : undefined;
}