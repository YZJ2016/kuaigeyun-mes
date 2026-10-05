/**
 * 旧工作日历 URL：自动跳转班次排班「工位停机窗」Tab（菜单已下线）。
 */

import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Spin } from 'antd';
import { ListPageTemplate } from '../../../../../components/layout-templates';

const WorkCalendarPage: React.FC = () => {
  const navigate = useNavigate();

  useEffect(() => {
    navigate('/apps/kuaizhizao/performance/shift-rosters?tab=downtime', { replace: true });
  }, [navigate]);

  return (
    <ListPageTemplate>
      <Spin />
    </ListPageTemplate>
  );
};

export default WorkCalendarPage;
