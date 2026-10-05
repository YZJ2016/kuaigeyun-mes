"use strict";

const PATH = {
	scan: '<path d="M4 8V5a1 1 0 0 1 1-1h3"/><path d="M16 4h3a1 1 0 0 1 1 1v3"/><path d="M20 16v3a1 1 0 0 1-1 1h-3"/><path d="M8 20H5a1 1 0 0 1-1-1v-3"/><rect x="8" y="8" width="8" height="8" rx="1"/>',
	user: '<circle cx="12" cy="8" r="3"/><path d="M5.5 19.2c1.2-2.6 3.4-3.7 6.5-3.7s5.3 1.1 6.5 3.7"/>',
	file: '<path d="M7 3.5h7l4 4V20a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1z"/><path d="M14 3.5V8h4"/><path d="M8.5 12.5h7M8.5 16h5"/>',
	list: '<path d="M9 7h10M9 12h10M9 17h10"/><path d="M5 7h.01M5 12h.01M5 17h.01"/>',
	history: '<circle cx="12" cy="12" r="8"/><path d="M12 8v4.5l3 2"/>',
	check: '<path d="M5 12.5 9.2 17 19 7"/>',
	"check-circle": '<circle cx="12" cy="12" r="8"/><path d="M8.5 12.2 11 14.7 15.8 9.5"/>',
	"close-circle": '<circle cx="12" cy="12" r="8"/><path d="M9 9l6 6M15 9l-6 6"/>',
	inbox: '<path d="M3.5 13 5.2 5.5A1 1 0 0 1 6.2 4.8h11.6a1 1 0 0 1 1 .7L20.5 13"/><path d="M3.5 13h4.2l1.3 2.2h6l1.3-2.2h4.2V19a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1z"/>',
	"plus-square": '<rect x="4.5" y="4.5" width="15" height="15" rx="2"/><path d="M12 8v8M8 12h8"/>',
	"minus-square": '<rect x="4.5" y="4.5" width="15" height="15" rx="2"/><path d="M8 12h8"/>',
	warning: '<path d="M12 4.5 21 19.5H3z"/><path d="M12 10v4.5"/><path d="M12 17.2h.01"/>',
	chart: '<path d="M4 19.5h16"/><path d="M7 16v-4M12 16V7M17 16v-6"/>',
	export: '<path d="M12 4v10"/><path d="M8 8l4-4 4 4"/><path d="M5 14.5V19a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-4.5"/>',
	rollback: '<path d="M8 8H4.5V4.5"/><path d="M4.8 8.2A7.5 7.5 0 1 1 6.2 17"/>',
	shopping: '<circle cx="9" cy="19" r="1"/><circle cx="17" cy="19" r="1"/><path d="M3.5 5h2l1.6 9.2a1 1 0 0 0 1 .8h8.6a1 1 0 0 0 1-.8L20 8H6"/>',
	truck: '<path d="M3 7h11v8H3z"/><path d="M14 10h4l3 3v2h-7z"/><circle cx="7" cy="17.5" r="1.4"/><circle cx="17" cy="17.5" r="1.4"/>',
	audit: '<rect x="6" y="3.5" width="12" height="17" rx="2"/><path d="M9 8h6M9 12h6M9 16h3"/>',
	search: '<circle cx="11" cy="11" r="6"/><path d="M16 16l4 4"/>',
	swap: '<path d="M7 7h11l-3-3"/><path d="M17 17H6l3 3"/>',
	bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2H4.5z"/><path d="M10 18.5a2 2 0 0 0 4 0"/>',
	shield: '<path d="M12 3.5 19 6.5v5.2c0 4.2-2.8 6.8-7 8.3-4.2-1.5-7-4.1-7-8.3V6.5z"/>',
	link: '<path d="M10 13a4 4 0 0 0 6 .4l2-2a4 4 0 0 0-5.6-5.7L11 7"/><path d="M14 11a4 4 0 0 0-6-.4l-2 2a4 4 0 0 0 5.6 5.7L13 17"/>',
	tool: '<path d="M14.5 6.5a3.2 3.2 0 0 0-4.4 4.4L4 17l3 3 6.1-6.1a3.2 3.2 0 0 0 4.4-4.4L15 12l-3-3z"/>',
	maintain: '<path d="M14.5 5.5a3 3 0 0 0-4 4L5 15l2 2 1.5 1.5 5.5-5.5a3 3 0 0 0 4-4L15.5 11 13 8.5z"/>',
	import: '<path d="M12 20V10"/><path d="M8 16l4 4 4-4"/><path d="M5 9.5V5a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v4.5"/>',
	refresh: '<path d="M20 12a8 8 0 1 1-2.2-5.5"/><path d="M20 4.5V9h-4.5"/>'
};

const TENANTS = [
	{ tenantId: "1001", tenantName: "星环精密", tenantDomain: "xinghuan.local" },
	{ tenantId: "1002", tenantName: "南区装配", tenantDomain: "south.local" }
];

const WORKBENCH = [
	{ scope: "workshop", title: "车间作业", entries: [
		{ label: "扫码报工", icon: "scan", route: "/mes/scan", solo: true },
		{ label: "工单指派", icon: "user", route: "/mes/assign" },
		{ label: "我的工单", icon: "file", route: "/mes?my=1" },
		{ label: "全部工单", icon: "list", route: "/mes" },
		{ label: "我的报工", icon: "history", route: "/mes/reporting-history" },
		{ label: "报工审核", icon: "check", route: "/mes/reporting-approve" },
		{ label: "装箱绑定", icon: "inbox", route: "/mes/packing" },
		{ label: "异常提报", icon: "plus-square", route: "/exception/report" },
		{ label: "异常追踪", icon: "warning", route: "/exception" },
		{ label: "我的绩效", icon: "chart", route: "/performance" }
	]},
	{ scope: "warehouse", title: "仓储作业", entries: [
		{ label: "生产领料", icon: "export", route: "/wms/pickings" },
		{ label: "生产退料", icon: "rollback", route: "/wms/returns" },
		{ label: "成品入库", icon: "inbox", route: "/wms/receipts" },
		{ label: "采购收货", icon: "shopping", route: "/wms/purchase-receipts" },
		{ label: "销售出库", icon: "truck", route: "/wms/sales-deliveries" },
		{ label: "送货单", icon: "file", route: "/wms/delivery-notices" },
		{ label: "其它入库", icon: "plus-square", route: "/wms/other-inbounds" },
		{ label: "其它出库", icon: "minus-square", route: "/wms/other-outbounds" },
		{ label: "移动盘点", icon: "audit", route: "/wms/stocktaking" },
		{ label: "库存查询", icon: "search", route: "/wms/inventory" },
		{ label: "调拨确认", icon: "swap", route: "/wms/transfers" },
		{ label: "库存预警", icon: "bell", route: "/wms/alerts" }
	]},
	{ scope: "quality", title: "质量检验", entries: [
		{ label: "待检验", icon: "shield", route: "/quality" },
		{ label: "过程检验", icon: "scan", route: "/quality/process" },
		{ label: "来料检验", icon: "shopping", route: "/quality/incoming" },
		{ label: "成品检验", icon: "inbox", route: "/quality/finished" },
		{ label: "出库检验", icon: "check-circle", route: "/quality/oqc" },
		{ label: "不合格品", icon: "close-circle", route: "/quality/nonconforming" }
	]},
	{ scope: "equipment", title: "设备作业", entries: [
		{ label: "扫码查设备", icon: "scan", route: "/equipment/scan" },
		{ label: "设备点检", icon: "check", route: "/equipment/spot-checks" },
		{ label: "换线绑定", icon: "link", route: "/equipment/line-rebinds" },
		{ label: "路线巡检", icon: "list", route: "/equipment/route-patrols" },
		{ label: "报修维修", icon: "warning", route: "/equipment/faults" },
		{ label: "维修台账", icon: "tool", route: "/equipment/repairs" },
		{ label: "保养执行记录", icon: "maintain", route: "/equipment/maintenance-executions" },
		{ label: "维护提醒", icon: "bell", route: "/equipment/maintenance-reminders" }
	]},
	{ scope: "mold", title: "模具作业", entries: [
		{ label: "扫码查模具", icon: "scan", route: "/mold/scan" },
		{ label: "模具领用", icon: "export", route: "/mold/borrows" },
		{ label: "模具归还", icon: "import", route: "/mold/returns" },
		{ label: "模具保养", icon: "maintain", route: "/mold/maintenances" },
		{ label: "模具维修", icon: "tool", route: "/mold/repairs" },
		{ label: "模具保养提醒", icon: "bell", route: "/mold/reminders" }
	]}
];

const OPS = {
	"1801": [{ id: "op10", code: "OP10", name: "上料" }, { id: "op20", code: "OP20", name: "组装" }, { id: "op30", code: "OP30", name: "测试" }],
	"1802": [{ id: "op10", code: "OP10", name: "焊接" }, { id: "op20", code: "OP20", name: "点胶" }],
	"1803": [{ id: "op10", code: "OP10", name: "注塑" }]
};

const orders = [
	{ id: "1801", code: "WO-20261004-018", name: "星环控制器", status: "生产中", product: "XH-CTRL-A2", mine: true },
	{ id: "1802", code: "WO-20261003-007", name: "传感模组", status: "已派工", product: "SN-MOD-11", mine: true },
	{ id: "1803", code: "WO-20261002-004", name: "外壳组件", status: "待开工", product: "CASE-09", mine: false }
];

const workers = [{ id: "18", name: "张工" }, { id: "27", name: "李敏" }, { id: "31", name: "王磊" }];
const teams = [{ id: "t1", name: "装配一组" }, { id: "t2", name: "测试二组" }];
const materials = [{ code: "MAT-2201", name: "连接器座" }, { code: "MAT-1188", name: "屏蔽罩" }];
const SAMPLES = ["WO-20261004-018", "PK-20261004-003", "EQ-CNC-014"];

function line(code, name, qty, book, productId) {
	return {
		materialCode: code, materialName: name, qty: String(qty),
		locationCode: "A-01-02", batch: "B202610",
		book: String(book == null ? qty : book), actual: "", remarks: "",
		productId: productId || ""
	};
}

function doc(id, code, status, whName, personName, rows) {
	return { id: id, title: code, status: status, subtitle: whName + " · " + personName, warehouseName: whName, personName: personName, lines: rows };
}

