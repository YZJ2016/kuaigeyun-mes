/**
 * 触屏工位入口。
 * 路径：/apps/kuaizhizao/production-execution/station
 */
import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import { matchPath, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { App, Button, Drawer, Input, List, Space, Typography } from 'antd';
import { listExecutableWorkOrders, type StationWorkOrder } from '../execution/api';
import { TouchScreenTemplate } from '../../../../components/layout-templates/hmi';
import { HMI_DESIGN_TOKENS, HMI_STATION_LAYOUT, HMI_TOUCH } from '../../../../theme/hmi';
import { STATION_ENTRY_PATH } from '../../../../utils/clientChannel';
import PageSkeleton from '../../../../components/page-skeleton';
import { touchButtonProps } from '../../../../components/touch-terminal';
import { getCurrentUser } from '../../../../services/auth';
import { formatUserDisplayLabel } from '../../../../utils/userDisplay';
import { searchUserDisplay } from '../../../../services/user';
import StationBinder, { getStationStorageKey, type StationInfo } from '../../components/StationBinder';
import { workOrderApi } from '../../services/production';
import { parseWorkOrderScanCode, rowsFromListResponse } from '../reporting/quickReporting';
import { resolveWorkstation } from './resolveWorkstation';
import {
  getStationWorkstation,
  readShellWorkstationId,
  setStationExecutionSelection,
  setStationOperator,
  setStationOperatorCandidate,
  setStationWorkstation,
  setTerminalAccountName,
  useStationEntrySnapshot,
  type StationOperator,
} from './session';
import {
  closeStationOperatorSession,
  confirmStationOperatorSession,
} from '../operatorSession';

const EXECUTION_LINKS: Array<{ title: string; to: string }> = [
  { title: '报工', to: `${STATION_ENTRY_PATH}/reporting` },
  { title: '执行', to: `${STATION_ENTRY_PATH}/execution` },
];

const RESOURCE_LINKS: Array<{ title: string; to: string }> = [
  { title: 'SOP', to: `${STATION_ENTRY_PATH}/sop-viewer/kiosk` },
  { title: '图纸', to: `${STATION_ENTRY_PATH}/drawing-viewer/kiosk` },
  { title: '程序查看', to: `${STATION_ENTRY_PATH}/program-viewer/kiosk` },
];

const STATION_LINKS: Array<{ title: string; to: string }> = [
  { title: '刷脸交接', to: `${STATION_ENTRY_PATH}/face` },
  { title: '安灯', to: `${STATION_ENTRY_PATH}/andon` },
];

const OPERATOR_PAGE_SIZE = 20;

const STATION_PANEL_STYLE: React.CSSProperties = {
  background: HMI_DESIGN_TOKENS.BG_PANEL,
  border: `1px solid ${HMI_DESIGN_TOKENS.BORDER}`,
  borderRadius: HMI_DESIGN_TOKENS.PANEL_RADIUS,
  padding: 20,
};

const STATION_STATUS_PILL_STYLE: React.CSSProperties = {
  border: `1px solid ${HMI_DESIGN_TOKENS.BORDER}`,
  borderRadius: 999,
  padding: '4px 12px',
  fontSize: 14,
  lineHeight: '22px',
};

function ModuleNotReady() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const stationId = positiveWorkstationId(searchParams.get('workstationId'));

  return (
    <TouchScreenTemplate
      title="工位入口"
      footerButtons={[
        {
          title: '返回工位入口',
          onClick: () => navigate(withWorkstationId(STATION_ENTRY_PATH, stationId)),
        },
      ]}
    >
      <Typography.Title level={3}>模块未就绪</Typography.Title>
      <Typography.Text type="secondary">页面资源加载失败或暂未启用，请返回后重试。</Typography.Text>
    </TouchScreenTemplate>
  );
}

