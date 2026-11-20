import type { TFunction } from 'i18next';
import type { DataNode } from 'antd/es/tree';
import { QMS_DOC_TYPE_OPTIONS } from '../qms/qmsMeta';

export type SystemDocumentNavDimension = 'standard' | 'doc_type' | 'lifecycle';

export const SYSTEM_DOCUMENT_NAV_STORAGE_KEY = 'qms-system-docs-nav-v1';

export const SYSTEM_DOCUMENT_NAV_ALL_KEY = 'all';

export interface QmsStandardNavItem {
  id: number;
  code: string;
  name?: string;
}

export interface SystemDocumentListNavParams {
  zone?: 'formal' | 'pending' | 'all';
  review_due?: boolean;
  status?: string;
  status_in?: string;
  standard_id?: number;
  standard_id_null?: boolean;
  doc_type?: string;
}

export interface StoredSystemDocumentNav {
  dimension: SystemDocumentNavDimension;
  selectedKey: string;
}

const KEY_SEP = ':';

export function buildStandardTreeKey(part: string): string {
  return `standard${KEY_SEP}${part}`;
}

export function buildDocTypeTreeKey(part: string): string {
  return `doc_type${KEY_SEP}${part}`;
}

export function buildLifecycleTreeKey(part: string): string {
  return `lifecycle${KEY_SEP}${part}`;
}

export function defaultNavSelection(dimension: SystemDocumentNavDimension = 'standard'): StoredSystemDocumentNav {
  if (dimension === 'doc_type') {
    return { dimension, selectedKey: buildDocTypeTreeKey(SYSTEM_DOCUMENT_NAV_ALL_KEY) };
  }
  if (dimension === 'lifecycle') {
    return { dimension, selectedKey: buildLifecycleTreeKey('formal') };
  }
  return { dimension, selectedKey: buildStandardTreeKey(SYSTEM_DOCUMENT_NAV_ALL_KEY) };
}

export function loadStoredSystemDocumentNav(): StoredSystemDocumentNav {
  if (typeof window === 'undefined') return defaultNavSelection();
  try {
    const raw = window.localStorage.getItem(SYSTEM_DOCUMENT_NAV_STORAGE_KEY);
    if (!raw) return defaultNavSelection();
    const parsed = JSON.parse(raw) as StoredSystemDocumentNav;
    if (
      parsed?.dimension !== 'standard' &&
      parsed?.dimension !== 'doc_type' &&
      parsed?.dimension !== 'lifecycle'
    ) {
      return defaultNavSelection();
    }
    if (typeof parsed.selectedKey !== 'string' || !parsed.selectedKey.includes(KEY_SEP)) {
      return defaultNavSelection(parsed.dimension);
    }
    return parsed;
  } catch {
    return defaultNavSelection();
  }
}

export function saveStoredSystemDocumentNav(state: StoredSystemDocumentNav): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(SYSTEM_DOCUMENT_NAV_STORAGE_KEY, JSON.stringify(state));
}

export function navSelectionToListParams(
  dimension: SystemDocumentNavDimension,
  selectedKey: string,
): SystemDocumentListNavParams {
  const [, part] = selectedKey.split(KEY_SEP);
  if (dimension === 'standard') {
    if (part === SYSTEM_DOCUMENT_NAV_ALL_KEY) {
      return { zone: 'all' };
    }
    if (part === 'null') {
      return { zone: 'all', standard_id_null: true };
    }
    const id = Number(part);
    if (Number.isFinite(id)) {
      return { zone: 'all', standard_id: id };
    }
    return { zone: 'all' };
  }
  if (dimension === 'doc_type') {
    if (part === SYSTEM_DOCUMENT_NAV_ALL_KEY || !part) {
      return { zone: 'all' };
    }
    return { zone: 'all', doc_type: part };
  }
  switch (part) {
    case SYSTEM_DOCUMENT_NAV_ALL_KEY:
      return { zone: 'all' };
    case 'formal':
      return { zone: 'formal' };
    case 'review_due':
      return { zone: 'formal', review_due: true };
    case 'pending':
      return { zone: 'pending' };
    case 'pending_audit':
      return { zone: 'all', status: 'pending' };
    case 'draft_rejected':
      return { zone: 'all', status_in: 'draft,rejected' };
    case 'obsolete':
      return { zone: 'all', status: 'obsolete' };
    default:
      return { zone: 'formal' };
  }
}

