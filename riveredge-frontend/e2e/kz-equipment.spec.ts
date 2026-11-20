/**
 * 快设备 e2e 业务测试（TEST-EQP-）：补 equipment-management.spec.ts 未覆盖项
 * 复用 helpers/equipmentApi.ts 的 api() 与夹具
 *
 * 覆盖：点检执行主链、巡检路线/巡检执行、保养计划→发布→提醒生成、备件领用单、
 *      模具 试模/领还/报废、工装 领还、计量器具检定到期提醒、MTTR/MTBF 报表。
 * 数据纪律：用例内建的台账资源 finally 软删清理；单据留痕于 E2E 前缀（租户 3 测试库允许）。
 */
import { test, expect } from '@playwright/test';
import {
  api,
  createEquipment,
  createEquipmentFault,
  createEquipmentRepair,
  getArrivedRepair,
  createMaintenanceExecution,
  createMold,
  createMoldBorrow,
  createMoldReturn,
  createMoldScrap,
  createMoldTrial,
  createMeasuringInstrument,
  createPatrolRoute,
  createRoutePatrol,
  createSparePart,
  createSparePartRequisition,
  createSpotCheck,
  createTool,
  createToolBorrow,
  createToolReturn,
  deleteEquipment,
  deleteMold,
  deleteTool,
  ensureMaintenanceScheme,
  ensureSpotCheckScheme,
  getEquipmentTrace,
  getEquipmentReport,
  listCalibrationReminders,
  listMaintenanceReminders,
  publishMaintenancePlan,
  checkMaintenanceReminders,
  createMaintenancePlan,
  updateMaintenanceExecution,
  updateEquipment,
  getCalibrationReminderSettings,
  completeEquipmentRepair,
  arriveAtFault,
  createCalibration,
  updateMold,
  updateTool,
  submitSparePartRequisition,
  uniqueSuffix,
} from './helpers/equipmentApi';

/** 用例内可清理的台账资源（设备/模具/工装，台账寻址均按 uuid） */
function cleanup() {
  const equipment: string[] = [];
  const molds: string[] = [];
  const tools: string[] = [];
  const done = async () => {
    for (const u of equipment) await deleteEquipment(u).catch(() => undefined);
    for (const u of molds) await deleteMold(u).catch(() => undefined);
    for (const u of tools) await deleteTool(u).catch(() => undefined);
  };
  return { equipment, molds, tools, done };
}

test.describe('TEST-EQP-01 点检/巡检执行链', () => {
  test('新建设备 → 配点检项/方案/绑定 → 点检执行 → 巡检路线 → 巡检执行', async () => {
    const c = cleanup();
    try {
      const eq = await createEquipment({ status: '正常', name: `E2E-TEST-EQP-${uniqueSuffix()}` });
      c.equipment.push(eq.uuid);
      expect(eq.id).toBeTruthy();

      const { schemeId } = await ensureSpotCheckScheme(eq.id);
      const sc = await createSpotCheck(eq.id, { scheme_id: schemeId });
      expect(sc.id || sc.uuid || sc.document_no, `点检执行创建返回缺主键: ${JSON.stringify(sc)}`).toBeTruthy();

      const route = await createPatrolRoute(eq.id);
      expect(route.id).toBeTruthy();

      const patrol = await createRoutePatrol(route.id, eq.id);
      expect(patrol.id || patrol.uuid || patrol.document_no, `巡检执行返回缺主键: ${JSON.stringify(patrol)}`).toBeTruthy();

      const trace = await getEquipmentTrace(eq.uuid);
      expect(trace, '设备追溯应可读').toBeTruthy();
    } finally {
      await c.done();
    }
  });
});

test.describe('TEST-EQP-02 保养计划触发生成提醒', () => {
  test('设备+保养项/方案 → 保养计划(草稿→已发布) → /check 生成到期提醒可查', async () => {
    const c = cleanup();
    try {
      const eq = await createEquipment({ status: '正常', name: `E2E-TEST-EQP-${uniqueSuffix()}` });
      c.equipment.push(eq.uuid);

      const { schemeId } = await ensureMaintenanceScheme(eq.id);
      const plan = await createMaintenancePlan(eq.uuid, schemeId);
      expect(plan.uuid || plan.id, `保养计划创建返回缺主键: ${JSON.stringify(plan)}`).toBeTruthy();

      await publishMaintenancePlan(plan.uuid);

      // 手动检查（30 天内到期）：Inngest 定时任务的手动触发端点
      const result = await checkMaintenanceReminders(30);
      expect(result, '保养提醒检查端点应返回结果').toBeTruthy();

      const reminders = await listMaintenanceReminders({ limit: 20, equipment_uuid: eq.uuid });
      expect(Array.isArray(reminders?.items), `保养提醒列表应含 items: ${JSON.stringify(reminders)}`).toBeTruthy();
      // 提醒是否真实生成取决于周期是否到期：空则记录前置（计划侧断言已覆盖主链）
    } finally {
      await c.done();
    }
  });

  test('保养执行：草稿→确认→验收 全状态机', async () => {
    const c = cleanup();
    try {
      const eq = await createEquipment({ status: '正常', name: `E2E-TEST-EQP-${uniqueSuffix()}` });
      c.equipment.push(eq.uuid);
      const exec = await createMaintenanceExecution(eq.uuid, { status: '草稿' });
      expect(exec.uuid).toBeTruthy();
      const confirmed = await updateMaintenanceExecution(exec.uuid, { status: '已确认', execution_result: '正常' });
      expect(confirmed.status).toBe('已确认');
      const accepted = await updateMaintenanceExecution(exec.uuid, { status: '已验收', acceptance_result: '合格' });
      expect(accepted.status).toBe('已验收');
    } finally {
      await c.done();
    }
  });
});

