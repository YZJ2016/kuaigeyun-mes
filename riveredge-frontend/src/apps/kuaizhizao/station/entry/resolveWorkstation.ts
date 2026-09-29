/**
 * 用已有工位主数据列表把 URL 上的 workstationId 解析成入口绑定信息。
 * 列表接口没有按数字 ID 过滤的参数，因此分页查找。
 */
import {
  factoryListItems,
  productionLineApi,
  workstationApi,
} from '../../../master-data/services/factory';
import type {
  FactoryPaginatedList,
  ProductionLine,
  Workstation,
} from '../../../master-data/types/factory';
import type { StationInfo } from '../../components/StationBinder';

const PAGE_SIZE = 100;
const MAX_PAGES = 20;

async function findById<T extends { id: number }>(
  load: (skip: number) => Promise<FactoryPaginatedList<T>>,
  id: number,
): Promise<T | null> {
  let seen = 0;
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const res = await load(page * PAGE_SIZE);
    const items = factoryListItems(res);
    const hit = items.find((item) => Number(item.id) === id);
    if (hit) return hit;
    seen += items.length;
    const total = Number(res.total ?? items.length);
    if (items.length === 0 || seen >= total) return null;
  }
  return null;
}

function optionalText(row: object, camel: string, snake: string): string | undefined {
  const rec = row as Record<string, unknown>;
  const raw = rec[camel] ?? rec[snake];
  if (raw == null) return undefined;
  const text = String(raw).trim();
  return text || undefined;
}

function optionalId(row: object, camel: string, snake: string): number | undefined {
  const rec = row as Record<string, unknown>;
  const raw = rec[camel] ?? rec[snake];
  const id = Number(raw);
  return Number.isFinite(id) ? id : undefined;
}

export async function resolveWorkstation(workstationId: number): Promise<StationInfo | null> {
  const station = await findById<Workstation>(
    (skip) => workstationApi.list({ skip, limit: PAGE_SIZE }),
    workstationId,
  );
  if (!station) return null;

  const line = station.productionLineId
    ? await findById<ProductionLine>(
        (skip) => productionLineApi.list({ skip, limit: PAGE_SIZE }),
        station.productionLineId,
      )
    : null;

  return {
    workshopId: line?.workshopId ?? 0,
    workshopName: line?.workshopName || '',
    lineId: station.productionLineId,
    lineName: station.productionLineName || line?.name,
    stationId: station.id,
    stationName: station.name,
    stationCode: station.code,
    workCenterId: optionalId(station, 'workCenterId', 'work_center_id'),
    workCenterName: optionalText(station, 'workCenterName', 'work_center_name'),
  };
}
