/**
 * 按平台设置同步页面 meta robots（是否接受搜索引擎收录）。
 */

const META_NAME = 'robots';
const META_ATTR = 'data-riveredge-search-engine-indexing';

export function applySearchEngineIndexing(enabled: boolean | undefined | null): void {
  if (typeof document === 'undefined') return;
  const allow = enabled !== false;
  let meta = document.head.querySelector(
    `meta[name="${META_NAME}"][${META_ATTR}]`,
  ) as HTMLMetaElement | null;
  if (!meta) {
    meta = document.createElement('meta');
    meta.setAttribute('name', META_NAME);
    meta.setAttribute(META_ATTR, '1');
    document.head.appendChild(meta);
  }
  meta.setAttribute('content', allow ? 'index,follow' : 'noindex,nofollow');
}
