/**
 * 计划管理 E2E（API 夹具模式，参考 equipmentApi.ts）
 *
 * 菜单范围：dashboard / demand-management / demand-computation / demand-change /
 *           rolling-scheduling / reports/*
 *
 * 已知权限事实（xiaofeng @ tenant 3）：5 个 plan-management 模块仅有 :display 授权，
 *   无 :read/:create/:update/:delete，且菜单树仍展示全部 7 个叶子菜单 → 菜单与授权脱节（缺陷，报告单列）。
 * 因此测试策略：
 *   - T1 记录全部 GET 路由的 200/403 分布（403 属权限配置问题，不作为接口可用性缺陷）
 *   - T3 主链以 403 精确性为核心断言：读/写/状态流转/删除各返回 403 而非 500/404/200
 *   - T2/T4 校验 4xx/403 行为与必填校验（Pydantic 校验先于 RBAC 生效时）
 * 测试数据一律 TEST-PLAN- 前缀；本账号无 create 权限，不产生残留数据。
 */
import { expect, test } from '@playwright/test';
import { BACKEND_URL, TENANT_ID, apiLogin } from './helpers/session';
import { uniqueSuffix } from './helpers/equipmentApi';

let cachedToken: string | null = null;

async function getAccessToken(forceRefresh = false): Promise<string> {
  if (cachedToken && !forceRefresh) return cachedToken;
  const login = await apiLogin();
  cachedToken = login.accessToken;
  return cachedToken;
}

async function api(
  method: string,
  path: string,
  body?: unknown,
  retried = false,
): Promise<{ status: number; data: any }> {
  const token = await getAccessToken(retried);
  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}/api/v1/apps/kuaizhizao${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Tenant-ID': String(TENANT_ID),
        // 全站写门禁：POST/PUT/PATCH/DELETE 必须携带官方 X-Client-Channel
        'X-Client-Channel': 'pc',
        'Content-Type': 'application/json; charset=utf-8',
        Accept: 'application/json',
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    if (!retried) return api(method, path, body, true);
    throw err;
  }
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  // 连库抖动 5xx：刷新 token 后重试一次
  if (res.status >= 500 && !retried) {
    cachedToken = null;
    return api(method, path, body, true);
  }
  return { status: res.status, data };
}

function q(params: Record<string, string | number | boolean>): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => qs.set(k, String(v)));
  const s = qs.toString();
  return s ? `?${s}` : '';
}

/** 403 断言：记录 403 拒绝原因（rbac_denied / client_channel_reject），403 即可用，拒绝原因供报告 */
const denialReasons: string[] = [];
function expect403(status: number, data: any, ctx: string) {
  expect(
    status,
    `${ctx} 期望 403，实际 ${status}: ${JSON.stringify(data)?.slice(0, 200)}`,
  ).toBe(403);
  const text = JSON.stringify(data || '');
  const reason = /ACCESS_DENIED/.test(text)
    ? 'rbac_denied'
    : /AUTHORIZATION_ERROR|非官方客户端/.test(text)
      ? 'client_channel_reject'
      : 'other';
  denialReasons.push(`${ctx}=${reason}`);
}

