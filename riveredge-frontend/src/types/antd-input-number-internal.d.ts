declare module '@antd-input-number-internal' {
  export type { InputNumberProps, InputNumberRef } from 'antd/es/input-number';
  import type { InputNumberProps } from 'antd/es/input-number';
  import type React from 'react';

  const InputNumber: React.ForwardRefExoticComponent<
    InputNumberProps & React.RefAttributes<import('antd/es/input-number').InputNumberRef>
  > & {
    _InternalPanelDoNotUseOrYouWillBeFired?: React.ComponentType<InputNumberProps>;
  };
  export default InputNumber;
}
