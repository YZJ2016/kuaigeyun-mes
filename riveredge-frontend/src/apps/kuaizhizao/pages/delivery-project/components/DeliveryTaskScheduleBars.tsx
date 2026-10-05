/**
 * 项目工作台：具体任务计划条，标工期以及提前或逾期天数。
 */

import React, { useMemo } from 'react';
import { Typography } from 'antd';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import type { DeliveryProjectNodeTask } from '../../../services/delivery-project';

function daySpan(start: string, end: string): number {
  const days = dayjs(end).startOf('day').diff(dayjs(start).startOf('day'), 'day');
  return Math.max(days, 1);
}

const DeliveryTaskScheduleBars: React.FC<{ tasks: DeliveryProjectNodeTask[] }> = ({ tasks }) => {
  const { t } = useTranslation();
  const rows = useMemo(
    () =>
      tasks.filter(
        (task) =>
          task.task_layer !== 'substage' && task.planned_start_date && task.planned_end_date,
      ),
    [tasks],
  );
  const range = useMemo(() => {
    if (!rows.length) return null;
    const starts = rows.map((task) => dayjs(task.planned_start_date).startOf('day').valueOf());
    const ends = rows.map((task) => dayjs(task.planned_end_date).startOf('day').valueOf());
    return { min: Math.min(...starts), max: Math.max(...ends) };
  }, [rows]);

  if (!range || range.max <= range.min) {
    return (
      <Typography.Text type="secondary">
        {t('app.kuaizhizao.deliveryProject.taskGanttEmpty')}
      </Typography.Text>
    );
  }

  const span = Math.max(range.max - range.min, 24 * 60 * 60 * 1000);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {rows.map((task) => {
        const start = dayjs(task.planned_start_date).startOf('day').valueOf();
        const end = dayjs(task.planned_end_date).startOf('day').valueOf();
        const left = ((start - range.min) / span) * 100;
        const width = Math.max(((Math.max(end, start) - start) / span) * 100, 8);
        const days = daySpan(task.planned_start_date!, task.planned_end_date!);
        const mark = task.ahead_days
          ? t('app.kuaizhizao.deliveryProject.taskAheadDays', { days: task.ahead_days })
          : task.overdue_days
            ? t('app.kuaizhizao.deliveryProject.taskOverdueDays', { days: task.overdue_days })
            : t('app.kuaizhizao.deliveryProject.taskDurationDays', { days });
        return (
          <div key={task.id}>
            <Typography.Text ellipsis style={{ display: 'block', fontSize: 12 }}>
              {task.task_name} {mark}
            </Typography.Text>
            <div
              style={{
                position: 'relative',
                height: 14,
                marginTop: 4,
                borderRadius: 4,
                background: 'rgba(0, 0, 0, 0.04)',
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  left: `${left}%`,
                  width: `${width}%`,
                  height: '100%',
                  borderRadius: 4,
                  background: task.overdue_days
                    ? '#cf1322'
                    : task.ahead_days
                      ? '#389e0d'
                      : '#1677ff',
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default DeliveryTaskScheduleBars;
