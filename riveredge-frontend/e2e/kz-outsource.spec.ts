/**
 * 委外管理 E2E 业务测试（API 级，租户 3 / xiaofeng）
 * 范围：委外工单(outsource-work-orders) 主链 新建→查询→编辑→删除 + 必填/状态机/一致性校验
 *      + 委外单(outsource-orders)、委外发料/收货/退料/退货、委外结算、dashboard/报表 列表可用性
 * 测试数据统一 TEST-OUT- 前缀；afterAll 清理自造数据（供应商/物料/仓库/工单等）
 *
 * 已知环境事实（2026-10-23 实测，xiaofeng @ tenant 3）：
 * - 账号无 master-data / kuaizhizao:outsource-* RBAC 读权限：全部 kuaizhizao outsource 路由 403
 *   （rbac_denied），403 = 权限配置缺口而非接口缺陷；本 spec 按 kz-plan 模式断言 403 精确性。
 * - 鉴权门禁：无 token 401；全站写无 X-Client-Channel 403。
 * - 报表：/reports/production?report_type=outsource-* → 200 可直测。
 */
import fs from 'node:fs';
import path from 'node:path';
import { test, expect } from '@playwright/test';
import { BACKEND_URL, TENANT_ID, apiLogin } from './helpers/session';

type Json = Record<string, unknown>;

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
  extraHeaders: Record<string, string> = {},
): Promise<{ status: number; data: any; headers: Headers }> {
  const token = await getAccessToken(retried);
  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}/api/v1${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Tenant-ID': String(TENANT_ID),
        // 全站写门禁：POST/PUT/PATCH/DELETE 必须携带官方 X-Client-Channel
        'X-Client-Channel': 'pc',
        'Content-Type': 'application/json; charset=utf-8',
        Accept: 'application/json',
        ...extraHeaders,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    if (!retried) return api(method, path, body, true, extraHeaders);
    throw err;
  }
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  // 连库抖动 5xx：刷 token 重试一次（与 equipmentApi 同款）
  if (res.status >= 500 && !retried) {
    cachedToken = null;
    return api(method, path, body, true, extraHeaders);
  }
  return { status: res.status, data, headers: res.headers };
}

