import React from 'react';
import BusinessBoardPage from '../../../../../pages/system/dashboard/analysis/BusinessBoardPage';

/** 设备运维 HUD 大屏：复用系统运营看板壳与主题，数据走设备看板 API */
const EquipmentBusinessBoardPage: React.FC = () => <BusinessBoardPage scope="equipment" />;

export default EquipmentBusinessBoardPage;
