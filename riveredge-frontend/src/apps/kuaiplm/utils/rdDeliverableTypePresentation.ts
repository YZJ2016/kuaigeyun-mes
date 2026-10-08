import type { TFunction } from 'i18next';

/** 交付物类型码 → i18n key（含阶段门模板 document/quality/sop 等） */
const RD_DELIVERABLE_TYPE_I18N: Record<string, string> = {
  part_spec: 'app.kuaiplm.rdProjects.detail.deliverable.type.partSpec',
  component_spec: 'app.kuaiplm.rdProjects.detail.deliverable.type.partSpec',
  software_spec: 'app.kuaiplm.rdProjects.detail.deliverable.type.softwareSpec',
  sw_spec: 'app.kuaiplm.rdProjects.detail.deliverable.type.softwareSpec',
  schematic: 'app.kuaiplm.rdProjects.detail.deliverable.type.schematic',
  layout: 'app.kuaiplm.rdProjects.detail.deliverable.type.layout',
  gerber: 'app.kuaiplm.rdProjects.detail.deliverable.type.gerber',
  panelization: 'app.kuaiplm.rdProjects.detail.deliverable.type.panelization',
  panel: 'app.kuaiplm.rdProjects.detail.deliverable.type.panelization',
  schematic_gerber: 'app.kuaiplm.rdProjects.detail.deliverable.type.schematicGerber',
  test_report_part: 'app.kuaiplm.rdProjects.detail.deliverable.type.testReportPart',
  test_report_complete: 'app.kuaiplm.rdProjects.detail.deliverable.type.testReportComplete',
  test_report: 'app.kuaiplm.rdProjects.detail.deliverable.type.testReportPart',
  test: 'app.kuaiplm.rdProjects.detail.deliverable.type.testReportPart',
  drawing_3d: 'app.kuaiplm.rdProjects.detail.deliverable.type.drawing3d',
  drawing_cad: 'app.kuaiplm.rdProjects.detail.deliverable.type.drawingCad',
  drawing_pdf: 'app.kuaiplm.rdProjects.detail.deliverable.type.drawingPdf',
  mold_dfm: 'app.kuaiplm.rdProjects.detail.deliverable.type.moldDfm',
  mold_drawing: 'app.kuaiplm.rdProjects.detail.deliverable.type.moldDrawing',
  mold_acceptance: 'app.kuaiplm.rdProjects.detail.deliverable.type.moldAcceptance',
  reliability_report: 'app.kuaiplm.rdProjects.detail.deliverable.type.reliabilityReport',
  mold_repair: 'app.kuaiplm.rdProjects.detail.deliverable.type.moldRepair',
  drawing_silkscreen: 'app.kuaiplm.rdProjects.detail.deliverable.type.drawingSilkscreen',
  drawing_assembly: 'app.kuaiplm.rdProjects.detail.deliverable.type.drawingAssembly',
  drawing_packaging: 'app.kuaiplm.rdProjects.detail.deliverable.type.drawingPackaging',
  drawing_pcb_assembly: 'app.kuaiplm.rdProjects.detail.deliverable.type.drawingPcbAssembly',
  customer_spec: 'app.kuaiplm.rdProjects.detail.deliverable.type.customerSpec',
  customer_approval: 'app.kuaiplm.rdProjects.detail.deliverable.type.customerApproval',
  document: 'app.kuaiplm.rdProjects.detail.deliverable.type.document',
  quality: 'app.kuaiplm.rdProjects.detail.deliverable.type.quality',
  sop: 'app.kuaiplm.rdProjects.detail.deliverable.type.sop',
  bom: 'app.kuaiplm.rdProjects.detail.deliverable.type.bom',
  drawing: 'app.kuaiplm.rdProjects.detail.deliverable.type.drawing',
  process: 'app.kuaiplm.rdProjects.detail.deliverable.type.process',
};

/** 新建/编辑下拉：canonical 类型码顺序 */
const RD_DELIVERABLE_TYPE_SELECT_VALUES = [
  'part_spec',
  'software_spec',
  'schematic',
  'layout',
  'gerber',
  'panelization',
  'test_report_part',
  'test_report_complete',
  'drawing_3d',
  'drawing_cad',
  'drawing_pdf',
  'mold_dfm',
  'mold_drawing',
  'mold_acceptance',
  'reliability_report',
  'mold_repair',
  'drawing_silkscreen',
  'drawing_assembly',
  'drawing_packaging',
  'drawing_pcb_assembly',
  'customer_spec',
  'customer_approval',
  'document',
  'quality',
  'sop',
  'bom',
  'drawing',
  'process',
  'test',
] as const;

export function resolveRdDeliverableTypeLabel(t: TFunction, type?: string | null): string {
  const code = String(type ?? '').trim().toLowerCase();
  if (!code) return '';
  const key = RD_DELIVERABLE_TYPE_I18N[code];
  return key ? t(key) : code;
}

export function buildRdDeliverableTypeSelectOptions(t: TFunction) {
  return RD_DELIVERABLE_TYPE_SELECT_VALUES.map((value) => ({
    value,
    label: resolveRdDeliverableTypeLabel(t, value),
  }));
}

/** 类型列定宽：须完整显示「材料部品规格书」「测试报告（整机）」等（勿用 markerBadge 80px 窄列） */
export const RD_DELIVERABLE_TYPE_COLUMN_WIDTH = 200;
