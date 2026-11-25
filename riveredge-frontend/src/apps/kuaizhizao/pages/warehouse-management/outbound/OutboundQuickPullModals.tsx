import React, { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, InputNumber, Select } from 'antd';
import { formatQuantity, formatBusinessDateOnly } from '../../../../../utils/format';
import { resolveKuaizhizaoDocumentAction } from '../../../constants/documentActionRegistry';
import { deliveryNoticeApi, type DeliveryNoticePullLine } from '../../../services/delivery-notice';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import {
  UniPullQueryModal,
  PULL_SOURCE_REFERENCE,
  isPullableScope,
  loadPullSourceReferenceOptions,
  loadPullWarehouseReferenceOptions,
  renderPullCapabilityTag,
  toUniPullQueryHttpParams,
  useUniPullQuery,
  buildDefaultPullOpenLineQtyColumns,
  buildPullQueryMaterialIdentityColumn,
  buildPullQueryPartnerDocumentColumn,
} from '../../../../../components/uni-pull-query';

const OUTBOUND_HOST_RESOURCE = 'kuaizhizao:outbound';
import {
  warehouseApi,
  type OutsourceIssuePullLine,
  type SalesDeliveryNoticePullLine,
  type SalesDeliveryOrderPullLine,
  type WorkOrderPickingPullLine,
} from '../../../services/warehouse-execution';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import type { OutboundQuickPullKey } from './outboundPullEntryTypes';
import type { SalesDeliveryCreateDraft } from './SalesDeliveryCreateModal';

export type { OutboundQuickPullKey };

export type OutboundQuickPullSuccessDetail = {
  pullKey: OutboundQuickPullKey;
  createdCount?: number;
  pickingId?: number;
  pickingCode?: string;
  salesDeliveryDraft?: SalesDeliveryCreateDraft;
};

export type OutboundQuickPullModalsRef = {
  open: (key: OutboundQuickPullKey) => void;
};

type PullWorkOrderCandidate = WorkOrderPickingPullLine;
type PullOutsourceWoCandidate = OutsourceIssuePullLine;
type PullSalesOrderCandidate = SalesDeliveryOrderPullLine;
type PullShipmentNoticeCandidate = SalesDeliveryNoticePullLine;
type PullDeliveryNoticeCandidate = DeliveryNoticePullLine;

type OutboundQuickPullModalsProps = {
  onSuccess?: (detail?: OutboundQuickPullSuccessDetail) => void;
};

