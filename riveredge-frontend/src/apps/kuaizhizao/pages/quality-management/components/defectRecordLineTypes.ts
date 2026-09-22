export type InspectionDefectDispositionSource = 'incoming' | 'process' | 'finished';

export type InspectionDefectLineDraft = {
  key: string;
  defect_quantity: number;
  defect_type: string;
  defect_reason: string;
  disposition: string;
  remarks?: string;
  quarantine_warehouse_id?: number;
  stock_warehouse_id?: number;
  downgrade_material_id?: number;
  downgrade_warehouse_id?: number;
};

export type InspectionDefectLinePayload = {
  defect_quantity: number;
  defect_type: string;
  defect_reason: string;
  disposition: string;
  remarks?: string;
  quarantine_warehouse_id?: number;
  stock_warehouse_id?: number;
  downgrade_material_id?: number;
  downgrade_warehouse_id?: number;
};

export function createEmptyDefectLine(
  quantity = 0,
  defaultDisposition = 'quarantine',
): InspectionDefectLineDraft {
  return {
    key: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    defect_quantity: quantity,
    defect_type: 'other',
    defect_reason: '',
    disposition: defaultDisposition,
    remarks: '',
  };
}

export function sumDefectLineQuantities(lines: InspectionDefectLineDraft[]): number {
  return lines.reduce((sum, line) => sum + Number(line.defect_quantity || 0), 0);
}

export function toDefectLinePayload(line: InspectionDefectLineDraft): InspectionDefectLinePayload {
  return {
    defect_quantity: Number(line.defect_quantity || 0),
    defect_type: line.defect_type,
    defect_reason: String(line.defect_reason || '').trim(),
    disposition: line.disposition,
    remarks: line.remarks?.trim() || undefined,
    quarantine_warehouse_id: line.quarantine_warehouse_id,
    stock_warehouse_id: line.stock_warehouse_id,
    downgrade_material_id: line.downgrade_material_id,
    downgrade_warehouse_id: line.downgrade_warehouse_id,
  };
}

export function lineNeedsExpandFields(disposition?: string): boolean {
  return ['quarantine', 'scrap', 'accept', 'downgrade', 'other'].includes(String(disposition || ''));
}