const lists = {
	"/mes/reporting-history": [
		{ id: "rh1", title: "WO-20261003-007 OP10 焊接", status: "已提交", subtitle: "报工 20 · 合格 20 · 工时 1.5", fields: [["报工数量", "20"], ["合格数量", "20"], ["不合格数量", "0"], ["工时", "1.5"], ["报工人员", "张工"]] }
	],
	"/mes/reporting-approve": [
		{ id: "ra1", title: "WO-20261004-018 OP20 组装", status: "待审核", subtitle: "李敏 · 报工 16", fields: [["报工数量", "16"], ["合格数量", "15"], ["不合格数量", "1"], ["工时", "2"], ["报工人员", "李敏"]], action: "通过", alt: "驳回", done: "已通过", altDone: "已驳回" }
	],
	"/mes/packing": [
		{ id: "pk1", title: "XH-CTRL-A2 星环控制器", status: "已绑定", subtitle: "箱号 BX-014 · 数量 12", fields: [["产品编码", "XH-CTRL-A2"], ["产品名称", "星环控制器"], ["装箱数量", "12"], ["箱号", "BX-014"], ["方式", "扫码"], ["绑定人", "张工"], ["绑定时间", "2026-10-04 09:20"]] }
	],
	"/exception": [
		{ id: "ex1", title: "缺料 WO-20261004-018", status: "待处理", subtitle: "连接器座 · 缺 40", fields: [["工单", "WO-20261004-018"], ["物料", "连接器座"], ["缺料数量", "40"]] },
		{ id: "ex2", title: "交期 WO-20261003-007", status: "跟进中", subtitle: "来料延迟 · 2 天", fields: [["工单", "WO-20261003-007"], ["延期原因", "来料延迟"], ["延期天数", "2"]] },
		{ id: "ex3", title: "质量 WO-20261002-004", status: "待处理", subtitle: "外观划伤 · 一般", fields: [["工单", "WO-20261002-004"], ["问题描述", "外观划伤"], ["严重程度", "一般"]] }
	],
	"/performance": [
		{ id: "pf1", title: "张工", status: "已确认", subtitle: "2026-10 · 420 件", fields: [["期间", "2026-10"], ["总工时", "86"], ["总件数", "420"], ["金额", "12600"]] }
	],
	"/wms/pickings": [doc("pk-1", "PK-20261004-003", "待领料", "原料仓", "张工", [line("MAT-2201", "连接器座", 40), line("MAT-1188", "屏蔽罩", 40)])],
	"/wms/returns": [doc("rt-1", "RT-20261004-001", "待退料", "原料仓", "李敏", [line("MAT-1188", "屏蔽罩", 6)])],
	"/wms/receipts": [doc("fg-1", "FG-20261004-008", "待入库", "成品仓", "张工", [line("XH-CTRL-A2", "星环控制器", 12, null, "301")])],
	"/wms/purchase-receipts": [doc("pr-1", "PR-20261004-015", "待收货", "原料仓", "王磊", [line("MAT-2201", "连接器座", 200)])],
	"/wms/sales-deliveries": [doc("sd-1", "SD-20261004-006", "待出库", "成品仓", "李敏", [line("XH-CTRL-A2", "星环控制器", 8, null, "301")])],
	"/wms/delivery-notices": [doc("dn-1", "DN-20261004-002", "待发送", "成品仓", "张工", [line("SN-MOD-11", "传感模组", 30)])],
	"/wms/other-inbounds": [doc("oi-1", "OI-20261003-004", "待入库", "备件仓", "王磊", [line("SP-009", "密封圈", 50)])],
	"/wms/other-outbounds": [doc("oo-1", "OO-20261003-002", "待出库", "备件仓", "李敏", [line("SP-009", "密封圈", 4)])],
	"/wms/stocktaking": [doc("st-1", "ST-20261004-001", "盘点中", "原料仓", "张工", [line("MAT-2201", "连接器座", 480, 480), line("MAT-1188", "屏蔽罩", 120, 126)])],
	"/wms/inventory": [
		{ id: "ib1", title: "MAT-2201 连接器座", status: "正常", subtitle: "原料仓 · 480", fields: [["物料编码", "MAT-2201"], ["物料名称", "连接器座"], ["单位", "个"], ["数量", "480"], ["仓库", "原料仓"]] },
		{ id: "ib2", title: "MAT-1188 屏蔽罩", status: "正常", subtitle: "原料仓 · 126", fields: [["物料编码", "MAT-1188"], ["物料名称", "屏蔽罩"], ["单位", "个"], ["数量", "126"], ["仓库", "原料仓"]] },
		{ id: "ib3", title: "XH-CTRL-A2 星环控制器", status: "正常", subtitle: "成品仓 · 36", fields: [["物料编码", "XH-CTRL-A2"], ["物料名称", "星环控制器"], ["单位", "台"], ["数量", "36"], ["仓库", "成品仓"]] }
	],
	"/wms/transfers": [doc("tf-1", "TF-20261004-001", "待执行", "原料仓", "张工", [line("MAT-2201", "连接器座", 20)])],
	"/wms/alerts": [
		{ id: "al1", title: "MAT-1188 低于安全库存", status: "待处理", subtitle: "当前 126", fields: [["物料编码", "MAT-1188"], ["预警", "低于安全库存"], ["当前数量", "126"]], notes: "" }
	],
	"/quality/process": [
		{ id: "qi-p1", title: "IPQC-20261004-011", status: "待检", subtitle: "WO-20261004-018 · 检验数量 20", qty: "20", kind: "process", steps: ["外观", "尺寸"] },
		{ id: "qi-p2", title: "IPQC-20261003-006", status: "已检验", subtitle: "WO-20261003-007 · 检验数量 10", qty: "10", kind: "process", steps: ["外观"] }
	],
	"/quality/incoming": [
		{ id: "qi-i1", title: "IQC-20261004-004", status: "待检", subtitle: "MAT-2201 · 检验数量 50", qty: "50", kind: "incoming", steps: ["来料外观", "包装"] }
	],
	"/quality/finished": [
		{ id: "qi-f1", title: "FQC-20261004-002", status: "待检", subtitle: "XH-CTRL-A2 · 检验数量 12", qty: "12", kind: "finished", steps: ["功能", "外观"] }
	],
	"/quality/oqc": [
		{ id: "qi-o1", title: "OQC-20261004-001", status: "待检", subtitle: "SD-20261004-006 · 检验数量 8", qty: "8", kind: "oqc", steps: ["出库外观"] }
	],
	"/quality/nonconforming": [
		{ id: "nc1", title: "NC-20261003-003", status: "待处置", subtitle: "外观划伤 · 2", fields: [["单号", "NC-20261003-003"], ["产品", "传感模组"], ["缺陷类型", "外观划伤"], ["缺陷数量", "2"], ["缺陷原因", "转运磕碰"], ["处置", "待定"]] }
	],
	"/equipment/spot-checks": [
		{ id: "sc1", title: "EQ-CNC-014 立式加工中心", status: "待点检", subtitle: "一车间 · 一线", steps: ["外观", "润滑", "安全防护"] },
		{ id: "sc2", title: "EQ-ASM-006 组装台", status: "已点检", subtitle: "一车间 · 二线", steps: ["外观"] }
	],
	"/equipment/line-rebinds": [
		{ id: "lr1", title: "EQ-CNC-014", status: "待换线", subtitle: "一线 → 三线", fields: [["设备", "立式加工中心"], ["原产线", "一线"], ["目标产线", "三线"]], action: "提交换线", done: "已换线" }
	],
	"/equipment/route-patrols": [
		{ id: "rp1", title: "一车间早班路线", status: "进行中", subtitle: "3 个点", fields: [["路线", "一车间早班"], ["已巡", "1 / 3"]] }
	],
	"/equipment/faults": [
		{ id: "ft1", title: "FT-20261004-002", status: "待处理", subtitle: "立式加工中心 · 主轴异响", fields: [["报修单", "FT-20261004-002"], ["设备", "立式加工中心"], ["故障类型", "异响"], ["等级", "一般"], ["描述", "主轴异响"]] },
		{ id: "ft2", title: "FT-20261003-009", status: "待处理", subtitle: "组装台 · 急停失灵", fields: [["报修单", "FT-20261003-009"], ["设备", "组装台"], ["故障类型", "急停"], ["等级", "严重"], ["描述", "急停失灵"]] }
	],
	"/equipment/repairs": [
		{ id: "rpair1", title: "RP-20261002-004", status: "维修中", subtitle: "立式加工中心", fields: [["维修单", "RP-20261002-004"], ["设备", "立式加工中心"], ["到场", "2026-10-02 14:10"], ["原因", "轴承磨损"], ["内容", "更换轴承"]], action: "完工", done: "已完工" }
	],
	"/equipment/maintenance-executions": [
		{ id: "me1", title: "立式加工中心 月保", status: "已执行", subtitle: "2026-09-28", fields: [["设备", "立式加工中心"], ["计划", "月保"], ["执行时间", "2026-09-28"], ["执行人", "王磊"]] }
	],
	"/equipment/maintenance-reminders": [
		{ id: "mr1", title: "EQ-CNC-014 月保逾期", status: "逾期", subtitle: "上次 2026-09-01", fields: [["设备", "立式加工中心"], ["提醒", "月保"], ["上次保养", "2026-09-01"]] },
		{ id: "mr2", title: "EQ-ASM-006 周保", status: "未到期", subtitle: "下次 2026-10-08", fields: [["设备", "组装台"], ["提醒", "周保"], ["下次", "2026-10-08"]] }
	],
	"/mold/borrows": [
		{ id: "mb1", title: "BR-20261004-003", status: "待领用", subtitle: "MD-INJ-021 前壳模", fields: [["单据", "BR-20261004-003"], ["模具编码", "MD-INJ-021"], ["模具名称", "前壳模"], ["领用日期", "2026-10-04"], ["领用人", "张工"]], action: "确认领用", done: "已领用" }
	],
	"/mold/returns": [
		{ id: "mrt1", title: "RN-20261003-001", status: "待归还", subtitle: "MD-INJ-021 前壳模", fields: [["单据", "RN-20261003-001"], ["模具编码", "MD-INJ-021"], ["模具名称", "前壳模"], ["领用人", "张工"]], action: "确认归还", done: "已归还" }
	],
	"/mold/maintenances": [
		{ id: "mm1", title: "MD-INJ-021 前壳模", status: "待保养", subtitle: "上次 2026-08-12", fields: [["模具编码", "MD-INJ-021"], ["名称", "前壳模"], ["上次保养", "2026-08-12"]], action: "完成保养", done: "已保养" }
	],
	"/mold/repairs": [
		{ id: "mrp1", title: "MD-INJ-008 后盖模", status: "维修中", subtitle: "分型面拉伤", fields: [["模具编码", "MD-INJ-008"], ["名称", "后盖模"], ["现象", "分型面拉伤"]] }
	],
	"/mold/reminders": [
		{ id: "mrm1", title: "MD-INJ-021 保养到期", status: "待处理", subtitle: "按次数 · 累计 12000", fields: [["模具编码", "MD-INJ-021"], ["名称", "前壳模"], ["提醒类型", "保养"], ["触发", "按次数"], ["上次保养", "2026-08-12"]] }
	]
};

const DOC = {
	"/wms/pickings": { title: "生产领料", person: "领料人", action: "确认领料", done: "已领料", mode: "doc", expect: "应领" },
	"/wms/returns": { title: "生产退料", person: "退料人", action: "确认退料", done: "已退料", mode: "doc", expect: "应退" },
	"/wms/receipts": { title: "成品入库", person: "入库人", action: "确认入库", done: "已入库", mode: "doc", expect: "应入" },
	"/wms/purchase-receipts": { title: "采购收货", person: "收货人", action: "确认收货", done: "已收货", mode: "doc", expect: "应收", actual: "实收" },
	"/wms/sales-deliveries": { title: "销售出库", person: "出库人", action: "确认出库", done: "已出库", mode: "doc", expect: "应出" },
	"/wms/delivery-notices": { title: "送货单", person: "发送人", action: "确认发送", done: "已发送", mode: "doc", expect: "应送" },
	"/wms/other-inbounds": { title: "其它入库", person: "入库人", action: "确认入库", done: "已入库", mode: "doc", expect: "应入" },
	"/wms/other-outbounds": { title: "其它出库", person: "出库人", action: "确认出库", done: "已出库", mode: "doc", expect: "应出" },
	"/wms/stocktaking": { title: "移动盘点", person: "盘点人", action: "提交盘点", done: "已记录", mode: "stock", expect: "账面", actual: "实盘" },
	"/wms/inventory": { title: "库存查询", mode: "query" },
	"/wms/transfers": { title: "调拨确认", person: "执行人", action: "确认调拨", done: "已执行", mode: "doc", expect: "应调" },
	"/wms/alerts": { title: "库存预警", mode: "alert" }
};

const DISPOSE = [
	["return", "退货"], ["accept", "让步"], ["quarantine", "隔离"], ["rework", "返工"],
	["scrap", "报废"], ["downgrade", "降级"], ["other", "其他"]
];
const PLACES = [["原料仓", "原料仓"], ["成品仓", "成品仓"], ["备件仓", "备件仓"]];
const REPAIR_RESULTS = [["成功", "成功"], ["失败", "失败"], ["部分成功", "部分成功"]];

const TITLES = {
	apps: "全部功能", "scan-hub": "扫码",
	"/mes/scan": "扫码报工", "/mes/assign": "工单指派", "/mes?my=1": "我的工单", "/mes": "全部工单",
	"/mes/reporting-history": "我的报工", "/mes/reporting-approve": "报工审核", "/mes/packing": "装箱绑定",
	"/exception/report": "异常提报", "/exception": "异常追踪", "/performance": "我的绩效",
	"/quality": "待检验", "/quality/process": "过程检验", "/quality/incoming": "来料检验",
	"/quality/finished": "成品检验", "/quality/oqc": "出库检验", "/quality/nonconforming": "不合格品",
	"/equipment/scan": "扫码查设备", "/equipment/spot-checks": "设备点检", "/equipment/line-rebinds": "换线绑定",
	"/equipment/route-patrols": "路线巡检", "/equipment/faults": "报修维修", "/equipment/repairs": "维修台账",
	"/equipment/maintenance-executions": "保养执行记录", "/equipment/maintenance-reminders": "维护提醒",
	"/mold/scan": "扫码查模具", "/mold/borrows": "模具领用", "/mold/returns": "模具归还",
	"/mold/maintenances": "模具保养", "/mold/repairs": "模具维修", "/mold/reminders": "模具保养提醒"
};

const QUALITY_ROUTES = ["/quality/incoming", "/quality/process", "/quality/finished", "/quality/oqc"];
const WAREHOUSE_COUNT_ROUTES = ["/wms/pickings", "/wms/returns", "/wms/receipts", "/wms/purchase-receipts", "/wms/sales-deliveries", "/wms/delivery-notices", "/wms/other-inbounds", "/wms/other-outbounds", "/wms/transfers", "/wms/alerts"];

const ui = {
	route: "login", loggedIn: false, tenantId: "", tenants: [], notice: "", banner: "",
	returnTo: "workbench", appsScope: "", detailId: "", step: 0, lineIndex: 0, lineNote: "", filter: "全部",
	query: "", loading: false, dialog: null, errors: [], draft: {}, choices: {}, photos: [],
	conductId: "", faultOpen: false, packOpen: false, scanCode: "", scanOrder: "", scanOp: "", sampleIndex: 0,
	assignOrder: "", assignOp: "", assignMode: "worker", pickedWorkers: {}, assignTeam: "",
	exKind: "material-shortage", exOrder: "", exMaterial: "", matKeyword: "",
	equipCode: "", moldCode: "", resolved: null, next: null, loadTimer: 0
};

const screen = document.getElementById("screen");
const dock = document.getElementById("dock");
const navTitle = document.getElementById("nav-title");
const backBtn = document.getElementById("back");
const homeBtn = document.getElementById("home");
const dialogEl = document.getElementById("dialog");
const phone = document.getElementById("phone");

function esc(value) {
	return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
		return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
	});
}

function icon(name, scope) {
	const body = PATH[name] || PATH.file;
	const cls = scope ? "icon icon-tile icon-" + scope : "icon";
	return '<span class="' + cls + '" aria-hidden="true"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">' + body + "</svg></span>";
}

function view(body, dockHtml) {
	return { body: body, dock: dockHtml || "" };
}

function tone(status) {
	const text = String(status || "");
	if (text === "逾期" || text === "严重" || text.indexOf("不合格") >= 0 || text === "已驳回") return "danger";
	if (text.indexOf("待") === 0) return "warning";
	if (text === "生产中" || text === "进行中" || text === "已派工" || text === "维修中" || text === "盘点中" || text === "跟进中" || text === "处理中") return "progress";
	if (text === "未到期") return "neutral";
	return "success";
}

function badge(status) {
	return '<span class="badge badge-' + tone(status) + '">' + esc(status) + "</span>";
}

function rank(status) {
	const kind = tone(status);
	if (kind === "danger") return 0;
	if (kind === "warning") return 1;
	if (kind === "progress") return 2;
	return 3;
}

function draftValue(id) {
	return ui.draft[id] == null ? "" : ui.draft[id];
}

function invalidAttr(id) {
	const hit = (ui.errors || []).some(function (item) { return item.id === id; });
	return hit ? ' aria-invalid="true" aria-describedby="' + id + '-error"' : "";
}

function fieldError(id) {
	const hit = (ui.errors || []).filter(function (item) { return item.id === id; })[0];
	return hit ? '<p class="field-error" id="' + id + '-error">' + esc(hit.text) + "</p>" : "";
}

