import React from 'react';
import { useTranslation } from 'react-i18next';
import { ThemedSegmented } from '../../../../../components/themed-segmented';
import {
  FORM_FIELD_TITLE_SEGMENTED_CLASS,
  FormFieldTitleSegmentedRow,
} from '../../../../../components/form-field-title-segmented';

export type ProductScope = 'make' | 'all';

type ProductScopeColumnTitleProps = {
  productScope: ProductScope;
  onProductScopeChange: (scope: ProductScope) => void;
  /** 默认与销售订单明细「产品」列一致 */
  titleKey?: string;
};

export function ProductScopeColumnTitle({
  productScope,
  onProductScopeChange,
  titleKey = 'app.kuaizhizao.salesOrder.material',
}: ProductScopeColumnTitleProps) {
  const { t } = useTranslation();
  return (
    <FormFieldTitleSegmentedRow title={t(titleKey)}>
      <ThemedSegmented
        className={FORM_FIELD_TITLE_SEGMENTED_CLASS}
        size="small"
        value={productScope}
        options={[
          { label: t('app.kuaizhizao.sales.common.productScopeMake'), value: 'make' },
          { label: t('app.kuaizhizao.sales.common.productScopeAll'), value: 'all' },
        ]}
        onChange={(val) => onProductScopeChange((val as ProductScope) ?? 'make')}
      />
    </FormFieldTitleSegmentedRow>
  );
}