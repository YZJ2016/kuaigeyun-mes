import React, { useEffect, useMemo, useRef, useState } from 'react';
import { App, Button, Col, DatePicker, Form, Input, InputNumber, Row, Select, Table } from 'antd';
import type { ProFormInstance } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { type Dayjs } from 'dayjs';
import { FormModalTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import { UniTableDetail } from '../../../../../components/uni-table-detail';
import { SupplierSelectDropdown } from '../../../../master-data/components/SupplierSelectDropdown';
import type { Supplier } from '../../../../master-data/types/supply-chain';
import { formatApiErrorDetail } from '../../../../../services/api';
import { coerceFormDate, toApiDateString } from '../../../../../utils/formDate';
import {
  outsourceSettlementApi,
  type OutsourceSettleableReceipt,
  type OutsourceSettlement,
  type OutsourceMaterialDeductionPreview,
  type OutsourceSettlementPayload,
} from '../../../services/outsource-settlement';

export type OutsourceSettlementFormModalProps = {
  open: boolean;
  editing: OutsourceSettlement | null;
  onClose: () => void;
  onSuccess: () => void;
};

type LineForm = {
  outsource_material_receipt_id?: number;
  receipt_code?: string;
  product_name?: string;
  settleable_quantity?: number;
  settlement_quantity?: number;
  unit_price?: number;
  notes?: string;
};

function supplierDisplayName(s: Supplier | null | undefined): string {
  if (!s) return '';
  const row = s as Record<string, unknown>;
  return String(row.name ?? row.supplier_name ?? '').trim();
}

const OutsourceSettlementFormModal: React.FC<OutsourceSettlementFormModalProps> = ({
  open,
  editing,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>();
  const [submitting, setSubmitting] = useState(false);
  const [supplierId, setSupplierId] = useState<number | undefined>();
  const [receiptOptions, setReceiptOptions] = useState<OutsourceSettleableReceipt[]>([]);
  const [receiptLoading, setReceiptLoading] = useState(false);
  const [deductionLines, setDeductionLines] = useState<OutsourceMaterialDeductionPreview[]>([]);
  const [deductionLoading, setDeductionLoading] = useState(false);
  const isCreditAuto = Boolean(editing?.settlement_kind === 'credit' && editing?.auto_generated);

  useEffect(() => {
    if (!open) return;
    setSupplierId(editing?.supplier_id);
  }, [editing?.supplier_id, open]);

  useEffect(() => {
    if (!open || !supplierId) {
      setReceiptOptions([]);
      return;
    }
    let cancelled = false;
    setReceiptLoading(true);
    void outsourceSettlementApi
      .listSettleableReceipts(supplierId, editing?.id)
      .then((rows) => {
        if (!cancelled) setReceiptOptions(rows);
      })
      .catch(() => {
        if (!cancelled) setReceiptOptions([]);
      })
      .finally(() => {
        if (!cancelled) setReceiptLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [editing?.id, open, supplierId]);

  const initialValues = useMemo(() => {
    if (editing) {
      const biz = editing.business_date ? coerceFormDate(editing.business_date) : null;
      return {
        supplier_id: editing.supplier_id,
        supplier_name: editing.supplier_name,
        business_date: biz?.isValid() ? biz : null,
        notes: editing.notes ?? undefined,
        items:
          (editing.items ?? [])
            .filter((item) => (item.line_type ?? 'processing') === 'processing')
            .map((item) => ({
              outsource_material_receipt_id: item.outsource_material_receipt_id,
              receipt_code: item.receipt_code,
              product_name: item.product_name,
              settlement_quantity: Number(item.settlement_quantity),
              unit_price: Number(item.unit_price),
              notes: item.notes ?? undefined,
            })) || [{}],
      };
    }
    return { items: [{}] };
  }, [editing]);

  useEffect(() => {
    if (!open) {
      setDeductionLines([]);
      return;
    }
    if (editing?.items?.length) {
      const rows = editing.items
        .filter((item) => item.line_type === 'material_deduction')
        .map((item) => ({
          outsource_work_order_id: Number(item.outsource_work_order_id),
          outsource_work_order_code: String(item.outsource_work_order_code ?? ''),
          material_id: 0,
          material_code: String(item.product_code ?? ''),
          material_name: String(item.product_name ?? ''),
          standard_qty: Number(item.deduction_basis_qty ?? 0),
          actual_qty: 0,
          overrun_qty: Number(item.settlement_quantity),
          unit_price: Number(item.unit_price),
          deduction_amount: Number(item.deduction_basis_amount ?? item.amount ?? 0),
        }));
      setDeductionLines(rows);
    }
  }, [editing, open]);

  const handleFinish = async (values: Record<string, unknown>) => {
    const items = ((values.items as LineForm[]) || []).filter(
      (row) => row.outsource_material_receipt_id != null && Number(row.settlement_quantity) > 0,
    );
    if (!isCreditAuto && !items.length) {
      messageApi.error(t('app.kuaizhizao.outsourceManagement.settlement.linesRequired'));
      return;
    }
    const businessDateRaw = values.business_date as Dayjs | null | undefined;
    const processingItems = items.map((row) => ({
      line_type: 'processing',
      outsource_material_receipt_id: Number(row.outsource_material_receipt_id),
      settlement_quantity: Number(row.settlement_quantity),
      unit_price: Number(row.unit_price) || 0,
      notes: row.notes,
    }));
    const deductionItems = deductionLines.map((row) => ({
      line_type: 'material_deduction',
      outsource_work_order_id: row.outsource_work_order_id,
      settlement_quantity: Number(row.overrun_qty),
      unit_price: Number(row.unit_price),
      deduction_basis_qty: Number(row.standard_qty),
      deduction_basis_amount: Number(row.deduction_amount),
    }));
    const payload: OutsourceSettlementPayload = {
      supplier_id: Number(values.supplier_id),
      business_date: businessDateRaw?.isValid() ? toApiDateString(businessDateRaw) : undefined,
      notes: (values.notes as string) || undefined,
      items: isCreditAuto ? [] : [...processingItems, ...deductionItems],
    };
    if (!isCreditAuto && !payload.items.length) {
      messageApi.error(t('app.kuaizhizao.outsourceManagement.settlement.linesRequired'));
      return;
    }
    setSubmitting(true);
    try {
      if (editing) {
        const updateBody = isCreditAuto
          ? {
              business_date: payload.business_date,
              notes: payload.notes,
            }
          : payload;
        await outsourceSettlementApi.update(editing.id, updateBody);
        messageApi.success(t('common.saveSuccess'));
      } else {
        await outsourceSettlementApi.create(payload);
        messageApi.success(t('common.createSuccess'));
      }
      onSuccess();
      onClose();
    } catch (error) {
      messageApi.error(formatApiErrorDetail(error) || t('common.saveFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <FormModalTemplate
      key={editing?.id ?? 'create'}
      formRef={formRef}
      open={open}
      onClose={onClose}
      title={
        editing
          ? t('app.kuaizhizao.outsourceManagement.settlement.editTitle')
          : t('app.kuaizhizao.outsourceManagement.settlement.createTitle')
      }
      width={MODAL_CONFIG.LARGE_WIDTH}
      grid={false}
      isEdit={Boolean(editing)}
      loading={submitting}
      initialValues={initialValues}
      onFinish={handleFinish}
    >
      <Row gutter={16}>
        <Col span={8}>
          <Form.Item name="supplier_name" hidden>
            <Input />
          </Form.Item>
          <Form.Item
            name="supplier_id"
            label={t('app.kuaizhizao.outsourceManagement.settlement.field.supplierName')}
            rules={[{ required: true, message: t('common.required') }]}
          >
            <SupplierSelectDropdown
              hostResource="kuaizhizao:outsource-settlement"
              disabled={Boolean(editing)}
              style={{ width: '100%' }}
              onSupplierPick={(s) => {
                setSupplierId(s?.id != null ? Number(s.id) : undefined);
                formRef.current?.setFieldsValue({
                  supplier_name: supplierDisplayName(s),
                  items: [{}],
                });
              }}
            />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item
            name="business_date"
            label={t('app.kuaizhizao.outsourceManagement.settlement.field.businessDate')}
          >
            <DatePicker
              style={{ width: '100%' }}
              onChange={(v) =>
                formRef.current?.setFieldValue('business_date', v ? v.startOf('day') : null)
              }
            />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="notes" label={t('common.remark')}>
            <Input.TextArea rows={1} />
          </Form.Item>
        </Col>
      </Row>

      {isCreditAuto ? (
        <>
          <div style={{ marginBottom: 16, color: 'rgba(0,0,0,0.65)' }}>
            {t('app.kuaizhizao.outsourceManagement.settlement.creditAutoHint')}
          </div>
          <Table
            size="small"
            pagination={false}
            rowKey={(r) => String(r.id ?? r.outsource_material_receipt_id)}
            dataSource={editing?.items ?? []}
            columns={[
              { title: t('app.kuaizhizao.outsourceManagement.settlement.field.receiptCode'), dataIndex: 'receipt_code' },
              { title: t('app.kuaizhizao.outsourceManagement.settlement.field.settlementQuantity'), dataIndex: 'settlement_quantity', align: 'right' },
              { title: t('app.kuaizhizao.outsourceManagement.settlement.field.unitPrice'), dataIndex: 'unit_price', align: 'right' },
              { title: t('app.kuaizhizao.outsourceManagement.settlement.field.lineAmount'), dataIndex: 'amount', align: 'right' },
            ]}
          />
        </>
      ) : null}

      {!isCreditAuto ? (
      <UniTableDetail
        name="items"
        title={t('app.kuaizhizao.outsourceManagement.settlement.processingItemsTitle')}
        minRows={1}
        columns={[
          {
            title: t('app.kuaizhizao.outsourceManagement.settlement.field.receiptCode'),
            width: 160,
            render: (_v, _r, index) => (
              <>
                <Form.Item name={[index, 'receipt_code']} hidden>
                  <Input />
                </Form.Item>
                <Form.Item name={[index, 'product_name']} hidden>
                  <Input />
                </Form.Item>
                <Form.Item
                  name={[index, 'outsource_material_receipt_id']}
                  rules={[{ required: true, message: t('common.required') }]}
                  style={{ margin: 0 }}
                >
                  <Select
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    loading={receiptLoading}
                    disabled={!supplierId}
                    placeholder={t('app.kuaizhizao.outsourceManagement.settlement.selectReceipt')}
                    options={receiptOptions.map((o) => ({
                      value: o.id,
                      label: `${o.code} ${o.product_name} (${t('app.kuaizhizao.outsourceManagement.settlement.settleableQty', { qty: o.settleable_quantity })})`,
                    }))}
                    onChange={(value: number | undefined) => {
                      const picked = receiptOptions.find((o) => o.id === value);
                      if (!picked) return;
                      formRef.current?.setFieldValue(['items', index, 'receipt_code'], picked.code);
                      formRef.current?.setFieldValue(['items', index, 'product_name'], picked.product_name);
                      formRef.current?.setFieldValue(
                        ['items', index, 'settlement_quantity'],
                        Number(picked.settleable_quantity),
                      );
                      formRef.current?.setFieldValue(['items', index, 'unit_price'], Number(picked.unit_price));
                    }}
                  />
                </Form.Item>
              </>
            ),
          },
          {
            title: t('app.kuaizhizao.outsourceManagement.settlement.field.settlementQuantity'),
            width: 120,
            render: (_v, _r, index) => (
              <Form.Item name={[index, 'settlement_quantity']} style={{ margin: 0 }}>
                <InputNumber min={0} precision={4} style={{ width: '100%' }} />
              </Form.Item>
            ),
          },
          {
            title: t('app.kuaizhizao.outsourceManagement.settlement.field.unitPrice'),
            width: 120,
            render: (_v, _r, index) => (
              <Form.Item name={[index, 'unit_price']} style={{ margin: 0 }}>
                <InputNumber min={0} precision={4} style={{ width: '100%' }} />
              </Form.Item>
            ),
          },
          {
            title: t('common.remark'),
            render: (_v, _r, index) => (
              <Form.Item name={[index, 'notes']} style={{ margin: 0 }}>
                <Input />
              </Form.Item>
            ),
          },
        ]}
      />
      ) : null}

      {!isCreditAuto ? (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '16px 0 8px' }}>
            <span>{t('app.kuaizhizao.outsourceManagement.settlement.deductionItemsTitle')}</span>
            <Button
              size="small"
              loading={deductionLoading}
              disabled={!supplierId}
              onClick={async () => {
                const woIds = Array.from(
                  new Set(receiptOptions.map((r) => r.outsource_work_order_id)),
                );
                if (!woIds.length) {
                  messageApi.warning(t('app.kuaizhizao.outsourceManagement.settlement.deductionNoWorkOrder'));
                  return;
                }
                setDeductionLoading(true);
                try {
                  const rows = await outsourceSettlementApi.previewDeductions(supplierId!, woIds);
                  setDeductionLines(rows);
                  if (!rows.length) {
                    messageApi.info(t('app.kuaizhizao.outsourceManagement.settlement.deductionEmpty'));
                  }
                } catch (error) {
                  messageApi.error(formatApiErrorDetail(error) || t('common.loadFailed'));
                } finally {
                  setDeductionLoading(false);
                }
              }}
            >
              {t('app.kuaizhizao.outsourceManagement.settlement.calcDeduction')}
            </Button>
          </div>
          <Table
            size="small"
            pagination={false}
            rowKey={(row) => `${row.outsource_work_order_id}-${row.material_id}-${row.material_code}`}
            dataSource={deductionLines}
            locale={{ emptyText: t('app.kuaizhizao.outsourceManagement.settlement.deductionEmpty') }}
            columns={[
              {
                title: t('app.kuaizhizao.outsourceManagement.settlement.field.workOrderCode'),
                dataIndex: 'outsource_work_order_code',
              },
              {
                title: t('app.kuaizhizao.outsourceManagement.settlement.field.materialName'),
                dataIndex: 'material_name',
              },
              {
                title: t('app.kuaizhizao.outsourceManagement.settlement.field.overrunQty'),
                dataIndex: 'overrun_qty',
              },
              {
                title: t('app.kuaizhizao.outsourceManagement.settlement.field.lineAmount'),
                dataIndex: 'deduction_amount',
              },
            ]}
          />
        </>
      ) : null}
    </FormModalTemplate>
  );
};

export default OutsourceSettlementFormModal;
