/**
 * 收/付款方式「票据」：关联应收/应付票据台账 + 参考号（票号）。
 */
import React, { useEffect, useMemo, useState } from 'react';
import { ProForm, ProFormDependency, ProFormSelect, ProFormText } from '@ant-design/pro-components';
import { App, Col, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { getApiErrorMessage } from '../../../utils/errorHandler';
import {
  financeNoteService,
  type FinanceNote,
  type FinanceNoteDirection,
} from '../services/finance/note';

type Props = {
  direction: FinanceNoteDirection;
  partnerFieldName: 'customer_id' | 'supplier_id';
  noteName?: string;
  colProps?: { span: number };
  /** 父级 Row 内嵌时：不传 colProps，字段外包 Col */
  rowNestedFieldSpan?: number;
};

export const AcceptanceBillLinkFields: React.FC<Props> = ({
  direction,
  partnerFieldName,
  noteName = 'bank_account',
  colProps = { span: 12 },
  rowNestedFieldSpan,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const form = ProForm.useFormInstance();
  const partnerId = ProForm.useWatch(partnerFieldName, form);
  const noteId = ProForm.useWatch('note_id', form);
  const totalAmount = ProForm.useWatch('total_amount', form);
  const [notes, setNotes] = useState<FinanceNote[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const pid = partnerId != null && partnerId !== '' ? Number(partnerId) : null;
    if (!pid) {
      setNotes([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const res = await financeNoteService.list(direction, {
          partner_id: pid,
          unlinked_only: true,
          limit: 200,
        });
        if (!cancelled) setNotes(res.data || []);
      } catch (error) {
        if (!cancelled) {
          setNotes([]);
          messageApi.error(getApiErrorMessage(error, t('app.kuaicaiwu.notes.linkFailed')));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [direction, partnerId, messageApi, t]);

  const noteOptions = useMemo(
    () =>
      notes.map((n) => ({
        label: `${n.bill_no} ¥${Number(n.amount).toFixed(2)} (${n.note_code})`,
        value: n.id,
      })),
    [notes],
  );

  useEffect(() => {
    if (!noteId) return;
    const selected = notes.find((n) => n.id === Number(noteId));
    if (selected?.bill_no) {
      form.setFieldValue(noteName, selected.bill_no);
    }
  }, [noteId, notes, form, noteName]);

  const amountHint = useMemo(() => {
    if (!noteId || totalAmount == null) return null;
    const selected = notes.find((n) => n.id === Number(noteId));
    if (!selected) return null;
    const diff = Math.abs(Number(selected.amount) - Number(totalAmount));
    if (diff > 0.009) {
      return t('app.kuaicaiwu.notes.linkAmountMismatch', {
        noteAmount: Number(selected.amount).toFixed(2),
        voucherAmount: Number(totalAmount).toFixed(2),
      });
    }
    return null;
  }, [noteId, notes, totalAmount, t]);

  const hasPartner = partnerId != null && partnerId !== '';
  const nested = rowNestedFieldSpan != null;
  const fieldCols = nested ? undefined : colProps;
  const wrapNested = (node: React.ReactNode) =>
    nested ? <Col span={rowNestedFieldSpan}>{node}</Col> : node;

  return (
    <>
      {wrapNested(
      <ProFormSelect
        name="note_id"
        label={t('app.kuaicaiwu.notes.linkField')}
        colProps={fieldCols}
        options={noteOptions}
        showSearch
        allowClear
        placeholder={
          hasPartner
            ? t('app.kuaicaiwu.notes.linkPlaceholder')
            : t('app.kuaicaiwu.notes.linkNeedPartner')
        }
        fieldProps={{
          loading,
          optionFilterProp: 'label',
          disabled: !hasPartner,
        }}
        extra={t('app.kuaicaiwu.notes.linkHint')}
      />,
      )}
      <ProFormDependency name={['note_id']}>
        {({ note_id: linkedNoteId }) =>
          wrapNested(
          <ProFormText
            name={noteName}
            label={t('app.kuaicaiwu.common.referenceNumber')}
            colProps={fieldCols}
            placeholder={t('app.kuaicaiwu.common.referenceNumberPlaceholder')}
            rules={[
              {
                required: true,
                message: t('app.kuaicaiwu.common.referenceNumberRequired'),
              },
            ]}
            extra={
              amountHint && linkedNoteId ? (
                <Typography.Text type="warning">{amountHint}</Typography.Text>
              ) : undefined
            }
          />
          )
        }
      </ProFormDependency>
    </>
  );
};

export async function linkAcceptanceNoteAfterVoucherCreate(
  direction: FinanceNoteDirection,
  noteId: unknown,
  voucherId: number,
  voucherKind: 'receipt' | 'payment',
): Promise<void> {
  const id = noteId != null && noteId !== '' ? Number(noteId) : 0;
  if (!id || !voucherId) return;
  const payload =
    voucherKind === 'receipt' ? { receipt_id: voucherId } : { payment_id: voucherId };
  await financeNoteService.update(direction, id, payload);
}