const OutboundQuickPullModals = forwardRef<OutboundQuickPullModalsRef, OutboundQuickPullModalsProps>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const { message: messageApi } = App.useApp();
    const invalidateMenuBadgeCounts = useInvalidateMenuBadgeCounts();
    const pullFromWorkOrderAction = resolveKuaizhizaoDocumentAction(t, 'outbound.pull_from_work_order');
    const pullFromSalesOrderAction = resolveKuaizhizaoDocumentAction(t, 'sales_delivery.pull_from_sales_order');
    const pullFromShipmentNoticeAction = resolveKuaizhizaoDocumentAction(t, 'sales_delivery.pull_from_shipment_notice');
    const pullFromOutsourceWorkOrderAction = resolveKuaizhizaoDocumentAction(t, 'outbound.pull_from_outsource_work_order');
    const pullFromSalesDeliveryAction = resolveKuaizhizaoDocumentAction(t, 'delivery_note.pull_from_sales_delivery');

    const pullSourceSalesOrderIdRef = useRef<number | undefined>(undefined);
    const pullSourceNoticeIdRef = useRef<number | undefined>(undefined);
    const pullSourceWorkOrderIdRef = useRef<number | undefined>(undefined);
    const pullSourceOutsourceIdRef = useRef<number | undefined>(undefined);
    const pullSourceDeliveryIdRef = useRef<number | undefined>(undefined);
    const [pullSourceSalesOrderId, setPullSourceSalesOrderId] = useState<number | undefined>();
    const [pullSourceNoticeId, setPullSourceNoticeId] = useState<number | undefined>();
    const [pullSourceWorkOrderId, setPullSourceWorkOrderId] = useState<number | undefined>();
    const [pullSourceOutsourceId, setPullSourceOutsourceId] = useState<number | undefined>();
    const [pullSourceDeliveryId, setPullSourceDeliveryId] = useState<number | undefined>();
    const [pullSourceSalesOrderOptions, setPullSourceSalesOrderOptions] = useState<Array<{ value: number; label: string }>>([]);
    const [pullSourceNoticeOptions, setPullSourceNoticeOptions] = useState<Array<{ value: number; label: string }>>([]);
    const [pullSourceWorkOrderOptions, setPullSourceWorkOrderOptions] = useState<Array<{ value: number; label: string }>>([]);
    const [pullSourceOutsourceOptions, setPullSourceOutsourceOptions] = useState<Array<{ value: number; label: string }>>([]);
    const [pullSourceDeliveryOptions, setPullSourceDeliveryOptions] = useState<Array<{ value: number; label: string }>>([]);
    /** 销售订单取单：本次下推数量（与销售订单下推预览同契约，上限为可发货） */
    const [salesOrderPullQtys, setSalesOrderPullQtys] = useState<Record<number, number>>({});
    const [salesDeliveryPullWarehouseOptions, setSalesDeliveryPullWarehouseOptions] = useState<
      Array<{ label: string; value: number }>
    >([]);
    const [shipmentNoticePullLineWh, setShipmentNoticePullLineWh] = useState<Record<number, number>>({});
    const [shipmentNoticePullBatchWarehouseId, setShipmentNoticePullBatchWarehouseId] = useState<
      number | undefined
    >();

    const pullDocumentScopeOptions = useMemo(
      () => [
        { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
        { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
      ],
      [t],
    );


    const isPullLineSelectable = useCallback(
      (record: { remaining_quantity?: number }) => Number(record.remaining_quantity ?? 0) > 0,
      [],
    );


    const pullFromWorkOrderQuery = useUniPullQuery<PullWorkOrderCandidate>({
      rowKey: 'id',
      selectionType: 'checkbox',
      scopeOptions: pullDocumentScopeOptions,
      defaultScope: 'pullable',
      onOpen: () => {
        pullSourceWorkOrderIdRef.current = undefined;
        setPullSourceWorkOrderId(undefined);
        void loadPullSourceReferenceOptions({
          resource: PULL_SOURCE_REFERENCE.workOrder,
          hostResource: OUTBOUND_HOST_RESOURCE,
        })
          .then(setPullSourceWorkOrderOptions)
          .catch((error: unknown) => {
            messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.warehouseOutbound.pull.wo.loadSourceFailed')));
            setPullSourceWorkOrderOptions([]);
          });
      },
      loadData: async (params) => {
        const { scope } = params;
        try {
          const listRes = await warehouseApi.productionPicking.listWorkOrderPullLines({
            ...toUniPullQueryHttpParams(params),
            work_order_id: pullSourceWorkOrderIdRef.current,
            pullable_only: isPullableScope(scope),
          });
          return { data: listRes?.data ?? [], total: listRes?.total ?? 0 };
        } catch (error: unknown) {
          messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.warehouseOutbound.pull.loadWorkOrdersFailed')));
          return { data: [], total: 0 };
        }
      },
      isRowDisabled: (record) => !isPullLineSelectable(record),
      onConfirm: async (_keys, rows) => {
        const selectedIds = rows
          .filter((row) => isPullLineSelectable(row))
          .map((row) => Number(row.id))
          .filter((id) => id > 0);
        if (!selectedIds.length) {
          messageApi.warning(t('app.kuaizhizao.warehouseOutbound.pull.wo.selectLinesFirst'));
          return;
        }
        try {
          const res = await warehouseApi.productionPicking.pullFromWorkOrderItems(selectedIds);
          messageApi.success(
            res.message ||
              t('app.kuaizhizao.shipmentNotice.createFromSourceSuccess', {
                source: pullFromWorkOrderAction.sourceLabel,
                target: pullFromWorkOrderAction.targetLabel,
              }),
          );
          pullFromWorkOrderQuery.closeModal();
          invalidateMenuBadgeCounts();
          const pickingId = Number(res.picking_id ?? res.pickings?.[0]?.picking_id ?? 0);
          onSuccess?.({
            pullKey: 'work_order',
            createdCount: res.pickings?.length ?? selectedIds.length,
            pickingId: pickingId > 0 ? pickingId : undefined,
            pickingCode:
              String(res.picking_code ?? res.pickings?.[0]?.picking_code ?? '').trim() || undefined,
          });
        } catch (error: unknown) {
          messageApi.error(
            getApiErrorMessage(
              error,
              t('app.kuaizhizao.shipmentNotice.createFromSourceFailed', {
                source: pullFromWorkOrderAction.sourceLabel,
                target: pullFromWorkOrderAction.targetLabel,
              }),
            ),
          );
        }
      },
    });

    const pullFromSalesOrderQuery = useUniPullQuery<PullSalesOrderCandidate>({
      rowKey: 'id',
      selectionType: 'checkbox',
      scopeOptions: pullDocumentScopeOptions,
      defaultScope: 'pullable',
      onOpen: () => {
        pullSourceSalesOrderIdRef.current = undefined;
        setPullSourceSalesOrderId(undefined);
        setSalesOrderPullQtys({});
        void loadPullSourceReferenceOptions({
          resource: PULL_SOURCE_REFERENCE.salesOrder,
          hostResource: OUTBOUND_HOST_RESOURCE,
        })
          .then(setPullSourceSalesOrderOptions)
          .catch((error: unknown) => {
            messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.warehouseOutbound.pull.loadSourceFailed')));
            setPullSourceSalesOrderOptions([]);
          });
      },
      loadData: async (params) => {
        const { scope } = params;
        try {
          const listRes = await warehouseApi.salesDelivery.listSalesOrderPullLines({
            ...toUniPullQueryHttpParams(params),
            sales_order_id: pullSourceSalesOrderIdRef.current,
            pullable_only: isPullableScope(scope),
          });
          const rows = listRes?.data ?? [];
          setSalesOrderPullQtys((prev) => {
            const next = { ...prev };
            for (const row of rows) {
              const id = Number(row.id);
              if (!Number.isFinite(id) || id <= 0) continue;
              if (next[id] == null) {
                next[id] = Number(row.remaining_quantity ?? 0);
              }
            }
            return next;
          });
          return { data: rows, total: listRes?.total ?? 0 };
        } catch (error: unknown) {
          messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.warehouseOutbound.pull.loadSalesOrdersFailed')));
          return { data: [], total: 0 };
        }
      },
      isRowDisabled: (record) => !isPullLineSelectable(record),
      onConfirm: async (_keys, rows) => {
        const selected = rows.filter((row) => isPullLineSelectable(row));
        if (!selected.length) {
          messageApi.warning(t('app.kuaizhizao.warehouseOutbound.pull.soSelectLinesFirst'));
          return;
        }
        const customerIds = new Set(
          selected.map((row) => Number(row.customer_id ?? 0)).filter((id) => id > 0),
        );
        const priceTypes = new Set(
          selected.map((row) => String(row.price_type ?? '').trim()).filter(Boolean),
        );
        if (customerIds.size > 1 || priceTypes.size > 1) {
          messageApi.warning(t('app.kuaizhizao.warehouseOutbound.pull.soSameCustomerPriceTypeRequired'));
          return;
        }
        const headerCustomerOrderNo = selected.reduce<string>((acc, row) => {
          if (acc) return acc;
          const lineNo =
            row.customer_order_no != null ? String(row.customer_order_no).trim() : '';
          return lineNo || acc;
        }, '');
        const draftItems: Array<Record<string, unknown>> = [];
        for (const row of selected) {
          const id = Number(row.id);
          const maxQty = Number(row.remaining_quantity ?? 0);
          const qty = Number(salesOrderPullQtys[id] ?? maxQty);
          if (!Number.isFinite(id) || id <= 0) continue;
          if (!Number.isFinite(qty) || qty <= 0) {
            messageApi.warning(
              t('app.kuaizhizao.salesOrder.pushQtyInvalid', {
                code: row.material_code || id,
              }),
            );
            return;
          }
          if (qty > maxQty) {
            messageApi.warning(
              t('app.kuaizhizao.salesOrder.pushQtyExceedsShippable', {
                code: row.material_code || id,
              }),
            );
            return;
          }
          draftItems.push({
            sales_order_item_id: id,
            material_id: row.material_id,
            material_code: row.material_code,
            material_name: row.material_name,
            material_spec: row.material_spec,
            material_model:
              row.material_model != null ? String(row.material_model).trim() || undefined : undefined,
            partner_material_code:
              row.partner_material_code != null
                ? String(row.partner_material_code).trim() || ''
                : '',
            partner_material_name:
              row.partner_material_name != null
                ? String(row.partner_material_name).trim() || ''
                : '',
            material_unit: row.unit,
            delivery_quantity: qty,
            unit_price: Number(row.unit_price ?? 0),
            tax_rate: Number(row.tax_rate ?? 0),
            warehouse_id:
              row.warehouse_id != null && Number(row.warehouse_id) > 0
                ? Number(row.warehouse_id)
                : undefined,
            warehouse_name: row.warehouse_name ?? undefined,
            notes: row.line_notes ?? undefined,
            customer_order_no:
              (row.customer_order_no != null && String(row.customer_order_no).trim()) ||
              headerCustomerOrderNo ||
              undefined,
          });
        }
        if (!draftItems.length) {
          messageApi.warning(t('app.kuaizhizao.warehouseOutbound.pull.soSelectLinesFirst'));
          return;
        }
        const orderIds = [...new Set(selected.map((row) => Number(row.sales_order_id)).filter((id) => id > 0))];
        const orderCodes = [...new Set(selected.map((row) => String(row.order_code ?? '').trim()).filter(Boolean))];
        const headerRow = selected[0];
        pullFromSalesOrderQuery.closeModal();
        onSuccess?.({
          pullKey: 'sales_order',
          salesDeliveryDraft: {
            salesOrderId: orderIds.length === 1 ? orderIds[0] : null,
            salesOrderCode: orderCodes.length === 1 ? orderCodes[0] : '',
            customerOrderNo: headerCustomerOrderNo || undefined,
            customerId: headerRow?.customer_id,
            customerName: headerRow?.customer_name,
            customerContact:
              headerRow?.customer_contact != null ? String(headerRow.customer_contact) : undefined,
            customerPhone:
              headerRow?.customer_phone != null ? String(headerRow.customer_phone) : undefined,
            revenueRecognition:
              headerRow?.revenue_recognition != null
                ? String(headerRow.revenue_recognition)
                : undefined,
            currencyCode:
              headerRow?.currency_code != null ? String(headerRow.currency_code) : undefined,
            exchangeRate:
              headerRow?.exchange_rate != null ? Number(headerRow.exchange_rate) : undefined,
            shippingAddress:
              headerRow?.shipping_address != null ? String(headerRow.shipping_address) : undefined,
            shippingMethod:
              headerRow?.shipping_method != null ? String(headerRow.shipping_method) : undefined,
            paymentMethodCode:
              headerRow?.payment_method_code != null ? String(headerRow.payment_method_code) : undefined,
            paymentWirePercent:
              headerRow?.payment_wire_percent != null
                ? Number(headerRow.payment_wire_percent)
                : undefined,
            paymentAcceptancePercent:
              headerRow?.payment_acceptance_percent != null
                ? Number(headerRow.payment_acceptance_percent)
                : undefined,
            priceType: headerRow?.price_type,
            items: draftItems,
          },
        });
      },
    });

    const pullFromShipmentNoticeQuery = useUniPullQuery<PullShipmentNoticeCandidate>({
      rowKey: 'id',
      selectionType: 'checkbox',
      scopeOptions: pullDocumentScopeOptions,
      defaultScope: 'pullable',
      onOpen: () => {
        pullSourceNoticeIdRef.current = undefined;
        setPullSourceNoticeId(undefined);
        setShipmentNoticePullLineWh({});
        setShipmentNoticePullBatchWarehouseId(undefined);
        void loadPullSourceReferenceOptions({
          resource: PULL_SOURCE_REFERENCE.shipmentNotice,
          hostResource: OUTBOUND_HOST_RESOURCE,
        })
          .then(setPullSourceNoticeOptions)
          .catch((error: unknown) => {
            messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.warehouseOutbound.pull.loadSourceFailed')));
            setPullSourceNoticeOptions([]);
          });
        void loadPullWarehouseReferenceOptions(OUTBOUND_HOST_RESOURCE)
          .then(setSalesDeliveryPullWarehouseOptions)
          .catch((error: unknown) => {
            messageApi.error(
              getApiErrorMessage(error, t('app.kuaizhizao.warehouseOutbound.pull.loadWarehouseFailed')),
            );
            setSalesDeliveryPullWarehouseOptions([]);
          });
      },
      loadData: async (params) => {
        const { scope } = params;
        try {
          const listRes = await warehouseApi.salesDelivery.listShipmentNoticePullLines({
            ...toUniPullQueryHttpParams(params),
            notice_id: pullSourceNoticeIdRef.current,
            pullable_only: isPullableScope(scope),
          });
          return { data: listRes?.data ?? [], total: listRes?.total ?? 0 };
        } catch (error: unknown) {
          messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.warehouseOutbound.pull.loadShipmentNoticesFailed')));
          return { data: [], total: 0 };
        }
      },
      isRowDisabled: (record) => !isPullLineSelectable(record),
      onConfirm: async (_keys, rows) => {
        const selectedRows = rows.filter((row) => isPullLineSelectable(row));
        const selectedIds = selectedRows.map((row) => Number(row.id)).filter((id) => id > 0);
        if (!selectedIds.length) {
          messageApi.warning(t('app.kuaizhizao.warehouseOutbound.pull.snSelectLinesFirst'));
          return;
        }
        const customerIds = new Set(
          selectedRows.map((row) => Number(row.customer_id ?? 0)).filter((id) => id > 0),
        );
        const priceTypes = new Set(
          selectedRows.map((row) => String(row.price_type ?? '').trim()).filter(Boolean),
        );
        if (customerIds.size > 1 || priceTypes.size > 1) {
          messageApi.warning(t('app.kuaizhizao.warehouseOutbound.pull.soSameCustomerPriceTypeRequired'));
          return;
        }
        const lineWarehouses: Record<number, number> = {};
        for (const row of selectedRows) {
          const id = Number(row.id);
          const wh =
            shipmentNoticePullLineWh[id] ??
            (row.warehouse_id != null && Number(row.warehouse_id) > 0
              ? Number(row.warehouse_id)
              : undefined);
          if (wh == null || !(wh > 0)) {
            messageApi.error(
              t('app.kuaizhizao.warehouseOutbound.pull.selectWarehouseForMaterial', {
                material: row.material_code || row.material_name || '-',
              }),
            );
            return;
          }
          lineWarehouses[id] = wh;
        }
        try {
          const res = await warehouseApi.salesDelivery.pullFromShipmentNoticeItems(selectedIds, {
            lineWarehouses,
            pushMode: 'draft',
          });
          messageApi.success(
            res.message ||
              t('app.kuaizhizao.shipmentNotice.createFromSourceSuccess', {
                source: pullFromShipmentNoticeAction.sourceLabel,
                target: pullFromShipmentNoticeAction.targetLabel,
              }),
          );
          pullFromShipmentNoticeQuery.closeModal();
          onSuccess?.({
            pullKey: 'shipment_notice',
            createdCount: res.deliveries?.length ?? selectedIds.length,
          });
        } catch (error: unknown) {
          messageApi.error(
            getApiErrorMessage(
              error,
              t('app.kuaizhizao.shipmentNotice.createFromSourceFailed', {
                source: pullFromShipmentNoticeAction.sourceLabel,
                target: pullFromShipmentNoticeAction.targetLabel,
              }),
            ),
          );
        }
      },
    });

    useEffect(() => {
      if (!pullFromShipmentNoticeQuery.open) return;
      const rows = pullFromShipmentNoticeQuery.dataSource;
      if (!rows.length) return;
      setShipmentNoticePullLineWh((prev) => {
        let changed = false;
        const next = { ...prev };
        for (const row of rows) {
          const id = Number(row.id);
          if (!(id > 0) || next[id] != null) continue;
          const suggested = Number(row.warehouse_id);
          if (Number.isFinite(suggested) && suggested > 0) {
            next[id] = suggested;
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }, [pullFromShipmentNoticeQuery.open, pullFromShipmentNoticeQuery.dataSource]);

    const applyShipmentNoticePullBatchWarehouse = useCallback(
      (warehouseId: number) => {
        setShipmentNoticePullBatchWarehouseId(warehouseId);
        const targetIds =
          pullFromShipmentNoticeQuery.selectedRowKeys.length > 0
            ? pullFromShipmentNoticeQuery.selectedRowKeys.map((k) => Number(k)).filter((id) => id > 0)
            : pullFromShipmentNoticeQuery.dataSource.map((row) => Number(row.id)).filter((id) => id > 0);
        if (!targetIds.length) {
          messageApi.warning(t('app.kuaizhizao.warehouseOutbound.pull.batchWarehouseNoLines'));
          return;
        }
        setShipmentNoticePullLineWh((prev) => {
          const next = { ...prev };
          for (const id of targetIds) next[id] = warehouseId;
          return next;
        });
        messageApi.success(
          t('app.kuaizhizao.warehouseOutbound.pull.batchWarehouseApplied', { count: targetIds.length }),
        );
      },
      [
        messageApi,
        pullFromShipmentNoticeQuery.dataSource,
        pullFromShipmentNoticeQuery.selectedRowKeys,
        t,
      ],
    );

    const pullFromOutsourceWorkOrderQuery = useUniPullQuery<PullOutsourceWoCandidate>({
      rowKey: 'id',
      selectionType: 'checkbox',
      scopeOptions: pullDocumentScopeOptions,
      defaultScope: 'pullable',
      onOpen: () => {
        pullSourceOutsourceIdRef.current = undefined;
        setPullSourceOutsourceId(undefined);
        void loadPullSourceReferenceOptions({
          resource: PULL_SOURCE_REFERENCE.outsourceWorkOrder,
          hostResource: OUTBOUND_HOST_RESOURCE,
        })
          .then(setPullSourceOutsourceOptions)
          .catch((error: unknown) => {
            messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.warehouseOutbound.pull.os.loadSourceFailed')));
            setPullSourceOutsourceOptions([]);
          });
      },
      loadData: async (params) => {
        const { scope } = params;
        try {
          const listRes = await warehouseApi.outsourceIssue.listWorkOrderPullLines({
            ...toUniPullQueryHttpParams(params),
            outsource_work_order_id: pullSourceOutsourceIdRef.current,
            pullable_only: isPullableScope(scope),
          });
          return { data: listRes?.data ?? [], total: listRes?.total ?? 0 };
        } catch (error: unknown) {
          messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.warehouseOutbound.pull.loadOutsourceFailed')));
          return { data: [], total: 0 };
        }
      },
      isRowDisabled: (record) => !isPullLineSelectable(record),
      onConfirm: async (_keys, rows) => {
        const selectedIds = rows
          .filter((row) => isPullLineSelectable(row))
          .map((row) => Number(row.id))
          .filter((id) => id > 0);
        if (!selectedIds.length) {
          messageApi.warning(t('app.kuaizhizao.warehouseOutbound.pull.os.selectLinesFirst'));
          return;
        }
        try {
          const res = await warehouseApi.outsourceIssue.pullFromWorkOrderItems(selectedIds);
          messageApi.success(
            res.message ||
              t('app.kuaizhizao.shipmentNotice.createFromSourceSuccess', {
                source: pullFromOutsourceWorkOrderAction.sourceLabel,
                target: pullFromOutsourceWorkOrderAction.targetLabel,
              }),
          );
          pullFromOutsourceWorkOrderQuery.closeModal();
          onSuccess();
        } catch (error: unknown) {
          messageApi.error(
            getApiErrorMessage(
              error,
              t('app.kuaizhizao.shipmentNotice.createFromSourceFailed', {
                source: pullFromOutsourceWorkOrderAction.sourceLabel,
                target: pullFromOutsourceWorkOrderAction.targetLabel,
              }),
            ),
          );
        }
      },
    });

    const pullFromSalesDeliveryQuery = useUniPullQuery<PullDeliveryNoticeCandidate>({
      rowKey: 'id',
      selectionType: 'checkbox',
      scopeOptions: pullDocumentScopeOptions,
      defaultScope: 'pullable',
      onOpen: () => {
        pullSourceDeliveryIdRef.current = undefined;
        setPullSourceDeliveryId(undefined);
        void warehouseApi.salesDelivery.list({ skip: 0, limit: 100 })
          .then((res: { items?: Array<{ id?: number; delivery_code?: string }>; data?: Array<{ id?: number; delivery_code?: string }> }) => {
            const rows = res?.items ?? res?.data ?? [];
            setPullSourceDeliveryOptions(
              rows
                .filter((row) => row.id != null && row.delivery_code)
                .map((row) => ({ value: row.id!, label: String(row.delivery_code) })),
            );
          })
          .catch((error: unknown) => {
            messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.deliveryNote.pull.loadSourceFailed')));
            setPullSourceDeliveryOptions([]);
          });
      },
      loadData: async (params) => {
        const { scope } = params;
        try {
          const listRes = await deliveryNoticeApi.listSalesDeliveryPullLines({
            ...toUniPullQueryHttpParams(params),
            sales_delivery_id: pullSourceDeliveryIdRef.current,
            pullable_only: isPullableScope(scope),
          });
          return { data: listRes?.data ?? [], total: listRes?.total ?? 0 };
        } catch (error: unknown) {
          messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.deliveryNote.msg.loadListFailed')));
          return { data: [], total: 0 };
        }
      },
      isRowDisabled: (record) => !isPullLineSelectable(record),
      onConfirm: async (_keys, rows) => {
        const selectedIds = rows
          .filter((row) => isPullLineSelectable(row))
          .map((row) => Number(row.id))
          .filter((id) => id > 0);
        if (!selectedIds.length) {
          messageApi.warning(t('app.kuaizhizao.deliveryNote.pull.selectLinesFirst'));
          return;
        }
        try {
          const res = await deliveryNoticeApi.pullFromSalesDeliveryItems(selectedIds);
          messageApi.success(
            res.message ||
              t('app.kuaizhizao.shipmentNotice.createFromSourceSuccess', {
                source: pullFromSalesDeliveryAction.sourceLabel,
                target: pullFromSalesDeliveryAction.targetLabel,
              }),
          );
          pullFromSalesDeliveryQuery.closeModal();
          invalidateMenuBadgeCounts();
          onSuccess();
        } catch (error: unknown) {
          messageApi.error(
            getApiErrorMessage(
              error,
              t('app.kuaizhizao.shipmentNotice.createFromSourceFailed', {
                source: pullFromSalesDeliveryAction.sourceLabel,
                target: pullFromSalesDeliveryAction.targetLabel,
              }),
            ),
          );
        }
      },
    });

    useImperativeHandle(ref, () => ({
      open: (key: OutboundQuickPullKey) => {
        if (key === 'work_order') {
          pullFromWorkOrderQuery.openModal();
        } else if (key === 'sales_order') {
          pullFromSalesOrderQuery.openModal();
        } else if (key === 'shipment_notice') {
          pullFromShipmentNoticeQuery.openModal();
        } else if (key === 'delivery_note') {
          pullFromSalesDeliveryQuery.openModal();
        } else {
          pullFromOutsourceWorkOrderQuery.openModal();
        }
      },
    }));

    const pullOpenQtyTripleColumns = useMemo(
      () =>
        buildDefaultPullOpenLineQtyColumns(t, {
          includeRemaining: true,
          widths: { suggested: 100, pushed: 100, remaining: 100 },
        }),
      [t],
    );

    const workOrderColumns = useMemo(
      () => [
        { title: t('app.kuaizhizao.warehouseOutbound.pull.colWorkOrderCode'), dataIndex: 'work_order_code', width: 168, ellipsis: true },
        buildPullQueryMaterialIdentityColumn<PullWorkOrderCandidate>(t),
        ...pullOpenQtyTripleColumns,
        {
          title: t('app.kuaizhizao.warehouseOutbound.pull.convertStatus'),
          key: 'convert_status',
          width: 100,
          align: 'center' as const,
          render: (_: unknown, record: PullWorkOrderCandidate) =>
            renderPullCapabilityTag(
              Number(record.remaining_quantity ?? 0) > 0,
              t('app.kuaizhizao.warehouseOutbound.pull.canCreate'),
              t('app.kuaizhizao.purchaseRequisition.pull.cannotCreate'),
            ),
        },
      ],
      [t],
    );

    const salesOrderColumns = useMemo(
      () => [
        {
          title: t('components.uniPullQuery.documentDateColumn'),
          dataIndex: 'document_date',
          width: 112,
          render: (_: unknown, record: PullSalesOrderCandidate) => {
            const raw = record.document_date || record.order_date;
            return raw ? formatBusinessDateOnly(String(raw)) : '-';
          },
        },
        buildPullQueryPartnerDocumentColumn<PullSalesOrderCandidate>(t, {
          titleKey: 'app.kuaizhizao.warehouseOutbound.pull.colSalesOrderCode',
          codeDataIndex: 'order_code',
          partnerField: 'customer_name',
        }),
        buildPullQueryMaterialIdentityColumn<PullSalesOrderCandidate>(t),
        {
          title: t('app.kuaizhizao.warehouseOutbound.pull.colOrderQty'),
          dataIndex: 'suggested_quantity',
          width: 100,
          align: 'right' as const,
          render: formatQuantity,
        },
        {
          title: t('app.kuaizhizao.warehouseOutbound.pull.colCurrentStock'),
          dataIndex: 'current_stock',
          width: 112,
          align: 'right' as const,
          render: (v: number | undefined) => formatQuantity(Number(v ?? 0)),
        },
        {
          title: t('app.kuaizhizao.purchaseOrder.pull.col.convertedQty'),
          dataIndex: 'pushed_quantity',
          width: 112,
          align: 'right' as const,
          render: formatQuantity,
        },
        {
          title: t('app.kuaizhizao.salesOrder.deliveryDate'),
          dataIndex: 'required_date',
          width: 112,
          render: (v: string | null | undefined) => (v ? formatBusinessDateOnly(String(v)) : '-'),
        },
        {
          title: t('app.kuaizhizao.purchaseOrder.form.lineNotes'),
          dataIndex: 'line_notes',
          width: 160,
          ellipsis: true,
          render: (v: string | null | undefined) => (v && String(v).trim() ? String(v) : '-'),
        },
        {
          title: t('app.kuaizhizao.salesOrder.colPushQty'),
          key: 'push_quantity',
          width: 130,
          render: (_: unknown, record: PullSalesOrderCandidate) => {
            const id = Number(record.id);
            const maxQty = Number(record.remaining_quantity ?? 0);
            const disabled = !Number.isFinite(maxQty) || maxQty <= 0;
            return (
              <InputNumber
                min={0}
                max={maxQty > 0 ? maxQty : undefined}
                step={1}
                disabled={disabled}
                style={{ width: '100%' }}
                value={Number.isFinite(id) ? salesOrderPullQtys[id] : undefined}
                onChange={(v) => {
                  if (!Number.isFinite(id) || id <= 0) return;
                  setSalesOrderPullQtys((prev) => ({
                    ...prev,
                    [id]: Number(v ?? 0),
                  }));
                }}
              />
            );
          },
        },
      ],
      [
        salesOrderPullQtys,
        t,
      ],
    );

    const shipmentNoticeColumns = useMemo(
      () => [
        { title: t('app.kuaizhizao.warehouseOutbound.pull.colShipmentNoticeCode'), dataIndex: 'notice_code', width: 168, ellipsis: true },
        buildPullQueryMaterialIdentityColumn<PullShipmentNoticeCandidate>(t),
        {
          title: t('app.kuaizhizao.warehouseOutbound.col.warehouse'),
          key: 'warehouse',
          width: 150,
          render: (_: unknown, record: PullShipmentNoticeCandidate) => (
            <Select
              style={{ width: '100%', minWidth: 118 }}
              size="small"
              showSearch
              optionFilterProp="label"
              placeholder={t('app.kuaizhizao.warehouseOutbound.msg.selectWarehouse')}
              value={shipmentNoticePullLineWh[record.id]}
              options={salesDeliveryPullWarehouseOptions}
              onChange={(value) => {
                const nextId = Number(value);
                if (!(Number.isFinite(nextId) && nextId > 0)) return;
                setShipmentNoticePullLineWh((prev) => ({ ...prev, [record.id]: nextId }));
              }}
            />
          ),
        },
        ...pullOpenQtyTripleColumns,
        { title: t('app.kuaizhizao.warehouseOutbound.col.customer'), dataIndex: 'customer_name', width: 140, ellipsis: true },
        {
          title: t('app.kuaizhizao.warehouseOutbound.pull.convertStatus'),
          key: 'convert_status',
          width: 100,
          align: 'center' as const,
          render: (_: unknown, record: PullShipmentNoticeCandidate) =>
            renderPullCapabilityTag(
              Number(record.remaining_quantity ?? 0) > 0,
              t('app.kuaizhizao.warehouseOutbound.pull.canCreate'),
              t('app.kuaizhizao.purchaseRequisition.pull.cannotCreate'),
            ),
        },
      ],
      [salesDeliveryPullWarehouseOptions, shipmentNoticePullLineWh, t],
    );

    const outsourceColumns = useMemo(
      () => [
        { title: t('app.kuaizhizao.warehouseOutbound.pull.colOutsourceCode'), dataIndex: 'outsource_work_order_code', width: 168, ellipsis: true },
        buildPullQueryMaterialIdentityColumn<PullOutsourceWoCandidate>(t),
        ...pullOpenQtyTripleColumns,
        { title: t('app.kuaizhizao.warehouseOutbound.pull.colSupplier'), dataIndex: 'supplier_name', width: 140, ellipsis: true },
        {
          title: t('app.kuaizhizao.warehouseOutbound.pull.convertStatus'),
          key: 'convert_status',
          width: 100,
          align: 'center' as const,
          render: (_: unknown, record: PullOutsourceWoCandidate) =>
            renderPullCapabilityTag(
              Number(record.remaining_quantity ?? 0) > 0,
              t('app.kuaizhizao.warehouseOutbound.pull.canCreate'),
              t('app.kuaizhizao.purchaseRequisition.pull.cannotCreate'),
            ),
        },
      ],
      [t],
    );

    const salesDeliveryColumns = useMemo(
      () => [
        {
          title: t('app.kuaizhizao.deliveryNote.col.salesDeliveryCode'),
          dataIndex: 'delivery_code',
          width: 168,
          ellipsis: true,
        },
        buildPullQueryMaterialIdentityColumn<PullDeliveryNoticeCandidate>(t),
        ...pullOpenQtyTripleColumns,
        {
          title: t('app.kuaizhizao.deliveryNote.field.customer'),
          dataIndex: 'customer_name',
          width: 140,
          ellipsis: true,
        },
        {
          title: t('app.kuaizhizao.warehouseOutbound.pull.colOutboundDate'),
          dataIndex: 'required_date',
          width: 112,
          render: (v: string) => (v ? formatBusinessDateOnly(v) : '-'),
        },
        {
          title: t('app.kuaizhizao.deliveryNote.pull.gateStatus'),
          key: 'convert_status',
          width: 100,
          align: 'center' as const,
          render: (_: unknown, record: PullDeliveryNoticeCandidate) =>
            renderPullCapabilityTag(
              Number(record.remaining_quantity ?? 0) > 0,
              t('app.kuaizhizao.deliveryNote.pull.canCreate'),
              t('app.kuaizhizao.purchaseRequisition.pull.cannotCreate'),
            ),
        },
      ],
      [t],
    );

    return (
      <>
        <UniPullQueryModal<PullWorkOrderCandidate>
          title={t('app.kuaizhizao.warehouseOutbound.pull.fromWorkOrder')}
          pullQuery={pullFromWorkOrderQuery.pullQuery}
          open={pullFromWorkOrderQuery.open}
          onCancel={pullFromWorkOrderQuery.closeModal}
          onOk={pullFromWorkOrderQuery.handleConfirm}
          rowKey="id"
          columns={workOrderColumns}
          dataSource={pullFromWorkOrderQuery.dataSource}
          loading={pullFromWorkOrderQuery.loading}
          confirmLoading={pullFromWorkOrderQuery.confirmLoading}
          selectionType={pullFromWorkOrderQuery.selectionType}
          selectedRowKeys={pullFromWorkOrderQuery.selectedRowKeys}
          selectedRows={pullFromWorkOrderQuery.selectedRows}
          onSelectedRowKeysChange={pullFromWorkOrderQuery.handleSelectedRowKeysChange}
          isRowDisabled={pullFromWorkOrderQuery.isRowDisabled}
          searchDraft={pullFromWorkOrderQuery.searchDraft}
          onSearchDraftChange={pullFromWorkOrderQuery.setSearchDraft}
          onSearchApply={pullFromWorkOrderQuery.handleSearchApply}
          onSearchClear={pullFromWorkOrderQuery.handleSearchClear}
          appliedKeyword={pullFromWorkOrderQuery.appliedKeyword}
          searchPlaceholder={t('app.kuaizhizao.warehouseOutbound.pull.wo.searchPlaceholder')}
          filterExtra={(
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder={t('app.kuaizhizao.warehouseOutbound.pull.wo.sourceDocPlaceholder')}
              style={{ width: 220, flexShrink: 0 }}
              value={pullSourceWorkOrderId}
              options={pullSourceWorkOrderOptions}
              onChange={(value) => {
                const nextId = Number(value);
                const next = Number.isFinite(nextId) && nextId > 0 ? nextId : undefined;
                pullSourceWorkOrderIdRef.current = next;
                setPullSourceWorkOrderId(next);
                pullFromWorkOrderQuery.handleSearchApply(
                  pullFromWorkOrderQuery.appliedKeyword,
                );
              }}
            />
          )}
          getRowLabel={(row) => [row.work_order_code, row.material_code].filter(Boolean).join(' ')}
          page={pullFromWorkOrderQuery.page}
          pageSize={pullFromWorkOrderQuery.pageSize}
          total={pullFromWorkOrderQuery.total}
          onPageChange={pullFromWorkOrderQuery.handlePageChange}
          scopeOptions={pullFromWorkOrderQuery.scopeOptions}
          scope={pullFromWorkOrderQuery.scope}
          onScopeChange={pullFromWorkOrderQuery.handleScopeChange}
          okText={t('app.kuaizhizao.warehouseOutbound.pull.wo.ok')}
          footerHint={t('app.kuaizhizao.warehouseOutbound.pull.wo.batchHint')}
        />

        <UniPullQueryModal<PullSalesOrderCandidate>
          title={pullFromSalesOrderAction.label}
          pullQuery={pullFromSalesOrderQuery.pullQuery}
          open={pullFromSalesOrderQuery.open}
          onCancel={pullFromSalesOrderQuery.closeModal}
          onOk={pullFromSalesOrderQuery.handleConfirm}
          rowKey="id"
          columns={salesOrderColumns}
          dataSource={pullFromSalesOrderQuery.dataSource}
          loading={pullFromSalesOrderQuery.loading}
          confirmLoading={pullFromSalesOrderQuery.confirmLoading}
          selectionType={pullFromSalesOrderQuery.selectionType}
          selectedRowKeys={pullFromSalesOrderQuery.selectedRowKeys}
          selectedRows={pullFromSalesOrderQuery.selectedRows}
          onSelectedRowKeysChange={pullFromSalesOrderQuery.handleSelectedRowKeysChange}
          isRowDisabled={pullFromSalesOrderQuery.isRowDisabled}
          searchDraft={pullFromSalesOrderQuery.searchDraft}
          onSearchDraftChange={pullFromSalesOrderQuery.setSearchDraft}
          onSearchApply={pullFromSalesOrderQuery.handleSearchApply}
          onSearchClear={pullFromSalesOrderQuery.handleSearchClear}
          appliedKeyword={pullFromSalesOrderQuery.appliedKeyword}
          searchPlaceholder={t('app.kuaizhizao.warehouseOutbound.pull.searchSalesOrder')}
          filterExtra={(
            <>
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                placeholder={t('app.kuaizhizao.warehouseOutbound.pull.so.sourceDocPlaceholder')}
                style={{ width: 220, flexShrink: 0 }}
                value={pullSourceSalesOrderId}
                options={pullSourceSalesOrderOptions}
                onChange={(value) => {
                  const nextId = Number(value);
                  const next = Number.isFinite(nextId) && nextId > 0 ? nextId : undefined;
                  pullSourceSalesOrderIdRef.current = next;
                  setPullSourceSalesOrderId(next);
                  pullFromSalesOrderQuery.handleSearchApply(
                    pullFromSalesOrderQuery.appliedKeyword,
                  );
                }}
              />
            </>
          )}
          getRowLabel={(row) => [row.order_code, row.material_code].filter(Boolean).join(' ')}
          page={pullFromSalesOrderQuery.page}
          pageSize={pullFromSalesOrderQuery.pageSize}
          total={pullFromSalesOrderQuery.total}
          onPageChange={pullFromSalesOrderQuery.handlePageChange}
          scopeOptions={pullFromSalesOrderQuery.scopeOptions}
          scope={pullFromSalesOrderQuery.scope}
          onScopeChange={pullFromSalesOrderQuery.handleScopeChange}
          okText={t('app.kuaizhizao.warehouseOutbound.pull.so.ok')}
        />

        <UniPullQueryModal<PullShipmentNoticeCandidate>
          title={pullFromShipmentNoticeAction.label}
          pullQuery={pullFromShipmentNoticeQuery.pullQuery}
          open={pullFromShipmentNoticeQuery.open}
          onCancel={pullFromShipmentNoticeQuery.closeModal}
          onOk={pullFromShipmentNoticeQuery.handleConfirm}
          rowKey="id"
          columns={shipmentNoticeColumns}
          dataSource={pullFromShipmentNoticeQuery.dataSource}
          loading={pullFromShipmentNoticeQuery.loading}
          confirmLoading={pullFromShipmentNoticeQuery.confirmLoading}
          selectionType={pullFromShipmentNoticeQuery.selectionType}
          selectedRowKeys={pullFromShipmentNoticeQuery.selectedRowKeys}
          selectedRows={pullFromShipmentNoticeQuery.selectedRows}
          onSelectedRowKeysChange={pullFromShipmentNoticeQuery.handleSelectedRowKeysChange}
          isRowDisabled={pullFromShipmentNoticeQuery.isRowDisabled}
          searchDraft={pullFromShipmentNoticeQuery.searchDraft}
          onSearchDraftChange={pullFromShipmentNoticeQuery.setSearchDraft}
          onSearchApply={pullFromShipmentNoticeQuery.handleSearchApply}
          onSearchClear={pullFromShipmentNoticeQuery.handleSearchClear}
          appliedKeyword={pullFromShipmentNoticeQuery.appliedKeyword}
          searchPlaceholder={t('app.kuaizhizao.warehouseOutbound.pull.searchShipmentNotice')}
          filterExtra={(
            <>
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                placeholder={t('app.kuaizhizao.warehouseOutbound.pull.sn.sourceDocPlaceholder')}
                style={{ width: 220, flexShrink: 0 }}
                value={pullSourceNoticeId}
                options={pullSourceNoticeOptions}
                onChange={(value) => {
                  const nextId = Number(value);
                  const next = Number.isFinite(nextId) && nextId > 0 ? nextId : undefined;
                  pullSourceNoticeIdRef.current = next;
                  setPullSourceNoticeId(next);
                  pullFromShipmentNoticeQuery.handleSearchApply(
                    pullFromShipmentNoticeQuery.appliedKeyword,
                  );
                }}
              />
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                placeholder={t('app.kuaizhizao.warehouseOutbound.pull.batchWarehousePlaceholder')}
                style={{ width: 180, flexShrink: 0 }}
                value={shipmentNoticePullBatchWarehouseId}
                options={salesDeliveryPullWarehouseOptions}
                onChange={(value) => {
                  if (value == null) {
                    setShipmentNoticePullBatchWarehouseId(undefined);
                    return;
                  }
                  const nextId = Number(value);
                  if (Number.isFinite(nextId) && nextId > 0) {
                    applyShipmentNoticePullBatchWarehouse(nextId);
                  }
                }}
              />
            </>
          )}
          getRowLabel={(row) => [row.notice_code, row.material_code].filter(Boolean).join(' ')}
          page={pullFromShipmentNoticeQuery.page}
          pageSize={pullFromShipmentNoticeQuery.pageSize}
          total={pullFromShipmentNoticeQuery.total}
          onPageChange={pullFromShipmentNoticeQuery.handlePageChange}
          scopeOptions={pullFromShipmentNoticeQuery.scopeOptions}
          scope={pullFromShipmentNoticeQuery.scope}
          onScopeChange={pullFromShipmentNoticeQuery.handleScopeChange}
          okText={t('app.kuaizhizao.warehouseOutbound.pull.sn.ok')}
          footerHint={t('app.kuaizhizao.warehouseOutbound.pull.warehouseHint')}
        />

        <UniPullQueryModal<PullOutsourceWoCandidate>
          title={pullFromOutsourceWorkOrderAction.label}
          pullQuery={pullFromOutsourceWorkOrderQuery.pullQuery}
          open={pullFromOutsourceWorkOrderQuery.open}
          onCancel={pullFromOutsourceWorkOrderQuery.closeModal}
          onOk={pullFromOutsourceWorkOrderQuery.handleConfirm}
          rowKey="id"
          columns={outsourceColumns}
          dataSource={pullFromOutsourceWorkOrderQuery.dataSource}
          loading={pullFromOutsourceWorkOrderQuery.loading}
          confirmLoading={pullFromOutsourceWorkOrderQuery.confirmLoading}
          selectionType={pullFromOutsourceWorkOrderQuery.selectionType}
          selectedRowKeys={pullFromOutsourceWorkOrderQuery.selectedRowKeys}
          selectedRows={pullFromOutsourceWorkOrderQuery.selectedRows}
          onSelectedRowKeysChange={pullFromOutsourceWorkOrderQuery.handleSelectedRowKeysChange}
          isRowDisabled={pullFromOutsourceWorkOrderQuery.isRowDisabled}
          searchDraft={pullFromOutsourceWorkOrderQuery.searchDraft}
          onSearchDraftChange={pullFromOutsourceWorkOrderQuery.setSearchDraft}
          onSearchApply={pullFromOutsourceWorkOrderQuery.handleSearchApply}
          onSearchClear={pullFromOutsourceWorkOrderQuery.handleSearchClear}
          appliedKeyword={pullFromOutsourceWorkOrderQuery.appliedKeyword}
          searchPlaceholder={t('app.kuaizhizao.warehouseOutbound.pull.os.searchPlaceholder')}
          filterExtra={(
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder={t('app.kuaizhizao.warehouseOutbound.pull.os.sourceDocPlaceholder')}
              style={{ width: 220, flexShrink: 0 }}
              value={pullSourceOutsourceId}
              options={pullSourceOutsourceOptions}
              onChange={(value) => {
                const nextId = Number(value);
                const next = Number.isFinite(nextId) && nextId > 0 ? nextId : undefined;
                pullSourceOutsourceIdRef.current = next;
                setPullSourceOutsourceId(next);
                pullFromOutsourceWorkOrderQuery.handleSearchApply(
                  pullFromOutsourceWorkOrderQuery.appliedKeyword,
                );
              }}
            />
          )}
          getRowLabel={(row) => [row.outsource_work_order_code, row.material_code].filter(Boolean).join(' ')}
          page={pullFromOutsourceWorkOrderQuery.page}
          pageSize={pullFromOutsourceWorkOrderQuery.pageSize}
          total={pullFromOutsourceWorkOrderQuery.total}
          onPageChange={pullFromOutsourceWorkOrderQuery.handlePageChange}
          scopeOptions={pullFromOutsourceWorkOrderQuery.scopeOptions}
          scope={pullFromOutsourceWorkOrderQuery.scope}
          onScopeChange={pullFromOutsourceWorkOrderQuery.handleScopeChange}
          okText={t('app.kuaizhizao.warehouseOutbound.pull.os.ok')}
        />

        <UniPullQueryModal<PullDeliveryNoticeCandidate>
          title={pullFromSalesDeliveryAction.label}
          pullQuery={pullFromSalesDeliveryQuery.pullQuery}
          open={pullFromSalesDeliveryQuery.open}
          onCancel={pullFromSalesDeliveryQuery.closeModal}
          onOk={pullFromSalesDeliveryQuery.handleConfirm}
          rowKey="id"
          columns={salesDeliveryColumns}
          dataSource={pullFromSalesDeliveryQuery.dataSource}
          loading={pullFromSalesDeliveryQuery.loading}
          confirmLoading={pullFromSalesDeliveryQuery.confirmLoading}
          selectionType={pullFromSalesDeliveryQuery.selectionType}
          selectedRowKeys={pullFromSalesDeliveryQuery.selectedRowKeys}
          selectedRows={pullFromSalesDeliveryQuery.selectedRows}
          onSelectedRowKeysChange={pullFromSalesDeliveryQuery.handleSelectedRowKeysChange}
          isRowDisabled={pullFromSalesDeliveryQuery.isRowDisabled}
          searchDraft={pullFromSalesDeliveryQuery.searchDraft}
          onSearchDraftChange={pullFromSalesDeliveryQuery.setSearchDraft}
          onSearchApply={pullFromSalesDeliveryQuery.handleSearchApply}
          onSearchClear={pullFromSalesDeliveryQuery.handleSearchClear}
          appliedKeyword={pullFromSalesDeliveryQuery.appliedKeyword}
          searchPlaceholder={t('app.kuaizhizao.deliveryNote.pull.searchPlaceholder')}
          filterExtra={(
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder={t('app.kuaizhizao.deliveryNote.pull.sourceDocPlaceholder')}
              style={{ width: 220, flexShrink: 0 }}
              value={pullSourceDeliveryId}
              options={pullSourceDeliveryOptions}
              onChange={(value) => {
                const nextId = Number(value);
                const next = Number.isFinite(nextId) && nextId > 0 ? nextId : undefined;
                pullSourceDeliveryIdRef.current = next;
                setPullSourceDeliveryId(next);
                pullFromSalesDeliveryQuery.handleSearchApply(
                  pullFromSalesDeliveryQuery.appliedKeyword,
                );
              }}
            />
          )}
          getRowLabel={(row) => [row.delivery_code, row.material_code].filter(Boolean).join(' ')}
          page={pullFromSalesDeliveryQuery.page}
          pageSize={pullFromSalesDeliveryQuery.pageSize}
          total={pullFromSalesDeliveryQuery.total}
          onPageChange={pullFromSalesDeliveryQuery.handlePageChange}
          scopeOptions={pullFromSalesDeliveryQuery.scopeOptions}
          scope={pullFromSalesDeliveryQuery.scope}
          onScopeChange={pullFromSalesDeliveryQuery.handleScopeChange}
          okText={t('app.kuaizhizao.deliveryNote.pull.ok')}
        />
      </>
    );
  },
);

OutboundQuickPullModals.displayName = 'OutboundQuickPullModals';

export default OutboundQuickPullModals;