function errorHtml() {
	if (!ui.errors.length) return "";
	const items = ui.errors.map(function (item) {
		return '<li><button type="button" class="error-link" data-act="focus-field" data-id="' + esc(item.id) + '">' + esc(item.text) + "</button></li>";
	}).join("");
	return '<div id="error-summary" class="error-summary" role="alert" tabindex="-1"><h2>请先补全这些内容</h2><ul>' + items + "</ul></div>";
}

function bannerHtml() {
	return ui.banner ? '<div class="banner-in" role="status">' + esc(ui.banner) + "</div>" : "";
}

function noticeHtml() {
	return ui.notice ? '<div class="notice" role="status">' + esc(ui.notice) + "</div>" : "";
}

function facts(pairs) {
	return '<dl class="facts">' + pairs.map(function (pair) {
		return "<div><dt>" + esc(pair[0]) + "</dt><dd>" + esc(pair[1]) + "</dd></div>";
	}).join("") + "</dl>";
}

function choices(group, options) {
	return '<div class="choices" id="' + group + '" tabindex="-1" role="group">' + options.map(function (option) {
		const on = ui.choices[group] === option[0];
		return '<button type="button" class="choice' + (on ? " choice-on" : "") + '" data-act="choice" data-group="' + group + '" data-value="' + esc(option[0]) + '" aria-pressed="' + (on ? "true" : "false") + '">' + esc(option[1]) + "</button>";
	}).join("") + "</div>";
}

function optionLabel(options, value) {
	const hit = options.filter(function (option) { return option[0] === value; })[0];
	return hit ? hit[1] : "";
}

function collectsQty(meta) {
	return !!(meta && meta.actual);
}

function countStatus(route, status) {
	return (lists[route] || []).filter(function (row) { return row.status === status; }).length;
}

function tenantById(id) {
	return TENANTS.filter(function (item) { return item.tenantId === id; })[0];
}

function sourceRows(route) {
	if (route === "/mes?my=1") return orders.filter(function (item) { return item.mine; }).map(orderCard);
	if (route === "/mes") return orders.map(orderCard);
	return (lists[route] || []).slice();
}

function orderCard(order) {
	return {
		id: order.id,
		title: order.code + " " + order.name,
		status: order.status,
		subtitle: order.product,
		fields: [["工单", order.code], ["名称", order.name], ["产品", order.product]]
	};
}

function findRow(route, id) {
	const rows = sourceRows(route);
	for (let i = 0; i < rows.length; i++) if (rows[i].id === id) return rows[i];
	return null;
}

function cardSubtitle(row) {
	if (row.lines) {
		const sum = row.lines.reduce(function (total, item) { return total + Number(item.qty || 0); }, 0);
		return (row.subtitle || "") + " · " + row.lines.length + " 行 · 数量 " + sum;
	}
	return row.subtitle || "";
}

function visibleRows(route) {
	const word = ui.query.trim();
	return sourceRows(route).filter(function (row) {
		if (ui.filter !== "全部" && row.status !== ui.filter) return false;
		if (!word) return true;
		return (row.title + " " + cardSubtitle(row)).indexOf(word) >= 0;
	}).sort(function (a, b) { return rank(a.status) - rank(b.status); });
}

function filtersHtml(route) {
	const statuses = [];
	sourceRows(route).forEach(function (row) {
		if (statuses.indexOf(row.status) < 0) statuses.push(row.status);
	});
	const all = ["全部"].concat(statuses);
	return '<div class="filters" role="group" aria-label="按状态筛选">' + all.map(function (status) {
		const on = ui.filter === status;
		return '<button type="button" class="btn-chip' + (on ? " btn-chip-on" : "") + '" data-act="set-filter" data-value="' + esc(status) + '" aria-pressed="' + (on ? "true" : "false") + '">' + esc(status) + "</button>";
	}).join("") + "</div>";
}

function searchHtml() {
	return '<div class="search-row"><label class="sr" for="query-input">搜索单号或名称</label><input class="field" id="query-input" data-draft placeholder="搜索单号或名称" value="' + esc(draftValue("query-input")) + '"><button type="button" data-act="run-query">查询</button><button type="button" class="icon-btn" data-act="refresh" aria-label="刷新">' + icon("refresh") + "</button></div>";
}

function cardButton(row) {
	return '<button type="button" class="card-btn" data-act="open-row" data-id="' + esc(row.id) + '"><span class="card-top"><span class="item-title">' + esc(row.title) + "</span>" + badge(row.status) + '</span><span class="sub">' + esc(cardSubtitle(row)) + "</span></button>";
}

function emptyHtml(route) {
	const raw = sourceRows(route);
	if (raw.length === 0) {
		return '<div class="empty"><p class="empty-title">这里还没有单据</p><p class="hint">可以从扫码或待办进入新的作业。</p><button type="button" class="btn-primary" data-act="open-route" data-route="scan-hub">去扫码</button></div>';
	}
	return '<div class="empty"><p class="empty-title">没有匹配的单据</p><p class="hint">换个状态，或清除搜索后再看。</p><button type="button" class="btn-secondary" data-act="clear-filter">清除筛选</button></div>';
}

function listBody(route, rows) {
	if (ui.loading) {
		return bannerHtml() + '<div aria-busy="true"><span class="sr">正在加载</span><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>';
	}
	return bannerHtml() + searchHtml() + filtersHtml(route) + (rows.length ? rows.map(cardButton).join("") : emptyHtml(route));
}

function detailBody(row) {
	const pairs = (row.fields || []).filter(function (pair) { return pair[0] !== "状态"; });
	return bannerHtml() + '<p class="code">' + esc(row.title) + "</p>" + badge(row.status) + (pairs.length ? facts(pairs) : "");
}

function detailDock(row) {
	let html = "";
	if (row.action) html += '<button type="button" class="btn-primary" data-act="do-primary" data-id="' + esc(row.id) + '">' + esc(row.action) + "</button>";
	if (row.alt) html += '<button type="button" class="btn-danger" data-act="do-alt" data-id="' + esc(row.id) + '">' + esc(row.alt) + "</button>";
	return html;
}

function renderBrowser(route) {
	const row = ui.detailId ? findRow(route, ui.detailId) : null;
	if (row) {
		let dockHtml = detailDock(row);
		if (route === "/mes?my=1") dockHtml += '<button type="button" class="btn-primary" data-act="go-report" data-id="' + esc(row.id) + '">去报工</button>';
		return view('<div class="page">' + detailBody(row) + "</div>", dockHtml);
	}
	return view('<div class="page">' + listBody(route, visibleRows(route)) + "</div>");
}

function prepareIssued(row) {
	if (!row || !row.lines) return;
	row.lines.forEach(function (item) {
		if (item.issued == null) item.issued = "";
	});
}

function varianceText(meta, item) {
	const actual = meta.mode === "stock" ? item.actual : item.issued;
	if (actual === "" || actual == null) return "";
	const diff = Number(actual) - Number(meta.mode === "stock" ? item.book : item.qty);
	if (!diff) return "";
	return item.materialName + " 比" + meta.expect + (diff > 0 ? "多 " : "少 ") + Math.abs(diff);
}

function lineDiffs(meta, row) {
	return row.lines.map(function (item) { return varianceText(meta, item); }).filter(Boolean);
}

function stepper(label, value, name) {
	return '<label for="line-qty">' + esc(label) + '</label><div class="stepper" role="group" aria-label="' + esc(label) + '"><button type="button" data-act="qty-dec" aria-label="减少' + esc(label) + '">−</button><input class="field num" id="line-qty" inputmode="numeric" value="' + esc(value) + '"' + invalidAttr("line-qty") + '><button type="button" data-act="qty-inc" aria-label="增加' + esc(label) + '">+</button></div>' + fieldError("line-qty");
}

function renderWizard(route) {
	const meta = DOC[route];
	const row = findRow(route, ui.detailId);
	if (!row) return view('<div class="page">' + listBody(route, visibleRows(route)) + "</div>");
	if (meta.mode === "doc" && collectsQty(meta)) prepareIssued(row);
	const names = ["", "单据", "明细", "确认"];
	const stepName = names[ui.step] || "单据";
	let body = '<p class="step-label">第 <strong>' + ui.step + "</strong> 步，共 3 步 · " + stepName + "</p>" + errorHtml();
	let dockHtml = "";
	if (ui.step === 1) {
		body += '<p class="code">' + esc(row.title) + "</p>" + badge(row.status) + facts([["仓库", row.warehouseName], [meta.person, row.personName], ["行数", String(row.lines.length)]]);
		dockHtml = '<button type="button" class="btn-primary" data-act="wizard-next">开始核对</button>';
	} else if (ui.step === 2) {
		const item = row.lines[ui.lineIndex];
		const expectValue = meta.mode === "stock" ? item.book : item.qty;
		body += '<p class="hint">' + (ui.lineIndex + 1) + " / " + row.lines.length + "</p>";
		body += '<div class="line-head"><p class="code">' + esc(item.materialCode) + "</p>" + badge(row.status) + "</div>";
		body += '<p class="item-title">' + esc(item.materialName) + "</p>";
		body += facts([[meta.expect, expectValue], ["库位", item.locationCode], ["批号", item.batch]]);
		if (collectsQty(meta)) {
			const actualValue = meta.mode === "stock" ? (item.actual || "") : (item.issued || "");
			body += stepper(meta.actual, actualValue, meta.actual);
			const diff = varianceText(meta, item);
			if (diff) body += '<p class="variance">' + esc(diff) + "</p>";
			if (meta.mode === "doc") {
				body += '<div style="height:8px"></div><button type="button" class="btn-secondary" data-act="copy-expect">与' + esc(meta.expect) + "相同</button>";
			}
			if (meta.mode === "stock") {
				body += '<label for="remarks">备注</label><input class="field" id="remarks" data-draft placeholder="可空" value="' + esc(item.remarks || "") + '">';
			}
		} else {
			body += '<p class="hint">单据数量只作核对，确认时不另填数量。</p>';
		}
		if (ui.lineNote) {
			const missed = ui.lineNote === "这张单没有这个物料";
			body += '<p class="' + (missed ? "variance" : "note") + '" role="' + (missed ? "alert" : "status") + '">' + esc(ui.lineNote) + "</p>";
		}
		body += '<div style="height:8px"></div><button type="button" class="btn-secondary" data-act="locate-line">扫码定位物料</button>';
		if (ui.lineIndex > 0) dockHtml += '<button type="button" class="btn-secondary" data-act="line-prev">上一条</button>';
		dockHtml += ui.lineIndex < row.lines.length - 1
			? '<button type="button" class="btn-primary" data-act="line-next">下一条</button>'
			: '<button type="button" class="btn-primary" data-act="wizard-review">去确认</button>';
	} else {
		const expectSum = row.lines.reduce(function (total, item) { return total + Number(meta.mode === "stock" ? item.book : item.qty); }, 0);
		let summary = [["行数", String(row.lines.length)], [meta.expect + "合计", String(expectSum)]];
		const rows = row.lines.map(function (item) {
			const expectValue = meta.mode === "stock" ? item.book : item.qty;
			if (!collectsQty(meta)) return [item.materialName, meta.expect + " " + expectValue];
			const raw = meta.mode === "stock" ? item.actual : item.issued;
			const actual = raw === "" || raw == null ? "未填" : raw;
			const diff = varianceText(meta, item);
			return [item.materialName, meta.expect + " " + expectValue + " · " + meta.actual + " " + actual + (diff ? " · " + diff.replace(item.materialName + " ", "") : "")];
		});
		if (collectsQty(meta)) {
			const actualSum = row.lines.reduce(function (total, item) {
				const value = meta.mode === "stock" ? item.actual : item.issued;
				return total + (value === "" || value == null ? 0 : Number(value));
			}, 0);
			summary.push([meta.actual + "合计", String(actualSum)]);
		}
		body += '<p class="code">' + esc(row.title) + "</p>" + badge(row.status);
		body += facts(summary.concat(rows));
		dockHtml = '<button type="button" class="btn-primary" data-act="commit-ask">' + esc(meta.action) + "</button>";
	}
	return view('<div class="page">' + body + "</div>", dockHtml);
}

function renderAlert(route) {
	const row = ui.detailId ? findRow(route, ui.detailId) : null;
	if (!row) return view('<div class="page">' + listBody(route, visibleRows(route)) + "</div>");
	const current = ui.choices.alert || "processing";
	const chips = [["processing", "处理中"], ["resolved", "已解决"], ["ignored", "已忽略"]].map(function (item) {
		const on = current === item[0];
		return '<button type="button" class="btn-chip' + (on ? " btn-chip-on" : "") + '" data-act="alert-status" data-value="' + item[0] + '" aria-pressed="' + (on ? "true" : "false") + '">' + item[1] + "</button>";
	}).join("");
	const body = '<div class="page">' + errorHtml() + '<p class="code">' + esc(row.title) + "</p>" + badge(row.status) + facts(row.fields) + '<label id="alert-status-label">处理状态</label><div class="modes" role="group" aria-labelledby="alert-status-label">' + chips + '</div><label for="alert-notes">处理备注</label><input class="field" id="alert-notes" data-draft value="' + esc(draftValue("alert-notes") || row.notes || "") + '"></div>';
	return view(body, '<button type="button" class="btn-primary" data-act="alert-save">保存处理</button>');
}

function featureHits(word) {
	const query = String(word || "").trim().toLowerCase();
	const hits = [];
	if (!query) return hits;
	WORKBENCH.forEach(function (block) {
		block.entries.forEach(function (cell) {
			if (cell.label.toLowerCase().indexOf(query) >= 0) hits.push({ block: block, cell: cell });
		});
	});
	return hits;
}

