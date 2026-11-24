/**
 * 工序委外后续操作：下达 / 工序发料 / 登记收货 / 完成 / 结算
 */

import React, { useCallback, useEffect, useState } from 'react';
import { App, Button, Col, Form, InputNumber, Modal, Row, Space, Typography } from 'antd';
import { useNumericPrecisionPlaces } from '../../../hooks/useNumericPrecision';
import { formatQuantity } from '../../../utils/format';
import {
  applyOutsourceRegisterReceiptQuantityChange,
  isOutsourceRegisterReceiptQuantityBalanced,
} from '../utils/outsourceOrderRegisterReceiptQuantities';
import type { NavigateFunction } from 'react-router-dom';
import type { TFunction } from 'i18next';
import { SendOutlined, ExportOutlined, ImportOutlined, CheckOutlined, RollbackOutlined } from '@ant-design/icons';
import { outsourceOrderApi } from '../services/production';
import { getApiErrorMessage } from '../../../utils/errorHandler';
import { getOutsourceOrderProgressFlags } from '../utils/outsourceOrderLifecycle';
import { ROUTES } from '../constants/routes';
import { canOpenLinkedDocumentDetail } from '../utils/linkedDocumentDetail';
import type { useOptionalLinkedDocumentDetail } from '../../../components/linked-document-detail';
import { ActionConfirmPopconfirm } from '../../../components/action-confirm';
import { rowActionKind } from '../../../components/uni-action';

type LinkedDocumentDetailCtx = ReturnType<typeof useOptionalLinkedDocumentDetail>;

export type OutsourceOrderReceiptBatch = {
  id?: number;
  received_quantity?: number;
  qualified_quantity?: number;
  unqualified_quantity?: number;
  created_at?: string;
  created_by_name?: string;
};

export type OutsourceOrderProgressRecord = {
  id?: number;
  code?: string;
  status?: string;
  outsource_quantity?: number;
  received_quantity?: number;
  qualified_quantity?: number;
  unqualified_quantity?: number;
  purchase_receipt_id?: number;
  receipt_batches?: OutsourceOrderReceiptBatch[];
  issued_batch_quantity?: number;
  suggested_receipt_quantity?: number;
  capabilities?: {
    push_outsource_issue?: { allowed?: boolean; reason?: string };
  };
};

type RefreshFn = (updated: OutsourceOrderProgressRecord) => void;

export type OutsourceOrderProgressHandlers = {
  release: (record: OutsourceOrderProgressRecord) => Promise<void>;
  revokeRelease: (record: OutsourceOrderProgressRecord) => Promise<void>;
  start: (record: OutsourceOrderProgressRecord) => Promise<void>;
  complete: (record: OutsourceOrderProgressRecord) => Promise<void>;
};