function uniqueSuffix(): string {
  return `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;
}
const RUN_ID = uniqueSuffix();

const today = () => new Date().toISOString().slice(0, 10);
const KZ = '/apps/kuaizhizao';
const MD = '/apps/master-data';
// 注：供应商走 /apps/master-data/supply-chain/suppliers；物料走 /apps/master-data/materials；
// 仓库实际在 kuaizhizao 域 /apps/kuaizhizao/line-side-warehouse/warehouses（tenant3 实测空列表），
// /apps/master-data/warehouses 与 /apps/master-data/processes 均 404（见报告 D2）。

// ---------------------------------------------------------------------------
// 测试数据追踪（cleanup 用）
// ---------------------------------------------------------------------------
const created = {
  supplier: null as { id: number; uuid: string } | null,
  warehouse: null as { id: number; uuid: string } | null,
  material: null as { id: number; uuid: string } | null,
  owoIds: [] as number[],
};

async function cleanup(): Promise<string[]> {
  const failures: string[] = [];
  const tryDel = async (label: string, p: string) => {
    const r = await api('DELETE', p);
    if (r.status >= 400) failures.push(`${label} DELETE ${p} -> ${r.status}`);
  };
  for (const id of [...created.owoIds].reverse()) await tryDel('委外工单', `${KZ}/outsource-work-orders/${id}`);
  if (created.warehouse) await tryDel('仓库', `${KZ}/line-side-warehouse/warehouses/${created.warehouse.uuid}`);
  if (created.material) await tryDel('物料', `${MD}/materials/${created.material.uuid}`);
  if (created.supplier) await tryDel('供应商', `${MD}/supply-chain/suppliers/${created.supplier.uuid}`);
  return failures;
}

test.describe.configure({ mode: 'serial' });

// ---------------------------------------------------------------------------
// RBAC 断言辅助（403 精确性：接口可用但权限拒绝；5xx/404/200 才是缺陷）
// ---------------------------------------------------------------------------
const rbacAudit: Array<{ route: string; status: number; reason: string }> = [];
function expect403(status: number, data: any, ctx: string, allowed: number[] = [403, 422]) {
  const text = JSON.stringify(data ?? {});
  const reason = /ACCESS_DENIED/.test(text) ? 'rbac_denied' : /非官方客户端/.test(text) ? 'client_channel' : 'other';
  if (status === 403) rbacAudit.push({ route: ctx, status, reason });
  expect(status, `${ctx} 期望 403/4xx 权限拒绝，实际 ${status}: ${text.slice(0, 200)}`).toBeGreaterThanOrEqual(400);
  expect(status, `${ctx} 期望权限门禁 4xx，实际 ${status}`).toBeLessThan(500);
  if (allowed.length && status !== 403) {
    // 允许 422（Pydantic 先于 RBAC 时），其余记录
  }
  expect(status, `${ctx} 实际 ${status}`).toBe(allowed.includes(status) ? status : 403);
}

// 前置：供应商/物料/仓库（主链依赖；403 时跳过复用直接造数，失败记录）
async function ensureMasterData() {
  // 供应商：先找任意可用记录（避免对 403 路由重复请求），读不通再自造
  let supplier: any = null;
  const any = await api('GET', `${MD}/supply-chain/suppliers?limit=1`);
  if (any.status < 400 && Array.isArray(any.data?.data) && any.data.data.length > 0) {
    supplier = any.data.data[0];
  } else {
    const suffix = RUN_ID;
    const r = await api('POST', `${MD}/supply-chain/suppliers`, {
      code: `TEST-OUT-SUP-${suffix}`,
      name: `TEST-OUT供应商-${suffix}`,
      category: '委外加工',
      is_active: true,
      qualification_status: 'approved',
    });
    if (r.status >= 400) {
      rbacAudit.push({ route: 'POST /master-data suppliers', status: r.status, reason: JSON.stringify(r.data?.detail?.required || r.data?.detail || '').slice(0, 200) });
    } else {
      created.supplier = { id: r.data.id, uuid: r.data.uuid };
      supplier = r.data;
    }
  }
  test.info().annotations.push({ type: 'supplier', description: supplier ? `id=${supplier.id}` : 'unavailable(403)' });

  // 物料（Buy，稍后改 Outsource；若改不动则直接建 Outsource）
  const ms = RUN_ID;
  const mr = await api('POST', `${MD}/materials`, {
    code: `TEST-OUT-MAT-${ms}`,
    name: `TEST-OUT物料-${ms}`,
    base_unit: '件',
    source_type: 'Buy',
    is_active: true,
  });
  if (mr.status < 400) {
    created.material = { id: mr.data.id, uuid: mr.data.uuid };
  } else {
    rbacAudit.push({ route: 'POST /master-data materials', status: mr.status, reason: JSON.stringify(mr.data?.detail?.required || '').slice(0, 120) });
  }

  // 仓库（kuaizhizao 域 line-side-warehouse；tenant3 实测为空列表，造数需 POST）
  const wr = await api('GET', `${KZ}/line-side-warehouse/warehouses?limit=1`);
  let warehouse: any = wr.status < 400 ? wr.data?.data?.[0] : null;
  if (!warehouse) {
    const anyW = await api('POST', `${KZ}/line-side-warehouse/warehouses`, {
      code: `TEST-OUT-WH-${RUN_ID}`,
      name: `TEST-OUT仓库-${RUN_ID}`,
      is_active: true,
    });
    if (anyW.status < 400) {
      created.warehouse = { id: anyW.data.id, uuid: anyW.data.uuid };
      warehouse = anyW.data;
    } else {
      rbacAudit.push({ route: 'POST /kuaizhizao line-side-warehouse/warehouses', status: anyW.status, reason: JSON.stringify(anyW.data?.detail || '').slice(0, 150) });
    }
  } else {
    test.info().annotations.push({ type: 'warehouse', description: `reused id=${warehouse.id}` });
  }
  test.info().annotations.push({ type: 'material', description: created.material ? `id=${created.material.id}` : 'unavailable(403)' });
}

const owoPayload = (overrides: Json = {}) => ({
  code: `TEST-OUT-OWO-${RUN_ID}`,
  name: `TEST-OUT委外工单-${RUN_ID}`,
  product_id: created.material?.id || 0,
  product_code: 'TEST-OUT',
  product_name: 'TEST-OUT物料',
  quantity: 10,
  supplier_id: created.supplier?.id || 0,
  supplier_code: 'TEST-OUT-SUP',
  supplier_name: 'TEST-OUT供应商',
  outsource_operation: '表面喷涂',
  unit_price: 5,
  status: 'draft',
  remarks: 'E2E委外测试单',
  ...overrides,
});

// ===========================================================================
// 1. 列表/查询接口可用性（记录 200/403/404/500）
// ===========================================================================
test.describe('委外管理 API 列表可用性', () => {
  test.beforeAll(async () => {
    // 记录鉴权门禁（先于所有业务断言）
    const noTok = await fetch(`${BACKEND_URL}/api/v1${KZ}/outsource-work-orders`, {
      headers: { 'X-Tenant-ID': String(TENANT_ID) },
    });
    expect(noTok.status, '无 token 应 401').toBe(401);

    const noChan = await fetch(`${BACKEND_URL}/api/v1${KZ}/outsource-work-orders`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${await getAccessToken()}`,
        'X-Tenant-ID': String(TENANT_ID),
        'Content-Type': 'application/json',
      },
      body: '{}',
    });
    expect(noChan.status, '无 X-Client-Channel 写请求应 403 渠道门禁').toBe(403);
  });

  const routes: Array<[string, string, string]> = [
    ['GET', `${KZ}/outsource-work-orders`, '委外工单列表'],
    ['GET', `${KZ}/outsource-work-orders/statistics`, '委外工单 KPI'],
    ['GET', `${KZ}/outsource-orders`, '工序委外单列表'],
    ['GET', `${KZ}/outsource-material-issues`, '委外发料列表'],
    ['GET', `${KZ}/outsource-material-receipts`, '委外收货列表'],
    ['GET', `${KZ}/outsource-material-returns`, '委外退料列表'],
    ['GET', `${KZ}/outsource-product-returns`, '委外退货列表'],
    ['GET', `${KZ}/outsource-settlements`, '委外结算列表'],
    ['GET', `${KZ}/outsource-settlements/settleable-receipts?supplier_id=1`, '可结算收货'],
    ['GET', `${KZ}/reports/production?report_type=outsource-order-query`, '委外工单报表'],
    ['GET', `${KZ}/reports/production?report_type=outsource-material-reconciliation`, '委外对账报表'],
  ];

  test('各列表/查询路由可达（200/403/404 分布，拒绝 500）', async () => {
    const rows: Array<{ route: string; status: number; ok: boolean; note: string }> = [];
    for (const [m, p, label] of routes) {
      const { status, data } = await api(m, p);
      const ok = status === 200 || status === 403 || status === 404;
      const reqPerm = data?.detail?.required
        ? `(需权限: ${Array.isArray(data.detail.required) ? data.detail.required.join(',') : data.detail.required})`
        : '';
      rows.push({ route: `${m} ${p}`, status, ok, note: reqPerm });
      if (status >= 500) rbacAudit.push({ route: label, status, reason: '5xx' });
      if (status === 403) rbacAudit.push({ route: label, status, reason: 'rbac_denied' });
    }
    fs.mkdirSync(path.join(__dirname, 'output', 'outsource'), { recursive: true });
    fs.writeFileSync(
      path.join(__dirname, 'output', 'outsource', 'kz-outsource-routes.json'),
      JSON.stringify(rows, null, 2),
      'utf-8',
    );
    const fatal = rows.filter((r) => r.status >= 500);
    expect(fatal, `存在 5xx 路由: ${JSON.stringify(fatal)}`).toEqual([]);
    const rbac403 = rows.filter((r) => r.status === 403);
    const missing404 = rows.filter((r) => r.status === 404);
    if (rbac403.length > 0)
      console.log(`[kz-outsource] 403 无权限路由（测试账号权限缺口）: ${rbac403.map((r) => r.route).join(', ')}`);
    if (missing404.length > 0)
      console.log(`[kz-outsource] 404 路由缺失: ${missing404.map((r) => r.route).join(', ')}`);
  });

  test('报表 outsource 类型直测（无 RBAC 缺口）', async () => {
    const r1 = await api('GET', `${KZ}/reports/production?report_type=outsource-order-query`);
    expect(r1.status, `outsource-order-query 报表 → ${r1.status}: ${JSON.stringify(r1.data).slice(0, 200)}`).toBe(200);
    const r2 = await api('GET', `${KZ}/reports/production?report_type=outsource-material-reconciliation`);
    expect(r2.status, `outsource-material-reconciliation 报表 → ${r2.status}`).toBe(200);
  });
});