function homeTodoHtml() {
	const todos = [
		{ title: "待审报工", sub: "报工审核", count: countStatus("/mes/reporting-approve", "待审核"), text: "条待审核", route: "/mes/reporting-approve", tone: "warning" },
		{ title: "待领料", sub: "生产领料", count: countStatus("/wms/pickings", "待领料"), text: "张待领料", route: "/wms/pickings", tone: "warning" },
		{ title: "待检验", sub: "质量检验", count: QUALITY_ROUTES.reduce(function (sum, route) { return sum + countStatus(route, "待检"); }, 0), text: "张待检", route: "/quality", tone: "warning" },
		{ title: "逾期保养", sub: "维护提醒", count: countStatus("/equipment/maintenance-reminders", "逾期"), text: "条逾期", route: "/equipment/maintenance-reminders", tone: "danger" },
		{ title: "待处理故障", sub: "报修维修", count: countStatus("/equipment/faults", "待处理"), text: "条待处理", route: "/equipment/faults", tone: "warning" }
	].filter(function (item) { return item.count > 0; });
	if (!todos.length) return '<div class="empty"><p class="empty-title">今天没有待办</p><p class="hint">可以直接扫码开始作业。</p></div>';
	return todos.map(function (item) {
		return '<button type="button" class="todo" data-act="open-route" data-route="' + esc(item.route) + '"><span><span class="todo-title">' + esc(item.title) + '</span><span class="todo-sub">' + esc(item.sub) + '</span></span><span class="badge badge-' + item.tone + '">' + item.count + " " + item.text + "</span></button>";
	}).join("");
}

function homeFrequentHtml() {
	const frequent = [
		["我的工单", "file", "/mes?my=1"],
		["异常提报", "plus-square", "/exception/report"],
		["装箱绑定", "inbox", "/mes/packing"],
		["我的报工", "history", "/mes/reporting-history"]
	];
	return frequent.map(function (item) {
		return '<button type="button" class="cell" data-act="open-route" data-route="' + esc(item[2]) + '">' + icon(item[1], "workshop") + '<span class="cell-label">' + esc(item[0]) + "</span></button>";
	}).join("");
}

function renderHome() {
	const org = tenantById(ui.tenantId);
	const query = draftValue("feature-find").trim();
	const body = '<div class="page"><div class="who"><span class="who-name">张工</span><span class="who-meta">' + esc(org ? org.tenantName : "星环精密") + ' · 操作工 · 早班</span></div><button type="button" class="btn-primary btn-scan" data-act="open-route" data-route="scan-hub">' + icon("scan") + "扫码</button><p class=\"hint\">识别工单、领料单或设备</p><label for=\"feature-find\">检索功能</label><input class=\"field\" id=\"feature-find\" data-draft autocomplete=\"off\" placeholder=\"例如盘点、领料\" value=\"" + esc(query) + "\"><div id=\"feature-rest\">" + featureRest(query, homeTodoHtml(), homeFrequentHtml()) + "</div></div>";
	return view(body);
}

function featureRest(query, todoHtml, cells) {
	if (!query) {
		return '<h2 class="section-title">今日待办</h2>' + todoHtml + '<h2 class="section-title">常用</h2><div class="grid">' + cells + '</div><div style="height:12px"></div><button type="button" class="btn-secondary" data-act="open-route" data-route="apps">全部功能</button>';
	}
	const hits = featureHits(query);
	if (!hits.length) {
		return '<div class="empty"><p class="empty-title">没有这个功能</p><p class="hint">换个名称，或从全部分组里找。</p><button type="button" class="btn-secondary" data-act="open-route" data-route="apps">去全部分组</button></div>';
	}
	return hits.map(function (hit) {
		return '<button type="button" class="hit" data-act="open-route" data-route="' + esc(hit.cell.route) + '">' + icon(hit.cell.icon, hit.block.scope) + '<span class="scope-copy"><span class="item-title">' + esc(hit.cell.label) + '</span><span class="scope-meta">' + esc(hit.block.title) + "</span></span></button>";
	}).join("");
}

function scopeNote(scope) {
	if (scope === "workshop") {
		const count = countStatus("/mes/reporting-approve", "待审核");
		return count ? count + " 条待审报工" : "";
	}
	if (scope === "warehouse") {
		const count = WAREHOUSE_COUNT_ROUTES.reduce(function (sum, route) {
			return sum + (lists[route] || []).filter(function (row) { return String(row.status).indexOf("待") === 0; }).length;
		}, 0);
		return count ? count + " 张待处理单据" : "";
	}
	if (scope === "quality") {
		const count = QUALITY_ROUTES.reduce(function (sum, route) { return sum + countStatus(route, "待检"); }, 0);
		return count ? count + " 张待检" : "";
	}
	if (scope === "equipment") {
		const faults = countStatus("/equipment/faults", "待处理");
		const overdue = countStatus("/equipment/maintenance-reminders", "逾期");
		const parts = [];
		if (faults) parts.push(faults + " 条待处理故障");
		if (overdue) parts.push(overdue + " 条逾期保养");
		return parts.join("，");
	}
	if (scope === "mold") {
		const count = countStatus("/mold/reminders", "待处理");
		return count ? count + " 条待处理提醒" : "";
	}
	return "";
}

const SCOPE_ICON = { workshop: "scan", warehouse: "inbox", quality: "shield", equipment: "tool", mold: "maintain" };

function scopeBlock(scope) {
	return WORKBENCH.filter(function (block) { return block.scope === scope; })[0] || null;
}

function renderApps() {
	const block = scopeBlock(ui.appsScope);
	if (!block) {
		const cards = WORKBENCH.map(function (item) {
			const note = scopeNote(item.scope);
			const meta = item.entries.length + " 项" + (note ? " · " + note : "");
			return '<button type="button" class="scope-card" data-act="open-scope" data-scope="' + esc(item.scope) + '">' + icon(SCOPE_ICON[item.scope] || "file", item.scope) + '<span class="scope-copy"><span class="item-title">' + esc(item.title) + '</span><span class="scope-meta">' + esc(meta) + '</span></span><span class="chevron" aria-hidden="true"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg></span></button>';
		}).join("");
		return view('<div class="page">' + cards + "</div>");
	}
	const cells = block.entries.map(function (cell) {
		return '<button type="button" class="cell' + (cell.solo ? " solo" : "") + '" data-act="open-route" data-route="' + esc(cell.route) + '">' + icon(cell.icon, block.scope) + '<span class="cell-label">' + esc(cell.label) + "</span></button>";
	}).join("");
	return view('<div class="page"><div class="grid">' + cells + "</div></div>");
}

function resolveCode(code) {
	const value = String(code || "").trim();
	if (!value) return null;
	const order = orders.filter(function (item) { return item.code === value; })[0];
	if (order) {
		return { kind: "工单", title: order.code + " " + order.name, status: order.status, detail: order.product, route: "/mes/scan", next: { scanCode: value, scanOrder: order.id } };
	}
	const routes = Object.keys(lists);
	for (let i = 0; i < routes.length; i++) {
		const row = (lists[routes[i]] || []).filter(function (item) { return item.title === value; })[0];
		if (row) {
			const next = { detailId: row.id, step: DOC[routes[i]] && (DOC[routes[i]].mode === "doc" || DOC[routes[i]].mode === "stock") ? 1 : 0 };
			return { kind: TITLES[routes[i]] || "单据", title: row.title, status: row.status, detail: cardSubtitle(row), route: routes[i], next: next };
		}
	}
	if (value === "EQ-CNC-014") {
		return { kind: "设备", title: "立式加工中心", status: "运行", detail: "一车间 · 一线", route: "/equipment/scan", next: { equipCode: value } };
	}
	if (value === "MD-INJ-021") {
		return { kind: "模具", title: "前壳模", status: "在库", detail: "模具架 A-3", route: "/mold/scan", next: { moldCode: value } };
	}
	return null;
}

function renderScanHub() {
	let result = "";
	if (ui.resolved && ui.resolved.missing) {
		result = '<div class="empty"><p class="empty-title">没有匹配的单据</p><p class="hint">检查单号，或改用下面的样例码。</p></div>';
	} else if (ui.resolved) {
		result = '<div class="card"><p class="hint">已识别' + esc(ui.resolved.kind) + '</p><p class="code">' + esc(ui.resolved.title) + "</p>" + badge(ui.resolved.status) + '<p class="sub">' + esc(ui.resolved.detail) + '</p></div>';
	}
	const samples = SAMPLES.map(function (code) {
		return '<button type="button" class="btn-chip" data-act="use-sample" data-value="' + esc(code) + '">' + esc(code) + "</button>";
	}).join("");
	const body = '<div class="page">' + bannerHtml() + '<p class="hint">原型不打开相机，用样例码演示识别结果。</p><label for="manual-code">单号或设备编码</label><input class="field" id="manual-code" data-draft placeholder="例如 WO-20261004-018" value="' + esc(draftValue("manual-code")) + '"><div style="height:8px"></div><button type="button" class="btn-primary btn-scan" data-act="fake-scan">' + icon("scan") + "模拟扫码</button><h2 class=\"section-title\">样例码</h2><div class=\"filters\">" + samples + "</div>" + result + "</div>";
	const dockHtml = ui.resolved && !ui.resolved.missing ? '<button type="button" class="btn-primary" data-act="open-resolved">打开</button>' : "";
	return view(body, dockHtml);
}

function renderScan() {
	const order = orders.filter(function (item) { return item.id === ui.scanOrder; })[0];
	let body = bannerHtml() + errorHtml();
	if (!order) {
		body += '<p class="hint">扫到工单后直接进入该工单，不再从全部工单里重选。</p><label for="manual-code">工单号</label><input class="field" id="manual-code" data-draft placeholder="WO-20261004-018" value="' + esc(draftValue("manual-code")) + '"' + invalidAttr("manual-code") + ">" + fieldError("manual-code");
		return view('<div class="page">' + body + "</div>", '<button type="button" class="btn-primary" data-act="scan-report">模拟扫码</button>');
	}
	body += '<p class="code">' + esc(order.code) + "</p>" + badge(order.status) + '<p class="item-title">' + esc(order.name) + '</p><p class="sub">' + esc(order.product) + " · 报工人员 张工</p>";
	body += '<h2 class="section-title">选择工序</h2>';
	body += (OPS[order.id] || []).map(function (op) {
		const on = ui.scanOp === op.id;
		return '<button type="button" class="card-btn' + (on ? " pick-on" : "") + '" data-act="pick-op" data-id="' + esc(op.id) + '" aria-pressed="' + (on ? "true" : "false") + '"><span class="item-title">' + esc(op.code + " " + op.name) + '</span><span class="sub">' + (on ? "已选" : "点选") + "</span></button>";
	}).join("");
	let dockHtml = "";
	if (ui.scanOp) {
		body += '<p class="hint">合格数量 = 报工数量 − 不合格数量</p>';
		body += '<label for="reported">报工数量</label><input class="field num" id="reported" data-draft inputmode="numeric" value="' + esc(draftValue("reported")) + '"' + invalidAttr("reported") + ">" + fieldError("reported");
		body += '<label for="unqualified">不合格数量</label><input class="field num" id="unqualified" data-draft inputmode="numeric" value="' + esc(draftValue("unqualified")) + '"' + invalidAttr("unqualified") + ">" + fieldError("unqualified");
		body += '<label for="qualified">合格数量</label><input class="field num" id="qualified" readonly value="' + esc(qualifiedPreview()) + '">';
		body += '<label for="hours">工时（小时）</label><input class="field num" id="hours" data-draft inputmode="decimal" value="' + esc(draftValue("hours")) + '"' + invalidAttr("hours") + ">" + fieldError("hours");
		dockHtml = '<button type="button" class="btn-primary" data-act="submit-report">提交报工</button>';
	}
	return view('<div class="page">' + body + "</div>", dockHtml);
}

function renderAssign() {
	const order = orders.filter(function (item) { return item.id === ui.assignOrder; })[0];
	if (!order) {
		const cards = orders.map(function (item) {
			return '<button type="button" class="card-btn" data-act="assign-order" data-id="' + item.id + '"><span class="item-title">' + esc(item.code + " " + item.name) + "</span>" + badge(item.status) + "</button>";
		}).join("");
		return view('<div class="page">' + bannerHtml() + '<p class="step-label">第 <strong>1</strong> 步，共 3 步 · 选择工单</p>' + cards + "</div>");
	}
	if (!ui.assignOp) {
		const cards = (OPS[order.id] || []).map(function (op) {
			return '<button type="button" class="card-btn" data-act="assign-op" data-id="' + op.id + '"><span class="item-title">' + esc(op.code + " " + op.name) + "</span></button>";
		}).join("");
		return view('<div class="page"><p class="step-label">第 <strong>2</strong> 步，共 3 步 · 选择工序</p><p class="code">' + esc(order.code) + "</p>" + cards + "</div>");
	}
	const mode = ui.assignMode;
	let people = "";
	if (mode === "worker") {
		people = workers.map(function (worker) {
			const on = !!ui.pickedWorkers[worker.id];
			return '<button type="button" class="card-btn' + (on ? " pick-on" : "") + '" data-act="toggle-worker" data-id="' + worker.id + '" aria-pressed="' + (on ? "true" : "false") + '"><span class="item-title">' + esc(worker.name) + '</span><span class="sub">' + (on ? "已选" : "点选") + "</span></button>";
		}).join("");
	} else {
		people = teams.map(function (team) {
			const on = ui.assignTeam === team.id;
			return '<button type="button" class="card-btn' + (on ? " pick-on" : "") + '" data-act="pick-team" data-id="' + team.id + '" aria-pressed="' + (on ? "true" : "false") + '"><span class="item-title">' + esc(team.name) + '</span><span class="sub">' + (on ? "已选" : "点选") + "</span></button>";
		}).join("");
	}
	const chips = '<div class="modes"><button type="button" class="btn-chip' + (mode === "worker" ? " btn-chip-on" : "") + '" data-act="assign-mode" data-value="worker" aria-pressed="' + (mode === "worker") + '">指派给人员</button><button type="button" class="btn-chip' + (mode === "team" ? " btn-chip-on" : "") + '" data-act="assign-mode" data-value="team" aria-pressed="' + (mode === "team") + '">指派给小组</button></div>';
	const body = '<div class="page">' + errorHtml() + '<p class="step-label">第 <strong>3</strong> 步，共 3 步 · 选择人员</p>' + chips + '<div id="assign-target" tabindex="-1">' + people + "</div>" + fieldError("assign-target") + '<label for="assign-remarks">备注</label><input class="field" id="assign-remarks" data-draft placeholder="可空" value="' + esc(draftValue("assign-remarks")) + '"></div>';
	return view(body, '<button type="button" class="btn-primary" data-act="submit-assign">指派</button>');
}

