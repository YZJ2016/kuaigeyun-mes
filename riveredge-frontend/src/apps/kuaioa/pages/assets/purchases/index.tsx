import React, { useMemo, useRef } from 'react';
import { App, Input } from 'antd';
import { useTranslation } from 'react-i18next';
import KuaioaCrudListPage from '../../../components/KuaioaCrudListPage';
import {
  advanceAssetPurchaseLifecycle,
  createAssetPurchase,
  deleteAssetPurchase,
  getAssetPurchase,
  listAssetPurchases,
  updateAssetPurchase,
} from '../../../services/assets';
import { buildOaApprovalStatusEnum } from '../../../utils/oaFormEnums';
import {
  mapOaAttachmentFormFieldToList,
  mapOaAttachmentListToFormField,
  mapOaFormValuesToPayload,
} from '../../../utils/oaFormDateUtils';
import { runKuaioaListExport } from '../../../utils/kuaioaListExport';
import type { KuaioaFieldConfig } from '../../../components/KuaioaCrudListPage';

const STAGE_FLOW = [
  'approved',
  'procuring',
  'paid',
  'inbound',
  'issued',
  'carded',
  'finance_audited',
  'written_off',
  'scrapped',
] as const;

function nextStage(current?: string | null): string | null {
  const cur = (current || 'approved').trim();
  const idx = STAGE_FLOW.indexOf(cur as (typeof STAGE_FLOW)[number]);
  if (idx < 0 || idx >= STAGE_FLOW.length - 1) return null;
  return STAGE_FLOW[idx + 1];
}

const PURCHASE_FIELDS: KuaioaFieldConfig[] = [
  { name: 'purchase_code', labelKey: 'app.kuaioa.assetPurchase.code', width: 140 },
  { name: 'title', labelKey: 'app.kuaioa.assetPurchase.title', required: true, width: 200 },
  { name: 'asset_category', labelKey: 'app.kuaioa.asset.category', width: 120 },
  { name: 'quantity', labelKey: 'common.quantity', width: 80, type: 'number' },
  { name: 'estimated_amount', labelKey: 'app.kuaioa.assetPurchase.amount', width: 120, type: 'number' },
  { name: 'currency', labelKey: 'app.kuaioa.assetPurchase.currency', width: 80, hideInTable: true },
  { name: 'department_name', labelKey: 'app.kuaioa.common.department', hideInTable: true },
  { name: 'applicant_name', labelKey: 'app.kuaioa.common.applicant', width: 100 },
  {
    name: 'lifecycle_stage',
    labelKey: 'app.kuaioa.asset.lifecycleStage',
    width: 120,
    type: 'select',
    hideInForm: true,
    options: [],
  },
  { name: 'status', labelKey: 'common.status', width: 100 },
  { name: 'purpose', labelKey: 'app.kuaioa.common.purpose', hideInTable: true, type: 'textarea' },
  {
    name: 'attachment_file',
    labelKey: 'app.kuaioa.common.attachment',
    type: 'file',
    hideInTable: true,
  },
];

