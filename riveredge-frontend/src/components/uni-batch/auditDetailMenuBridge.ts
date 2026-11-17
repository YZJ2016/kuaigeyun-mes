/**
 * 工具栏审核下拉「审核详情」桥接。
 *
 * useAuditBatchRunner（带 auditEntity）挂载时注册；UniBatchMenuButton 在含 approve 的菜单上
 * 自动追加「审核详情」，点击时打开同一 UniAuditModal hub 查看流程进度。
 * 禁止各业务页手写平行菜单项。
 */

import type React from 'react';

export type AuditDetailMenuOpener = {
  openFromKeys: (keys: React.Key[]) => void;
};

let currentOpener: AuditDetailMenuOpener | null = null;

export function registerAuditDetailMenuOpener(opener: AuditDetailMenuOpener): () => void {
  currentOpener = opener;
  return () => {
    if (currentOpener === opener) {
      currentOpener = null;
    }
  };
}

export function getAuditDetailMenuOpener(): AuditDetailMenuOpener | null {
  return currentOpener;
}

/** 菜单是否为审核工具栏（含「审核」项） */
export function isAuditToolbarMenu(items: ReadonlyArray<{ key: string }>): boolean {
  return items.some((it) => it.key === 'approve');
}
