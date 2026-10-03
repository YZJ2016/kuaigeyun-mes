/**
 * 生产日报模板：快制造通用菜单已下线，能力由定制应用维护。
 */
import React from 'react';
import { DedicatedHostOfflinePage } from '../../../components/DedicatedHostOfflinePage';

export default function ProductionDailyTemplatesPage() {
  return (
    <DedicatedHostOfflinePage
      titleKey="app.kuaizhizao.productionDailyTemplate.offlineTitle"
      descriptionKey="app.kuaizhizao.productionDailyTemplate.offlineDescription"
    />
  );
}
