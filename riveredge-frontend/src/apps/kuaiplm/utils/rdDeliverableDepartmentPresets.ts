/** 交付物部门视角：类型子集 + 列表 types 查询（与 rd-deliverables ?preset= 对齐） */

export type RdDeliverableDeptPreset = 'all' | 'electronics' | 'structure' | 'project' | 'customer';

const CUSTOMER_DOC_TYPES = ['customer_spec', 'customer_approval'] as const;

const ELECTRONICS_TYPES = [
  'part_spec',
  'software_spec',
  'schematic',
  'layout',
  'gerber',
  'panelization',
  'test_report_part',
  'test_report_complete',
  'drawing_silkscreen',
  'drawing_assembly',
  'drawing_packaging',
  'drawing_pcb_assembly',
] as const;

const STRUCTURE_TYPES = [
  'drawing_3d',
  'drawing_cad',
  'drawing_pdf',
  'mold_dfm',
  'mold_drawing',
  'mold_acceptance',
  'reliability_report',
  'mold_repair',
] as const;

const PROJECT_DOC_TYPES = [
  'customer_spec',
  'customer_approval',
  'document',
  'quality',
  'sop',
  'bom',
  'drawing',
  'process',
] as const;

export function parseRdDeliverableDeptPreset(raw: string | null | undefined): RdDeliverableDeptPreset {
  const v = String(raw ?? '').trim().toLowerCase();
  if (v === 'electronics' || v === 'structure' || v === 'project' || v === 'customer') return v;
  return 'all';
}

export function rdDeliverableTypesForPreset(preset: RdDeliverableDeptPreset): string[] | undefined {
  switch (preset) {
    case 'electronics':
      return [...ELECTRONICS_TYPES];
    case 'structure':
      return [...STRUCTURE_TYPES];
    case 'project':
      return [...PROJECT_DOC_TYPES];
    case 'customer':
      return [...CUSTOMER_DOC_TYPES];
    default:
      return undefined;
  }
}

export function rdDeliverableTypesQueryParam(types: string[] | undefined): string | undefined {
  if (!types?.length) return undefined;
  return types.join(',');
}
