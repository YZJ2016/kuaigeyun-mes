import React from 'react';
import AntdInputNumberBase from '@antd-input-number-internal';
import type { InputNumberProps } from '@antd-input-number-internal';
import type { InputNumberRef } from '@antd-input-number-internal';
import { mergeInputSelectAllOnFocus } from '../../utils/inputSelectAllOnFocus';
import { roundInputNumberPrecision } from './roundInputNumberPrecision';

export type { InputNumberProps, InputNumberRef };

/** 与 antd InputNumber 一致，聚焦默认全选当前值。 */
export const UNI_INPUT_NUMBER_MIN_WIDTH_PX = 96;

/** 编辑框去掉精度补零。1.5000 显示 1.5，0.0000 显示 0。列表展示仍走 formatQuantity 等。 */
function stripEditPrecisionPadding(raw: string): string {
  if (!raw.includes('.')) return raw;
  const stripped = raw.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');
  if (stripped === '' || stripped === '-' || stripped === '+') return '0';
  return stripped;
}

const PatchedInputNumber = React.forwardRef<InputNumberRef, InputNumberProps>((props, ref) => {
  const { precision, formatter, onFocus, onBlur, onChange, style, ...rest } = props;
  const precisionRef = React.useRef(precision);
  precisionRef.current = precision;

  const handleBlur: NonNullable<InputNumberProps['onBlur']> = (event) => {
    const p = precisionRef.current;
    if (p != null && p >= 0) {
      const raw = props.value;
      if (typeof raw === 'number' && Number.isFinite(raw)) {
        const rounded = roundInputNumberPrecision(raw, p);
        if (rounded !== raw) {
          onChange?.(rounded);
        }
      }
    }
    onBlur?.(event);
  };

  const editFormatter: NonNullable<InputNumberProps['formatter']> = (value, info) => {
    if (info.userTyping) {
      return formatter ? String(formatter(value, info) ?? '') : info.input;
    }
    const next = formatter ? String(formatter(value, info) ?? '') : value == null ? '' : String(value);
    return stripEditPrecisionPadding(next);
  };

  return (
    <AntdInputNumberBase
      ref={ref}
      {...rest}
      precision={undefined}
      formatter={editFormatter}
      onFocus={mergeInputSelectAllOnFocus(onFocus)}
      onBlur={handleBlur}
      onChange={onChange}
      style={{ minWidth: UNI_INPUT_NUMBER_MIN_WIDTH_PX, ...style }}
    />
  );
});

PatchedInputNumber.displayName = 'InputNumber';

type BaseWithPanel = typeof AntdInputNumberBase & {
  _InternalPanelDoNotUseOrYouWillBeFired?: React.ComponentType<InputNumberProps>;
};

const baseWithPanel = AntdInputNumberBase as BaseWithPanel;
if (baseWithPanel._InternalPanelDoNotUseOrYouWillBeFired) {
  (
    PatchedInputNumber as BaseWithPanel
  )._InternalPanelDoNotUseOrYouWillBeFired = baseWithPanel._InternalPanelDoNotUseOrYouWillBeFired;
}

export default PatchedInputNumber;