export function useOutsourceOrderProgressHandlers(
  t: TFunction,
  onRefreshed: RefreshFn,
): OutsourceOrderProgressHandlers {
  const { message } = App.useApp();

  const afterSuccess = useCallback(
    (updated: OutsourceOrderProgressRecord, successKey: string) => {
      message.success(t(successKey));
      onRefreshed(updated);
    },
    [message, onRefreshed, t],
  );

  const release = useCallback(
    async (record: OutsourceOrderProgressRecord) => {
      if (record.id == null) return;
      try {
        const updated = await outsourceOrderApi.release(String(record.id));
        afterSuccess(updated as OutsourceOrderProgressRecord, 'app.kuaizhizao.outsourceOrder.releaseSuccess');
      } catch (error) {
        message.error(getApiErrorMessage(error, t('app.kuaizhizao.outsourceOrder.releaseFailed')));
      }
    },
    [afterSuccess, message, t],
  );

  const revokeRelease = useCallback(
    async (record: OutsourceOrderProgressRecord) => {
      if (record.id == null) return;
      try {
        const updated = await outsourceOrderApi.revokeRelease(String(record.id));
        afterSuccess(updated as OutsourceOrderProgressRecord, 'app.kuaizhizao.outsourceOrder.revokeReleaseSuccess');
      } catch (error) {
        message.error(getApiErrorMessage(error, t('app.kuaizhizao.outsourceOrder.revokeReleaseFailed')));
      }
    },
    [afterSuccess, message, t],
  );

  const start = useCallback(
    async (record: OutsourceOrderProgressRecord) => {
      if (record.id == null) return;
      try {
        const updated = await outsourceOrderApi.start(String(record.id));
        afterSuccess(updated as OutsourceOrderProgressRecord, 'app.kuaizhizao.outsourceOrder.startSuccess');
      } catch (error) {
        message.error(getApiErrorMessage(error, t('app.kuaizhizao.outsourceOrder.startFailed')));
      }
    },
    [afterSuccess, message, t],
  );

  const complete = useCallback(
    async (record: OutsourceOrderProgressRecord) => {
      if (record.id == null) return;
      try {
        const updated = await outsourceOrderApi.complete(String(record.id));
        afterSuccess(updated as OutsourceOrderProgressRecord, 'app.kuaizhizao.outsourceOrder.completeSuccess');
      } catch (error) {
        message.error(getApiErrorMessage(error, t('app.kuaizhizao.outsourceOrder.completeFailed')));
      }
    },
    [afterSuccess, message, t],
  );

  return { release, revokeRelease, start, complete };
}

/** lifecycle=下达/撤回/完成；execution=发料/入库/登记等；all=抽屉内全量 */
export type OutsourceOrderProgressActionScope = 'lifecycle' | 'execution' | 'all';

function progressActionInScope(
  kind: 'lifecycle' | 'execution',
  scope: OutsourceOrderProgressActionScope,
): boolean {
  return scope === 'all' || scope === kind;
}

type BuildProgressActionsArgs = {
  record: OutsourceOrderProgressRecord;
  t: TFunction;
  navigate: NavigateFunction;
  linkedDetail: LinkedDocumentDetailCtx;
  handlers: OutsourceOrderProgressHandlers;
  onOpenRegisterReceipt: (record: OutsourceOrderProgressRecord) => void;
  onOpenProcessIssue: (record: OutsourceOrderProgressRecord) => void;
  layout: 'drawer' | 'row' | 'toolbar';
  scope?: OutsourceOrderProgressActionScope;
  /** 列表功能区：未单选或选中无效时整组置灰，按钮仍占位展示 */
  toolbarSelectionActive?: boolean;
  closeDrawer?: () => void;
};

function buildOutsourceToolbarIdleButtons(t: TFunction): React.ReactNode[] {
  return [
    <Button key="oo-toolbar-issue-idle" type="primary" disabled icon={<ExportOutlined />}>
      {t('app.kuaizhizao.outsourceOrder.actionProcessIssue')}
    </Button>,
    <Button key="oo-toolbar-register-idle" type="primary" disabled icon={<ImportOutlined />}>
      {t('app.kuaizhizao.outsourceOrder.actionRegisterReceipt')}
    </Button>,
  ];
}

