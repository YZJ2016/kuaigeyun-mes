/**
 * 触屏工位入口。
 * 路径：/apps/kuaizhizao/production-execution/station
 */
import React, { Suspense, lazy, useEffect, useState } from 'react';
import { matchPath, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { Button, Input, Space, Typography, message } from 'antd';
import { TouchScreenTemplate } from '../../../../components/layout-templates/hmi';
import { HMI_DESIGN_TOKENS } from '../../../../theme/hmi';
import { STATION_ENTRY_PATH } from '../../../../utils/clientChannel';
import PageSkeleton from '../../../../components/page-skeleton';
import { touchButtonProps } from '../../../../components/touch-terminal';
import { getCurrentUser } from '../../../../services/auth';
import { searchUserIdOptions } from '../../../../utils/userDisplay';
import StationBinder, { getStationStorageKey, type StationInfo } from '../../components/StationBinder';
import { resolveWorkstation } from './resolveWorkstation';
import {
  getStationWorkstation,
  readShellWorkstationId,
  setStationExecutionSelection,
  setStationOperator,
  setStationWorkstation,
  setTerminalAccountName,
  useStationEntrySnapshot,
  type StationOperator,
} from './session';

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
    } catch {
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
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { workstation, operator, terminalAccountName } = useStationEntrySnapshot();
  const [binding, setBinding] = useState(false);
  const [operators, setOperators] = useState<Array<{ label: string; value: number }>>([]);
  const [operatorKeyword, setOperatorKeyword] = useState('');
  const [scanDraft, setScanDraft] = useState('');
  const [lastScan, setLastScan] = useState('');

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
  }, []);

  useEffect(() => {
    let cancelled = false;
    const keyword = operatorKeyword.trim();
    const timer = window.setTimeout(() => {
      searchUserIdOptions({
        pageSize: 200,
        isActive: true,
        hostResource: 'kuaizhizao:production-execution-terminal',
        ...(keyword ? { keyword } : {}),
      })
        .then((items) => {
          if (!cancelled) setOperators(items);
        })
        .catch((error: unknown) => {
          if (!cancelled) {
            message.error(error instanceof Error ? error.message : '加载操作员失败');
          }
        });
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [operatorKeyword]);

  const commitScan = (value: string) => {
    const text = value.trim();
    if (!text) return;
    setLastScan(text);
    setScanDraft('');
  };

  const openWorkOrderDetail = () => {
    const text = (scanDraft.trim() || lastScan).trim();
    if (!/^[1-9]\d*$/.test(text)) {
      message.info('工单详情地址需要数字工单 ID');
      return;
    }
    navigate(withWorkstationId(`${STATION_ENTRY_PATH}/work-orders/${text}/kiosk`, workstation?.stationId));
  };

  const onBind = (info: StationInfo) => {
    setStationWorkstation(info, { notifyShell: true });
    const next = new URLSearchParams(searchParams);
    next.set('workstationId', String(info.stationId));
    setSearchParams(next, { replace: true });
    setBinding(false);
  };

  const pickOperator = (next: StationOperator) => {
    setStationOperator(next);
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
            当前操作员：{operator ? operator.name : '未选择'}
          </Typography.Text>
          <br />
          <Typography.Text>
            当前工位：
            {workstation
              ? `${workstation.stationName}（${workstation.stationCode}）`
              : '未绑定'}
          </Typography.Text>
        </div>

        <Input
          autoFocus
          size="large"
          value={scanDraft}
          placeholder="扫码输入"
          onChange={(event) => setScanDraft(event.target.value)}
          onPressEnter={() => commitScan(scanDraft)}
        />
        <Typography.Text>最近扫码：{lastScan || '无'}</Typography.Text>

        <Space wrap>
          <Button {...touchButtonProps({ variant: 'primary', size: 'action' })} onClick={() => setBinding(true)}>
            {workstation ? '切换工位' : '绑定工位'}
          </Button>
          <Button {...touchButtonProps({ size: 'action' })} onClick={openWorkOrderDetail}>
            工单详情
          </Button>
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

        {binding ? (
          <div
            style={{
              background: 'rgba(0, 12, 28, 0.95)',
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

        <div>
          <Typography.Text>点选当前操作员</Typography.Text>
          <Input
            size="large"
            value={operatorKeyword}
            placeholder="按姓名筛选"
            onChange={(event) => setOperatorKeyword(event.target.value)}
            style={{ marginTop: 8, marginBottom: 12 }}
          />
          <Space wrap>
            {operators.map((item) => (
              <Button
                key={item.value}
                {...touchButtonProps({
                  variant: operator?.id === item.value ? 'primary' : 'default',
                  size: 'chip',
                })}
                onClick={() => pickOperator({ id: item.value, name: item.label })}
              >
                {item.label}
              </Button>
            ))}
          </Space>
        </div>
      </Space>
    </TouchScreenTemplate>
  );
}

function matchStationLeaf(pathname: string, leaf: string): boolean {
  return Boolean(matchPath({ path: `${STATION_ENTRY_PATH}/${leaf}`, end: true }, pathname));
}

export default function StationEntryPage() {
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
  }, [workstationQuery]);

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
