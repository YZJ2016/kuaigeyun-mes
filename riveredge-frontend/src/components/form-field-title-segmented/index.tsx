import React from 'react';

/** 表单项 label / 明细表头内嵌分段：配合 global.less 中 form-field-segmented-sm，不撑高标题行 */
export const FORM_FIELD_TITLE_SEGMENTED_CLASS = 'form-field-segmented-sm';

export type FormFieldTitleSegmentedRowProps = {
  title: React.ReactNode;
  children: React.ReactNode;
  className?: string;
};

export function FormFieldTitleSegmentedRow({ title, children, className }: FormFieldTitleSegmentedRowProps) {
  return (
    <span className={['form-field-title-segmented-row', className].filter(Boolean).join(' ')}>
      <span className="form-field-title-segmented-row__text">{title}</span>
      {children}
    </span>
  );
}