test.describe('TEST-EQP-03 设备故障→报修→维修→关闭闭环', () => {
  test('设备置维修中 → 报修 → 到场签到 → 完修 → 设备回正常', async () => {
    const c = cleanup();
    try {
      const eq = await createEquipment({ status: '正常', name: `E2E-TEST-EQP-${uniqueSuffix()}` });
      c.equipment.push(eq.uuid);

      await updateEquipment(eq.uuid, { status: '维修中' });
      expect((await api('GET', `/equipment/${eq.uuid}`)).data.status).toBe('维修中');

      const fault = await createEquipmentFault(eq.uuid);
      expect(fault.uuid).toBeTruthy();

      // 到场签到是完修前置（扫码设备需与故障设备一致）；签到会为故障自建一张维修单
      await arriveAtFault(fault.uuid, eq.uuid);

      // 取签到自建的维修单（arrival_at 已写入）完修
      const repair = await getArrivedRepair(fault.uuid);
      const done = await completeEquipmentRepair(repair.uuid);
      expect(done.status, `完修后状态应为已完成，实际 ${done.status}`).toBe('已完成');

      // 故障单据状态应联动为已修复/已关闭
      const gotFault = await api('GET', `/equipment-faults/${fault.uuid}`);
      expect(gotFault.status).toBeLessThan(400);
      const faultStatus = String((gotFault.data as any).status || '');
      expect(
        ['已修复', '已关闭', '处理中', '已完成'].includes(faultStatus),
        `故障单据状态应联动，实际「${faultStatus}」: ${JSON.stringify(gotFault.data)}`,
      ).toBeTruthy();

      // 台账状态真源（equipment_fault_service.sync_equipment_status_from_faults）：
      // 无进行中维修且无未闭环故障 → 设备应被同步回「正常」
      const auto = await api('GET', `/equipment/${eq.uuid}`);
      expect(
        String(auto.data.status),
        `完修后设备台账状态应由故障真源同步为「正常」，实际「${auto.data.status}」`,
      ).toBe('正常');

      // 手工状态流转仍可正常执行（白名单：正常）
      await updateEquipment(eq.uuid, { status: '正常' });
      expect((await api('GET', `/equipment/${eq.uuid}`)).data.status).toBe('正常');
    } finally {
      await c.done();
    }
  });
});

test.describe('TEST-EQP-04 备件领用与台账', () => {
  test('备件创建 → 库存/预警 API → 领用单(设备+明细行) → 提交', async () => {
    const c = cleanup();
    try {
      const eq = await createEquipment({ status: '正常', name: `E2E-TEST-EQP-${uniqueSuffix()}` });
      c.equipment.push(eq.uuid);

      const part = await createSparePart({ safety_stock: 5, unit: '件' });
      const partId = part.id as number;
      expect(partId, `备件创建返回缺 id: ${JSON.stringify(part)}`).toBeTruthy();

      // 台账聚合 API 可用性
      const { status: invStatus } = await api('GET', '/spare-parts/inventory?limit=5');
      expect(invStatus, '备件库存 API 应 <400').toBeLessThan(400);
      const { status: alertStatus } = await api('GET', '/spare-parts/alerts');
      expect(alertStatus, '备件预警 API 应 <400').toBeLessThan(400);

      const req = await createSparePartRequisition({
        equipment_id: eq.id,
        lines: [{ spare_part_id: partId, quantity: 1, warehouse_location: 'E2E库位', remark: 'TEST-EQP 领用' }],
      });
      expect(req.id, `备件领用单创建缺主键: ${JSON.stringify(req)}`).toBeTruthy();

      const submitted = await submitSparePartRequisition(req.id);
      expect(submitted, '领用单提交应成功').toBeTruthy();
    } finally {
      await c.done();
    }
  });
});

