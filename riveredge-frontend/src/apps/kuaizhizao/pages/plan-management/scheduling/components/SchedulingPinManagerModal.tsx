import React, { useMemo } from 'react';
import { Modal, Select, Space, Typography } from 'antd';
import type { TFunction } from 'i18next';
import type { GanttTaskLevel } from '../../../../components/GanttSchedulingChart/types';
import type { SchedulingWorkerResource } from '../schedulingResourceFilters';
import type { SchedulingPinnedResources } from '../schedulingPinnedResources';
import { pinnedIdsForLevel } from '../schedulingPinnedResources';

interface PinOption {
  value: number;
  label: string;
}

interface SchedulingPinManagerModalProps {
  open: boolean;
  t: TFunction;
  taskLevel: GanttTaskLevel;
  pinned: SchedulingPinnedResources;
  stationOptions: PinOption[];
  equipmentOptions: PinOption[];
  workerOptions: SchedulingWorkerResource[];
  onClose: () => void;
  onChange: (next: SchedulingPinnedResources) => void;
}

export default function SchedulingPinManagerModal({
  open,
  t,
  taskLevel,
  pinned,
  stationOptions,
  equipmentOptions,
  workerOptions,
  onClose,
  onChange,
}: SchedulingPinManagerModalProps) {
  const currentIds = pinnedIdsForLevel(pinned, taskLevel);

  const options = useMemo(() => {
    if (taskLevel === 'station') return stationOptions;
    if (taskLevel === 'equipment') return equipmentOptions;
    if (taskLevel === 'worker') {
      return workerOptions.map((worker) => ({
        value: worker.id,
        label: worker.name || worker.username || String(worker.id),
      }));
    }
    return [];
  }, [equipmentOptions, stationOptions, taskLevel, workerOptions]);

  const levelLabel =
    taskLevel === 'station'
      ? t('app.kuaizhizao.scheduling.ganttToolbar.resourceStation')
      : taskLevel === 'equipment'
        ? t('app.kuaizhizao.scheduling.ganttToolbar.resourceEquipment')
        : taskLevel === 'worker'
          ? t('app.kuaizhizao.scheduling.ganttToolbar.resourceWorker')
          : t('app.kuaizhizao.scheduling.ganttToolbar.resourceViewLabel');

  return (
    <Modal
      open={open}
      title={t('app.kuaizhizao.scheduling.pinManager.title')}
      onCancel={onClose}
      onOk={onClose}
      destroyOnHidden
      width={520}
    >
      <Space orientation="vertical" size={12} style={{ width: '100%' }}>
        <Typography.Text type="secondary">
          {t('app.kuaizhizao.scheduling.pinManager.description', { level: levelLabel })}
        </Typography.Text>
        <Select
          mode="multiple"
          allowClear
          style={{ width: '100%' }}
          placeholder={t('app.kuaizhizao.scheduling.pinManager.placeholder')}
          value={currentIds}
          options={options}
          onChange={(values) => {
            const ids = values.map(Number).filter((id) => Number.isInteger(id) && id > 0);
            if (taskLevel === 'station') {
              onChange({ ...pinned, stationIds: ids });
              return;
            }
            if (taskLevel === 'equipment') {
              onChange({ ...pinned, equipmentIds: ids });
              return;
            }
            if (taskLevel === 'worker') {
              onChange({ ...pinned, workerIds: ids });
            }
          }}
        />
      </Space>
    </Modal>
  );
}
