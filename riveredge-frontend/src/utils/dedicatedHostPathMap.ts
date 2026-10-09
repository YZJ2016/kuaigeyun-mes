/**
 * 定制应用菜单 path 与宿主 URL 的映射约定（前端剥离真源）。
 *
 * 菜单：`/apps/{host}/{rest}` → `/apps/{dedicated}/{dedicatedRest}`
 * - kuaiplm / kuaizhizao / kuaioa：`dedicatedRest = rest`（去掉 `/apps/{host}/` 前缀）
 * - master-data：`dedicatedRest = master-data/{rest}`
 *
 * 页文件：`apps/{dedicated}/pages/{hostApp}/{rest}`（镜像宿主 pages 树，禁止 re-export 宿主页）
 * API / 权限：仍 import 宿主 `services` 与 manifest 权限码。
 */

export function hostMenuPathToDedicatedRest(
  hostPath: string,
  dedicatedAppCode: string,
): string | null {
  const path = (hostPath || '').split('?')[0].replace(/\/$/, '');
  const prefix = `/apps/${dedicatedAppCode}`;
  if (path.startsWith(prefix)) return null;

  const m = path.match(/^\/apps\/([^/]+)\/(.*)$/);
  if (!m) return null;
  const hostApp = m[1];
  const rest = m[2];
  if (!rest) return null;

  if (hostApp === 'master-data') return `master-data/${rest}`;
  if (hostApp === 'kuaiplm' || hostApp === 'kuaizhizao' || hostApp === 'kuaioa') return rest;
  return null;
}

export function dedicatedRestToHostAppPageDir(
  dedicatedRest: string,
): { hostApp: string; pageDir: string } | null {
  const rest = dedicatedRest.replace(/^\//, '');
  if (rest.startsWith('master-data/')) {
    const sub = rest.slice('master-data/'.length);
    return { hostApp: 'master-data', pageDir: mapMasterDataMenuToPageDir(sub) };
  }
  if (rest.startsWith('hr/') || rest.startsWith('approval/') || rest.startsWith('collaboration/') || rest.startsWith('compliance/') || rest.startsWith('assets/')) {
    return { hostApp: 'kuaioa', pageDir: `pages/${rest}` };
  }
  const kuaiplmRoots = new Set([
    'dashboard',
    'pending-inbox',
    'rd-projects',
    'rd-deliverables',
    'gate-templates',
    'change-management',
    'knowledge-base',
    'project-proposals',
    'bom-collaborations',
    'product-firmwares',
    'production-files',
    'lab-requests',
    'lab-board',
    'lab-judgment-rules',
    'annual-lab-plans',
    'trial-flows',
    'sample-process-applications',
    'material-reviews',
    'mold-sample-orders',
    'prototype-build-sheets',
    'engineering-changes',
  ]);
  const first = rest.split('/')[0];
  if (kuaiplmRoots.has(first) || rest.startsWith('phase2/')) {
    return { hostApp: 'kuaiplm', pageDir: mapKuaiplmMenuToPageDir(rest) };
  }
  return { hostApp: 'kuaizhizao', pageDir: `pages/${rest}` };
}

function mapKuaiplmMenuToPageDir(rest: string): string {
  if (rest === 'lab-board') return 'pages/lab-requests';
  return `pages/${rest}`;
}

function mapMasterDataMenuToPageDir(sub: string): string {
  if (sub === 'materials') return 'pages/materials/management';
  if (sub === 'process/engineering-bom') return 'pages/materials/bom';
  return `pages/${sub}`;
}
