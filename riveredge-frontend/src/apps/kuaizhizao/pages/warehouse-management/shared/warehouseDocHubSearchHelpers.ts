import { warehouseApi } from '../../../../master-data/services/warehouse';
import { materialApi } from '../../../../master-data/services/material';
import { supplierApi, unwrapSupplyPagedList } from '../../../../master-data/services/supply-chain';

export async function requestActiveWarehouseSelectOptions(params?: { keyWords?: string }) {
  const res = await warehouseApi.list({
    ...(params?.keyWords?.trim() ? { keyword: params.keyWords.trim() } : {}),
    is_active: true,
    limit: 200,
  });
  return (res.items || []).map((w) => ({ label: w.name, value: w.id }));
}

export async function requestActiveSupplierNameSelectOptions(params?: { keyWords?: string }) {
  const res = await supplierApi.list({
    ...(params?.keyWords?.trim() ? { keyword: params.keyWords.trim() } : {}),
    isActive: true,
    limit: 200,
  });
  return unwrapSupplyPagedList(res).map((s) => ({ label: s.name, value: s.name }));
}

export async function requestActiveMaterialSelectOptions(params?: { keyWords?: string }) {
  const res = await materialApi.list({
    ...(params?.keyWords?.trim() ? { keyword: params.keyWords.trim() } : {}),
    isActive: true,
    limit: 50,
  });
  return (res.items || []).map((m) => ({
    label: `${m.code} ${m.name}`.trim(),
    value: m.id,
  }));
}