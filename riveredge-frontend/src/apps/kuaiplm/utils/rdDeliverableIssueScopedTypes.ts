/** 须批准后再「下发」、使用方按 grant 可见（L53/L57，与后端 rd_deliverable_issue 对齐） */
export const RD_DELIVERABLE_TYPES_ISSUE_SCOPED = new Set([
  'drawing_silkscreen',
  'drawing_assembly',
  'drawing_packaging',
  'drawing_pcb_assembly',
  'customer_spec',
  'customer_approval',
]);

export function isRdDeliverableIssueScopedType(type?: string | null): boolean {
  return RD_DELIVERABLE_TYPES_ISSUE_SCOPED.has(String(type || '').trim().toLowerCase());
}
