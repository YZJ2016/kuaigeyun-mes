/** 工装/模具保养与维修单明细：API 使用 is_done，与完修弹窗共用 */

export interface MaintenanceLineView {
  id?: number;
  line_no?: number;
  item_id?: number;
  item_code?: string;
  item_name?: string;
  requirement?: string;
  is_done?: boolean;
  remark?: string;
}

export function mapMaintenanceLineFromApi(raw: Record<string, unknown>): MaintenanceLineView {
  return {
    id: raw.id != null ? Number(raw.id) : undefined,
    line_no: raw.line_no != null ? Number(raw.line_no) : undefined,
    item_id: raw.item_id != null ? Number(raw.item_id) : undefined,
    item_code: raw.item_code != null ? String(raw.item_code) : undefined,
    item_name: raw.item_name != null ? String(raw.item_name) : undefined,
    requirement: raw.requirement != null ? String(raw.requirement) : undefined,
    is_done: Boolean(raw.is_done),
    remark: raw.remark != null ? String(raw.remark) : undefined,
  };
}

export function mapMaintenanceLinesFromApi(
  lines: unknown[] | null | undefined,
): MaintenanceLineView[] {
  if (!lines?.length) return [];
  return lines.map((row) => mapMaintenanceLineFromApi(row as Record<string, unknown>));
}

export function toMaintenanceLinePayload(line: MaintenanceLineView) {
  return {
    line_no: line.line_no ?? 1,
    item_id: line.item_id,
    item_code: line.item_code,
    item_name: line.item_name,
    requirement: line.requirement,
    is_done: line.is_done ?? false,
    remark: line.remark,
  };
}
