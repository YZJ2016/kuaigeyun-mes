import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Select, Space } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { EquipmentDispatchSnapshot } from './EquipmentDispatchCardPicker';

type EquipmentListRow = {
  id: number;
  code?: string;
  name?: string;
  status?: string;
};

export interface EquipmentDispatchFieldTriggerProps {
  value?: number[];
  onChange?: (equipmentIds: number[]) => void;
  onOpenSelect: () => void;
  equipmentList: EquipmentListRow[];
  snapshotsById: Record<number, EquipmentDispatchSnapshot>;
}

const EquipmentDispatchFieldTrigger: React.FC<EquipmentDispatchFieldTriggerProps> = ({
  value,
  onChange,
  onOpenSelect,
  equipmentList,
  snapshotsById,
}) => {
  const { t } = useTranslation();

  const selectedIds = useMemo(() => {
    const raw = value ?? [];
    return raw.filter((id) => Number.isInteger(id) && id > 0);
  }, [value]);

  const selectOptions = useMemo(() => {
    return selectedIds.map((equipmentId) => {
      const row = equipmentList.find((e) => Number(e.id) === equipmentId);
      const snap = snapshotsById[equipmentId];
      const code = snap?.code ?? row?.code ?? '';
      const name = snap?.name ?? row?.name ?? '';
      const label = `${code} ${name}`.trim() || String(equipmentId);
      return { value: equipmentId, label };
    });
  }, [equipmentList, selectedIds, snapshotsById]);

  return (
    <Space.Compact block style={{ width: '100%' }}>
      <Select
        mode="multiple"
        style={{ flex: 1, minWidth: 0 }}
        placeholder={t('app.kuaizhizao.workOrder.equipmentDispatchPreview.equipmentPlaceholder')}
        value={selectedIds}
        options={selectOptions}
        open={false}
        allowClear
        maxTagCount="responsive"
        onChange={(next) => {
          const ids = (Array.isArray(next) ? next : [])
            .map((id) => Number(id))
            .filter((id) => Number.isInteger(id) && id > 0);
          onChange?.(ids);
        }}
        onClick={() => {
          if (selectedIds.length === 0) {
            onOpenSelect();
          }
        }}
      />
      <Button type="default" icon={<SearchOutlined />} onClick={onOpenSelect}>
        {t('app.kuaizhizao.workOrder.equipmentDispatchPreview.openSelectModal')}
      </Button>
    </Space.Compact>
  );
};

export default EquipmentDispatchFieldTrigger;
