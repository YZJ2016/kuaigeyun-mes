import { warehouseApi } from '../../../services/production';
import type { OutboundHubOrder } from '../outbound/outboundHubTypes';

/** 出库 Hub 各类型详情（导出、确认等共用） */
export async function fetchOutboundHubDetail(
  record: OutboundHubOrder,
): Promise<Record<string, unknown> | null> {
  const id = String(record.id);
  if (!record.outbound_type || !record.id) return null;
  switch (record.outbound_type) {
    case 'production_picking':
      return (await warehouseApi.productionPicking.get(id)) as Record<string, unknown>;
    case 'sales_delivery':
      return (await warehouseApi.salesDelivery.get(id)) as Record<string, unknown>;
    case 'other_outbound':
      return (await warehouseApi.otherOutbound.get(id)) as Record<string, unknown>;
    case 'material_borrow':
      return (await warehouseApi.materialBorrow.get(id)) as Record<string, unknown>;
    case 'purchase_return':
      return (await warehouseApi.purchaseReturn.get(id)) as Record<string, unknown>;
    case 'outsource_issue':
      return null;
    default:
      return null;
  }
}
