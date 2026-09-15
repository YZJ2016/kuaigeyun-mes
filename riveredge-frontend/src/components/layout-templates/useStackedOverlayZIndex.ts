/**
 * 叠层弹窗 z-index：在已有 Drawer/Modal 上再开一层时，保证新层在上。
 */
import { theme } from 'antd';
import {
  MODAL_ABOVE_DETAIL_SIDECHAIN_OFFSET,
  MODAL_NESTED_ABOVE_PARENT_OFFSET,
} from './constants';
import { useOptionalDetailDrawerChrome } from './DetailDrawerChromeContext';

/**
 * @param explicit 调用方指定时优先
 * @returns 相对父级详情抽屉 / 关联 chrome 抬升后的 zIndex；无父级时抬到详情侧链之上
 */
export function useStackedOverlayZIndex(explicit?: number): number {
  const { token } = theme.useToken();
  const chrome = useOptionalDetailDrawerChrome();
  if (explicit != null) {
    return explicit;
  }
  if (chrome?.zIndex != null) {
    return chrome.zIndex + MODAL_NESTED_ABOVE_PARENT_OFFSET;
  }
  return token.zIndexPopupBase + MODAL_ABOVE_DETAIL_SIDECHAIN_OFFSET;
}
