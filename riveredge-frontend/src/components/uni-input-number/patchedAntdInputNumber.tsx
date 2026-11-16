import React from 'react';
import AntdInputNumberBase from '@antd-input-number-internal';
import type { InputNumberProps } from '@antd-input-number-internal';
import type { InputNumberRef } from '@antd-input-number-internal';
import { mergeInputSelectAllOnFocus } from '../../utils/inputSelectAllOnFocus';
import { roundInputNumberPrecision } from './roundInputNumberPrecision';

export type { InputNumberProps, InputNumberRef };

/** 与 antd InputNumber 一致，聚焦默认全选当前值。 */
export const UNI_INPUT_NUMBER_MIN_WIDTH_PX = 96;

const PatchedInputNumber = React.forwardRef<InputNumberRef, InputNumberProps>((props, ref) => {
  const { precision, onFocus, onBlur, onChange, style, ...rest } = props;
  const [focused, setFocused] = React.useState(false);
  const precisionRef = React.useRef(precision);
  precisionRef.current = precision;

  const handleBlur: NonNullable<InputNumberProps['onBlur']> = (event) => {
    setFocused(false);
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

  return (
    <AntdInputNumberBase
      ref={ref}
      {...rest}
      precision={focused ? undefined : precision}
      onFocus={mergeInputSelectAllOnFocus(() => setFocused(true), onFocus)}
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
