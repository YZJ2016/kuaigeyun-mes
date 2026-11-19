import { warehouseApi } from '../../../services/warehouse-execution';
import { readExternalWithdrawMessage } from '../shared/externalWithdrawMessage';
import type { OutboundHubOrder } from './outboundHubTypes';

export async function withdrawOutboundDocument(
  record: OutboundHubOrder,
): Promise<string | undefined> {
  const id = String(record.id);
  switch (record.outbound_type) {
    case 'production_picking': {
      const res = await warehouseApi.productionPicking.withdraw(id);
      return readExternalWithdrawMessage(res);
    }
    case 'sales_delivery': {
      const res = await warehouseApi.salesDelivery.withdraw(id);
      return readExternalWithdrawMessage(res);
    }
    case 'other_outbound': {
      const res = await warehouseApi.otherOutbound.withdraw(id);
      return readExternalWithdrawMessage(res);
    }
    case 'material_borrow':
      await warehouseApi.materialBorrow.withdraw(id);
      return undefined;
    case 'purchase_return':
      await warehouseApi.purchaseReturn.withdraw(id);
      return undefined;
    default:
      throw new Error('该类型不支持撤回');
  }
}

export async function deleteOutboundDocument(record: OutboundHubOrder): Promise<void> {
  const id = String(record.id);
  switch (record.outbound_type) {
    case 'production_picking':
      await warehouseApi.productionPicking.delete(id);
      return;
    case 'sales_delivery':
      await warehouseApi.salesDelivery.delete(id);
      return;
    case 'other_outbound':
      await warehouseApi.otherOutbound.delete(id);
      return;
    case 'material_borrow':
      await warehouseApi.materialBorrow.delete(id);
      return;
    case 'purchase_return':
      await warehouseApi.purchaseReturn.delete(id);
      return;
    default:
      throw new Error('该类型不支持删除');
  }
}
