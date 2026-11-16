import type { FocusEvent, FocusEventHandler } from 'react';

/** 聚焦时选中输入框全文，便于直接键入新数值（Input / InputNumber 内层 input）。 */
export function mergeInputSelectAllOnFocus<T extends HTMLElement = HTMLInputElement>(
  existing?: FocusEventHandler<T>,
): FocusEventHandler<T> {
  return (event: FocusEvent<T>) => {
    const target = event.target;
    if (target instanceof HTMLInputElement && typeof target.select === 'function') {
      target.select();
    }
    existing?.(event);
  };
}