function renderException() {
	const kind = ui.exKind;
	const chips = [["material-shortage", "缺料"], ["delivery-delay", "交期"], ["quality", "质量"]].map(function (item) {
		const on = kind === item[0];
		return '<button type="button" class="btn-chip' + (on ? " btn-chip-on" : "") + '" data-act="ex-kind" data-value="' + item[0] + '" aria-pressed="' + on + '">' + item[1] + "</button>";
	}).join("");
	const orderCards = orders.map(function (item) {
		const on = ui.exOrder === item.id;
		return '<button type="button" class="card-btn' + (on ? " pick-on" : "") + '" data-act="ex-order" data-id="' + item.id + '" aria-pressed="' + on + '"><span class="item-title">' + esc(item.code + " " + item.name) + '</span><span class="sub">' + (on ? "已选" : esc(item.status)) + "</span></button>";
	}).join("");
	let extra = "";
	if (kind === "material-shortage") {
		const word = ui.matKeyword;
		const shown = materials.filter(function (item) {
			return !word || (item.code + item.name).indexOf(word) >= 0;
		});
		extra += '<label for="mat-key">物料</label><div class="search-row"><input class="field" id="mat-key" data-draft placeholder="名称或编码" value="' + esc(draftValue("mat-key")) + '"><button type="button" data-act="search-mat">查找</button></div>';
		extra += '<div id="ex-mat" tabindex="-1">' + (shown.length ? shown.map(function (item) {
			const on = ui.exMaterial === item.code;
			return '<button type="button" class="card-btn' + (on ? " pick-on" : "") + '" data-act="ex-mat" data-id="' + esc(item.code) + '" aria-pressed="' + on + '"><span class="item-title">' + esc(item.code + " " + item.name) + '</span><span class="sub">' + (on ? "已选" : "点选") + "</span></button>";
		}).join("") : '<div class="empty"><p class="empty-title">没有匹配的物料</p></div>') + "</div>" + fieldError("ex-mat");
		extra += '<label for="shortage">缺料数量</label><input class="field num" id="shortage" data-draft inputmode="numeric" value="' + esc(draftValue("shortage")) + '"' + invalidAttr("shortage") + ">" + fieldError("shortage");
	} else if (kind === "delivery-delay") {
		extra += '<label for="delay-reason">延期原因</label><input class="field" id="delay-reason" data-draft value="' + esc(draftValue("delay-reason")) + '"' + invalidAttr("delay-reason") + ">" + fieldError("delay-reason");
		extra += '<label for="delay-days">延期天数</label><input class="field num" id="delay-days" data-draft inputmode="numeric" placeholder="可空" value="' + esc(draftValue("delay-days")) + '">';
	} else {
		extra += '<label for="problem">问题描述</label><input class="field" id="problem" data-draft value="' + esc(draftValue("problem")) + '"' + invalidAttr("problem") + ">" + fieldError("problem");
	}
	const body = '<div class="page">' + errorHtml() + '<div class="modes" id="ex-kind" tabindex="-1">' + chips + '</div><h2 class="section-title">工单</h2><div id="ex-order" tabindex="-1">' + orderCards + "</div>" + fieldError("ex-order") + extra + '<label for="ex-remarks">备注</label><input class="field" id="ex-remarks" data-draft placeholder="可空" value="' + esc(draftValue("ex-remarks")) + '"></div>';
	return view(body, '<button type="button" class="btn-primary" data-act="submit-ex">提交</button>');
}

function renderHub() {
	const rows = [
		["来料检验", countStatus("/quality/incoming", "待检"), "/quality/incoming"],
		["过程检验", countStatus("/quality/process", "待检"), "/quality/process"],
		["成品检验", countStatus("/quality/finished", "待检"), "/quality/finished"],
		["出库检验", countStatus("/quality/oqc", "待检"), "/quality/oqc"]
	].filter(function (row) { return row[1] > 0; });
	const body = rows.length ? rows.map(function (row) {
		return '<button type="button" class="todo" data-act="open-route" data-route="' + esc(row[2]) + '"><span class="todo-title">' + esc(row[0]) + '</span><span class="badge badge-warning">' + row[1] + " 张待检</span></button>";
	}).join("") : '<div class="empty"><p class="empty-title">没有待检单据</p><p class="hint">新的检验单会出现在这里。</p></div>';
	return view('<div class="page">' + bannerHtml() + body + "</div>");
}

function photoBlock() {
	const rows = ui.photos.map(function (name, index) {
		return '<div class="photo-row"><span>' + esc(name) + '</span><button type="button" class="btn-secondary" data-act="remove-photo" data-index="' + index + '" style="width:auto">移除</button></div>';
	}).join("");
	return '<label>附件</label><button type="button" class="btn-secondary" data-act="add-photo">拍照</button>' + rows;
}

function renderInspect(route) {
	const row = ui.conductId ? findRow(route, ui.conductId) : null;
	if (row && row.status === "待检") {
		if (row.okQty == null) row.okQty = String(row.qty);
		if (row.badQty == null) row.badQty = "0";
		const steps = row.steps.map(function (name, index) {
			return '<label>' + esc(name) + "</label>" + choices("step-" + index, [["pass", "合格"], ["fail", "不合格"]]) + fieldError("step-" + index);
		}).join("");
		let oqc = "";
		if (row.kind === "oqc") {
			oqc = '<label>检验结果</label>' + choices("result", [["合格", "合格"], ["不合格", "不合格"], ["部分合格", "部分合格"]]) + fieldError("result") + '<label>质量状态</label>' + choices("qstatus", [["合格", "合格"], ["不合格", "不合格"]]) + fieldError("qstatus") + '<label>放行结论</label>' + choices("release", [["pending", "待判定"], ["release", "放行"], ["reject", "拒绝放行"]]) + fieldError("release") + '<label for="release-note">放行说明</label><input class="field" id="release-note" data-draft value="' + esc(draftValue("release-note")) + '">';
		}
		const reason = row.kind === "oqc" ? "" : '<label for="reason">不合格原因</label><input class="field" id="reason" data-draft placeholder="有不合格步骤时必填" value="' + esc(draftValue("reason")) + '"' + invalidAttr("reason") + ">" + fieldError("reason");
		const body = '<div class="page">' + errorHtml() + '<p class="code">' + esc(row.title) + '</p><p class="sub">' + esc(row.subtitle) + "</p>" + facts([["检验数量", row.qty], ["检验员", "张工"]]) + '<label for="ok-qty">合格数量</label><div class="stepper"><button type="button" data-act="pair-dec" data-key="okQty" aria-label="减少合格数量">−</button><input class="field num" id="ok-qty" readonly value="' + esc(row.okQty) + '"><button type="button" data-act="pair-inc" data-key="okQty" aria-label="增加合格数量">+</button></div><label for="bad-qty">不合格数量</label><div class="stepper"><button type="button" data-act="pair-dec" data-key="badQty" aria-label="减少不合格数量">−</button><input class="field num" id="bad-qty" readonly value="' + esc(row.badQty) + '"><button type="button" data-act="pair-inc" data-key="badQty" aria-label="增加不合格数量">+</button></div>' + fieldError("bad-qty") + oqc + '<label>整体判定</label>' + choices("overall", [["pass", "合格"], ["fail", "不合格"]]) + fieldError("overall") + steps + reason + '<label for="notes">备注</label><input class="field" id="notes" data-draft placeholder="可空" value="' + esc(draftValue("notes")) + '">' + photoBlock() + "</div>";
		return view(body, '<button type="button" class="btn-primary" data-act="submit-inspect" data-id="' + esc(row.id) + '">提交检验</button>');
	}
	const list = (lists[route] || []).slice().sort(function (a, b) { return rank(a.status) - rank(b.status); }).map(function (item) {
		const open = item.status === "待检" ? '<span class="sub">点按执行检验</span>' : "";
		const act = item.status === "待检" ? "open-conduct" : "noop";
		return '<button type="button" class="card-btn" data-act="' + act + '" data-id="' + esc(item.id) + '"><span class="card-top"><span class="item-title">' + esc(item.title) + "</span>" + badge(item.status) + '</span><span class="sub">' + esc(item.subtitle) + "</span>" + open + "</button>";
	}).join("");
	return view('<div class="page">' + bannerHtml() + (list || '<div class="empty"><p class="empty-title">暂无检验单</p></div>') + "</div>");
}

function renderSpot() {
	const row = ui.conductId ? findRow("/equipment/spot-checks", ui.conductId) : null;
	if (row && row.status === "待点检") {
		const steps = row.steps.map(function (name, index) {
			return '<label>' + esc(name) + "</label>" + choices("spot-" + index, [["pass", "合格"], ["fail", "不合格"]]) + fieldError("spot-" + index);
		}).join("");
		return view('<div class="page">' + errorHtml() + '<p class="code">' + esc(row.title) + '</p><p class="sub">' + esc(row.subtitle) + "</p>" + steps + "</div>", '<button type="button" class="btn-primary" data-act="submit-spot" data-id="' + esc(row.id) + '">提交点检</button>');
	}
	const list = lists["/equipment/spot-checks"].map(function (item) {
		const act = item.status === "待点检" ? "open-conduct" : "noop";
		return '<button type="button" class="card-btn" data-act="' + act + '" data-id="' + esc(item.id) + '"><span class="card-top"><span class="item-title">' + esc(item.title) + "</span>" + badge(item.status) + '</span><span class="sub">' + esc(item.subtitle) + "</span></button>";
	}).join("");
	return view('<div class="page">' + bannerHtml() + list + "</div>");
}

function renderFaults() {
	if (ui.faultOpen) {
		const level = ui.choices["fault-level"] || "";
		const body = '<div class="page">' + errorHtml() + '<label for="fault-eq">设备</label><input class="field" id="fault-eq" data-draft value="' + esc(draftValue("fault-eq")) + '"' + invalidAttr("fault-eq") + ">" + fieldError("fault-eq") + '<label for="fault-type">故障类型</label><input class="field" id="fault-type" data-draft placeholder="例如漏油" value="' + esc(draftValue("fault-type")) + '"' + invalidAttr("fault-type") + ">" + fieldError("fault-type") + '<label>等级</label>' + choices("fault-level", [["一般", "一般"], ["严重", "严重"]]) + fieldError("fault-level") + '<label for="fault-desc">描述</label><input class="field" id="fault-desc" data-draft value="' + esc(draftValue("fault-desc")) + '"' + invalidAttr("fault-desc") + ">" + fieldError("fault-desc") + "</div>";
		return view(body, '<button type="button" class="btn-primary" data-act="submit-fault">提交报修</button>');
	}
	const row = ui.detailId ? findRow("/equipment/faults", ui.detailId) : null;
	if (row && row.status === "待处理") {
		const body = '<div class="page">' + errorHtml() + detailBody(row) + '<label for="fault-cause">故障原因</label><input class="field" id="fault-cause" data-draft value="' + esc(draftValue("fault-cause")) + '"' + invalidAttr("fault-cause") + ">" + fieldError("fault-cause") + '<label for="repair-content">维修内容</label><input class="field" id="repair-content" data-draft value="' + esc(draftValue("repair-content")) + '"' + invalidAttr("repair-content") + ">" + fieldError("repair-content") + '<label>维修结果</label>' + choices("repair-result", REPAIR_RESULTS) + fieldError("repair-result") + "</div>";
		return view(body, '<button type="button" class="btn-primary" data-act="submit-repair" data-id="' + esc(row.id) + '">填写维修结果</button>');
	}
	if (row) return view('<div class="page">' + detailBody(row) + "</div>");
	return view('<div class="page">' + listBody("/equipment/faults", visibleRows("/equipment/faults")) + "</div>", '<button type="button" class="btn-primary" data-act="open-fault">登记报修</button>');
}

function renderEquipScan() {
	let body = '<p class="hint">扫设备码后直接看状态，再决定点检或报修。</p>';
	let dockHtml = '<button type="button" class="btn-primary" data-act="scan-eq">模拟扫码</button>';
	if (ui.equipCode) {
		body += '<div class="card"><p class="hint">已识别设备</p><p class="code">EQ-CNC-014</p>' + badge("运行") + facts([["名称", "立式加工中心"], ["车间", "一车间"], ["产线", "一线"]]) + "</div>";
		dockHtml = '<button type="button" class="btn-primary" data-act="open-route" data-route="/equipment/spot-checks">去点检</button><button type="button" class="btn-secondary" data-act="repair-this">登记报修</button>';
	}
	return view('<div class="page">' + body + "</div>", dockHtml);
}

function packingSources() {
	const specs = [["/wms/receipts", "成品入库"], ["/wms/sales-deliveries", "销售出库"]];
	const out = [];
	specs.forEach(function (spec) {
		(lists[spec[0]] || []).forEach(function (row) {
			const products = (row.lines || []).filter(function (item) { return item.productId; }).map(function (item) {
				return { id: item.productId, label: item.materialCode + " " + item.materialName, code: item.materialCode, name: item.materialName };
			});
			out.push({ key: spec[0] + ":" + row.id, label: spec[1] + " " + row.title, products: products });
		});
	});
	return out;
}