export function navHidesStatusSearch(
  dimension: SystemDocumentNavDimension,
  selectedKey: string,
): boolean {
  if (dimension !== 'lifecycle') return false;
  const params = navSelectionToListParams(dimension, selectedKey);
  if (params.review_due) return true;
  if (params.zone === 'formal' && !params.status && !params.status_in) return true;
  if (params.zone === 'pending' && !params.status && !params.status_in) return true;
  if (params.status === 'obsolete') return true;
  if (params.status === 'pending') return true;
  if (params.status_in) return true;
  return false;
}

export function buildSystemDocumentNavTreeData(
  dimension: SystemDocumentNavDimension,
  t: TFunction,
  standards: QmsStandardNavItem[],
): DataNode[] {
  const allNode = (key: string, title: string): DataNode => ({
    key,
    title,
    isLeaf: true,
  });

  if (dimension === 'standard') {
    return [
      allNode(buildStandardTreeKey(SYSTEM_DOCUMENT_NAV_ALL_KEY), t('app.kuaizhizao.quality.qms.nav.all')),
      allNode(buildStandardTreeKey('null'), t('app.kuaizhizao.quality.qms.nav.unlinkedStandard')),
      ...standards.map((s) =>
        allNode(
          buildStandardTreeKey(String(s.id)),
          s.name ? `${s.code} ${s.name}` : s.code,
        ),
      ),
    ];
  }

  if (dimension === 'doc_type') {
    return [
      allNode(buildDocTypeTreeKey(SYSTEM_DOCUMENT_NAV_ALL_KEY), t('app.kuaizhizao.quality.qms.nav.all')),
      ...QMS_DOC_TYPE_OPTIONS.map((o) =>
        allNode(buildDocTypeTreeKey(o.value), t(o.labelKey)),
      ),
    ];
  }

  return [
    allNode(buildLifecycleTreeKey(SYSTEM_DOCUMENT_NAV_ALL_KEY), t('app.kuaizhizao.quality.qms.nav.all')),
    allNode(buildLifecycleTreeKey('formal'), t('app.kuaizhizao.quality.qms.zone.formal')),
    allNode(buildLifecycleTreeKey('review_due'), t('app.kuaizhizao.quality.qms.zone.reviewDue')),
    allNode(buildLifecycleTreeKey('pending'), t('app.kuaizhizao.quality.qms.zone.pending')),
    allNode(buildLifecycleTreeKey('pending_audit'), t('app.kuaizhizao.quality.qms.nav.pendingAudit')),
    allNode(buildLifecycleTreeKey('draft_rejected'), t('app.kuaizhizao.quality.qms.nav.draftRejected')),
    allNode(buildLifecycleTreeKey('obsolete'), t('app.kuaizhizao.quality.qms.nav.obsolete')),
  ];
}

export function resolveNavNodeTitle(
  dimension: SystemDocumentNavDimension,
  selectedKey: string,
  t: TFunction,
  standards: QmsStandardNavItem[],
): string {
  const [, part] = selectedKey.split(KEY_SEP);
  if (dimension === 'standard') {
    if (part === SYSTEM_DOCUMENT_NAV_ALL_KEY) {
      return t('app.kuaizhizao.quality.qms.nav.all');
    }
    if (part === 'null') {
      return t('app.kuaizhizao.quality.qms.nav.unlinkedStandard');
    }
    const id = Number(part);
    const standard = standards.find((s) => s.id === id);
    if (standard) {
      return standard.name ? `${standard.code} ${standard.name}` : standard.code;
    }
  }
  const tree = buildSystemDocumentNavTreeData(dimension, t, standards);
  const hit = tree.find((n) => n.key === selectedKey);
  if (hit && typeof hit.title === 'string') return hit.title;
  return t('app.kuaizhizao.quality.qms.nav.all');
}

export function dimensionLabel(dimension: SystemDocumentNavDimension, t: TFunction): string {
  switch (dimension) {
    case 'standard':
      return t('app.kuaizhizao.quality.qms.nav.dimension.standard');
    case 'doc_type':
      return t('app.kuaizhizao.quality.qms.nav.dimension.docType');
    case 'lifecycle':
      return t('app.kuaizhizao.quality.qms.nav.dimension.lifecycle');
    default:
      return '';
  }
}