function lazyStationExport(loaders: Array<Record<string, () => Promise<unknown>>>) {
  const load = loaders.map((item) => Object.values(item)[0]).find(Boolean);
  return lazy(async (): Promise<{ default: React.ComponentType<any> }> => {
    if (!load) return { default: ModuleNotReady };
    try {
      const page = await load();
      if (typeof page !== 'function') return { default: ModuleNotReady };
      return { default: page as React.ComponentType<any> };
    } catch (error) {
      console.error('工位模块加载失败', error);
      return { default: ModuleNotReady };
    }
  });
}

const StationExecutionPage = lazyStationExport([
  import.meta.glob('../execution/index.ts', { import: 'StationExecutionPage' }),
]);
const StationReportingPage = lazyStationExport([
  import.meta.glob('../reporting/index.ts', { import: 'StationReportingPage' }),
]);
const StationAndonPage = lazyStationExport([
  import.meta.glob('../andon/index.ts', { import: 'StationAndonPage' }),
]);
const StationFaceHandoverPage = lazyStationExport([
  import.meta.glob('../face/index.ts', { import: 'StationFaceHandoverPage' }),
]);

function LazyModule({
  page: Page,
  pageProps,
}: {
  page: React.LazyExoticComponent<React.ComponentType<any>>;
  pageProps: Record<string, unknown>;
}) {
  return (
    <Suspense fallback={<PageSkeleton variant="content" />}>
      <Page {...pageProps} />
    </Suspense>
  );
}

function withWorkstationId(path: string, workstationId: number | null | undefined): string {
  if (typeof workstationId !== 'number' || !Number.isInteger(workstationId) || workstationId <= 0) {
    return path;
  }
  const [pathname, query = ''] = path.split('?');
  const params = new URLSearchParams(query);
  params.set('workstationId', String(workstationId));
  return `${pathname}?${params.toString()}`;
}

function positiveWorkstationId(raw: string | null | undefined): number | null {
  const text = String(raw ?? '').trim();
  if (!/^[1-9]\d*$/.test(text)) return null;
  const id = Number(text);
  return Number.isSafeInteger(id) ? id : null;
}

function readSavedStation(): StationInfo | null {
  const raw = localStorage.getItem(getStationStorageKey());
  if (!raw) return null;
  try {
    const info = JSON.parse(raw) as StationInfo;
    if (!info || !Number.isFinite(Number(info.stationId))) return null;
    return info;
  } catch {
    localStorage.removeItem(getStationStorageKey());
    return null;
  }
}