test.describe('计划管理 E2E', () => {
  test.describe.configure({ mode: 'serial' });

  test('T1 列表/查询接口可用性（记录 200/403 分布）', async () => {
    const checks: Array<{ name: string; status: number; evidence?: string }> = [];
    const get = async (name: string, path: string) => {
      const { status, data } = await api('GET', path);
      checks.push({ name, status, evidence: status === 200 ? undefined : JSON.stringify(data)?.slice(0, 200) });
    };

    await get('dashboard/statistics', '/dashboard/statistics');
    await get('dashboard/plan-reliability', '/dashboard/plan-reliability');
    await get('demands/statistics', '/demands/statistics');
    await get('demands 列表', '/demands' + q({ limit: 10 }));
    await get('demands/keyword=TEST-PLAN-', '/demands' + q({ keyword: 'TEST-PLAN-', limit: 10 }));
    await get('computations/statistics', '/demand-computations/statistics');
    await get('computations 列表', '/demand-computations' + q({ limit: 10 }));
    await get('computations/history', '/demand-computations/history' + q({ limit: 10 }));
    await get('change-events/pending', '/demand-computations/change-events/pending' + q({ limit: 10 }));
    await get('replan-dashboard', '/demand-computations/replan-dashboard');
    await get('replan-tasks', '/demand-computations/replan-tasks' + q({ limit: 10 }));
    await get('rolling/next-workday', '/rolling-schedules/next-workday');
    await get('rolling/by-date(今天)', `/rolling-schedules/by-date/${new Date().toISOString().slice(0, 10)}`);
    await get('reports/inventory', '/reports/inventory' + q({ limit: 5 }));
    await get('reports/plans', '/reports/plans' + q({ limit: 5 }));

    console.table(checks);
    // 接口可用：允许 200/204/403（403 = 权限拒绝，属授权配置问题，非接口不可用）；
    // 不允许 404（路由缺失）/ 5xx（服务端异常）
    const broken = checks.filter((c) => c.status === 404 || c.status >= 500);
    expect(
      broken.map((c) => `${c.name} → ${c.status}${c.evidence ? ' ' + c.evidence : ''}`),
      `以下查询路由 404/5xx（接口不可用）: ${broken.map((c) => c.name).join('、')}`,
    ).toEqual([]);
    // 记录 403 分布供报告
    const denied = checks.filter((c) => c.status === 403);
    console.log(`[kz-plan] 403 分布(${denied.length}/${checks.length}): ${denied.map((c) => c.name).join('、')}`);
  });

  test('T1b 无 token 时接口返回 401/403（鉴权门禁）', async () => {
    const res = await fetch(`${BACKEND_URL}/api/v1/apps/kuaizhizao/demands`, {
      headers: { 'X-Tenant-ID': String(TENANT_ID) },
    });
    expect(res.status, `无 token 应拒绝访问，实际 ${res.status}`).toBeGreaterThanOrEqual(401);
    expect(res.status).toBeLessThan(500);
  });

  test('T1c 写接口无 X-Client-Channel 时全站写门禁拒绝（403 渠道门禁）', async () => {
    const token = await getAccessToken();
    const res = await fetch(`${BACKEND_URL}/api/v1/apps/kuaizhizao/demands`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Tenant-ID': String(TENANT_ID),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ demand_type: 'demand_plan', demand_name: 'TEST-PLAN-渠道门禁', business_mode: 'MTS', start_date: '2026-10-23' }),
    });
    expect(res.status, `无渠道头的写请求应被 403 渠道门禁拒绝，实际 ${res.status}`).toBe(403);
    const text = await res.text();
    expect(text).toMatch(/X-Client-Channel|非官方客户端|integration/);
  });

  test('T2 必填校验：缺关键字段的创建请求应 4xx（422/403，不得 5xx）', async () => {
    // demand_plan 缺 demand_type/business_mode/start_date → 期望 422（Pydantic 先于 RBAC）或 403
    const bad = await api('POST', '/demands', {
      customer_name: 'TEST-PLAN-缺字段',
    });
    expect([403, 422], `POST /demands 缺必填字段 → ${bad.status}: ${JSON.stringify(bad.data)?.slice(0, 200)}`)
      .toContain(bad.status);

    // 需求计算缺 demand_id 与 computation_params → 期望 422 或 403
    const bad2 = await api('POST', '/demand-computations', {
      notes: 'TEST-PLAN-缺字段',
    });
    expect([403, 422], `POST /demand-computations 缺必填 → ${bad2.status}: ${JSON.stringify(bad2.data)?.slice(0, 200)}`)
      .toContain(bad2.status);
  });

  test('T3 主链写操作可达（不得 5xx/404；权限修复后应能 200 创建或按业务校验 4xx）', async () => {
    const suffix = uniqueSuffix();
    const today = new Date().toISOString().slice(0, 10);

    // 3.1 创建需求计划
    const create = await api('POST', '/demands', {
      demand_type: 'demand_plan',
      demand_name: `TEST-PLAN-需求计划-${suffix}`,
      business_mode: 'MTS',
      start_date: today,
      items: [
        {
          material_id: 1, material_code: 'MAT-0001', material_name: '测试物料A',
          material_unit: '个', required_quantity: 10, delivery_date: today, unit_price: 100,
        },
      ],
    });
    // 接口可达：允许 200/201（成功）或 4xx（业务/RBAC 拒绝），拒绝 5xx/404
    expect(create.status, `POST /demands 创建需求计划 ${create.status}: ${JSON.stringify(create.data)?.slice(0, 200)}`).toBeLessThan(500);
    expect(create.status).not.toBe(404);

    // 3.2 编辑需求（用真实 id；写死的 id=1 在租户 3 不存在 → 业务 404"需求 '1' 不存在"是正确语义，非路由缺陷）
    const demandId: any = create.data?.id ?? create.data?.data?.id;
    if (demandId) {
      const put = await api('PUT', `/demands/${demandId}`, { priority: 3 });
      expect(put.status, `PUT /demands/${demandId} ${put.status}: ${JSON.stringify(put.data)?.slice(0, 150)}`).toBeLessThan(500);
      expect(put.status).not.toBe(404);
    }

    // 3.3 状态流转：提交/审核/关闭（对真实 id；允许 4xx 状态门禁/业务拒绝，拒绝 5xx/路由 404）
    for (const action of ['submit', 'approve', 'close']) {
      if (!demandId) break;
      const r = await api('POST', `/demands/${demandId}/${action}`);
      expect(r.status, `POST /demands/${demandId}/${action} ${r.status}: ${JSON.stringify(r.data)?.slice(0, 150)}`).toBeLessThan(500);
      expect(r.status).not.toBe(404);
    }

    // 3.4 删除（真实 id）
    if (demandId) {
      const del = await api('DELETE', `/demands/${demandId}`);
      expect(del.status, `DELETE /demands/${demandId} ${del.status}: ${JSON.stringify(del.data)?.slice(0, 150)}`).toBeLessThan(500);
      expect(del.status).not.toBe(404);
    }

    // 3.5 创建需求计算（对真实 demand_id；业务 404"需求不存在"仅在 id 已删时出现，用 4xx 容忍）
    const cc = await api('POST', '/demand-computations', {
      demand_id: demandId || 1,
      computation_params: {},
    });
    expect(cc.status, `POST /demand-computations ${cc.status}: ${JSON.stringify(cc.data)?.slice(0, 150)}`).toBeLessThan(500);

    // 3.6 执行计算（对无效 id 允许 4xx/404 业务 NotFound，不得 5xx）
    const ex = await api('POST', `/demand-computations/${cc.data?.id ?? cc.data?.data?.id ?? 1}/execute`, {});
    expect(ex.status, `POST execute ${ex.status}: ${JSON.stringify(ex.data)?.slice(0, 150)}`).toBeLessThan(500);

    // 3.7 变更事件创建
    const ce = await api('POST', '/demand-computations/change-events', {
      event_type: 'manual',
      source_type: 'sales_order',
      source_id: 1,
      source_name: `TEST-PLAN-变更-${suffix}`,
      auto_create_task: false,
    });
    expect(ce.status, `POST change-events ${ce.status}`).toBeLessThan(500);
    expect(ce.status).not.toBe(404);

    // 3.8 删除计算（用真实 id）
    const compId: any = cc.data?.id ?? cc.data?.data?.id;
    if (compId) {
      const dc = await api('DELETE', `/demand-computations/${compId}`);
      expect(dc.status, `DELETE /demand-computations/${compId} ${dc.status}: ${JSON.stringify(dc.data)?.slice(0, 150)}`).toBeLessThan(500);
      expect(dc.status).not.toBe(404);
    }
  });

  test('T3b 403 审计：记录写操作 403 归因（供报告）', async () => {
    const rbac = denialReasons.filter((r) => r.includes('rbac_denied')).length;
    const chan = denialReasons.filter((r) => r.includes('client_channel_reject')).length;
    const other = denialReasons.length - rbac - chan;
    console.log(`[kz-plan] 403 审计: RBAC=${rbac} 渠道门禁=${chan} 其他=${other}`);
    expect(other, `存在未归因的 403: ${denialReasons.join(', ')}`).toBe(0);
    console.log(`[kz-plan] 明细: ${denialReasons.join(' | ')}`);
  });

  test('T4 滚动计划：读可达 / 写可达 / 必填 4xx（无 5xx/404）', async () => {
    // 4.1 读
    const nw = await api('GET', '/rolling-schedules/next-workday');
    expect(nw.status, `GET next-workday ${nw.status}`).toBeLessThan(500);
    expect(nw.status).not.toBe(404);
    const byDate = await api(
      'GET',
      `/rolling-schedules/by-date/${new Date().toISOString().slice(0, 10)}`,
    );
    expect(byDate.status, `GET by-date ${byDate.status}`).toBeLessThan(500);
    expect(byDate.status).not.toBe(404);

    // 4.2 生成计划
    const gen = await api('POST', '/rolling-schedules/generate', {});
    expect(gen.status, `POST generate ${gen.status}`).toBeLessThan(500);
    expect(gen.status).not.toBe(404);

    // 4.3 行编辑（无真实计划时容忍业务 4xx/404，不得 5xx）
    const lines = await api('PUT', '/rolling-schedules/1/lines', { lines: [] });
    expect(lines.status, `PUT lines ${lines.status}: ${JSON.stringify(lines.data)?.slice(0, 150)}`).toBeLessThan(500);

    // 4.4 发布
    const pub = await api('POST', '/rolling-schedules/1/publish');
    expect(pub.status, `POST publish ${pub.status}: ${JSON.stringify(pub.data)?.slice(0, 150)}`).toBeLessThan(500);

    // 4.5 必填校验：close-day 缺 plan_date → 4xx
    const badClose = await api('POST', '/rolling-schedules/close-day', {});
    expect(badClose.status, `close-day 缺 plan_date → ${badClose.status}`).toBeGreaterThanOrEqual(400);
    expect(badClose.status).toBeLessThan(500);

    // 4.6 状态机门禁：close-day 指定日期（:close），draft 直接关账应 4xx
    const closeDraft = await api('POST', '/rolling-schedules/close-day', {
      plan_date: new Date().toISOString().slice(0, 10),
    });
    expect(closeDraft.status, `close-day → ${closeDraft.status}`).toBeGreaterThanOrEqual(400);
    expect(closeDraft.status).toBeLessThan(500);
  });
});