const AssetPurchasesPage: React.FC = () => {
  const { t } = useTranslation();
  const { modal, message } = App.useApp();
  const statusEnum = useMemo(() => buildOaApprovalStatusEnum(t), [t]);
  const paymentAmountRef = useRef('');

  const fields = useMemo(
    (): KuaioaFieldConfig[] =>
      PURCHASE_FIELDS.map((field) =>
        field.name === 'lifecycle_stage'
          ? {
              ...field,
              options: [
                { label: t('app.kuaioa.asset.stage.draft'), value: 'draft' },
                { label: t('app.kuaioa.asset.stage.pending'), value: 'pending' },
                { label: t('app.kuaioa.asset.stage.approved'), value: 'approved' },
                { label: t('app.kuaioa.asset.stage.procuring'), value: 'procuring' },
                { label: t('app.kuaioa.asset.stage.paid'), value: 'paid' },
                { label: t('app.kuaioa.asset.stage.inbound'), value: 'inbound' },
                { label: t('app.kuaioa.asset.stage.issued'), value: 'issued' },
                { label: t('app.kuaioa.asset.stage.carded'), value: 'carded' },
                { label: t('app.kuaioa.asset.stage.finance_audited'), value: 'finance_audited' },
                { label: t('app.kuaioa.asset.stage.written_off'), value: 'written_off' },
                { label: t('app.kuaioa.asset.stage.scrapped'), value: 'scrapped' },
              ],
            }
          : field,
      ),
    [t],
  );

  const exportColumns = useMemo(
    () => [
      { key: 'purchase_code', title: t('app.kuaioa.assetPurchase.code') },
      { key: 'title', title: t('app.kuaioa.assetPurchase.title') },
      { key: 'asset_category', title: t('app.kuaioa.asset.category') },
      { key: 'quantity', title: t('common.quantity') },
      { key: 'estimated_amount', title: t('app.kuaioa.assetPurchase.amount') },
      { key: 'lifecycle_stage', title: t('app.kuaioa.asset.lifecycleStage') },
      { key: 'status', title: t('common.status') },
      { key: 'applicant_name', title: t('app.kuaioa.common.applicant') },
    ],
    [t],
  );

  const promptAdvance = async (_record: Record<string, unknown>, stage: string) => {
    if (stage === 'paid') {
      paymentAmountRef.current = '';
      return new Promise<{ stage: string; payment_amount?: number; remark?: string } | null>((resolve) => {
        modal.confirm({
          title: t('app.kuaioa.asset.stage.paid'),
          content: (
            <Input
              style={{ marginTop: 8 }}
              placeholder={t('app.kuaioa.assetPurchase.paymentAmount')}
              onChange={(e) => {
                paymentAmountRef.current = e.target.value;
              }}
            />
          ),
          onOk: () => {
            const n = Number(paymentAmountRef.current);
            if (!Number.isFinite(n) || n <= 0) {
              message.error(t('app.kuaioa.assetPurchase.paymentAmountRequired'));
              return Promise.reject();
            }
            resolve({ stage, payment_amount: n });
          },
          onCancel: () => resolve(null),
        });
      });
    }
    return { stage };
  };

  return (
    <KuaioaCrudListPage
      createButtonKey="app.kuaioa.assetPurchase.createButton"
      resource="kuaioa:asset-purchase"
      codeField="purchase_code"
      nameField="title"
      autoGenerateCode
      statusEnum={statusEnum}
      statusPresentation="lifecycle"
      detailVariant="approval"
      getDetailFn={getAssetPurchase}
      columnPersistenceId="apps.kuaioa.asset-purchase.list-v5"
      auditWorkflow={{
        entityType: 'kuaioa_asset_purchase',
        resourcePrefix: 'kuaioa:asset-purchase',
        auditNodeKey: 'kuaioa_asset_purchase',
        entityNameKey: 'app.kuaioa.assetPurchase.entityName',
      }}
      fields={fields}
      mapRecordToFormValues={(record) => mapOaAttachmentListToFormField(record)}
      mapFormValuesToPayload={(values) =>
        mapOaAttachmentFormFieldToList(mapOaFormValuesToPayload(fields, values))
      }
      listFn={listAssetPurchases}
      createFn={createAssetPurchase}
      updateFn={updateAssetPurchase}
      deleteFn={deleteAssetPurchase}
      showExportButton
      onExport={async (type, keys, pageData) => {
        await runKuaioaListExport({
          type,
          keys,
          pageData,
          listFn: listAssetPurchases,
          columns: exportColumns,
          filename: t('app.kuaioa.assetPurchase.exportFileName'),
          messageApi: message,
          noDataText: t('common.exportNoData'),
        });
      }}
      extraActions={[
        {
          key: 'advance',
          labelKey: 'app.kuaioa.asset.advanceStage',
          requireUpdate: true,
          visible: (r) => r.status === 'approved' && !!nextStage(String(r.lifecycle_stage || '')),
          onClick: async (r) => {
            const stage = nextStage(String(r.lifecycle_stage || ''));
            if (!stage) return;
            const payload = await promptAdvance(r, stage);
            if (!payload) return;
            await advanceAssetPurchaseLifecycle(Number(r.id), payload);
          },
        },
      ]}
    />
  );
};

export default AssetPurchasesPage;