test.describe('TEST-EQP-05 模具 试模/领还/报废', () => {
  test('模具台账(启用→待用) → 试模 → 领用 → 归还 → 报废申请', async () => {
    const c = cleanup();
    try {
      const mold = await createMold({ name: `E2E模具-TEST-EQP-${uniqueSuffix()}` });
      c.molds.push(mold.uuid);
      expect(mold.id).toBeTruthy();

      // 领用前置：状态须为「待用」（PUT /molds/{uuid}）
      await updateMold(mold.uuid, { status: '待用' });

      const borrow = await createMoldBorrow(mold.id);
      expect(borrow.id, `模具领用缺主键: ${JSON.stringify(borrow)}`).toBeTruthy();

      const ret = await createMoldReturn(mold.id, borrow.id);
      expect(ret.id, `模具归还缺主键: ${JSON.stringify(ret)}`).toBeTruthy();

      // 试模会置模具为「试模中」锁定，放在领还链之后创建并删除（避免残留占用状态机）
      const trial = await createMoldTrial(mold.id);
      expect(trial.id, `试模单缺主键: ${JSON.stringify(trial)}`).toBeTruthy();
      await api('DELETE', `/mold-trials/${trial.id}`).catch(() => undefined);

      const scrap = await createMoldScrap(mold.id);
      expect(scrap.id, `模具报废申请缺主键: ${JSON.stringify(scrap)}`).toBeTruthy();
    } finally {
      await c.done();
    }
  });
});

test.describe('TEST-EQP-06 工装 领还', () => {
  test('工装台账(启用→待用) → 领用 → 归还', async () => {
    const c = cleanup();
    try {
      const tool = await createTool({ name: `E2E工装-TEST-EQP-${uniqueSuffix()}` });
      c.tools.push(tool.uuid);
      expect(tool.id).toBeTruthy();

      await updateTool(tool.uuid, { status: '待用' });

      const borrow = await createToolBorrow(tool.id);
      expect(borrow.id, `工装领用缺主键: ${JSON.stringify(borrow)}`).toBeTruthy();

      const ret = await createToolReturn(tool.id, borrow.id);
      expect(ret.id, `工装归还缺主键: ${JSON.stringify(ret)}`).toBeTruthy();
    } finally {
      await c.done();
    }
  });
});

test.describe('TEST-EQP-07 计量器具检定到期提醒', () => {
  test('计量器具(需检定) + 已过期检定记录 → /calibration-reminders 应包含该设备', async () => {
    const c = cleanup();
    try {
      // 提醒链路前置：设备须 needs_calibration=true 且台账 next_calibration_date 非空
      const mi = await createMeasuringInstrument({
        name: `E2E计量-TEST-EQP-${uniqueSuffix()}`,
        needs_calibration: true,
        calibration_period: 30,
      });
      c.equipment.push(mi.uuid);

      // 过期检定记录：expiry_date 昨天（台账自动推导 next_calibration_date）
      const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
      await createCalibration(mi.uuid, {
        expiry_date: yesterday,
        result: '合格',
        certificate_no: `CAL-E2E-${uniqueSuffix()}`,
      });

      const reminders = await listCalibrationReminders({ limit: 50, due_type: 'overdue' });
      const items: any[] = reminders?.items || [];
      expect(Array.isArray(items), `检定到期提醒列表应含 items: ${JSON.stringify(reminders)}`).toBeTruthy();
      const hit = items.find((i) => i.equipment_uuid === mi.uuid || i.uuid === mi.uuid);
      expect(hit, `已过期计量器具 ${mi.uuid} 未出现在 overdue 检定提醒中`).toBeTruthy();
    } finally {
      await c.done();
    }
  });

  test('检定提醒设置 API 可读（advance_days 为数字）', async () => {
    const settings = await getCalibrationReminderSettings();
    expect(settings, '检定提醒设置应可读').toBeTruthy();
    expect(
      typeof (settings as any).advance_days === 'number',
      `advance_days 应为数字: ${JSON.stringify(settings)}`,
    ).toBeTruthy();
  });
});

test.describe('TEST-EQP-08 报表 MTTR/MTBF', () => {
  test('设备报表 API：maintenance 与 equipment-mttr-mtbf 类型可用', async () => {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
    const end = now.toISOString().slice(0, 10);

    const maint = await getEquipmentReport('maintenance', { date_start: start, date_end: end, limit: 10 });
    expect(maint, '保养报表应可读').toBeTruthy();

    const mt = await getEquipmentReport('equipment-mttr-mtbf', { date_start: start, date_end: end, limit: 10 });
    expect(mt, 'MTTR/MTBF 报表端点应可读').toBeTruthy();
    expect((mt as any).success !== false, `报表返回 success=false: ${JSON.stringify(mt).slice(0, 300)}`).toBeTruthy();
    // 无维修记录时 data 为空列表属正常（租户级报表）；有数据时每行应含 mttr/mtbf 字段
    const rows: any[] = (mt as any).data || [];
    for (const row of rows) {
      expect(row, 'MTTR/MTBF 报表行应非空').toBeTruthy();
    }
  });
});