function renderPacking() {
	const route = "/mes/packing";
	if (ui.packOpen) {
		const sources = packingSources();
		const source = sources.filter(function (item) { return item.key === ui.choices["pack-source"]; })[0];
		if (source) {
			const picked = ui.choices["pack-product"];
			const still = source.products.some(function (item) { return item.id === picked; });
			if (picked && !still) ui.choices["pack-product"] = "";
		}
		const sourceOptions = sources.map(function (item) { return [item.key, item.label]; });
		const productOptions = source ? source.products.map(function (item) { return [item.id, item.label]; }) : [];
		let body = '<div class="page">' + errorHtml() + '<p class="hint">先选来源单据，再选该单上的产品。箱号可空。</p><label>来源单据</label>' + choices("pack-source", sourceOptions) + fieldError("pack-source");
		if (source) body += '<label>产品</label>' + choices("pack-product", productOptions) + fieldError("pack-product");
		body += '<label for="pack-qty">装箱数量</label><input class="field num" id="pack-qty" data-draft inputmode="numeric" value="' + esc(draftValue("pack-qty")) + '"' + invalidAttr("pack-qty") + ">" + fieldError("pack-qty") + '<label for="pack-box">箱号（可选）</label><input class="field" id="pack-box" data-draft placeholder="可空" value="' + esc(draftValue("pack-box")) + '"></div>';
		return view(body, '<button type="button" class="btn-primary" data-act="submit-pack">确认绑定</button>');
	}
	const row = ui.detailId ? findRow(route, ui.detailId) : null;
	if (row) return view('<div class="page">' + detailBody(row) + "</div>", detailDock(row));
	return view('<div class="page">' + listBody(route, visibleRows(route)) + "</div>", '<button type="button" class="btn-primary" data-act="open-pack">绑定新箱</button>');
}

function renderReminders() {
	const route = "/equipment/maintenance-reminders";
	const row = ui.detailId ? findRow(route, ui.detailId) : null;
	if (row && row.status === "逾期") {
		const body = '<div class="page">' + errorHtml() + detailBody(row) + '<p class="hint">确认后标记已处理。</p><label for="maintain-remark">备注（可选，不会保存）</label><input class="field" id="maintain-remark" data-draft placeholder="可空" value="' + esc(draftValue("maintain-remark")) + '"></div>';
		return view(body, '<button type="button" class="btn-primary" data-act="submit-maintain" data-id="' + esc(row.id) + '">标记已处理</button>');
	}
	return renderBrowser(route);
}

function patrolCounts(row) {
	const fields = row.fields || [];
	for (let i = 0; i < fields.length; i++) {
		if (fields[i][0] !== "已巡") continue;
		const parts = String(fields[i][1]).split("/");
		if (parts.length !== 2) return null;
		const done = Number(parts[0]);
		const total = Number(parts[1]);
		if (Number.isNaN(done) || Number.isNaN(total)) return null;
		return { done: done, total: total, pair: fields[i] };
	}
	return null;
}

function renderPatrols() {
	const route = "/equipment/route-patrols";
	const row = ui.detailId ? findRow(route, ui.detailId) : null;
	if (row && row.status === "进行中") {
		const progress = patrolCounts(row);
		const done = progress ? progress.done : 0;
		const total = progress ? progress.total : 0;
		const label = progress && done < total ? "巡下一点" : "完成巡检";
		const act = progress && done < total ? "patrol-next" : "patrol-finish";
		return view('<div class="page">' + detailBody(row) + "</div>", '<button type="button" class="btn-primary" data-act="' + act + '" data-id="' + esc(row.id) + '">' + label + "</button>");
	}
	return renderBrowser(route);
}

function renderNonconforming() {
	const route = "/quality/nonconforming";
	const row = ui.detailId ? findRow(route, ui.detailId) : null;
	if (row && row.status === "待处置") {
		const code = ui.choices.dispose || "";
		let extra = "";
		if (code === "quarantine" || code === "scrap" || code === "accept" || code === "downgrade") {
			const placeLabel = code === "quarantine" ? "隔离仓库" : code === "scrap" ? "报废仓库" : code === "accept" ? "放行仓库" : "入库仓库";
			extra += '<label>' + placeLabel + "</label>" + choices("dispose-wh", PLACES) + fieldError("dispose-wh");
		}
		if (code === "downgrade") {
			extra += "<label>目标原料</label>" + choices("dispose-mat", materials.map(function (item) { return [item.code, item.name]; })) + fieldError("dispose-mat");
		}
		if (code === "other") {
			extra += '<label for="dispose-note">备注</label><input class="field" id="dispose-note" data-draft value="' + esc(draftValue("dispose-note")) + '"' + invalidAttr("dispose-note") + ">" + fieldError("dispose-note");
		}
		const body = '<div class="page">' + errorHtml() + detailBody(row) + "<label>处置</label>" + choices("dispose", DISPOSE) + fieldError("dispose") + extra + "</div>";
		return view(body, '<button type="button" class="btn-primary" data-act="submit-dispose" data-id="' + esc(row.id) + '">确认处置</button>');
	}
	return renderBrowser(route);
}

function renderMoldScan() {
	let body = '<p class="hint">扫模具码后直接看在库状态。</p>';
	let dockHtml = '<button type="button" class="btn-primary" data-act="scan-mold">模拟扫码</button>';
	if (ui.moldCode) {
		body += '<div class="card"><p class="hint">已识别模具</p><p class="code">MD-INJ-021</p>' + badge("在库") + facts([["名称", "前壳模"], ["类型", "注塑"], ["库位", "模具架 A-3"], ["累计使用", "12000"], ["上次保养", "2026-08-12"]]) + "</div>";
		dockHtml = '<button type="button" class="btn-primary" data-act="open-route" data-route="/mold/borrows">去领用</button>';
	}
	return view('<div class="page">' + body + "</div>", dockHtml);
}

function renderLogin() {
	const org = tenantById(ui.tenantId);
	const selected = org ? '<p class="note">已选组织 ' + esc(org.tenantName) + '</p><button type="button" class="btn-secondary" data-act="clear-tenant">重选组织</button>' : "";
	const results = ui.tenants.map(function (item) {
		return '<button type="button" class="card-btn" data-act="choose-tenant" data-id="' + esc(item.tenantId) + '"><span class="item-title">' + esc(item.tenantName) + '</span><span class="sub">' + esc(item.tenantDomain) + "</span></button>";
	}).join("");
	const body = '<div class="page"><div class="login-hero"><div class="login-mark">星</div><span class="brand-name">星制造</span><span class="brand-desc">用账号进入生产现场</span></div>' + errorHtml() + noticeHtml() + '<label for="username">用户名</label><input class="field" id="username" data-draft autocomplete="username" placeholder="请输入用户名" value="' + esc(draftValue("username")) + '"' + invalidAttr("username") + ">" + fieldError("username") + '<label for="password">密码</label><input class="field" id="password" data-draft type="password" autocomplete="current-password" placeholder="请输入密码" value="' + esc(draftValue("password")) + '"' + invalidAttr("password") + ">" + fieldError("password") + '<label for="org-key">组织</label>' + selected + '<input class="field" id="org-key" data-draft placeholder="组织名称或域名，留空可看全部" value="' + esc(draftValue("org-key")) + '"' + invalidAttr("org-key") + ">" + fieldError("org-key") + '<div style="height:8px"></div><button type="button" class="btn-secondary" data-act="search-org">搜索组织</button>' + results + "</div>";
	return view(body, '<button type="button" class="btn-primary" data-act="password-login">登录</button><button type="button" class="btn-secondary" data-act="wecom">企业微信登录</button>');
}

function renderPage(route) {
	if (route === "apps") return renderApps();
	if (route === "scan-hub") return renderScanHub();
	if (route === "/mes/scan") return renderScan();
	if (route === "/mes/assign") return renderAssign();
	if (route === "/exception/report") return renderException();
	if (route === "/quality") return renderHub();
	if (route === "/quality/process" || route === "/quality/incoming" || route === "/quality/finished" || route === "/quality/oqc") return renderInspect(route);
	if (route === "/equipment/scan") return renderEquipScan();
	if (route === "/equipment/spot-checks") return renderSpot();
	if (route === "/equipment/faults") return renderFaults();
	if (route === "/mes/packing") return renderPacking();
	if (route === "/equipment/maintenance-reminders") return renderReminders();
	if (route === "/equipment/route-patrols") return renderPatrols();
	if (route === "/quality/nonconforming") return renderNonconforming();
	if (route === "/mold/scan") return renderMoldScan();
	if (DOC[route]) {
		if (DOC[route].mode === "doc" || DOC[route].mode === "stock") return renderWizard(route);
		if (DOC[route].mode === "alert") return renderAlert(route);
		if (DOC[route].mode === "query") return renderBrowser(route);
	}
	return renderBrowser(route);
}

function titleOf(route) {
	if (route === "login") return "登录";
	if (route === "workbench") return "工作台";
	if (route === "apps") {
		const block = scopeBlock(ui.appsScope);
		if (block) return block.title;
	}
	const meta = DOC[route];
	if (meta && ui.detailId && (meta.mode === "doc" || meta.mode === "stock")) {
		const names = ["", "单据", "明细", "确认"];
		return meta.title + " · " + (names[ui.step] || "单据");
	}
	if (meta) return meta.title;
	return TITLES[route] || "星制造";
}

function currentRow() {
	return findRow(ui.route, ui.detailId);
}

function capture() {
	document.querySelectorAll("[data-draft]").forEach(function (el) {
		if (el.id) ui.draft[el.id] = el.value;
	});
	const lineQty = document.getElementById("line-qty");
	const row = currentRow();
	if (lineQty && row && row.lines && row.lines[ui.lineIndex]) {
		const key = DOC[ui.route] && DOC[ui.route].mode === "stock" ? "actual" : "issued";
		row.lines[ui.lineIndex][key] = lineQty.value;
	}
	const remarks = document.getElementById("remarks");
	if (remarks && row && row.lines && row.lines[ui.lineIndex]) row.lines[ui.lineIndex].remarks = remarks.value;
}

function lineReady(meta, row) {
	if (!collectsQty(meta)) return true;
	const item = row.lines[ui.lineIndex];
	const value = meta.mode === "stock" ? item.actual : item.issued;
	if (value === "" || value == null || Number.isNaN(Number(value))) {
		ui.errors = [{ id: "line-qty", text: "请填写" + meta.actual + "数量" }];
		return false;
	}
	return true;
}

function blankLineIndex(meta, row) {
	if (!collectsQty(meta)) return -1;
	const key = meta.mode === "stock" ? "actual" : "issued";
	for (let i = 0; i < row.lines.length; i++) {
		const value = row.lines[i][key];
		if (value === "" || value == null || Number.isNaN(Number(value))) return i;
	}
	return -1;
}

function applyNext(next) {
	ui.detailId = next.detailId || "";
	ui.step = next.step || 0;
	ui.lineIndex = next.lineIndex || 0;
	ui.faultOpen = !!next.faultOpen;
	ui.scanCode = next.scanCode || "";
	ui.scanOrder = next.scanOrder || "";
	ui.scanOp = "";
	ui.equipCode = next.equipCode || "";
	ui.moldCode = next.moldCode || "";
	if (next.draft) {
		const keys = Object.keys(next.draft);
		for (let i = 0; i < keys.length; i++) ui.draft[keys[i]] = next.draft[keys[i]];
	}
}

function go(route) {
	const next = ui.next || {};
	ui.next = null;
	ui.detailId = "";
	ui.step = 0;
	ui.lineIndex = 0;
	ui.lineNote = "";
	ui.conductId = "";
	ui.faultOpen = false;
	ui.packOpen = false;
	ui.dialog = null;
	ui.errors = [];
	ui.filter = "全部";
	ui.query = "";
	ui.banner = "";
	ui.notice = "";
	ui.loading = false;
	ui.scanCode = "";
	ui.scanOrder = "";
	ui.scanOp = "";
	ui.equipCode = "";
	ui.moldCode = "";
	ui.photos = [];
	ui.draft = {};
	ui.choices = {};
	ui.resolved = null;
	ui.matKeyword = "";
	applyNext(next);
	ui.route = route;
	const hash = "#/" + encodeURIComponent(route);
	if (location.hash === hash) render();
	else location.hash = hash;
}

function openRoute(route) {
	ui.returnTo = ui.route === "login" || ui.route === "workbench" ? "workbench" : ui.route;
	if (route === "apps") ui.appsScope = "";
	go(route);
}

function showRoute(route) {
	ui.detailId = "";
	ui.step = 0;
	ui.conductId = "";
	ui.faultOpen = false;
	ui.packOpen = false;
	ui.dialog = null;
	ui.route = route;
	const hash = "#/" + encodeURIComponent(route);
	if (location.hash === hash) render();
	else location.hash = hash;
}

function backToParent() {
	const dest = ui.returnTo && ui.returnTo !== ui.route ? ui.returnTo : "workbench";
	ui.returnTo = "workbench";
	go(dest);
}

function goHome() {
	ui.appsScope = "";
	go("workbench");
}

function handleBack() {
	if (ui.dialog) { ui.dialog = null; render(); return; }
	const meta = DOC[ui.route];
	if (meta && (meta.mode === "doc" || meta.mode === "stock") && ui.detailId) {
		if (ui.step > 1) { ui.step -= 1; ui.errors = []; render(); return; }
		ui.detailId = "";
		ui.step = 0;
		render();
		return;
	}
	if (ui.detailId || ui.conductId || ui.faultOpen || ui.packOpen) {
		ui.detailId = "";
		ui.conductId = "";
		ui.faultOpen = false;
		ui.packOpen = false;
		ui.errors = [];
		render();
		return;
	}
	if (ui.route === "/mes/assign") {
		if (ui.assignOp) { ui.assignOp = ""; render(); return; }
		if (ui.assignOrder) { ui.assignOrder = ""; render(); return; }
	}
	if (ui.route === "/mes/scan" && (ui.scanOrder || ui.scanOp)) {
		ui.scanOrder = "";
		ui.scanOp = "";
		ui.scanCode = "";
		render();
		return;
	}
	if (ui.route === "apps" && ui.appsScope) {
		ui.appsScope = "";
		render();
		return;
	}
	backToParent();
}

function openDialog(spec) {
	ui.dialog = spec;
	render();
}

function commitDoc() {
	const meta = DOC[ui.route];
	const row = currentRow();
	if (!row || !meta) return;
	row.status = meta.done;
	ui.banner = meta.done + " " + row.title;
	ui.detailId = "";
	ui.step = 0;
	ui.dialog = null;
	render();
}

function numberOrNull(value) {
	if (value == null || String(value).trim() === "") return null;
	const number = Number(value);
	return Number.isNaN(number) ? null : number;
}