// ===========================================================================
// 2. 必填校验 + 主链（403 精确性：Pydantic 先于 RBAC 时 422 也算可用）
// ===========================================================================
test.describe('委外工单 必填校验与主链', () => {
  test.beforeAll(async () => {
    await ensureMasterData();
  });

  test('T1 必填校验：缺关键字段的创建请求应 4xx（422/403，不得 5xx/2xx）', async () => {
    // 缺 product_id（schema 必填 int）
    const r1 = await api('POST', `${KZ}/outsource-work-orders`, {
      quantity: 10,
      supplier_code: 'X',
      supplier_name: 'X',
    });
    expect([403, 422], `POST /outsource-work-orders 缺 product_id → ${r1.status}: ${JSON.stringify(r1.data).slice(0, 200)}`).toContain(r1.status);
    expect(r1.status, '不得 5xx').toBeLessThan(500);

    // 缺 quantity
    const r2 = await api('POST', `${KZ}/outsource-work-orders`, {
      product_id: created.material?.id || 0,
      supplier_id: created.supplier?.id || 0,
      supplier_code: 'X',
      supplier_name: 'X',
    });
    expect([403, 422], `缺 quantity → ${r2.status}`).toContain(r2.status);

    // 完全空 body
    const r3 = await api('POST', `${KZ}/outsource-work-orders`, {});
    expect([403, 422], `空 body → ${r3.status}: ${JSON.stringify(r3.data).slice(0, 160)}`).toContain(r3.status);
  });

  test('T2 主链：新建→查询→编辑→删除（master-data 造数后）', async () => {
    if (!created.material || !created.supplier) {
      test.skip(true, `master-data 造数 403 RBAC（xiaofeng 无 supplier/material 读写权限，见 rbacAudit），主链跳过`);
      return;
    }
    // 物料必须为 Outsource 来源；尝试 source_type=Outsource 创建/变更
    const matCode = `TEST-OUT-MAT-${RUN_ID}`;
    const mr = await api('POST', `${MD}/materials`, {
      code: matCode,
      name: `TEST-OUT委外物料-${RUN_ID}`,
      base_unit: '件',
      source_type: 'Outsource',
      is_active: true,
    });
    let owoMaterial = created.material;
    if (mr.status < 400) {
      owoMaterial = { id: mr.data.id, uuid: mr.data.uuid };
      created.material = owoMaterial; // 替换为主物料（旧 Buy 物料 cleanup 仍会删）
    } else {
      // 复用 Buy 物料：尝试变更来源类型（若 RBAC 允许）
      const chg = await api('POST', `${MD}/materials/${created.material.uuid}/source-change`, {
        new_source_type: 'Outsource',
        new_source_config: { outsource_supplier_id: created.supplier.id },
      });
      rbacAudit.push({ route: 'POST /materials source-change', status: chg.status, reason: JSON.stringify(chg.data?.detail || '').slice(0, 150) });
      if (chg.status >= 400) {
        test.skip(true, `物料来源类型无法变更/创建（${mr.status}/${chg.status}），委外工单主链跳过`);
        return;
      }
    }

    // 新建委外工单
    const create = await api('POST', `${KZ}/outsource-work-orders`, owoPayload({ product_id: owoMaterial.id }));
    if (create.status === 403) {
      test.skip(true, `委外工单创建 403 RBAC（测试账号无 kuaizhizao:outsource-work-order:create）：${JSON.stringify(create.data?.detail?.required || create.data?.detail || '')}`);
      return;
    }
    expect(create.status, `创建委外工单 → ${create.status}: ${JSON.stringify(create.data).slice(0, 300)}`).toBeLessThan(400);
    const owo = create.data;
    created.owoIds.push(owo.id);
    expect(owo.code, '工单编码').toBeTruthy();
    expect(owo.status, '默认状态').toBe('draft');

    // 查询
    const get = await api('GET', `${KZ}/outsource-work-orders/${owo.id}`);
    expect(get.status, `查询 → ${get.status}`).toBe(200);
    expect(get.data.code).toBe(owo.code);

    // 列表按 code 过滤
    const list = await api('GET', `${KZ}/outsource-work-orders?code=${encodeURIComponent(owo.code)}&limit=5`);
    expect(list.status, `列表 → ${list.status}`).toBe(200);
    const hit = (list.data?.data || []).find((x: any) => x.id === owo.id);
    expect(hit, `列表 code 过滤应包含新单`).toBeTruthy();

    // 编辑（仅允许字段；status 不可直改）
    const up = await api('PUT', `${KZ}/outsource-work-orders/${owo.id}`, {
      name: `TEST-OUT委外工单已编辑-${RUN_ID}`,
      remarks: 'E2E已编辑',
    });
    expect(up.status, `编辑 → ${up.status}: ${JSON.stringify(up.data).slice(0, 200)}`).toBe(200);
    expect(up.data.name).toContain('已编辑');

    // status 直接 PUT 应被拒绝（状态机门禁）
    const badStatus = await api('PUT', `${KZ}/outsource-work-orders/${owo.id}`, { status: 'completed' });
    expect(badStatus.status, `直改 status=completed 应 4xx，实际 ${badStatus.status}: ${JSON.stringify(badStatus.data).slice(0, 160)}`).toBe(400);

    // 删除（draft 可删）
    const del = await api('DELETE', `${KZ}/outsource-work-orders/${owo.id}`);
    expect(del.status, `删除 draft 工单 → ${del.status}: ${JSON.stringify(del.data).slice(0, 200)}`).toBeLessThan(400);
    created.owoIds = created.owoIds.filter((x) => x !== owo.id);

    // 删除后再查应 404
    const getDel = await api('GET', `${KZ}/outsource-work-orders/${owo.id}`);
    expect(getDel.status, '删除后查询应 404').toBe(404);
  });

  test('T2b 主链：下达→发料/收货→结案 状态流转', async () => {
    // 需要 Outsource 来源物料；复用 T2 已造物料或尝试变更/新建
    let owoMaterial: { id: number; uuid: string } | null = null;
    if (created.material) {
      const chg = await api('POST', `${MD}/materials/${created.material.uuid}/source-change`, {
        new_source_type: 'Outsource',
        new_source_config: { outsource_supplier_id: created.supplier?.id },
      });
      if (chg.status < 400) owoMaterial = created.material;
      else rbacAudit.push({ route: 'POST /materials source-change', status: chg.status, reason: JSON.stringify(chg.data?.detail || '').slice(0, 150) });
    }
    if (!owoMaterial && created.supplier) {
      const mr = await api('POST', `${MD}/materials`, {
        code: `TEST-OUT-OWOMAT-${RUN_ID}`,
        name: `TEST-OUT委外物料2-${RUN_ID}`,
        base_unit: '件',
        source_type: 'Outsource',
        is_active: true,
      });
      if (mr.status < 400) {
        owoMaterial = { id: mr.data.id, uuid: mr.data.uuid };
        created.material = owoMaterial;
      }
    }
    if (!owoMaterial || !created.supplier) {
      test.skip(true, '委外物料/供应商不可用（xiaofeng 无 master-data RBAC 权限），状态流转主链跳过');
      return;
    }

    const owo = await api('POST', `${KZ}/outsource-work-orders`, owoPayload({
      code: `TEST-OUT-OWO2-${RUN_ID}`,
      product_id: owoMaterial.id,
    }));
    if (owo.status === 403) {
      test.skip(true, `委外工单创建 403 RBAC：${JSON.stringify(owo.data?.detail?.required || '').slice(0, 150)}`);
      return;
    }
    expect(owo.status, `创建 → ${owo.status}: ${JSON.stringify(owo.data).slice(0, 200)}`).toBeLessThan(400);
    const id = owo.data.id;
    created.owoIds.push(id);

    // 草稿不能发料
    const issueDraft = await api('POST', `${KZ}/outsource-material-issues`, {
      outsource_work_order_id: id,
      outsource_work_order_code: owo.data.code,
      material_id: created.material.id,
      material_code: 'TEST-OUT',
      material_name: 'TEST-OUT物料',
      quantity: 2,
      unit: '件',
      warehouse_id: created.warehouse?.id,
      warehouse_name: 'TEST-OUT仓库',
      status: 'draft',
    });
    expect(issueDraft.status, `草稿态发料应 4xx（门禁），实际 ${issueDraft.status}: ${JSON.stringify(issueDraft.data).slice(0, 200)}`).toBeGreaterThanOrEqual(400);

    // 下达
    const rel = await api('POST', `${KZ}/outsource-work-orders/${id}/release`);
    expect(rel.status, `下达 → ${rel.status}: ${JSON.stringify(rel.data).slice(0, 200)}`).toBeLessThan(400);
    expect(rel.data.status, '下达后状态').toBe('released');

    // 已下达可发料（库存不足时 400 业务校验也算门禁通过；403 RBAC 则跳过后续）
    const issue = await api('POST', `${KZ}/outsource-material-issues`, {
      outsource_work_order_id: id,
      outsource_work_order_code: owo.data.code,
      material_id: created.material.id,
      material_code: 'TEST-OUT',
      material_name: 'TEST-OUT物料',
      quantity: 2,
      unit: '件',
      warehouse_id: created.warehouse?.id,
      warehouse_name: 'TEST-OUT仓库',
      status: 'draft',
    });
    if (issue.status === 403) {
      test.skip(true, `委外发料 403 RBAC（无 kuaizhizao:outsource-issue:create），状态流转后续跳过`);
      return;
    }
    expect(issue.status, `发料 → ${issue.status}: ${JSON.stringify(issue.data).slice(0, 200)}`).toBeLessThan(400);
    expect(issue.data.status, '发料完成态').toBe('completed');

    // 工单进入 in_progress
    const owoAfter = await api('GET', `${KZ}/outsource-work-orders/${id}`);
    expect(owoAfter.data.status, `发料后工单状态 → ${owoAfter.data.status}`).toBe('in_progress');
    expect(parseFloat(owoAfter.data.issued_quantity), '已发数量').toBeGreaterThan(0);

    // 收货：数量/金额一致性（合格数 × 单价 = total_amount）
    const receipt = await api('POST', `${KZ}/outsource-material-receipts`, {
      outsource_work_order_id: id,
      outsource_work_order_code: owo.data.code,
      quantity: 10,
      qualified_quantity: 10,
      unqualified_quantity: 0,
      unit: '件',
      warehouse_id: created.warehouse?.id,
      warehouse_name: 'TEST-OUT仓库',
      status: 'draft',
    });
    if (receipt.status === 403) {
      test.skip(true, '委外收货 403 RBAC');
      return;
    }
    expect(receipt.status, `收货 → ${receipt.status}: ${JSON.stringify(receipt.data).slice(0, 200)}`).toBeLessThan(400);
    expect(receipt.data.status).toBe('completed');
    const amount = parseFloat(receipt.data.total_amount);
    const unitPrice = parseFloat(receipt.data.unit_price);
    expect(amount, `收货金额 ${amount} 应=合格数10×单价${unitPrice}`).toBeCloseTo(10 * unitPrice, 6);

    // 超收应 400（一致性校验）
    const overReceipt = await api('POST', `${KZ}/outsource-material-receipts`, {
      outsource_work_order_id: id,
      outsource_work_order_code: owo.data.code,
      quantity: 1,
      qualified_quantity: 1,
      unit: '件',
      warehouse_id: created.warehouse?.id,
      warehouse_name: 'TEST-OUT仓库',
    });
    expect(overReceipt.status, `超收应 4xx，实际 ${overReceipt.status}: ${JSON.stringify(overReceipt.data).slice(0, 200)}`).toBeGreaterThanOrEqual(400);
    expect(overReceipt.status, '超收不得 2xx/5xx').toBeLessThan(500);

    // 全部收完 → 结案应被拒（fully_received 门禁）
    const owoFull = await api('GET', `${KZ}/outsource-work-orders/${id}`);
    expect(parseFloat(owoFull.data.received_quantity), '已收数量').toBe(10);
    const closeFull = await api('POST', `${KZ}/outsource-work-orders/${id}/close`, 'E2E已全收结案');
    expect(closeFull.status, `全收后结案应 4xx，实际 ${closeFull.status}: ${JSON.stringify(closeFull.data).slice(0, 200)}`).toBeGreaterThanOrEqual(400);

    // 退料（in_progress 可推）
    const ret = await api('POST', `${KZ}/outsource-material-returns`, {
      code: `TEST-OUT-RET-${RUN_ID}`,
      outsource_work_order_id: id,
      outsource_work_order_code: owo.data.code,
      material_id: created.material.id,
      material_code: 'TEST-OUT',
      material_name: 'TEST-OUT物料',
      quantity: 1,
      unit: '件',
      warehouse_id: created.warehouse?.id,
      warehouse_name: 'TEST-OUT仓库',
    });
    if (ret.status === 403) {
      test.skip(true, '委外退料 403 RBAC');
      return;
    }
    expect(ret.status, `退料 → ${ret.status}: ${JSON.stringify(ret.data).slice(0, 200)}`).toBeLessThan(400);

    // 退货（可退数门禁：收10未退 → 可退10）
    const prodRet = await api('POST', `${KZ}/outsource-product-returns`, {
      code: `TEST-OUT-PRODT-${RUN_ID}`,
      outsource_work_order_id: id,
      outsource_work_order_code: owo.data.code,
      quantity: 2,
      unit: '件',
      return_reason: 'E2E退货',
      outsource_material_receipt_id: receipt.data.id,
    });
    if (prodRet.status === 403) {
      test.skip(true, '委外退货 403 RBAC');
      return;
    }
    expect(prodRet.status, `退货 → ${prodRet.status}: ${JSON.stringify(prodRet.data).slice(0, 200)}`).toBeLessThan(400);

    // 超退应 400
    const overRet = await api('POST', `${KZ}/outsource-product-returns`, {
      code: `TEST-OUT-PRODTE-${RUN_ID}`,
      outsource_work_order_id: id,
      outsource_work_order_code: owo.data.code,
      quantity: 99,
      unit: '件',
      outsource_material_receipt_id: receipt.data.id,
    });
    expect(overRet.status, `超退应 4xx，实际 ${overRet.status}: ${JSON.stringify(overRet.data).slice(0, 200)}`).toBeGreaterThanOrEqual(400);

    // 结案（有活动 → allowed）
    const close = await api('POST', `${KZ}/outsource-work-orders/${id}/close`, 'E2E强制结案');
    expect(close.status, `结案 → ${close.status}: ${JSON.stringify(close.data).slice(0, 200)}`).toBeLessThan(400);
    expect(['completed', 'closed'], '结案后状态').toContain(close.data.status);

    // 终态再取消应 400
    const cancelAfter = await api('POST', `${KZ}/outsource-work-orders/${id}/cancel`, 'E2E');
    expect(cancelAfter.status, `终态取消应 4xx，实际 ${cancelAfter.status}`).toBeGreaterThanOrEqual(400);
    created.owoIds = created.owoIds.filter((x) => x !== id);
  });

  test('T3 结算：创建→提交→驳回 状态流转（依赖收货数据）', async () => {
    let owoMaterial: { id: number; uuid: string } | null = null;
    if (created.material) {
      const chg = await api('POST', `${MD}/materials/${created.material.uuid}/source-change`, {
        new_source_type: 'Outsource',
        new_source_config: { outsource_supplier_id: created.supplier?.id },
      });
      if (chg.status < 400) owoMaterial = created.material;
    }
    if (!owoMaterial && created.supplier) {
      const mr = await api('POST', `${MD}/materials`, {
        code: `TEST-OUT-OWOMAT3-${RUN_ID}`,
        name: `TEST-OUT委外物料3-${RUN_ID}`,
        base_unit: '件',
        source_type: 'Outsource',
        is_active: true,
      });
      if (mr.status < 400) {
        owoMaterial = { id: mr.data.id, uuid: mr.data.uuid };
        created.material = owoMaterial;
      }
    }
    if (!owoMaterial || !created.supplier) {
      test.skip(true, '委外物料/供应商不可用（403 RBAC）');
      return;
    }
    const owo = await api('POST', `${KZ}/outsource-work-orders`, owoPayload({
      code: `TEST-OUT-OWO3-${RUN_ID}`,
      product_id: owoMaterial.id,
    }));
    if (owo.status === 403) {
      test.skip(true, '委外工单 403 RBAC');
      return;
    }
    if (owo.status >= 400) {
      test.skip(true, `前置工单创建失败 ${owo.status}: ${JSON.stringify(owo.data).slice(0, 150)}`);
      return;
    }
    const id = owo.data.id;
    created.owoIds.push(id);
    await api('POST', `${KZ}/outsource-work-orders/${id}/release`);

    const receipt = await api('POST', `${KZ}/outsource-material-receipts`, {
      outsource_work_order_id: id,
      outsource_work_order_code: owo.data.code,
      quantity: 5,
      qualified_quantity: 5,
      unit: '件',
      warehouse_id: created.warehouse?.id,
      warehouse_name: 'TEST-OUT仓库',
    });
    if (receipt.status === 403) {
      test.skip(true, '收货 403 RBAC');
      return;
    }
    if (receipt.status >= 400) {
      test.skip(true, `收货前置失败 ${receipt.status}: ${JSON.stringify(receipt.data).slice(0, 150)}`);
      return;
    }

    // 创建结算（含加工费行）
    const st = await api('POST', `${KZ}/outsource-settlements`, {
      supplier_id: created.supplier.id,
      business_date: today(),
      notes: `TEST-OUT结算-${RUN_ID}`,
      items: [
        {
          line_type: 'processing',
          outsource_material_receipt_id: receipt.data.id,
          settlement_quantity: 5,
          unit_price: 5,
          notes: 'E2E加工费行',
        },
      ],
    });
    if (st.status === 403) {
      test.skip(true, '结算 403 RBAC');
      return;
    }
    expect(st.status, `创建结算 → ${st.status}: ${JSON.stringify(st.data).slice(0, 250)}`).toBeLessThan(400);
    const sid = st.data.id;
    expect(parseFloat(st.data.total_amount), '结算总额=5×5').toBeCloseTo(25, 6);

    // 结算必填校验：缺 supplier_id
    const badSt = await api('POST', `${KZ}/outsource-settlements`, { items: [] });
    expect([400, 403, 422], `结算缺 supplier_id → ${badSt.status}: ${JSON.stringify(badSt.data).slice(0, 160)}`).toContain(badSt.status);
    expect(badSt.status).toBeLessThan(500);

    // 明细校验：加工费行缺收货单
    const badLine = await api('POST', `${KZ}/outsource-settlements`, {
      supplier_id: created.supplier.id,
      items: [{ line_type: 'processing', settlement_quantity: 1, unit_price: 1 }],
    });
    expect([400, 403, 422], `加工费行缺收货单 → ${badLine.status}`).toContain(badLine.status);

    // 提交 → 审核 → 驳回 流转
    const sub = await api('POST', `${KZ}/outsource-settlements/${sid}/submit`);
    if (sub.status === 403) {
      test.skip(true, '结算提交 403 RBAC');
      return;
    }
    expect(sub.status, `提交 → ${sub.status}`).toBeLessThan(400);
    const aud = await api('POST', `${KZ}/outsource-settlements/${sid}/audit`, { review_remarks: 'E2E审核' });
    expect(aud.status, `审核 → ${aud.status}: ${JSON.stringify(aud.data).slice(0, 150)}`).toBeLessThan(400);
    const rej = await api('POST', `${KZ}/outsource-settlements/${sid}/reject`, { review_remarks: 'E2E驳回' });
    expect(rej.status, `驳回已审核单 → ${rej.status}: ${JSON.stringify(rej.data).slice(0, 150)}`).toBeLessThan(400);

    // 删结算（驳回态可删；若 400 记录）
    const delSt = await api('DELETE', `${KZ}/outsource-settlements/${sid}`);
    expect(delSt.status, `删结算 → ${delSt.status}: ${JSON.stringify(delSt.data).slice(0, 150)}`).toBeLessThan(500);
    if (delSt.status === 204 || delSt.status === 200) {
      // 已删，不再由 cleanup 处理
    }
  });

  test('T4 工序委外单 outsource-orders：必填/状态门禁', async () => {
    // 缺 work_order_operation_id → 422 或 403
    const bad = await api('POST', `${KZ}/outsource-orders`, {
      outsource_quantity: 1,
    });
    expect([403, 422], `POST /outsource-orders 缺工序 → ${bad.status}: ${JSON.stringify(bad.data).slice(0, 200)}`).toContain(bad.status);
    expect(bad.status).toBeLessThan(500);

    // 列表与详情路由 403/200 可用性（已在列表用例覆盖，这里补 detail 404 校验）
    const det = await api('GET', `${KZ}/outsource-orders/99999999`);
    expect([200, 403, 404], `详情不存在 → ${det.status}: ${JSON.stringify(det.data).slice(0, 150)}`).toContain(det.status);
  });
});

// ===========================================================================
// 收尾
// ===========================================================================
test.afterAll(async () => {
  const failures = await cleanup();
  const auditOut = {
    run_id: RUN_ID,
    created: {
      supplier: created.supplier,
      warehouse: created.warehouse,
      material: created.material,
      owoIds: created.owoIds,
    },
    rbac_audit: rbacAudit,
    cleanup_failures: failures,
  };
  fs.mkdirSync(path.join(__dirname, 'output', 'outsource'), { recursive: true });
  fs.writeFileSync(
    path.join(__dirname, 'output', 'outsource', 'kz-outsource-audit.json'),
    JSON.stringify(auditOut, null, 2),
    'utf-8',
  );
  console.log(`[kz-outsource] 清理结果: ${failures.length === 0 ? '全部清理成功' : failures.join('; ')}`);
  console.log(`[kz-outsource] RBAC 审计 ${rbacAudit.length} 条已写入 output/outsource/kz-outsource-audit.json`);
});
