import React from 'react';
import type { InputNumberProps } from 'antd/es/input-number';
import PatchedInputNumber from './patchedAntdInputNumber';

export { UNI_INPUT_NUMBER_MIN_WIDTH_PX } from './patchedAntdInputNumber';

/** 全局 InputNumber 行为见 patchedAntdInputNumber（Vite 别名注入 antd）。 */
export const UniInputNumber: React.FC<InputNumberProps> = (props) => (
  <PatchedInputNumber {...props} />
);
