/** 采购申请表单字段显示偏好（用户级，存 user preference） */

export const PURCHASE_REQUISITION_FORM_PREF_DOC = 'kuaizhizao-purchase-requisition';

export type PurchaseRequisitionFormFieldVisibility = {
  requisition_name: boolean;
};

const DEFAULT_VISIBILITY: PurchaseRequisitionFormFieldVisibility = {
  /** 默认不显示；用户在「字段设置」勾选后才出现 */
  requisition_name: false,
};

export function resolvePurchaseRequisitionFormFieldVisibility(
  preferences: Record<string, unknown> | null | undefined,
): PurchaseRequisitionFormFieldVisibility {
  const doc = preferences?.ui as Record<string, unknown> | undefined;
  const forms = doc?.documentForms as Record<string, unknown> | undefined;
  const pr = forms?.[PURCHASE_REQUISITION_FORM_PREF_DOC] as Record<string, unknown> | undefined;
  const nameNode = pr?.requisition_name as { visible?: boolean } | undefined;
  if (nameNode && typeof nameNode.visible === 'boolean') {
    return { requisition_name: nameNode.visible };
  }
  return DEFAULT_VISIBILITY;
}

export function buildPurchaseRequisitionFormFieldVisibilityPatch(
  visibility: PurchaseRequisitionFormFieldVisibility,
): Record<string, unknown> {
  return {
    ui: {
      documentForms: {
        [PURCHASE_REQUISITION_FORM_PREF_DOC]: {
          requisition_name: { visible: visibility.requisition_name },
        },
      },
    },
  };
}
