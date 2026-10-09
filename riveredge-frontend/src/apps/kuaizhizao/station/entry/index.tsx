/**
 * 触屏工位入口。
 * 路径：/apps/kuaizhizao/production-execution/station
 */
import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import { matchPath, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { App, Button, Drawer, Input, List, Space, Typography } from 'antd';
import { listExecutableWorkOrders, type StationWorkOrder } from '../execution/api';
import { TouchScreenTemplate } from '../../../../components/layout-templates/hmi';
import { HMI_DESIGN_TOKENS, HMI_TOUCH } from '../../../../theme/hmi';
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

const KIOSK_LINKS: Array<{ title: string; to: string }> = [
  { title: '报工', to: `${STATION_ENTRY_PATH}/reporting` },
  { title: 'SOP', to: `${STATION_ENTRY_PATH}/sop-viewer/kiosk` },
  { title: '图纸', to: `${STATION_ENTRY_PATH}/drawing-viewer/kiosk` },
  { title: '程序查看', to: `${STATION_ENTRY_PATH}/program-viewer/kiosk` },
];

const MODULE_LINKS: Array<{ title: string; to: string }> = [
  { title: '执行', to: `${STATION_ENTRY_PATH}/execution` },
  { title: '安灯', to: `${STATION_ENTRY_PATH}/andon` },
  { title: '刷脸交接', to: `${STATION_ENTRY_PATH}/face` },
];

const OPERATOR_PAGE_SIZE = 20;

function ModuleNotReady() {
  return (
    <TouchScreenTemplate title="工位入口">
      <Typography.Title level={3}>模块未就绪</Typography.Title>
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
    <TouchScreenTemplate title="工位入口">
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div>
          <Typography.Text>
            终端账号：{terminalAccountName || '未读取到登录账号'}
          </Typography.Text>
          <br />
          <Typography.Text>
            当前操作员：{operator ? operator.name : '未确认'}
          </Typography.Text>
          {candidate ? (
            <>
              <br />
              <Typography.Text>
                候选人：{candidate.name}（待刷脸或员工码确认）
              </Typography.Text>
            </>
          ) : null}
          {operator ? (
            <>
              {' '}
              <Button
                {...touchButtonProps({
                  size: 'header',
                  style: { height: HMI_TOUCH.HEADER_BTN_HEIGHT },
                })}
                loading={exiting}
                onClick={() => void switchOperator()}
              >
                更换操作员
              </Button>
            </>
          ) : null}
          <br />
          <Typography.Text>
            当前工位：
            {workstation
              ? `${workstation.stationName}（${workstation.stationCode}）`
              : '未绑定'}
          </Typography.Text>
        </div>

        <Space wrap>
          <Button {...touchButtonProps({ size: 'action' })} onClick={() => setBinding(true)}>
            {workstation ? '切换工位' : '绑定工位'}
          </Button>
        </Space>
        {binding ? (
          <div
            style={{
              background: HMI_DESIGN_TOKENS.BG_PANEL,
              borderRadius: HMI_DESIGN_TOKENS.PANEL_RADIUS,
              border: `1px solid ${HMI_DESIGN_TOKENS.BORDER}`,
              padding: HMI_DESIGN_TOKENS.SECTION_GAP,
            }}
          >
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

        {!operator ? (
          <div>
            <Typography.Title level={3}>员工身份确认</Typography.Title>
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
            {candidate ? (
              <Space direction="vertical" size="middle" style={{ marginTop: 16, width: '100%' }}>
                <Typography.Text>
                  候选人 {candidate.name}：请输入员工码确认，或到「刷脸交接」页刷脸确认。
                </Typography.Text>
                <Space wrap>
                  <Input
                    size="large"
                    value={employeeCode}
                    placeholder="员工码"
                    style={{ width: 240 }}
                    onChange={(event) => setEmployeeCode(event.target.value)}
                    onPressEnter={() => void confirmByEmployeeCode()}
                  />
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
              </Space>
            ) : (
              <Typography.Text type="secondary" style={{ display: 'block', marginTop: 12 }}>
                点击“选择员工”查看可选员工；也可输入姓名缩小范围。
              </Typography.Text>
            )}
          </div>
        ) : (
          <div>
            <Typography.Title level={3}>我的派工工单</Typography.Title>
            <List
              bordered
              loading={ordersLoading}
              style={{ maxHeight: 420, overflowY: 'auto' }}
              dataSource={assignedOrders}
              locale={{ emptyText: '暂无本人派工；可扫描工单码或输入编号查找' }}
              renderItem={(row) => (
                <List.Item actions={[
                  <Button key="report" type="primary" size="large" onClick={() => navigate(reportingPath(row.code))}>报工</Button>,
                  <Button key="detail" size="large" onClick={() => navigate(withWorkstationId(`${STATION_ENTRY_PATH}/work-orders/${row.id}/kiosk`, workstation?.stationId))}>详情</Button>,
                ]}>
                  <List.Item.Meta title={row.code} description={`${row.productName} · ${row.status === 'released' ? '已下达' : '执行中'} · 数量 ${row.quantity}`} />
                </List.Item>
              )}
            />
            {ordersHasMore ? (
              <Button size="large" loading={ordersLoading} onClick={() => setOrdersPage({ key: ordersKey, skip: ordersSkip + 50 })}>
                加载更多
              </Button>
            ) : null}
          </div>
        )}

        <div>
          <Typography.Title level={3}>扫码或输入工单编号</Typography.Title>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              size="large"
              value={scanDraft}
              placeholder="扫描工单码 / 输入工单编号"
              onChange={(event) => setScanDraft(event.target.value)}
              onPressEnter={() => void openWorkOrderByCode()}
            />
            <Button type="primary" size="large" loading={openingWorkOrder} onClick={() => void openWorkOrderByCode()}>
              查找并报工
            </Button>
            <Button size="large" disabled={openingWorkOrder} onClick={() => void openWorkOrderByCode(true)}>
              工单详情
            </Button>
          </Space.Compact>
        </div>

        <Space wrap>
          {KIOSK_LINKS.map((item) => (
            <Button
              key={item.to}
              {...touchButtonProps({ size: 'action' })}
              onClick={() => navigate(withWorkstationId(item.to, workstation?.stationId))}
            >
              {item.title}
            </Button>
          ))}
          {MODULE_LINKS.map((item) => (
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