function qualifiedPreview() {
	const reported = numberOrNull(draftValue("reported"));
	const unqualified = numberOrNull(draftValue("unqualified"));
	if (reported == null || unqualified == null || reported < 0 || unqualified < 0 || unqualified > reported) return "";
	return String(reported - unqualified);
}

function render() {
	const route = ui.route;
	navTitle.textContent = titleOf(route);
	backBtn.hidden = route === "login" || route === "workbench";
	homeBtn.hidden = route === "login" || route === "workbench";
	const org = tenantById(ui.tenantId);
	document.getElementById("status-org").textContent = ui.loggedIn && org ? org.tenantName : "未登录";
	const page = route === "login" ? renderLogin() : route === "workbench" ? renderHome() : renderPage(route);
	screen.innerHTML = page.body;
	dock.innerHTML = page.dock || "";
	dock.hidden = !page.dock;
	if (ui.dialog) {
		const danger = ui.dialog.tone === "danger";
		const confirmClass = danger ? "btn-danger" : "btn-primary";
		dialogEl.innerHTML = '<div class="sheet" id="sheet" role="dialog" aria-modal="true" aria-labelledby="dialog-title" tabindex="-1"><h2 id="dialog-title">' + esc(ui.dialog.title) + "</h2><p>" + esc(ui.dialog.body) + '</p><button type="button" class="' + confirmClass + '" data-act="' + esc(ui.dialog.act) + '">' + esc(ui.dialog.confirm) + '</button><button type="button" class="btn-secondary" data-act="dialog-cancel">' + esc(ui.dialog.cancel || "返回修改") + "</button></div>";
		dialogEl.hidden = false;
	} else {
		dialogEl.innerHTML = "";
		dialogEl.hidden = true;
	}
	const summary = document.getElementById("error-summary");
	if (summary) summary.focus();
	else if (ui.dialog) {
		const sheet = document.getElementById("sheet");
		if (sheet) sheet.focus();
	}
}

