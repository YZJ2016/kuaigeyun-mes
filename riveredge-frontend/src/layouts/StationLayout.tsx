/**
 * 工位专用布局（spec 180 / STN-D12）。
 *
 * 工位路径不渲染 BasicLayout / UniTabs / 应用切换 / 系统配置 / 个人偏好 / 任意地址跳转。
 * 只保留工位、终端账号、当前操作员以及锁屏、退出所需的最小信息；
 * 任务、扫码等业务内容由工位页（station/entry 及其 kiosk 子页）自身承载。
 */
import React, { useCallback } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Button, Popconfirm, Typography, theme } from 'antd';
import { LockOutlined, LogoutOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { useGlobalStore, useThemeStore, useUserPreferenceStore } from '../stores';
import {
  setStationOperator,
  setStationOperatorCandidate,
  useStationEntrySnapshot,
} from '../apps/kuaizhizao/station/entry/session';
import { closeStationOperatorSession } from '../apps/kuaizhizao/station/operatorSession';
import { getSessionCurrentUser } from '../utils/sessionCurrentUser';
import { clearSessionScopedQueries } from '../utils/clearSessionQueries';
import { clearLanguageForLogout } from '../config/i18n';
import { redirectAfterLogout } from '../utils/loginEntry';

const BAR_HEIGHT = 56;

const StationLayout: React.FC = () => {
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const lockScreen = useGlobalStore((s) => s.lockScreen);
  const { workstation, operator, terminalAccountName } = useStationEntrySnapshot();

  const storeUser = useGlobalStore((s) => s.currentUser);
  const sessionUser = storeUser ?? getSessionCurrentUser();
  const accountName =
    terminalAccountName || sessionUser?.full_name || sessionUser?.username || '未读取';

  /** 锁屏：记录当前工位路径，解锁后由锁屏页回到 lockedPath */
  const handleLockScreen = useCallback(() => {
    lockScreen(location.pathname);
    navigate('/lock-screen', { replace: true });
  }, [lockScreen, location.pathname, navigate]);

  /** 退出终端账号：先尝试关闭操作员会话（失败不阻塞），再与 BasicLayout.performLogout 同一套本地清理 */
  const handleLogout = useCallback(async () => {
    try {
      await closeStationOperatorSession('terminal_logout');
    } catch {
      /* 操作员会话关闭失败不阻塞登出 */
    }
    setStationOperator(null);
    setStationOperatorCandidate(null);
    clearSessionScopedQueries(queryClient);
    useUserPreferenceStore.getState().clearForLogout();
    useThemeStore.getState().clearForLogout();
    clearLanguageForLogout();
    useGlobalStore.getState().logout();
    redirectAfterLogout(navigate);
  }, [queryClient, navigate]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        overflow: 'hidden',
        background: token.colorBgLayout,
      }}
    >
      <div
        style={{
          height: BAR_HEIGHT,
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          padding: '0 16px',
          background: token.colorBgContainer,
          borderBottom: `1px solid ${token.colorBorder}`,
        }}
      >
        <Typography.Text strong style={{ fontSize: 16 }}>
          {workstation
            ? `${workstation.stationName}（${workstation.stationCode}）`
            : '工位未绑定'}
        </Typography.Text>
        <div style={{ flex: 1 }} />
        <Typography.Text>终端账号：{accountName}</Typography.Text>
        <Typography.Text>
          当前操作员：{operator ? operator.name : '未确认'}
        </Typography.Text>
        <Button size="large" icon={<LockOutlined />} onClick={handleLockScreen}>
          锁屏
        </Button>
        <Popconfirm
          title="退出当前终端账号？"
          okText="退出"
          cancelText="取消"
          onConfirm={handleLogout}
        >
          <Button size="large" danger icon={<LogoutOutlined />}>
            退出
          </Button>
        </Popconfirm>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        <Outlet />
      </div>
    </div>
  );
};

export default StationLayout;
