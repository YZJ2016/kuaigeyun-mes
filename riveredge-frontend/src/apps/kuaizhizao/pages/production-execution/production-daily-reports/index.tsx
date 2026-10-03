/**
 * 生产日报：快制造通用菜单已下线，能力由定制应用维护。
 */
import React from 'react';
import { DedicatedHostOfflinePage } from '../../../components/DedicatedHostOfflinePage';

export default function ProductionDailyReportsPage() {
  return (
    <DedicatedHostOfflinePage
      titleKey="app.kuaizhizao.productionDailyReport.offlineTitle"
      descriptionKey="app.kuaizhizao.productionDailyReport.offlineDescription"
    />
  );
}