/** 每个后续动作单独一个节点，供操作列直出（禁止包在单组件 Fragment 里）。 */
export function buildOutsourceOrderProgressActionNodes(args: BuildProgressActionsArgs): React.ReactNode[] {
  const {
    record,
    t,
    navigate,
    linkedDetail,
    handlers,
    onOpenRegisterReceipt,
    onOpenProcessIssue,
    layout,
    scope = 'all',
    closeDrawer,
    toolbarSelectionActive = true,
  } = args;
  if (layout === 'toolbar' && !toolbarSelectionActive) {
    return buildOutsourceToolbarIdleButtons(t);
  }
  const flags = getOutsourceOrderProgressFlags(record as Record<string, unknown>);
  const isRow = layout === 'row';
  const primaryBtn = isRow ? { type: 'link' as const, size: 'small' as const } : { type: 'primary' as const };
  const defaultBtn = isRow ? { type: 'link' as const, size: 'small' as const } : {};

  const openInboundDoc = () => {
    if (record.purchase_receipt_id == null || !linkedDetail || !canOpenLinkedDocumentDetail('purchase_receipt')) {
      return;
    }
    linkedDetail.openLinkedDocumentDetail('purchase_receipt', Number(record.purchase_receipt_id));
  };

  const nodes: React.ReactNode[] = [];

  if (flags.canRevokeRelease && progressActionInScope('lifecycle', scope)) {
    nodes.push(
      <ActionConfirmPopconfirm
        key="oo-progress-revoke-pop"
        title={t('app.kuaizhizao.outsourceOrder.revokeReleaseConfirmTitle')}
        description={t('app.kuaizhizao.outsourceOrder.revokeReleaseConfirmContent', { code: record.code ?? '' })}
        onConfirm={() => handlers.revokeRelease(record)}
      >
        <Button
          {...(isRow ? rowActionKind('revoke') : {})}
          {...(isRow ? primaryBtn : defaultBtn)}
          icon={isRow ? undefined : <RollbackOutlined />}
          onClick={(e) => e.stopPropagation()}
        >
          {t('app.kuaizhizao.outsourceOrder.actionRevokeRelease')}
        </Button>
      </ActionConfirmPopconfirm>,
    );
  }
  if (flags.canRelease && progressActionInScope('lifecycle', scope)) {
    nodes.push(
      <Button
        key="oo-progress-release"
        {...(isRow ? rowActionKind('submit') : {})}
        {...primaryBtn}
        icon={isRow ? undefined : <SendOutlined />}
        onClick={(e) => {
          e.stopPropagation();
          void handlers.release(record);
        }}
      >
        {t('app.kuaizhizao.outsourceOrder.actionRelease')}
      </Button>,
    );
  }
  if (flags.canStart && progressActionInScope('execution', scope)) {
    nodes.push(
      <Button
        key="oo-progress-start"
        {...(isRow ? rowActionKind('export') : {})}
        {...primaryBtn}
        icon={isRow ? undefined : <ExportOutlined />}
        onClick={(e) => {
          e.stopPropagation();
          onOpenProcessIssue(record);
        }}
      >
        {(() => {
          const st = String(record.status ?? '').trim();
          return st === 'in_progress' || st === '执行中'
            ? t('app.kuaizhizao.outsourceOrder.actionProcessIssueContinue')
            : t('app.kuaizhizao.outsourceOrder.actionProcessIssue');
        })()}
      </Button>,
    );
  }
  if (flags.canOpenInboundDoc && progressActionInScope('execution', scope)) {
    nodes.push(
      <Button
        key="oo-progress-open-inbound"
        {...(isRow ? rowActionKind('read') : {})}
        {...defaultBtn}
        onClick={(e) => {
          e.stopPropagation();
          openInboundDoc();
        }}
      >
        {t('app.kuaizhizao.outsourceOrder.actionOpenInboundDoc')}
      </Button>,
    );
  }
  if (flags.canRegisterReceipt && progressActionInScope('execution', scope)) {
    nodes.push(
      <Button
        key="oo-progress-register"
        {...(isRow ? rowActionKind('import') : {})}
        {...primaryBtn}
        icon={isRow ? undefined : <ImportOutlined />}
        onClick={(e) => {
          e.stopPropagation();
          onOpenRegisterReceipt(record);
        }}
      >
        {t('app.kuaizhizao.outsourceOrder.actionRegisterReceipt')}
      </Button>,
    );
  }
  if (flags.canComplete && progressActionInScope('lifecycle', scope)) {
    nodes.push(
      <ActionConfirmPopconfirm
        key="oo-progress-complete-pop"
        title={t('app.kuaizhizao.outsourceOrder.completeConfirmTitle')}
        description={t('app.kuaizhizao.outsourceOrder.completeConfirmContent', { code: record.code ?? '' })}
        onConfirm={() => handlers.complete(record)}
      >
        <Button
          {...(isRow ? rowActionKind('complete') : {})}
          {...primaryBtn}
          icon={isRow ? undefined : <CheckOutlined />}
          onClick={(e) => e.stopPropagation()}
        >
          {t('app.kuaizhizao.outsourceOrder.actionComplete')}
        </Button>
      </ActionConfirmPopconfirm>,
    );
  }
  if (flags.canSettlement && progressActionInScope('execution', scope)) {
    nodes.push(
      <Button
        key="oo-progress-settlement"
        {...(isRow ? rowActionKind('read') : {})}
        {...defaultBtn}
        onClick={(e) => {
          e.stopPropagation();
          closeDrawer?.();
          navigate(ROUTES.OUTSOURCE_SETTLEMENTS);
        }}
      >
        {t('app.kuaizhizao.outsourceOrder.actionSettlement')}
      </Button>,
    );
  }

  return nodes;
}