function onClick(event) {
	const el = event.target.closest("[data-act]");
	if (!el) return;
	const act = el.getAttribute("data-act");
	if (act === "focus-field") {
		const node = document.getElementById(el.getAttribute("data-id"));
		if (node) node.focus();
		return;
	}
	if (act === "noop") return;
	capture();
	ui.errors = [];
	ui.notice = "";
	const route = ui.route;

	if (act === "password-login" || act === "wecom") {
		const errors = [];
		if (!draftValue("username").trim()) errors.push({ id: "username", text: "请输入用户名" });
		if (act === "password-login" && !draftValue("password")) errors.push({ id: "password", text: "请输入密码" });
		if (!ui.tenantId) errors.push({ id: "org-key", text: "请搜索并选择组织" });
		if (errors.length) { ui.errors = errors; render(); return; }
		if (act === "wecom") { ui.notice = "原型不发起企业微信授权"; render(); return; }
		ui.loggedIn = true;
		openRoute("workbench");
		return;
	}
	if (act === "search-org") {
		const word = draftValue("org-key").trim().toLowerCase();
		ui.tenants = TENANTS.filter(function (item) {
			if (!word) return true;
			return item.tenantName.toLowerCase().indexOf(word) >= 0 || item.tenantDomain.toLowerCase().indexOf(word) >= 0;
		});
		if (!ui.tenants.length) ui.errors = [{ id: "org-key", text: "没有匹配的组织" }];
		render();
		return;
	}
	if (act === "choose-tenant") { ui.tenantId = el.getAttribute("data-id"); ui.tenants = []; render(); return; }
	if (act === "clear-tenant") { ui.tenantId = ""; render(); return; }
	if (act === "open-route") { openRoute(el.getAttribute("data-route")); return; }
	if (act === "open-scope") { ui.appsScope = el.getAttribute("data-scope") || ""; render(); return; }
	if (act === "refresh") {
		ui.loading = true;
		render();
		clearTimeout(ui.loadTimer);
		ui.loadTimer = setTimeout(function () { ui.loading = false; ui.banner = "列表已更新"; render(); }, 400);
		return;
	}
	if (act === "run-query") { ui.query = draftValue("query-input").trim(); render(); return; }
	if (act === "clear-filter") { ui.filter = "全部"; ui.query = ""; ui.draft["query-input"] = ""; render(); return; }
	if (act === "set-filter") { ui.filter = el.getAttribute("data-value"); render(); return; }
	if (act === "open-row") {
		ui.detailId = el.getAttribute("data-id");
		ui.step = 1;
		ui.lineIndex = 0;
		ui.lineNote = "";
		render();
		return;
	}
	if (act === "dialog-cancel") { ui.dialog = null; render(); return; }
	if (act === "wizard-next") { ui.step = 2; ui.lineIndex = 0; render(); return; }
	if (act === "qty-dec" || act === "qty-inc") {
		const row = currentRow();
		const meta = DOC[route];
		if (row && meta && collectsQty(meta)) {
			const key = meta.mode === "stock" ? "actual" : "issued";
			const item = row.lines[ui.lineIndex];
			const current = item[key] === "" || item[key] == null ? 0 : Number(item[key]);
			const next = Math.max(0, (Number.isNaN(current) ? 0 : current) + (act === "qty-inc" ? 1 : -1));
			item[key] = String(next);
		}
		render();
		return;
	}
	if (act === "copy-expect") {
		const row = currentRow();
		const meta = DOC[route];
		const item = row && row.lines ? row.lines[ui.lineIndex] : null;
		if (item && meta && meta.mode === "doc" && collectsQty(meta)) item.issued = String(item.qty);
		render();
		return;
	}
	if (act === "locate-line") {
		const row = currentRow();
		if (!row || !row.lines) return;
		const index = row.lines.findIndex(function (item) { return item.materialCode === "MAT-2201"; });
		if (index < 0) {
			ui.lineNote = "这张单没有这个物料";
			render();
			return;
		}
		ui.lineIndex = index;
		ui.lineNote = "已定位到 " + row.lines[index].materialName;
		render();
		return;
	}
	if (act === "line-prev" || act === "line-next" || act === "wizard-review") {
		const row = currentRow();
		const meta = DOC[route];
		if (!row || !meta || !lineReady(meta, row)) { render(); return; }
		if (act === "wizard-review") {
			const blank = blankLineIndex(meta, row);
			if (blank >= 0) {
				ui.lineIndex = blank;
				ui.lineNote = "";
				ui.errors = [{ id: "line-qty", text: "请填写" + meta.actual + "数量" }];
				render();
				return;
			}
		}
		ui.lineNote = "";
		if (act === "line-prev") ui.lineIndex -= 1;
		else if (act === "line-next") ui.lineIndex += 1;
		else ui.step = 3;
		render();
		return;
	}
	if (act === "commit-ask") {
		const row = currentRow();
		const meta = DOC[route];
		if (!row || !meta) return;
		const blank = blankLineIndex(meta, row);
		if (blank >= 0) {
			ui.lineIndex = blank;
			ui.step = 2;
			ui.errors = [{ id: "line-qty", text: "请填写" + meta.actual + "数量" }];
			render();
			return;
		}
		const diffs = meta.mode === "doc" && collectsQty(meta) ? lineDiffs(meta, row) : [];
		if (diffs.length) {
			openDialog({ title: meta.actual + "与" + meta.expect + "不一致", body: diffs.join("。") + "。确认仍要提交？", confirm: "仍然提交", act: "commit-doc", tone: "danger" });
			return;
		}
		commitDoc();
		return;
	}
	if (act === "commit-doc") { commitDoc(); return; }
	if (act === "go-report") {
		ui.next = { scanOrder: el.getAttribute("data-id") || ui.detailId };
		openRoute("/mes/scan");
		return;
	}
	if (act === "do-primary") {
		const row = findRow(route, el.getAttribute("data-id"));
		if (row) { row.status = row.done; ui.banner = row.status + " " + row.title; }
		ui.detailId = "";
		render();
		return;
	}
	if (act === "do-alt") {
		const row = findRow(route, el.getAttribute("data-id"));
		if (!row) return;
		openDialog({ title: "确认" + row.alt, body: row.alt + "后，这条记录会标成" + row.altDone + "。", confirm: "确认" + row.alt, act: "commit-alt", tone: "danger", id: row.id });
		return;
	}
	if (act === "commit-alt") {
		const row = findRow(route, ui.dialog && ui.dialog.id);
		if (row) { row.status = row.altDone; ui.banner = row.status + " " + row.title; }
		ui.detailId = "";
		ui.dialog = null;
		render();
		return;
	}
	if (act === "alert-status") { ui.choices.alert = el.getAttribute("data-value"); render(); return; }
	if (act === "alert-save") {
		const row = currentRow();
		const choice = ui.choices.alert || "processing";
		if (choice === "ignored") {
			openDialog({ title: "忽略这条预警", body: "忽略后，它不再出现在待处理里。", confirm: "确认忽略", act: "commit-alert", tone: "danger" });
			return;
		}
		if (row) row.status = choice === "resolved" ? "已解决" : "处理中";
		if (row) row.notes = draftValue("alert-notes");
		ui.banner = "已保存 " + (row ? row.title : "");
		ui.detailId = "";
		render();
		return;
	}
	if (act === "commit-alert") {
		const row = currentRow();
		if (row) { row.status = "已忽略"; row.notes = draftValue("alert-notes"); ui.banner = "已忽略 " + row.title; }
		ui.detailId = "";
		ui.dialog = null;
		render();
		return;
	}
	if (act === "fake-scan") {
		let code = draftValue("manual-code").trim();
		if (!code) {
			code = SAMPLES[ui.sampleIndex % SAMPLES.length];
			ui.sampleIndex += 1;
		}
		ui.draft["manual-code"] = code;
		ui.resolved = resolveCode(code) || { missing: true };
		render();
		return;
	}
	if (act === "use-sample") {
		const code = el.getAttribute("data-value");
		ui.draft["manual-code"] = code;
		ui.resolved = resolveCode(code) || { missing: true };
		render();
		return;
	}
	if (act === "open-resolved" && ui.resolved && !ui.resolved.missing) {
		ui.next = ui.resolved.next;
		openRoute(ui.resolved.route);
		return;
	}
	if (act === "scan-report") {
		const code = (draftValue("manual-code") || "WO-20261004-018").trim();
		const order = orders.filter(function (item) { return item.code === code; })[0];
		if (!order) { ui.errors = [{ id: "manual-code", text: "没有这张工单" }]; render(); return; }
		ui.scanCode = code;
		ui.scanOrder = order.id;
		ui.scanOp = "";
		render();
		return;
	}
	if (act === "pick-op") { ui.scanOp = el.getAttribute("data-id"); render(); return; }
	if (act === "submit-report") {
		const order = orders.filter(function (item) { return item.id === ui.scanOrder; })[0];
		const op = (OPS[ui.scanOrder] || []).filter(function (item) { return item.id === ui.scanOp; })[0];
		const reported = numberOrNull(draftValue("reported"));
		const unqualified = numberOrNull(draftValue("unqualified"));
		const hours = numberOrNull(draftValue("hours"));
		const errors = [];
		if (reported == null) errors.push({ id: "reported", text: "请填写报工数量" });
		if (unqualified == null) errors.push({ id: "unqualified", text: "请填写不合格数量" });
		if (reported != null && unqualified != null && unqualified > reported) {
			errors.push({ id: "unqualified", text: "不合格数量不能大于报工数量" });
		}
		if (hours == null || hours <= 0) errors.push({ id: "hours", text: "请填写工时" });
		const qualified = reported != null && unqualified != null && unqualified <= reported ? reported - unqualified : null;
		if (!order || !op || qualified == null || errors.length) { ui.errors = errors; render(); return; }
		lists["/mes/reporting-history"].unshift({
			id: "rh-" + Date.now(), title: order.code + " " + op.code + " " + op.name, status: "已提交",
			subtitle: "报工 " + reported + " · 合格 " + qualified + " · 工时 " + hours,
			fields: [["报工数量", String(reported)], ["合格数量", String(qualified)], ["不合格数量", String(unqualified)], ["工时", String(hours)], ["报工人员", "张工"]]
		});
		lists["/mes/reporting-approve"].unshift({
			id: "ra-" + Date.now(), title: order.code + " " + op.code + " " + op.name, status: "待审核",
			subtitle: "张工 · 报工 " + reported,
			fields: [["报工数量", String(reported)], ["合格数量", String(qualified)], ["不合格数量", String(unqualified)], ["工时", String(hours)], ["报工人员", "张工"]],
			action: "通过", alt: "驳回", done: "已通过", altDone: "已驳回"
		});
		ui.banner = "已提交 " + order.code + " " + op.code;
		ui.scanOp = "";
		["reported", "qualified", "unqualified", "hours"].forEach(function (key) { ui.draft[key] = ""; });
		render();
		return;
	}
	if (act === "assign-order") { ui.assignOrder = el.getAttribute("data-id"); render(); return; }
	if (act === "assign-op") { ui.assignOp = el.getAttribute("data-id"); render(); return; }
	if (act === "assign-mode") { ui.assignMode = el.getAttribute("data-value"); render(); return; }
	if (act === "toggle-worker") {
		const id = el.getAttribute("data-id");
		ui.pickedWorkers[id] = !ui.pickedWorkers[id];
		render();
		return;
	}
	if (act === "pick-team") { ui.assignTeam = el.getAttribute("data-id"); render(); return; }
	if (act === "submit-assign") {
		const picked = workers.filter(function (worker) { return ui.pickedWorkers[worker.id]; });
		if (ui.assignMode === "worker" && !picked.length) { ui.errors = [{ id: "assign-target", text: "请选择人员" }]; render(); return; }
		if (ui.assignMode === "team" && !ui.assignTeam) { ui.errors = [{ id: "assign-target", text: "请选择小组" }]; render(); return; }
		const order = orders.filter(function (item) { return item.id === ui.assignOrder; })[0];
		if (order) order.status = "已派工";
		ui.banner = "已指派 " + (order ? order.code : "");
		ui.assignOrder = "";
		ui.assignOp = "";
		ui.pickedWorkers = {};
		ui.assignTeam = "";
		render();
		return;
	}
	if (act === "ex-kind") { ui.exKind = el.getAttribute("data-value"); render(); return; }
	if (act === "ex-order") { ui.exOrder = el.getAttribute("data-id"); render(); return; }
	if (act === "ex-mat") { ui.exMaterial = el.getAttribute("data-id"); render(); return; }
	if (act === "search-mat") { ui.matKeyword = draftValue("mat-key").trim(); render(); return; }
	if (act === "submit-ex") {
		const errors = [];
		if (!ui.exOrder) errors.push({ id: "ex-order", text: "请选择工单" });
		const order = orders.filter(function (item) { return item.id === ui.exOrder; })[0];
		let title = "";
		let subtitle = "";
		let fields = [];
		if (ui.exKind === "material-shortage") {
			if (!ui.exMaterial) errors.push({ id: "ex-mat", text: "请选择物料" });
			const shortage = numberOrNull(draftValue("shortage"));
			if (shortage == null || shortage <= 0) errors.push({ id: "shortage", text: "请填写缺料数量" });
			if (!errors.length && order) {
				const mat = materials.filter(function (item) { return item.code === ui.exMaterial; })[0];
				title = "缺料 " + order.code;
				subtitle = mat.name + " · 缺 " + shortage;
				fields = [["工单", order.code], ["物料", mat.name], ["缺料数量", String(shortage)]];
			}
		} else if (ui.exKind === "delivery-delay") {
			if (!draftValue("delay-reason").trim()) errors.push({ id: "delay-reason", text: "请填写延期原因" });
			if (!errors.length && order) {
				title = "交期 " + order.code;
				subtitle = draftValue("delay-reason") + (draftValue("delay-days") ? " · " + draftValue("delay-days") + " 天" : "");
				fields = [["工单", order.code], ["延期原因", draftValue("delay-reason")], ["延期天数", draftValue("delay-days") || ""]];
			}
		} else if (!draftValue("problem").trim()) {
			errors.push({ id: "problem", text: "请填写问题描述" });
		} else if (order) {
			title = "质量 " + order.code;
			subtitle = draftValue("problem");
			fields = [["工单", order.code], ["问题描述", draftValue("problem")]];
		}
		if (errors.length || !order) { ui.errors = errors.length ? errors : [{ id: "ex-order", text: "请选择工单" }]; render(); return; }
		lists["/exception"].unshift({ id: "ex-" + Date.now(), title: title, status: "待处理", subtitle: subtitle, fields: fields });
		ui.banner = "已提交 " + title;
		ui.exOrder = "";
		ui.exMaterial = "";
		showRoute("/exception");
		return;
	}
	if (act === "open-conduct") { ui.conductId = el.getAttribute("data-id"); ui.choices = {}; ui.photos = []; render(); return; }
	if (act === "choice") { ui.choices[el.getAttribute("data-group")] = el.getAttribute("data-value"); render(); return; }
	if (act === "pair-inc" || act === "pair-dec") {
		const row = findRow(route, ui.conductId);
		if (!row) return;
		const total = Number(row.qty);
		const key = el.getAttribute("data-key");
		const delta = act === "pair-inc" ? 1 : -1;
		let ok = Number(row.okQty);
		let bad = Number(row.badQty);
		if (key === "okQty") ok = Math.max(0, Math.min(total, ok + delta));
		else bad = Math.max(0, Math.min(total, bad + delta));
		if (key === "okQty") bad = total - ok;
		else ok = total - bad;
		row.okQty = String(ok);
		row.badQty = String(bad);
		render();
		return;
	}
	if (act === "add-photo") { ui.photos.push("现场照片" + (ui.photos.length + 1) + ".jpg"); render(); return; }
	if (act === "remove-photo") { ui.photos.splice(Number(el.getAttribute("data-index")), 1); render(); return; }
	if (act === "submit-inspect") {
		const row = findRow(route, el.getAttribute("data-id"));
		const errors = [];
		if (row && row.kind === "oqc") {
			if (!ui.choices.result) errors.push({ id: "result", text: "请选择检验结果" });
			if (!ui.choices.qstatus) errors.push({ id: "qstatus", text: "请选择质量状态" });
			if (!ui.choices.release) errors.push({ id: "release", text: "请选择放行结论" });
		}
		const stepFail = (row && row.steps || []).some(function (name, index) { return ui.choices["step-" + index] === "fail"; });
		if (!ui.choices.overall) errors.push({ id: "overall", text: "请选择整体判定" });
		else if (stepFail && ui.choices.overall !== "fail") errors.push({ id: "overall", text: "有不合格时，整体判定必须是不合格" });
		(row && row.steps || []).forEach(function (name, index) {
			if (!ui.choices["step-" + index]) errors.push({ id: "step-" + index, text: "请判定" + name });
		});
		if (row && row.kind !== "oqc" && stepFail) {
			if (!(Number(row.badQty) > 0)) errors.push({ id: "bad-qty", text: "有不合格步骤时，不合格数量须大于 0" });
			if (!draftValue("reason").trim()) errors.push({ id: "reason", text: "请填写不合格原因" });
		}
		if (errors.length) { ui.errors = errors; render(); return; }
		if (row) row.status = "已检验";
		ui.banner = "已提交检验 " + (row ? row.title : "");
		ui.conductId = "";
		ui.photos = [];
		render();
		return;
	}
	if (act === "submit-spot") {
		const row = findRow("/equipment/spot-checks", el.getAttribute("data-id"));
		const errors = [];
		(row && row.steps || []).forEach(function (name, index) {
			if (!ui.choices["spot-" + index]) errors.push({ id: "spot-" + index, text: "请判定" + name });
		});
		if (errors.length) { ui.errors = errors; render(); return; }
		if (row) row.status = "已点检";
		ui.banner = "已提交点检 " + (row ? row.title : "");
		ui.conductId = "";
		render();
		return;
	}
	if (act === "scan-eq") { ui.equipCode = "EQ-CNC-014"; render(); return; }
	if (act === "scan-mold") { ui.moldCode = "MD-INJ-021"; render(); return; }
	if (act === "repair-this") {
		ui.next = { faultOpen: true, draft: { "fault-eq": "立式加工中心" } };
		openRoute("/equipment/faults");
		return;
	}
	if (act === "open-fault") { ui.faultOpen = true; render(); return; }
	if (act === "submit-fault") {
		const errors = [];
		if (!draftValue("fault-eq").trim()) errors.push({ id: "fault-eq", text: "请填写设备" });
		if (!draftValue("fault-type").trim()) errors.push({ id: "fault-type", text: "请填写故障类型" });
		if (!ui.choices["fault-level"]) errors.push({ id: "fault-level", text: "请选择等级" });
		if (!draftValue("fault-desc").trim()) errors.push({ id: "fault-desc", text: "请填写描述" });
		if (errors.length) { ui.errors = errors; render(); return; }
		const no = "FT-20261004-" + String(lists["/equipment/faults"].length + 3).padStart(3, "0");
		lists["/equipment/faults"].unshift({
			id: "ft-" + Date.now(), title: no, status: "待处理",
			subtitle: draftValue("fault-eq") + " · " + draftValue("fault-desc"),
			fields: [["报修单", no], ["设备", draftValue("fault-eq")], ["故障类型", draftValue("fault-type")], ["等级", ui.choices["fault-level"]], ["描述", draftValue("fault-desc")]]
		});
		ui.banner = "已报修 " + no;
		ui.faultOpen = false;
		ui.choices["fault-level"] = "";
		render();
		return;
	}
	if (act === "open-pack") {
		ui.packOpen = true;
		ui.detailId = "";
		ui.choices["pack-source"] = "";
		ui.choices["pack-product"] = "";
		ui.draft["pack-qty"] = "";
		ui.draft["pack-box"] = "";
		render();
		return;
	}
	if (act === "submit-pack") {
		const errors = [];
		const sources = packingSources();
		const source = sources.filter(function (item) { return item.key === ui.choices["pack-source"]; })[0];
		const product = source ? source.products.filter(function (item) { return item.id === ui.choices["pack-product"]; })[0] : null;
		const qty = numberOrNull(draftValue("pack-qty"));
		const box = draftValue("pack-box").trim();
		if (!source) errors.push({ id: "pack-source", text: "请选择来源单据" });
		if (source && !product) errors.push({ id: "pack-product", text: "请选择产品" });
		if (qty == null || qty <= 0) errors.push({ id: "pack-qty", text: "请填写装箱数量" });
		if (errors.length) { ui.errors = errors; render(); return; }
		lists["/mes/packing"].unshift({
			id: "pk-" + Date.now(),
			title: product.code + " " + product.name,
			status: "已绑定",
			subtitle: (box ? "箱号 " + box : "未填箱号") + " · 数量 " + qty,
			fields: [["来源单据", source.label], ["产品编码", product.code], ["产品名称", product.name], ["装箱数量", String(qty)], ["箱号", box || "未填"], ["方式", "手工"], ["绑定人", "张工"]]
		});
		ui.banner = "已绑定 " + product.name;
		ui.packOpen = false;
		ui.choices["pack-source"] = "";
		ui.choices["pack-product"] = "";
		ui.draft["pack-qty"] = "";
		ui.draft["pack-box"] = "";
		render();
		return;
	}
	if (act === "submit-maintain") {
		const row = findRow("/equipment/maintenance-reminders", el.getAttribute("data-id") || ui.detailId);
		if (row) {
			row.status = "已处理";
			ui.banner = "已标记已处理 " + row.title;
		}
		ui.detailId = "";
		render();
		return;
	}
	if (act === "submit-repair") {
		const row = findRow("/equipment/faults", el.getAttribute("data-id") || ui.detailId);
		const cause = draftValue("fault-cause").trim();
		const content = draftValue("repair-content").trim();
		const result = ui.choices["repair-result"];
		const errors = [];
		if (!cause) errors.push({ id: "fault-cause", text: "请填写故障原因" });
		if (!content) errors.push({ id: "repair-content", text: "请填写维修内容" });
		if (!result) errors.push({ id: "repair-result", text: "请选择维修结果" });
		if (errors.length) { ui.errors = errors; render(); return; }
		if (row) {
			row.status = "已维修";
			row.fields.push(["故障原因", cause], ["维修内容", content], ["维修结果", result]);
			ui.banner = "已维修 " + row.title;
		}
		ui.detailId = "";
		ui.draft["fault-cause"] = "";
		ui.draft["repair-content"] = "";
		ui.choices["repair-result"] = "";
		render();
		return;
	}
	if (act === "patrol-next") {
		const row = findRow("/equipment/route-patrols", el.getAttribute("data-id") || ui.detailId);
		const progress = row ? patrolCounts(row) : null;
		if (progress && progress.done < progress.total) progress.pair[1] = (progress.done + 1) + " / " + progress.total;
		render();
		return;
	}
	if (act === "patrol-finish") {
		const row = findRow("/equipment/route-patrols", el.getAttribute("data-id") || ui.detailId);
		const progress = row ? patrolCounts(row) : null;
		if (!row || !progress || progress.done < progress.total) { render(); return; }
		row.status = "已完成";
		ui.banner = "已完成 " + row.title;
		ui.detailId = "";
		render();
		return;
	}
	if (act === "submit-dispose") {
		const row = findRow("/quality/nonconforming", el.getAttribute("data-id") || ui.detailId);
		const code = ui.choices.dispose || "";
		const errors = [];
		if (!code) errors.push({ id: "dispose", text: "请选择处置" });
		const needsPlace = code === "quarantine" || code === "scrap" || code === "accept" || code === "downgrade";
		if (needsPlace && !ui.choices["dispose-wh"]) {
			const placeText = code === "quarantine" ? "请选择隔离仓库" : code === "scrap" ? "请选择报废仓库" : code === "accept" ? "请选择放行仓库" : "请选择入库仓库";
			errors.push({ id: "dispose-wh", text: placeText });
		}
		if (code === "downgrade" && !ui.choices["dispose-mat"]) errors.push({ id: "dispose-mat", text: "请选择目标原料" });
		if (code === "other" && !draftValue("dispose-note").trim()) errors.push({ id: "dispose-note", text: "请填写备注" });
		if (errors.length) { ui.errors = errors; render(); return; }
		if (row) {
			let text = optionLabel(DISPOSE, code);
			if (needsPlace) text += " · " + ui.choices["dispose-wh"];
			if (code === "downgrade") text += " · " + optionLabel(materials.map(function (item) { return [item.code, item.name]; }), ui.choices["dispose-mat"]);
			if (code === "other") text += " · " + draftValue("dispose-note").trim();
			row.status = "已处置";
			(row.fields || []).forEach(function (pair) { if (pair[0] === "处置") pair[1] = text; });
			ui.banner = "已处置 " + row.title;
		}
		ui.detailId = "";
		ui.choices.dispose = "";
		ui.choices["dispose-wh"] = "";
		ui.choices["dispose-mat"] = "";
		ui.draft["dispose-note"] = "";
		render();
		return;
	}
}

function readHash() {
	const raw = decodeURIComponent((location.hash || "#/login").replace(/^#\//, ""));
	const route = raw || "login";
	if (route !== "login" && !ui.loggedIn) {
		ui.route = "login";
		if (location.hash !== "#/login") location.hash = "#/login";
		else render();
		return;
	}
	ui.route = route;
	render();
}

phone.addEventListener("input", function (event) {
	const el = event.target;
	if (!el) return;
	if (el.id === "reported" || el.id === "unqualified") {
		ui.draft[el.id] = el.value;
		const node = document.getElementById("qualified");
		if (node) node.value = qualifiedPreview();
		return;
	}
	if (el.id !== "feature-find") return;
	ui.draft["feature-find"] = el.value;
	const rest = document.getElementById("feature-rest");
	if (!rest) return;
	rest.innerHTML = featureRest(el.value.trim(), homeTodoHtml(), homeFrequentHtml());
});
phone.addEventListener("click", function (event) {
	if (event.target.id === "dialog") { ui.dialog = null; render(); return; }
	onClick(event);
});
backBtn.addEventListener("click", function () { capture(); handleBack(); });
homeBtn.addEventListener("click", goHome);
window.addEventListener("hashchange", readHash);
readHash();
