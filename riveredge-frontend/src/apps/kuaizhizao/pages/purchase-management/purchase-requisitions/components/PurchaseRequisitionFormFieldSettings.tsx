import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Checkbox, Popover, Space } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import { useUserPreferenceStore } from '../../../../../../stores/userPreferenceStore';
import {
  buildPurchaseRequisitionFormFieldVisibilityPatch,
  resolvePurchaseRequisitionFormFieldVisibility,
} from '../purchaseRequisitionFormFieldPrefs';

const P = 'app.kuaizhizao.purchaseRequisition.formFieldSettings';

export const PurchaseRequisitionFormFieldSettings: React.FC = () => {
  const { t } = useTranslation();
  const preferences = useUserPreferenceStore((s) => s.preferences);
  const updatePreferences = useUserPreferenceStore((s) => s.updatePreferences);
  const visibility = useMemo(
    () => resolvePurchaseRequisitionFormFieldVisibility(preferences),
    [preferences],
  );
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const persist = async (nextVisible: boolean) => {
    setSaving(true);
    try {
      await updatePreferences(
        buildPurchaseRequisitionFormFieldVisibilityPatch({
          requisition_name: nextVisible,
        }),
      );
    } finally {
      setSaving(false);
    }
  };

  const content = (
    <Space orientation="vertical" size={8}>
      <Checkbox
        checked={visibility.requisition_name}
        disabled={saving}
        onChange={(e) => void persist(e.target.checked)}
      >
        {t('app.kuaizhizao.purchaseRequisition.form.name')}
      </Checkbox>
    </Space>
  );

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      trigger="click"
      placement="bottomRight"
      title={t(`${P}.title`)}
      content={content}
    >
      <Button type="link" size="small" icon={<SettingOutlined />} style={{ paddingInline: 4 }}>
        {t(`${P}.action`)}
      </Button>
    </Popover>
  );
};