export function appendOutsourceOrderProgressRowActions(
  target: React.ReactNode[],
  args: Omit<BuildProgressActionsArgs, 'layout'> & { scope?: OutsourceOrderProgressActionScope },
): void {
  const { scope = 'all', ...rest } = args;
  target.push(...buildOutsourceOrderProgressActionNodes({ ...rest, layout: 'row', scope }));
}

/** 列表功能区：未单选时占位置灰；单选后按单据状态启用对应项。 */
export function buildOutsourceOrderProgressToolbarActions(
  args: Omit<BuildProgressActionsArgs, 'layout'>,
): React.ReactNode[] {
  return buildOutsourceOrderProgressActionNodes({ ...args, layout: 'toolbar', scope: 'execution' });
}

export function OutsourceOrderRegisterReceiptModal(props: {
  open: boolean;
  record: OutsourceOrderProgressRecord | null;
  onClose: () => void;
  onSaved: (updated: OutsourceOrderProgressRecord) => void;
  t: TFunction;
}) {
  const { open, record, onClose, onSaved, t } = props;
  const { message } = App.useApp();
  const [form] = Form.useForm<{ received_quantity: number; qualified_quantity: number; unqualified_quantity: number }>();
  const [submitting, setSubmitting] = useState(false);
  const outQty = Number(record?.outsource_quantity ?? 0);
  const accumulated = Number(record?.received_quantity ?? 0);
  const remainingQty = Math.max(0, outQty - accumulated);
  const quantityDecimals = useNumericPrecisionPlaces('quantity');

  const applyQtyChange = useCallback(
    (field: 'received_quantity' | 'qualified_quantity' | 'unqualified_quantity', raw: number | null) => {
      const current = form.getFieldsValue();
      const next = applyOutsourceRegisterReceiptQuantityChange(
        remainingQty,
        {
          received_quantity: Number(current.received_quantity ?? 0),
          qualified_quantity: Number(current.qualified_quantity ?? 0),
          unqualified_quantity: Number(current.unqualified_quantity ?? 0),
        },
        field,
        Number(raw ?? 0),
        quantityDecimals,
      );
      form.setFieldsValue(next);
    },
    [form, remainingQty, quantityDecimals],
  );

  useEffect(() => {
    if (!open || !record) return;
    const suggested = Number(record.suggested_receipt_quantity ?? 0);
    const basisDefault =
      Number.isFinite(suggested) && suggested > 0
        ? Math.min(remainingQty, suggested)
        : remainingQty;
    const defaultRecv = basisDefault > 0 ? basisDefault : undefined;
    form.setFieldsValue({
      received_quantity: defaultRecv,
      qualified_quantity: defaultRecv,
      unqualified_quantity: 0,
    });
  }, [open, record, form, remainingQty]);

  const handleOk = async () => {
    if (record?.id == null) return;
    try {
      const values = await form.validateFields();
      if (!isOutsourceRegisterReceiptQuantityBalanced(values)) {
        message.error(t('app.kuaizhizao.outsourceOrder.registerReceiptQtyImbalance'));
        return;
      }
      setSubmitting(true);
      const updated = await outsourceOrderApi.registerReceipt(String(record.id), values);
      message.success(t('app.kuaizhizao.outsourceOrder.registerReceiptSuccess'));
      onSaved(updated as OutsourceOrderProgressRecord);
      onClose();
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return;
      message.error(getApiErrorMessage(error, t('app.kuaizhizao.outsourceOrder.registerReceiptFailed')));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={t('app.kuaizhizao.outsourceOrder.registerReceiptTitle')}
      open={open}
      onCancel={onClose}
      onOk={() => void handleOk()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="received_quantity"
          label={t('app.kuaizhizao.outsourceOrder.fieldBatchCompletedQty')}
          rules={[{ required: true, message: t('app.kuaizhizao.outsourceOrder.placeholderReceivedQty') }]}
        >
          <InputNumber
            min={0}
            max={remainingQty > 0 ? remainingQty : undefined}
            precision={quantityDecimals}
            style={{ width: '100%' }}
            onChange={(val) => applyQtyChange('received_quantity', val)}
          />
        </Form.Item>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="qualified_quantity"
              label={t('app.kuaizhizao.outsourceOrder.fieldQualifiedQty')}
              rules={[{ required: true, message: t('app.kuaizhizao.outsourceOrder.placeholderQualifiedQty') }]}
            >
              <InputNumber
                min={0}
                precision={quantityDecimals}
                style={{ width: '100%' }}
                onChange={(val) => applyQtyChange('qualified_quantity', val)}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="unqualified_quantity"
              label={t('app.kuaizhizao.outsourceOrder.fieldUnqualifiedQty')}
              rules={[
                { required: true, message: t('app.kuaizhizao.outsourceOrder.placeholderUnqualifiedQty') },
              ]}
            >
              <InputNumber
                min={0}
                precision={quantityDecimals}
                style={{ width: '100%' }}
                disabled
              />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item noStyle shouldUpdate>
          {() => {
            const recv = Number(form.getFieldValue('received_quantity') ?? 0);
            const qq = Number(form.getFieldValue('qualified_quantity') ?? 0);
            const uq = Number(form.getFieldValue('unqualified_quantity') ?? 0);
            const sum = qq + uq;
            const balanced = Math.abs(sum - recv) <= 1e-9;
            return (
              <div style={{ marginBottom: 8 }}>
                <span style={{ color: 'var(--ant-color-text-secondary)' }}>
                  {t('app.kuaizhizao.outsourceOrder.registerReceiptQtySum')}
                </span>
                <span style={{ fontWeight: 600, marginLeft: 4 }}>{formatQuantity(sum)}</span>
                {!balanced && recv > 0 ? (
                  <Typography.Text type="danger" style={{ display: 'block', marginTop: 8 }}>
                    {t('app.kuaizhizao.outsourceOrder.registerReceiptQtyImbalanceHint', {
                      batch: formatQuantity(recv),
                    })}
                  </Typography.Text>
                ) : null}
              </div>
            );
          }}
        </Form.Item>
      </Form>
    </Modal>
  );
}

export function OutsourceOrderProgressButtons(props: {
  record: OutsourceOrderProgressRecord;
  t: TFunction;
  navigate: NavigateFunction;
  linkedDetail: LinkedDocumentDetailCtx;
  handlers: OutsourceOrderProgressHandlers;
  onOpenRegisterReceipt: (record: OutsourceOrderProgressRecord) => void;
  onOpenProcessIssue: (record: OutsourceOrderProgressRecord) => void;
  closeDrawer?: () => void;
}) {
  const nodes = buildOutsourceOrderProgressActionNodes({ ...props, layout: 'drawer' });
  if (nodes.length === 0) return null;
  return <Space wrap>{nodes}</Space>;
}
