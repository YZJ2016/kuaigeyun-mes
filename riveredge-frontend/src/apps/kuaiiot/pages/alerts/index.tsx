/**
 * 告警中心：告警规则 / 告警记录双视图。
 * 规则维护阈值与离线两类规则；记录页按状态机提供确认 / 处置 / 删除。
 */

import React, { useState } from 'react';
import { MultiTabListPageTemplate } from '../../../../components/layout-templates';
import RulesView from './RulesView';
import RecordsView from './RecordsView';

export default function AlertsPage() {
  const [activeTab, setActiveTab] = useState('rules');

  return (
    <MultiTabListPageTemplate
      activeTabKey={activeTab}
      onTabChange={setActiveTab}
      preserveMounted
      tabs={[
        { key: 'rules', label: '告警规则', children: <RulesView /> },
        { key: 'records', label: '告警记录', children: <RecordsView /> },
      ]}
    />
  );
}
