/**
 * Modal / Drawer 经 React Portal 挂到 body 后，点击仍会沿组件树冒泡到触发节点。
 * 表格单元格内打开弹层时，会误触底层行选中/行点击。
 *
 * 用法：传给 Modal 的 maskProps / wrapProps（或等价容器）。
 */
import type { SyntheticEvent } from 'react';

function stopPortalBubble(e: SyntheticEvent) {
  e.stopPropagation();
}

export const MODAL_ISOLATE_POINTER_PROPS = {
  onMouseDown: stopPortalBubble,
  onClick: stopPortalBubble,
  onDoubleClick: stopPortalBubble,
} as const;

/** Modal 内 Select 下拉挂到内容区，避免明细表 overflow 裁切与 body 滚动锁竞争 */
export function getPopupContainerInModal(trigger: HTMLElement): HTMLElement {
  const el = trigger.closest('.ant-modal-content') ?? trigger.closest('.ant-modal-wrap');
  return (el as HTMLElement) ?? document.body;
}
