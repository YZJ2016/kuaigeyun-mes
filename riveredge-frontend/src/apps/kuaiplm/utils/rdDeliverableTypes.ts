export const PART_SPEC_TYPES = new Set(['part_spec', 'component_spec']);
export const TEST_REPORT_PART_TYPES = new Set(['test_report_part', 'test_report', 'test']);
export const TEST_REPORT_COMPLETE_TYPES = new Set(['test_report_complete']);
export const SOFTWARE_SPEC_TYPES = new Set(['software_spec', 'sw_spec']);
export const SCHEMATIC_GERBER_TYPES = new Set([
  'schematic',
  'gerber',
  'schematic_gerber',
  'layout',
  'panelization',
  'panel',
]);

export function isPartSpecType(type?: string | null): boolean {
  return PART_SPEC_TYPES.has(String(type || '').trim().toLowerCase());
}

export function isTestReportPartType(type?: string | null): boolean {
  return TEST_REPORT_PART_TYPES.has(String(type || '').trim().toLowerCase());
}

export function isTestReportCompleteType(type?: string | null): boolean {
  return TEST_REPORT_COMPLETE_TYPES.has(String(type || '').trim().toLowerCase());
}

export function isSoftwareSpecType(type?: string | null): boolean {
  return SOFTWARE_SPEC_TYPES.has(String(type || '').trim().toLowerCase());
}

export function isSchematicGerberType(type?: string | null): boolean {
  return SCHEMATIC_GERBER_TYPES.has(String(type || '').trim().toLowerCase());
}

export function needsMaterialCode(type?: string | null): boolean {
  return (
    isPartSpecType(type) ||
    isSchematicGerberType(type) ||
    isTestReportPartType(type) ||
    isTestReportCompleteType(type)
  );
}

export function needsProjectCodeWithoutProject(
  type?: string | null,
  projectId?: number | null,
): boolean {
  if (projectId) return false;
  return isSoftwareSpecType(type);
}