function StationHome() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { workstation, operator, candidate, terminalAccountName } = useStationEntrySnapshot();
  const [binding, setBinding] = useState(false);
  const [operatorPickerOpen, setOperatorPickerOpen] = useState(false);
  const [operators, setOperators] = useState<Array<{ label: string; value: number }>>([]);
  const [operatorsLoading, setOperatorsLoading] = useState(false);
  const [operatorKeyword, setOperatorKeyword] = useState('');
  const [operatorPage, setOperatorPage] = useState(1);
  const [operatorTotal, setOperatorTotal] = useState(0);
  const operatorSearchSeq = useRef(0);
  const [scanDraft, setScanDraft] = useState('');
  const [openingWorkOrder, setOpeningWorkOrder] = useState(false);
  const [assignedOrderState, setAssignedOrderState] = useState<{
    key: string;
    rows: StationWorkOrder[];
    hasMore: boolean;
  }>({ key: '', rows: [], hasMore: false });
  const [ordersPage, setOrdersPage] = useState({ key: '', skip: 0 });
  const [ordersLoading, setOrdersLoading] = useState(false);
  const ordersRequestSeq = useRef(0);
  const [employeeCode, setEmployeeCode] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [exiting, setExiting] = useState(false);
  const ordersKey = operator && workstation ? `${workstation.stationId}:${operator.id}` : '';
  const ordersSkip = ordersPage.key === ordersKey ? ordersPage.skip : 0;
  const assignedOrders = assignedOrderState.key === ordersKey ? assignedOrderState.rows : [];
  const ordersHasMore = assignedOrderState.key === ordersKey && assignedOrderState.hasMore;

  useEffect(() => {
    let cancelled = false;
    getCurrentUser()
      .then((user) => {
        if (cancelled) return;
        const name = user.full_name || user.username || '';
        setTerminalAccountName(name);
      })
      .catch(() => {
        if (!cancelled) message.error('无法读取当前登录账号');
      });
    return () => {
      cancelled = true;
    };
  }, [message]);

  const loadOperators = useCallback(async (page: number, append = false) => {
    const keyword = operatorKeyword.trim();
    const requestSeq = ++operatorSearchSeq.current;
    setOperatorsLoading(true);
    try {
      const res = await searchUserDisplay({
        page,
        page_size: OPERATOR_PAGE_SIZE,
        ...(keyword ? { keyword } : {}),
        is_active: true,
        host_resource: 'kuaizhizao:production-execution-terminal',
      });
      if (requestSeq !== operatorSearchSeq.current) return;
      const items = (res.items || []).map((item) => ({
        label: item.label || formatUserDisplayLabel(item),
        value: item.id,
      }));
      setOperators((previous) => append ? [...previous, ...items] : items);
      setOperatorPage(page);
      setOperatorTotal(res.total || 0);
    } catch (error: unknown) {
      if (requestSeq === operatorSearchSeq.current) {
        message.error(error instanceof Error ? error.message : '加载操作员失败');
      }
    } finally {
      if (requestSeq === operatorSearchSeq.current) setOperatorsLoading(false);
    }
  }, [message, operatorKeyword]);

  useEffect(() => {
    if (!operatorPickerOpen) return;
    const timer = window.setTimeout(() => {
      void loadOperators(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [loadOperators, operatorPickerOpen]);

  const loadAssignedOrders = useCallback(async (key: string, operatorId: number, skip: number) => {
    const requestSeq = ++ordersRequestSeq.current;
    setOrdersLoading(true);
    try {
      const page = await listExecutableWorkOrders(skip, operatorId);
      if (requestSeq !== ordersRequestSeq.current) return;
      setAssignedOrderState((previous) => ({
        key,
        rows: skip === 0 ? page.rows : [...(previous.key === key ? previous.rows : []), ...page.rows],
        hasMore: page.hasMore,
      }));
    } catch {
      if (requestSeq === ordersRequestSeq.current) message.error('加载本人派工失败');
    } finally {
      if (requestSeq === ordersRequestSeq.current) setOrdersLoading(false);
    }
  }, [message]);

  useEffect(() => {
    if (!operator?.id || !ordersKey) return;
    const timer = window.setTimeout(() => {
      void loadAssignedOrders(ordersKey, operator.id, ordersSkip);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadAssignedOrders, operator?.id, ordersKey, ordersSkip]);

  const reportingPath = (code: string) =>
    withWorkstationId(`${STATION_ENTRY_PATH}/reporting?workOrderCode=${encodeURIComponent(code)}`, workstation?.stationId);

  // kiosk 详情路由参数是数字工单 ID：先按工单编号精确解析，兼容数字编码；
  // 未匹配且输入是纯数字时保留原有“直接输入工单 ID”入口。
  const openWorkOrderByCode = async (viewDetail = false) => {
    const text = parseWorkOrderScanCode(scanDraft);
    if (!text) {
      message.info('请扫描工单编号条码或输入工单编号');
      return;
    }
    if (openingWorkOrder) return;
    setOpeningWorkOrder(true);
    try {
      const raw = await workOrderApi.list({ code: text });
      const matched = rowsFromListResponse<{ id?: number; code?: string }>(raw).find(
        (row) => String(row.code ?? '').trim() === text,
      );
      const numericId = viewDetail && /^[1-9]\d*$/.test(text) ? Number(text) : null;
      const workOrderId = matched?.id ?? (numericId != null && Number.isSafeInteger(numericId) ? numericId : null);
      if (!workOrderId || (!viewDetail && !matched?.code)) {
        message.error('未找到该工单');
        return;
      }
      if (viewDetail) {
        navigate(withWorkstationId(`${STATION_ENTRY_PATH}/work-orders/${workOrderId}/kiosk`, workstation?.stationId));
      } else if (matched?.code) {
        navigate(reportingPath(matched.code));
      }
    } catch {
      message.error('加载工单失败');
    } finally {
      setOpeningWorkOrder(false);
    }
  };

  const onBind = (info: StationInfo) => {
    setStationWorkstation(info, { notifyShell: true });
    const next = new URLSearchParams(searchParams);
    next.set('workstationId', String(info.stationId));
    setSearchParams(next, { replace: true });
    setBinding(false);
  };

  const resetOperatorSearch = () => {
    operatorSearchSeq.current += 1;
    setOperators([]);
    setOperatorsLoading(false);
    setOperatorKeyword('');
    setOperatorPage(1);
    setOperatorTotal(0);
  };

  const openOperatorPicker = () => {
    resetOperatorSearch();
    setOperatorPickerOpen(true);
  };

  const closeOperatorPicker = () => {
    resetOperatorSearch();
    setOperatorPickerOpen(false);
  };

  // 点选姓名只产生候选人；刷脸或员工码与候选人一致并确认后才成为当前操作员
  const pickOperator = (next: StationOperator) => {
    setStationOperatorCandidate(next);
    setEmployeeCode('');
    closeOperatorPicker();
  };

  const confirmByEmployeeCode = async () => {
    const code = employeeCode.trim();
    if (!candidate || workstation?.stationId == null || !code || confirming) return;
    const candidateId = candidate.id;
    setConfirming(true);
    try {
      const session = await confirmStationOperatorSession({
        workstationId: workstation.stationId,
        candidateUserId: candidateId,
        confirmMethod: 'employee_code',
        employeeCode: code,
      });
      setStationOperator({ id: session.operator_user_id, name: session.operator_name });
      setStationOperatorCandidate(null);
      message.success('已确认当前操作员');
    } catch {
      // 通用失败文案：不回显员工码或失败原因细节
      message.error('操作员确认失败，请重试');
    } finally {
      setEmployeeCode('');
      setConfirming(false);
    }
  };

  const exitOperator = async () => {
    if (exiting) return;
    setExiting(true);
    try {
      // 显式退出/换人：服务端记 explicit_switch（审计区分于工位换绑的 explicit_close）
      await closeStationOperatorSession('explicit_switch');
    } catch {
      // 本地凭据已清空；服务端关闭失败不阻断退出
    } finally {
      ordersRequestSeq.current += 1;
      setStationOperator(null);
      setStationOperatorCandidate(null);
      setAssignedOrderState({ key: '', rows: [], hasMore: false });
      setOrdersPage({ key: '', skip: 0 });
      setEmployeeCode('');
      setExiting(false);
    }
  };

  const switchOperator = async () => {
    if (exiting) return;
    await exitOperator();
    openOperatorPicker();
  };

  return (
    <TouchScreenTemplate>
      <div
        style={{
          height: '100%',
          minHeight: 0,
          display: 'flex',
          flexDirection: 'column',
          gap: HMI_DESIGN_TOKENS.SECTION_GAP,
        }}
      >
        <div
          style={{
            ...STATION_PANEL_STYLE,
            minHeight: 64,
            paddingBlock: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
            flexWrap: 'wrap',
          }}
        >
          <Typography.Text
            style={{
              color: HMI_DESIGN_TOKENS.TEXT_PRIMARY,
              fontSize: 24,
              fontWeight: 600,
            }}
          >
            工位入口
          </Typography.Text>
          <Space size={20} wrap>
            <Space size={8}>
              <Typography.Text type="secondary">当前工位</Typography.Text>
              <Typography.Text strong>
                {workstation ? `${workstation.stationName}（${workstation.stationCode}）` : '未绑定'}
              </Typography.Text>
            </Space>
            <Space size={8}>
              <Typography.Text type="secondary">操作员</Typography.Text>
              <Typography.Text strong>{operator?.name || candidate?.name || '未确认'}</Typography.Text>
            </Space>
            <Space size={8}>
              <Typography.Text type="secondary">终端账号</Typography.Text>
              <Typography.Text strong>{terminalAccountName || '未读取'}</Typography.Text>
            </Space>
            <span
              style={{
                ...STATION_STATUS_PILL_STYLE,
                color: operator
                  ? HMI_DESIGN_TOKENS.STATUS_OK
                  : candidate
                    ? HMI_DESIGN_TOKENS.STATUS_WARNING
                    : HMI_DESIGN_TOKENS.TEXT_SECONDARY,
                borderColor: operator
                  ? HMI_DESIGN_TOKENS.STATUS_OK
                  : candidate
                    ? HMI_DESIGN_TOKENS.STATUS_WARNING
                    : HMI_DESIGN_TOKENS.BORDER,
              }}
            >
              {operator ? '已确认' : candidate ? '待确认' : '未确认'}
            </span>
          </Space>
        </div>

        {binding ? (
          <div style={STATION_PANEL_STYLE}>
            <StationBinder
              persist
              showCancel
              cancelText="返回"
              onCancel={() => setBinding(false)}
              onSelect={onBind}
              onBindSuccess={() => setBinding(false)}
            />
          </div>
        ) : null}

        <div className="hmi-station-home__main">

          <div
            style={{
              ...STATION_PANEL_STYLE,
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
              overflowY: 'auto',
            }}
          >
            <Typography.Title level={3} style={{ margin: 0 }}>
              {operator ? '当前操作员' : '员工身份确认'}
            </Typography.Title>
            {operator ? (
              <>
                <div
                  style={{
                    border: `1px solid ${HMI_DESIGN_TOKENS.STATUS_OK}`,
                    borderRadius: HMI_DESIGN_TOKENS.PANEL_RADIUS,
                    background: 'rgba(0, 200, 83, 0.10)',
                    padding: 16,
                  }}
                >
                  <Typography.Text
                    strong
                    style={{ display: 'block', fontSize: 28, color: HMI_DESIGN_TOKENS.TEXT_PRIMARY }}
                  >
                    {operator.name}
                  </Typography.Text>
                  <Typography.Text style={{ color: HMI_DESIGN_TOKENS.STATUS_OK }}>
                    已确认当前操作员
                  </Typography.Text>
                </div>
                <Button
                  {...touchButtonProps({ size: 'action' })}
                  loading={exiting}
                  onClick={() => void switchOperator()}
                >
                  更换操作员
                </Button>
              </>
            ) : candidate ? (
              <>
                <div
                  style={{
                    border: `1px solid ${HMI_DESIGN_TOKENS.STATUS_WARNING}`,
                    borderRadius: HMI_DESIGN_TOKENS.PANEL_RADIUS,
                    background: 'rgba(255, 179, 0, 0.10)',
                    padding: 16,
                  }}
                >
                  <Typography.Text
                    strong
                    style={{ display: 'block', fontSize: 28, color: HMI_DESIGN_TOKENS.TEXT_PRIMARY }}
                  >
                    {candidate.name}
                  </Typography.Text>
                  <Typography.Text style={{ color: HMI_DESIGN_TOKENS.STATUS_WARNING }}>
                    待员工码或刷脸确认
                  </Typography.Text>
                </div>
                <Input
                  size="large"
                  value={employeeCode}
                  placeholder="员工码"
                  style={{ minHeight: HMI_TOUCH.INPUT_HEIGHT, fontSize: 24 }}
                  onChange={(event) => setEmployeeCode(event.target.value)}
                  onPressEnter={() => void confirmByEmployeeCode()}
                />
                <Space wrap>
                  <Button
                    {...touchButtonProps({ variant: 'primary', size: 'action' })}
                    loading={confirming}
                    disabled={!workstation || !employeeCode.trim()}
                    onClick={() => void confirmByEmployeeCode()}
                  >
                    员工码确认
                  </Button>
                  <Button
                    {...touchButtonProps({ size: 'action' })}
                    disabled={!workstation}
                    onClick={() => navigate(withWorkstationId(`${STATION_ENTRY_PATH}/face`, workstation?.stationId))}
                  >
                    刷脸确认
                  </Button>
                </Space>
                <Space wrap>
                  <Button {...touchButtonProps({ size: 'action' })} onClick={openOperatorPicker}>
                    重新选择
                  </Button>
                  <Button
                    {...touchButtonProps({ size: 'action' })}
                    onClick={() => {
                      setStationOperatorCandidate(null);
                      setEmployeeCode('');
                    }}
                  >
                    取消候选
                  </Button>
                </Space>
                {!workstation ? (
                  <Typography.Text type="warning">未绑定工位，无法确认操作员</Typography.Text>
                ) : null}
              </>
            ) : (
              <>
                <Button
                  {...touchButtonProps({
                    variant: 'primary',
                    size: 'primary',
                    style: { minWidth: 240 },
                  })}
                  onClick={openOperatorPicker}
                >
                  选择员工
                </Button>
                <Typography.Text type="secondary">
                  点击“选择员工”查看可选员工；也可输入姓名缩小范围。
                </Typography.Text>
              </>
            )}
          </div>

          <div style={{ minHeight: 0, display: 'flex', flexDirection: 'column', gap: HMI_STATION_LAYOUT.SECTION_GAP }}>
            <div style={STATION_PANEL_STYLE}>
              <Typography.Title level={3} style={{ marginTop: 0 }}>
                工单快捷入口
              </Typography.Title>
              <Space.Compact style={{ width: '100%' }}>
                <Input
                  size="large"
                  value={scanDraft}
                  placeholder="扫描工单码 / 输入工单编号"
                  onChange={(event) => setScanDraft(event.target.value)}
                  onPressEnter={() => void openWorkOrderByCode()}
                  style={{ minHeight: HMI_TOUCH.INPUT_HEIGHT, fontSize: 24 }}
                />
                <Button
                  {...touchButtonProps({ variant: 'primary', size: 'action' })}
                  size="large"
                  loading={openingWorkOrder}
                  onClick={() => void openWorkOrderByCode()}
                >
                  查找并报工
                </Button>
                <Button
                  {...touchButtonProps({ size: 'action' })}
                  size="large"
                  disabled={openingWorkOrder}
                  onClick={() => void openWorkOrderByCode(true)}
                >
                  工单详情
                </Button>
              </Space.Compact>
              <Typography.Text type="secondary" style={{ display: 'block', marginTop: 12 }}>
                {operator ? '扫码用于定位工单，不改变当前操作员。' : '可先扫描工单；提交报工前仍需确认操作员。'}
              </Typography.Text>
            </div>

            <div
              style={{
                ...STATION_PANEL_STYLE,
                flex: 1,
                minHeight: 0,
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <Typography.Title level={3} style={{ marginTop: 0 }}>
                我的派工工单
              </Typography.Title>
              {operator ? (
                <>
                  <List
                    loading={ordersLoading}
                    style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}
                    dataSource={assignedOrders}
                    locale={{ emptyText: '暂无本人派工；可扫描工单码或输入编号查找' }}
                    renderItem={(row) => (
                      <div
                        className="hmi-list-item"
                        style={{
                          width: '100%',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: 16,
                        }}
                      >
                        <div style={{ minWidth: 0 }}>
                          <div className="hmi-list-item__title">{row.code}</div>
                          <div className="hmi-list-item__subtitle">
                            {row.productName} · {row.status === 'released' ? '已下达' : '执行中'} · 数量 {row.quantity}
                          </div>
                        </div>
                        <Space size={12}>
                          <Button
                            {...touchButtonProps({ variant: 'primary', size: 'action' })}
                            onClick={() => navigate(reportingPath(row.code))}
                          >
                            报工
                          </Button>
                          <Button
                            {...touchButtonProps({ size: 'action' })}
                            onClick={() => navigate(withWorkstationId(`${STATION_ENTRY_PATH}/work-orders/${row.id}/kiosk`, workstation?.stationId))}
                          >
                            详情
                          </Button>
                        </Space>
                      </div>
                    )}
                  />
                  {ordersHasMore ? (
                    <Button
                      block
                      size="large"
                      loading={ordersLoading}
                      onClick={() => setOrdersPage({ key: ordersKey, skip: ordersSkip + 50 })}
                      style={{ minHeight: HMI_TOUCH.ACTION_BTN_HEIGHT }}
                    >
                      加载更多
                    </Button>
                  ) : null}
                </>
              ) : (
                <div className="hmi-empty">
                  <div className="hmi-empty__text">确认操作员后显示本人派工</div>
                </div>
              )}
            </div>
          </div>
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'space-between',
            gap: 20,
            flexWrap: 'wrap',
            borderTop: `1px solid ${HMI_DESIGN_TOKENS.BORDER}`,
            paddingTop: 16,
          }}
        >
          <Space size={32} wrap>
            <Space direction="vertical" size={8}>
              <Typography.Text type="secondary">生产执行</Typography.Text>
              <Space wrap>
                {EXECUTION_LINKS.map((item, index) => (
                  <Button
                    key={item.to}
                    {...touchButtonProps({ variant: index === 0 ? 'primary' : 'default', size: 'action' })}
                    onClick={() => navigate(withWorkstationId(item.to, workstation?.stationId))}
                  >
                    {item.title}
                  </Button>
                ))}
              </Space>
            </Space>
            <Space direction="vertical" size={8}>
              <Typography.Text type="secondary">作业资料</Typography.Text>
              <Space wrap>
                {RESOURCE_LINKS.map((item) => (
                  <Button
                    key={item.to}
                    {...touchButtonProps({ size: 'action' })}
                    onClick={() => navigate(withWorkstationId(item.to, workstation?.stationId))}
                  >
                    {item.title}
                  </Button>
                ))}
              </Space>
            </Space>
            <Space direction="vertical" size={8}>
              <Typography.Text type="secondary">现场处理</Typography.Text>
              <Space wrap>
                {STATION_LINKS.map((item) => (
                  <Button
                    key={item.to}
                    {...touchButtonProps({ variant: item.title === '安灯' ? 'danger' : 'default', size: 'action' })}
                    onClick={() => navigate(withWorkstationId(item.to, workstation?.stationId))}
                  >
                    {item.title}
                  </Button>
                ))}
              </Space>
            </Space>
          </Space>
          <Space direction="vertical" size={8} style={{ alignItems: 'flex-end' }}>
            <Typography.Text type="secondary">终端管理</Typography.Text>
            <Button {...touchButtonProps({ size: 'action' })} onClick={() => setBinding(true)}>
              {workstation ? '切换工位' : '绑定工位'}
            </Button>
          </Space>
        </div>
      </div>

      <Drawer
        title="选择员工"
        placement="bottom"
        height="72vh"
        open={operatorPickerOpen}
        onClose={closeOperatorPicker}
        destroyOnHidden
      >
        <Input
          autoFocus
          size="large"
          value={operatorKeyword}
          placeholder="输入姓名关键词搜索员工"
          onChange={(event) => setOperatorKeyword(event.target.value)}
          style={{ minHeight: HMI_TOUCH.ACTION_BTN_HEIGHT }}
        />
        <List
          bordered
          loading={operatorsLoading}
          style={{ marginTop: 16, maxHeight: 'calc(72vh - 180px)', overflowY: 'auto' }}
          dataSource={operators}
          locale={{
            emptyText: operatorKeyword.trim()
              ? '暂无匹配员工，请更换关键词'
              : '暂无可选员工',
          }}
          renderItem={(item) => (
            <List.Item style={{ paddingInline: 0 }}>
              <Button
                block
                size="large"
                type={candidate?.id === item.value ? 'primary' : 'default'}
                onClick={() => pickOperator({ id: item.value, name: item.label })}
                style={{ minHeight: HMI_TOUCH.ACTION_BTN_HEIGHT }}
              >
                {item.label}
              </Button>
            </List.Item>
          )}
        />
        {operators.length < operatorTotal ? (
          <Button
            block
            size="large"
            loading={operatorsLoading}
            onClick={() => void loadOperators(operatorPage + 1, true)}
            style={{ marginTop: 12, minHeight: HMI_TOUCH.ACTION_BTN_HEIGHT }}
          >
            加载更多
          </Button>
        ) : null}
      </Drawer>
    </TouchScreenTemplate>
  );
}

function matchStationLeaf(pathname: string, leaf: string): boolean {
  return Boolean(matchPath({ path: `${STATION_ENTRY_PATH}/${leaf}`, end: true }, pathname));
}

export default function StationEntryPage() {
  const { message } = App.useApp();
  const { pathname } = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { workstation, operator, workOrderId, operationId } = useStationEntrySnapshot();
  const workstationQuery = searchParams.get('workstationId');
  const workstationId = workstation?.stationId ?? null;

  useEffect(() => {
    let cancelled = false;
    const restore = async () => {
      const memory = getStationWorkstation();
      if (memory && Number.isInteger(memory.stationId) && memory.stationId > 0) return;

      const queryText = workstationQuery?.trim() ?? '';
      const queryId = queryText ? positiveWorkstationId(queryText) : null;
      if (queryText && queryId == null) {
        message.warning('workstationId 无效');
      }
      if (queryId != null) {
        try {
          const info = await resolveWorkstation(queryId);
          if (cancelled) return;
          if (!info) {
            message.error('未找到该工位');
            setStationWorkstation(null);
            return;
          }
          setStationWorkstation(info, { notifyShell: true });
        } catch {
          if (!cancelled) message.error('加载工位失败');
        }
        return;
      }

      const saved = readSavedStation();
      if (saved) {
        if (!cancelled) setStationWorkstation(saved);
        return;
      }

      try {
        const shellId = await readShellWorkstationId();
        if (cancelled || shellId == null) return;
        const info = await resolveWorkstation(shellId);
        if (!cancelled && info) setStationWorkstation(info);
      } catch {
        if (!cancelled) message.error('加载工位失败');
      }
    };
    void restore();
    return () => {
      cancelled = true;
    };
  }, [message, workstationQuery]);

  useEffect(() => {
    if (typeof workstationId !== 'number' || !Number.isInteger(workstationId) || workstationId <= 0) {
      return;
    }
    if (workstationQuery === String(workstationId)) return;
    const next = new URLSearchParams(searchParams);
    next.set('workstationId', String(workstationId));
    setSearchParams(next, { replace: true });
  }, [workstationId, workstationQuery, searchParams, setSearchParams]);

  const workstationName = workstation?.stationName ?? null;

  if (matchStationLeaf(pathname, 'execution')) {
    return (
      <LazyModule
        page={StationExecutionPage}
        pageProps={{
          workstationId,
          operator,
          onSelectionChange: setStationExecutionSelection,
        }}
      />
    );
  }
  if (matchStationLeaf(pathname, 'reporting')) {
    return (
      <LazyModule
        page={StationReportingPage}
        pageProps={{
          operator,
          workstationId,
        }}
      />
    );
  }
  if (matchStationLeaf(pathname, 'andon')) {
    return (
      <LazyModule
        page={StationAndonPage}
        pageProps={{
          workstationId,
          workstationName,
          operatorId: operator?.id ?? null,
          operatorName: operator?.name ?? null,
        }}
      />
    );
  }
  if (matchStationLeaf(pathname, 'face')) {
    return (
      <LazyModule
        page={StationFaceHandoverPage}
        pageProps={{
          workstationId,
          workstationName,
          workOrderId,
          operationId,
          operatorUserId: operator?.id ?? null,
        }}
      />
    );
  }
  return <StationHome />;
}

export {
  getStationOperator,
  getStationWorkstation,
  getTerminalAccountName,
} from './session';
export type { StationOperator } from './session';
