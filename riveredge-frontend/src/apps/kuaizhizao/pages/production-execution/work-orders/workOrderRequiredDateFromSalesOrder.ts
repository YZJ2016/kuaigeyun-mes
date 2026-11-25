import dayjs, { type Dayjs } from 'dayjs';

export type SalesOrderDeliverySource = {
  delivery_date?: string | null;
  items?: Array<{
    id?: number;
    material_id?: number;
    delivery_date?: string | null;
  }>;
};

export function pickSalesOrderDeliveryDate(
  order: SalesOrderDeliverySource,
  match?: { salesOrderItemId?: number; productId?: number },
): string | undefined {
  const items = order.items ?? [];
  if (match?.salesOrderItemId != null && Number(match.salesOrderItemId) > 0) {
    const line = items.find((it) => Number(it.id) === Number(match.salesOrderItemId));
    const raw = line?.delivery_date ?? order.delivery_date;
    return normalizeDeliveryDateText(raw);
  }
  if (match?.productId != null && Number(match.productId) > 0) {
    const line = items.find((it) => Number(it.material_id) === Number(match.productId));
    const raw = line?.delivery_date ?? order.delivery_date;
    return normalizeDeliveryDateText(raw);
  }
  return normalizeDeliveryDateText(order.delivery_date);
}

function normalizeDeliveryDateText(raw?: string | null): string | undefined {
  const text = String(raw ?? '').trim();
  if (!text) return undefined;
  return text.slice(0, 10);
}

export function toWorkOrderRequiredDateDayjs(raw?: string | null): Dayjs | undefined {
  const text = normalizeDeliveryDateText(raw);
  if (!text) return undefined;
  const d = dayjs(text);
  return d.isValid() ? d : undefined;
}