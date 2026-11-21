/**
 * 工序委外：从工单工序加载源后的新建表单体（双栏栅格，与 FormModal grid 配合）
 */

import React from 'react';
import type { ProFormInstance } from '@ant-design/pro-components';
import {
  ProFormDatePicker,
  ProFormDigit,
  ProFormItem,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { Alert, Card, Col, Row, Typography } from 'antd';
import type { TFunction } from 'i18next';
import type { NavigateFunction } from 'react-router-dom';
import { FormModalGridBlock } from '../../../components/layout-templates';
import { UniDropdown } from '../../../components/uni-dropdown';
import { buildPayableLedgerRecognitionOptions } from '../../../utils/documentLedgerRecognition';
import { buildFutureDateShortcutFieldProps } from '../../../utils/futureDatePickerShortcuts';
import type { FormItemProps } from 'antd';

export type OutsourceCreateLockedOperation = {
  operation_name?: string;
  operation_code?: string;
  work_order_operation_id?: number;
};

export type OutsourceCreateWorkOrder = {
  code?: string;
  name?: string;
};

type SupplierOption = { id: number; code?: string; name?: string };

/** FormModal grid 一行三列 */
const COL_THIRD = { span: 8 } as const;

const fullWidthControlStyle = { width: '100%' } as const;

export interface OutsourceOrderCreateFromSourceFormProps {
  t: TFunction;
  navigate: NavigateFunction;
  workOrder: OutsourceCreateWorkOrder;
  lockedOperation: OutsourceCreateLockedOperation;
  maxOutsourceQty: number;
  supplierList: SupplierOption[];
  formRef: React.MutableRefObject<ProFormInstance | undefined | null>;
  formDateFormItemProps: FormItemProps;
}

export function OutsourceOrderCreateFromSourceForm({
  t,
  navigate,
  workOrder,
  lockedOperation,
  maxOutsourceQty,
  supplierList,
  formRef,
  formDateFormItemProps,
}: OutsourceOrderCreateFromSourceFormProps) {
  const operationLabel = `${lockedOperation.operation_name || '—'} (${lockedOperation.operation_code || '—'})`;

  return (
    <>
      <FormModalGridBlock>
        <Alert type="info" showIcon title={t('app.kuaizhizao.outsourceOrder.formSourceLocked')} />
      </FormModalGridBlock>

      <FormModalGridBlock>
        <Card size="small" styles={{ body: { padding: '8px 12px' } }}>
          <Row gutter={[16, 4]}>
            <Col span={8}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('app.kuaizhizao.outsourceOrder.colWorkOrderCode')}
              </Typography.Text>
              <div>{workOrder.code || '—'}</div>
            </Col>
            <Col span={8}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('app.kuaizhizao.workReporting.colWorkOrderName')}
              </Typography.Text>
              <div>{workOrder.name || '—'}</div>
            </Col>
            <Col span={8}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('app.kuaizhizao.outsourceOrder.colOperationName')}
              </Typography.Text>
              <div>{operationLabel}</div>
            </Col>
          </Row>
        </Card>
      </FormModalGridBlock>

      <ProFormText name="work_order_operation_id" hidden />

      {/* UniDropdown 非 ProForm 内置字段，colProps 不进 Col；须 FormModalGridBlock（与交付项目 CustomerSelect 一致） */}
      <FormModalGridBlock span={COL_THIRD.span}>
        <ProFormItem
          name="supplier_id"
          label={t('app.kuaizhizao.outsourceOrder.fieldSupplier')}
          rules={[{ required: true, message: t('app.kuaizhizao.outsourceOrder.ruleSelectSupplier') }]}
        >
          <UniDropdown
            placeholder={t('app.kuaizhizao.outsourceOrder.placeholderSupplier')}
            showSearch
            allowClear
            size="medium"
            style={fullWidthControlStyle}
            options={supplierList.map((s) => ({
              label: `${s.code} - ${s.name}`,
              value: s.id,
            }))}
            quickCreate={{
              label: t('app.kuaizhizao.outsourceOrder.supplierManage'),
              onClick: () => navigate('/apps/master-data/supply-chain/suppliers'),
            }}
          />
        </ProFormItem>
      </FormModalGridBlock>

      <ProFormDigit
        name="outsource_quantity"
        label={t('app.kuaizhizao.outsourceOrder.fieldOutsourceQty')}
        placeholder={t('app.kuaizhizao.outsourceOrder.placeholderOutsourceQty')}
        colProps={COL_THIRD}
        rules={[
          { required: true, message: t('app.kuaizhizao.outsourceOrder.ruleEnterOutsourceQty') },
          {
            validator: async (_, value) => {
              if (value == null || value === '') return;
              const qty = Number(value);
              if (!Number.isFinite(qty) || qty <= 0) {
                throw new Error(t('app.kuaizhizao.outsourceOrder.ruleEnterOutsourceQty'));
              }
              if (qty > maxOutsourceQty) {
                throw new Error(t('app.kuaizhizao.outsourceOrder.ruleEnterOutsourceQty'));
              }
            },
          },
        ]}
        min={0}
        max={maxOutsourceQty > 0 ? maxOutsourceQty : undefined}
        tooltip={`${t('app.kuaizhizao.salesOrder.colPushableQty')}: ${maxOutsourceQty}`}
        fieldProps={{ precision: 2, style: fullWidthControlStyle }}
      />

      <ProFormDigit
        name="unit_price"
        label={t('app.kuaizhizao.outsourceOrder.fieldUnitPrice')}
        placeholder={t('app.kuaizhizao.outsourceOrder.placeholderUnitPrice')}
        colProps={COL_THIRD}
        min={0}
        fieldProps={{ precision: 2, style: fullWidthControlStyle }}
      />

      <ProFormSelect
        name="payable_recognition"
        label={t('field.document.ledgerRecognition')}
        colProps={COL_THIRD}
        fieldProps={{ style: fullWidthControlStyle }}
        options={buildPayableLedgerRecognitionOptions(t).map((opt) =>
          opt.value === 'on_receipt'
            ? { ...opt, label: t('app.kuaizhizao.outsourceOrder.payableOnReceiptOrReport') }
            : opt.value === 'on_purchase_invoice'
              ? { ...opt, label: t('app.kuaizhizao.outsourceOrder.payableOnInvoice') }
              : opt.value === 'on_partner_statement'
                ? { ...opt, label: t('app.kuaizhizao.outsourceOrder.payableOnMonthlyStatement') }
                : opt,
        )}
        rules={[{ required: true, message: t('field.document.ledgerRecognitionRequired') }]}
      />

      <ProFormDatePicker
        name="planned_start_date"
        label={t('app.kuaizhizao.outsourceOrder.fieldPlannedStart')}
        placeholder={t('app.kuaizhizao.outsourceOrder.placeholderPlannedStart')}
        colProps={COL_THIRD}
        formItemProps={formDateFormItemProps}
        fieldProps={{ showTime: true, style: fullWidthControlStyle }}
      />

      <ProFormDatePicker
        name="planned_end_date"
        label={t('app.kuaizhizao.outsourceOrder.fieldPlannedEnd')}
        placeholder={t('app.kuaizhizao.outsourceOrder.placeholderPlannedEnd')}
        colProps={COL_THIRD}
        formItemProps={formDateFormItemProps}
        fieldProps={buildFutureDateShortcutFieldProps({
          getForm: () => formRef.current,
          fieldName: 'planned_end_date',
          baseFieldName: 'planned_start_date',
          t,
          fieldProps: { showTime: true, style: fullWidthControlStyle },
        })}
      />

      <ProFormTextArea
        name="remarks"
        label={t('common.remark')}
        placeholder={t('app.kuaizhizao.outsourceOrder.placeholderRemarks')}
        colProps={{ span: 24 }}
        fieldProps={{ rows: 2 }}
      />
    </>
  );
}