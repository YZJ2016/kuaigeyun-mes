const GLYPH = {
	scan: "📷", user: "👤", file: "📄", list: "≡", history: "🕘", check: "✅",
	"check-circle": "✔️", "close-circle": "❌", inbox: "📦", "plus-square": "➕",
	"minus-square": "➖", warning: "⚠️", chart: "📊", export: "📤", rollback: "↩️",
	shopping: "🛒", truck: "🚚", audit: "📋", search: "🔍", swap: "🔀", bell: "🔔",
	shield: "🛡️", link: "🔗", tool: "🔧", maintain: "🛠️", import: "📥"
};

const TENANTS = [
	{ tenantId: "1001", tenantName: "星环精密", tenantDomain: "xinghuan.local" },
	{ tenantId: "1002", tenantName: "南区装配", tenantDomain: "south.local" }
];

const WORKBENCH = [
	{
		scope: "workshop",
		title: "",
		entries: [
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
		]
	},
	{
		scope: "warehouse",
		title: "仓储作业",
		entries: [
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
		]
	},
	{
		scope: "quality",
		title: "质量检验",
		entries: [
			{ label: "待检验", icon: "shield", route: "/quality" },
			{ label: "过程检验", icon: "scan", route: "/quality/process" },
			{ label: "来料检验", icon: "shopping", route: "/quality/incoming" },
			{ label: "成品检验", icon: "inbox", route: "/quality/finished" },
			{ label: "出库检验", icon: "check-circle", route: "/quality/oqc" },
			{ label: "不合格品", icon: "close-circle", route: "/quality/nonconforming" }
		]
	},
	{
		scope: "equipment",
		title: "设备作业",
		badge: true,
		entries: [
			{ label: "扫码查设备", icon: "scan", route: "/equipment/scan" },
			{ label: "设备点检", icon: "check", route: "/equipment/spot-checks" },
			{ label: "换线绑定", icon: "link", route: "/equipment/line-rebinds" },
			{ label: "路线巡检", icon: "list", route: "/equipment/route-patrols" },
			{ label: "报修维修", icon: "warning", route: "/equipment/faults" },
			{ label: "维修台账", icon: "tool", route: "/equipment/repairs" },
			{ label: "保养执行记录", icon: "maintain", route: "/equipment/maintenance-executions" },
			{ label: "维护提醒", icon: "bell", route: "/equipment/maintenance-reminders" }
		]
	},
	{
		scope: "mold",
		title: "模具作业",
		entries: [
			{ label: "扫码查模具", icon: "scan", route: "/mold/scan" },
			{ label: "模具领用", icon: "export", route: "/mold/borrows" },
			{ label: "模具归还", icon: "import", route: "/mold/returns" },
			{ label: "模具保养", icon: "maintain", route: "/mold/maintenances" },
			{ label: "模具维修", icon: "tool", route: "/mold/repairs" },
			{ label: "模具保养提醒", icon: "bell", route: "/mold/reminders" }
		]
	}
];

const OPS = {
	"1801": [
		{ id: "op10", code: "OP10", name: "上料" },
		{ id: "op20", code: "OP20", name: "组装" },
		{ id: "op30", code: "OP30", name: "测试" }
	],
	"1802": [
		{ id: "op10", code: "OP10", name: "焊接" },
		{ id: "op20", code: "OP20", name: "点胶" }
	],
	"1803": [
		{ id: "op10", code: "OP10", name: "注塑" }
	]
};

const orders = [
	{ id: "1801", code: "WO-20261004-018", name: "星环控制器", status: "生产中", product: "XH-CTRL-A2", mine: true },
	{ id: "1802", code: "WO-20261003-007", name: "传感模组", status: "已派工", product: "SN-MOD-11", mine: true },
	{ id: "1803", code: "WO-20261002-004", name: "外壳组件", status: "待开工", product: "CASE-09", mine: false }
];

const workers = [
	{ id: "18", name: "张工" },
	{ id: "27", name: "李敏" },
	{ id: "31", name: "王磊" }
];

const teams = [
	{ id: "t1", name: "装配一组" },
	{ id: "t2", name: "测试二组" }
];

const materials = [
	{ code: "MAT-2201", name: "连接器座" },
	{ code: "MAT-1188", name: "屏蔽罩" }
];

function line(code, name, qty, book) {
	return {
		materialCode: code,
		materialName: name,
		qty: String(qty),
		warehouseId: "12",
		warehouseName: "原料仓",
		locationId: "3",
		locationCode: "A-01-02",
		batch: "B202610",
		serial: "",
		receipt: String(qty),
		book: String(book == null ? qty : book),
		actual: "",
		remarks: ""
	};
}

function doc(id, code, status, whName, personName, rows) {
	return {
		id: id,
		title: code,
		status: status,
		subtitle: whName + " · " + personName,
		warehouseId: "12",
		warehouseName: whName,
		personId: "18",
		personName: personName,
		lines: rows
	};
}

const lists = {
	"/mes/reporting-history": [
		{ id: "rh1", title: "WO-20261003-007 OP10 焊接", status: "已提交", subtitle: "报工 20 · 合格 20 · 工时 1.5", fields: [["报工数量", "20"], ["合格数量", "20"], ["不合格数量", "0"], ["工时", "1.5"], ["报工人员", "张工"]] }
	],
	"/mes/reporting-approve": [
		{ id: "ra1", title: "WO-20261004-018 OP20 组装", status: "待审核", subtitle: "李敏 · 报工 16", fields: [["报工数量", "16"], ["合格数量", "15"], ["不合格数量", "1"], ["工时", "2"]], action: "通过", alt: "驳回", done: "已通过", altDone: "已驳回" }
	],
	"/mes/packing": [
		{ id: "pk1", title: "XH-CTRL-A2 星环控制器", status: "已绑定", subtitle: "箱号 BX-014", fields: [["产品编码", "XH-CTRL-A2"], ["产品名称", "星环控制器"], ["装箱数量", "12"], ["箱号", "BX-014"], ["方式", "扫码"], ["绑定人", "张工"], ["绑定时间", "2026-10-04 09:20"]] }
	],
	"/exception": [
		{ id: "ex1", title: "缺料 WO-20261004-018", status: "待处理", subtitle: "连接器座 · 缺 40", fields: [["工单", "WO-20261004-018"], ["物料", "连接器座"], ["缺料数量", "40"], ["状态", "待处理"]] },
		{ id: "ex2", title: "交期 WO-20261003-007", status: "跟进中", subtitle: "来料延迟 · 2 天", fields: [["工单", "WO-20261003-007"], ["延期原因", "来料延迟"], ["延期天数", "2"], ["状态", "跟进中"]] },
		{ id: "ex3", title: "质量 WO-20261002-004", status: "待处理", subtitle: "外观划伤 · 一般", fields: [["工单", "WO-20261002-004"], ["问题描述", "外观划伤"], ["严重程度", "一般"], ["状态", "待处理"]] }
	],
	"/performance": [
		{ id: "pf1", title: "张工", status: "已确认", subtitle: "2026-10", fields: [["期间", "2026-10"], ["总工时", "86"], ["总件数", "420"], ["金额", "12600"], ["状态", "已确认"]] }
	],
	"/wms/pickings": [
		doc("pk-1", "PK-20261004-003", "待领料", "原料仓", "张工", [line("MAT-2201", "连接器座", 40), line("MAT-1188", "屏蔽罩", 40)])
	],
	"/wms/returns": [
		doc("rt-1", "RT-20261004-001", "待退料", "原料仓", "李敏", [line("MAT-1188", "屏蔽罩", 6)])
	],
	"/wms/receipts": [
		doc("fg-1", "FG-20261004-008", "待入库", "成品仓", "张工", [line("XH-CTRL-A2", "星环控制器", 12)])
	],
	"/wms/purchase-receipts": [
		doc("pr-1", "PR-20261004-015", "待收货", "原料仓", "王磊", [line("MAT-2201", "连接器座", 200)])
	],
	"/wms/sales-deliveries": [
		doc("sd-1", "SD-20261004-006", "待出库", "成品仓", "李敏", [line("XH-CTRL-A2", "星环控制器", 8)])
	],
	"/wms/delivery-notices": [
		doc("dn-1", "DN-20261004-002", "待发送", "成品仓", "张工", [line("SN-MOD-11", "传感模组", 30)])
	],
	"/wms/other-inbounds": [
		doc("oi-1", "OI-20261003-004", "待入库", "备件仓", "王磊", [line("SP-009", "密封圈", 50)])
	],
	"/wms/other-outbounds": [
		doc("oo-1", "OO-20261003-002", "待出库", "备件仓", "李敏", [line("SP-009", "密封圈", 4)])
	],
	"/wms/stocktaking": [
		doc("st-1", "ST-20261004-001", "盘点中", "原料仓", "张工", [line("MAT-2201", "连接器座", 480, 480), line("MAT-1188", "屏蔽罩", 120, 126)])
	],
	"/wms/inventory": [
		{ id: "ib1", title: "MAT-2201 连接器座", status: "正常", subtitle: "原料仓 · 480", fields: [["物料编码", "MAT-2201"], ["物料名称", "连接器座"], ["单位", "个"], ["数量", "480"], ["仓库", "原料仓"], ["状态", "正常"]] },
		{ id: "ib2", title: "MAT-1188 屏蔽罩", status: "正常", subtitle: "原料仓 · 126", fields: [["物料编码", "MAT-1188"], ["物料名称", "屏蔽罩"], ["单位", "个"], ["数量", "126"], ["仓库", "原料仓"], ["状态", "正常"]] },
		{ id: "ib3", title: "XH-CTRL-A2 星环控制器", status: "正常", subtitle: "成品仓 · 36", fields: [["物料编码", "XH-CTRL-A2"], ["物料名称", "星环控制器"], ["单位", "台"], ["数量", "36"], ["仓库", "成品仓"], ["状态", "正常"]] }
	],
	"/wms/transfers": [
		doc("tf-1", "TF-20261004-001", "待执行", "原料仓", "张工", [line("MAT-2201", "连接器座", 20)])
	],
	"/wms/alerts": [
		{ id: "al1", title: "MAT-1188 低于安全库存", status: "待处理", subtitle: "当前 126", fields: [["物料编码", "MAT-1188"], ["预警", "低于安全库存"], ["当前数量", "126"], ["状态", "待处理"]], notes: "" }
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
		{ id: "nc1", title: "NC-20261003-003", status: "待处置", subtitle: "外观划伤 · 2", fields: [["单号", "NC-20261003-003"], ["产品", "传感模组"], ["缺陷类型", "外观划伤"], ["缺陷数量", "2"], ["缺陷原因", "转运磕碰"], ["处置", "待定"], ["状态", "待处置"]] }
	],
	"/equipment/spot-checks": [
		{ id: "sc1", title: "EQ-CNC-014 立式加工中心", status: "待点检", subtitle: "一车间 · 一线", steps: ["外观", "润滑", "安全防护"] },
		{ id: "sc2", title: "EQ-ASM-006 组装台", status: "已点检", subtitle: "一车间 · 二线", steps: ["外观"] }
	],
	"/equipment/line-rebinds": [
		{ id: "lr1", title: "EQ-CNC-014", status: "待换线", subtitle: "一线 → 三线", fields: [["设备", "立式加工中心"], ["原产线", "一线"], ["目标产线", "三线"], ["状态", "待换线"]], action: "提交换线", done: "已换线" }
	],
	"/equipment/route-patrols": [
		{ id: "rp1", title: "一车间早班路线", status: "进行中", subtitle: "3 个点", fields: [["路线", "一车间早班"], ["已巡", "1 / 3"], ["状态", "进行中"]], action: "完成巡检", done: "已完成" }
	],
	"/equipment/faults": [
		{ id: "ft1", title: "FT-20261004-002", status: "待处理", subtitle: "立式加工中心 · 主轴异响", fields: [["报修单", "FT-20261004-002"], ["设备", "立式加工中心"], ["故障类型", "异响"], ["等级", "一般"], ["描述", "主轴异响"], ["状态", "待处理"]] },
		{ id: "ft2", title: "FT-20261003-009", status: "待处理", subtitle: "组装台 · 急停失灵", fields: [["报修单", "FT-20261003-009"], ["设备", "组装台"], ["故障类型", "急停"], ["等级", "严重"], ["描述", "急停失灵"], ["状态", "待处理"]] }
	],
	"/equipment/repairs": [
		{ id: "rpair1", title: "RP-20261002-004", status: "维修中", subtitle: "立式加工中心", fields: [["维修单", "RP-20261002-004"], ["设备", "立式加工中心"], ["到场", "2026-10-02 14:10"], ["原因", "轴承磨损"], ["内容", "更换轴承"], ["结果", ""], ["状态", "维修中"]], action: "完工", done: "已完工" }
	],
	"/equipment/maintenance-executions": [
		{ id: "me1", title: "立式加工中心 月保", status: "已执行", subtitle: "2026-09-28", fields: [["设备", "立式加工中心"], ["计划", "月保"], ["执行时间", "2026-09-28"], ["执行人", "王磊"], ["状态", "已执行"]] }
	],
	"/equipment/maintenance-reminders": [
		{ id: "mr1", title: "EQ-CNC-014 月保逾期", status: "逾期", subtitle: "上次 2026-09-01", fields: [["设备", "立式加工中心"], ["提醒", "月保"], ["上次保养", "2026-09-01"], ["状态", "逾期"]], action: "已知悉", done: "已读" },
		{ id: "mr2", title: "EQ-ASM-006 周保", status: "未到期", subtitle: "下次 2026-10-08", fields: [["设备", "组装台"], ["提醒", "周保"], ["下次", "2026-10-08"], ["状态", "未到期"]] }
	],
	"/mold/borrows": [
		{ id: "mb1", title: "BR-20261004-003", status: "待领用", subtitle: "MD-INJ-021 前壳模", fields: [["单据", "BR-20261004-003"], ["模具编码", "MD-INJ-021"], ["模具名称", "前壳模"], ["领用日期", "2026-10-04"], ["领用人", "张工"], ["状态", "待领用"]], action: "确认领用", done: "已领用" }
	],
	"/mold/returns": [
		{ id: "mrt1", title: "RN-20261003-001", status: "待归还", subtitle: "MD-INJ-021 前壳模", fields: [["单据", "RN-20261003-001"], ["模具编码", "MD-INJ-021"], ["模具名称", "前壳模"], ["领用人", "张工"], ["状态", "待归还"]], action: "确认归还", done: "已归还" }
	],
	"/mold/maintenances": [
		{ id: "mm1", title: "MD-INJ-021 前壳模", status: "待保养", subtitle: "上次 2026-08-12", fields: [["模具编码", "MD-INJ-021"], ["名称", "前壳模"], ["上次保养", "2026-08-12"], ["状态", "待保养"]], action: "完成保养", done: "已保养" }
	],
	"/mold/repairs": [
		{ id: "mrp1", title: "MD-INJ-008 后盖模", status: "维修中", subtitle: "分型面拉伤", fields: [["模具编码", "MD-INJ-008"], ["名称", "后盖模"], ["现象", "分型面拉伤"], ["状态", "维修中"]] }
	],
	"/mold/reminders": [
		{ id: "mrm1", title: "MD-INJ-021 保养到期", status: "待处理", subtitle: "按次数 · 累计 12000", fields: [["模具编码", "MD-INJ-021"], ["名称", "前壳模"], ["提醒类型", "保养"], ["触发", "按次数"], ["上次保养", "2026-08-12"], ["状态", "待处理"]] }
	]
};

const DOC = {
	"/wms/pickings": { title: "生产领料", person: "领料人", action: "确认领料", done: "已领料", mode: "doc" },
	"/wms/returns": { title: "生产退料", person: "退料人", action: "确认退料", done: "已退料", mode: "doc" },
	"/wms/receipts": { title: "成品入库", person: "入库人", action: "确认入库", done: "已入库", mode: "doc" },
	"/wms/purchase-receipts": { title: "采购收货", person: "收货人", action: "确认收货", done: "已收货", mode: "doc", receipt: true },
	"/wms/sales-deliveries": { title: "销售出库", person: "出库人", action: "确认出库", done: "已出库", mode: "doc" },
	"/wms/delivery-notices": { title: "送货单", person: "发送人", action: "发送", done: "已发送", mode: "doc" },
	"/wms/other-inbounds": { title: "其它入库", person: "入库人", action: "确认入库", done: "已入库", mode: "doc" },
	"/wms/other-outbounds": { title: "其它出库", person: "出库人", action: "确认出库", done: "已出库", mode: "doc" },
	"/wms/stocktaking": { title: "移动盘点", person: "盘点人", mode: "stock" },
	"/wms/inventory": { title: "库存查询", mode: "query" },
	"/wms/transfers": { title: "调拨确认", person: "执行人", action: "执行调拨", done: "已执行", mode: "doc" },
	"/wms/alerts": { title: "库存预警", mode: "alert" }
};

const TITLES = {
	"/mes/scan": "扫码报工",
	"/mes/assign": "工单指派",
	"/mes?my=1": "我的工单",
	"/mes": "全部工单",
	"/mes/reporting-history": "我的报工",
	"/mes/reporting-approve": "报工审核",
	"/mes/packing": "装箱绑定",
	"/exception/report": "异常提报",
	"/exception": "异常追踪",
	"/performance": "我的绩效",
	"/quality": "待检验",
	"/quality/process": "过程检验",
	"/quality/incoming": "来料检验",
	"/quality/finished": "成品检验",
	"/quality/oqc": "出库检验",
	"/quality/nonconforming": "不合格品",
	"/equipment/scan": "扫码查设备",
	"/equipment/spot-checks": "设备点检",
	"/equipment/line-rebinds": "换线绑定",
	"/equipment/route-patrols": "路线巡检",
	"/equipment/faults": "报修维修",
	"/equipment/repairs": "维修台账",
	"/equipment/maintenance-executions": "保养执行记录",
	"/equipment/maintenance-reminders": "维护提醒",
	"/mold/scan": "扫码查模具",
	"/mold/borrows": "模具领用",
	"/mold/returns": "模具归还",
	"/mold/maintenances": "模具保养",
	"/mold/repairs": "模具维修",
	"/mold/reminders": "模具保养提醒"
};

const ui = {
	route: "login",
	loggedIn: false,
	username: "",
	password: "",
	message: "",
	tenantId: "",
	orgOpen: false,
	keyword: "",
	tenants: [],
	detailId: "",
	query: "",
	scanCode: "",
	scanOrder: "",
	scanOp: "",
	exKind: "material-shortage",
	exOrder: "",
	exMaterial: "",
	assignOrder: "",
	assignOp: "",
	assignMode: "worker",
	pickedWorkers: {},
	assignTeam: "",
	conductId: "",
	choices: {},
	equipCode: "",
	moldCode: "",
	faultOpen: false
};

const screen = document.getElementById("screen");
const navTitle = document.getElementById("nav-title");
const backBtn = document.getElementById("back");
const toastEl = document.getElementById("toast");
let toastTimer = 0;

function esc(value) {
	return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
		return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
	});
}

function toast(text) {
	toastEl.textContent = text;
	toastEl.hidden = false;
	clearTimeout(toastTimer);
	toastTimer = setTimeout(function () { toastEl.hidden = true; }, 1600);
}

function go(route) {
	ui.detailId = "";
	ui.conductId = "";
	ui.faultOpen = false;
	location.hash = "#/" + encodeURIComponent(route);
}

function titleOf(route) {
	if (route === "login") return "登录";
	if (route === "workbench") return "工作台";
	if (DOC[route]) return DOC[route].title;
	return TITLES[route] || "星制造";
}

function pendingFaultCount() {
	return lists["/equipment/faults"].filter(function (row) { return row.status === "待处理"; }).length;
}

function overdueCount() {
	return lists["/equipment/maintenance-reminders"].filter(function (row) { return row.status === "逾期"; }).length;
}

function pendingQuality(route) {
	return (lists[route] || []).filter(function (row) { return row.status === "待检"; }).length;
}

function rowsFor(route) {
	if (route === "/mes?my=1") return orders.filter(function (item) { return item.mine; }).map(orderCard);
	if (route === "/mes") return orders.map(orderCard);
	return lists[route] || [];
}

function findRow(route, id) {
	const rows = rowsFor(route);
	for (let i = 0; i < rows.length; i++) {
		if (rows[i].id === id) return rows[i];
	}
	return null;
}

function fieldHtml(pairs) {
	return pairs.map(function (pair) {
		return '<text class="label">' + esc(pair[0]) + "</text><div class=\"meta\">" + esc(pair[1]) + "</div>";
	}).join("");
}

function cardsHtml(rows, openAct) {
	if (rows.length === 0) return '<div class="empty">没有数据</div>';
	return rows.map(function (row) {
		return '<div class="card" data-act="' + openAct + '" data-id="' + esc(row.id) + '"><div class="title">' + esc(row.title) + '</div><div class="meta">' + esc(row.status) + "</div>" + (row.subtitle ? '<div class="meta">' + esc(row.subtitle) + "</div>" : "") + "</div>";
	}).join("");
}

function detailActions(row) {
	let html = "";
	if (row.action) {
		html += '<button class="btn-primary" data-act="do-primary" data-id="' + esc(row.id) + '">' + esc(row.action) + "</button>";
	}
	if (row.alt) {
		html += '<button class="btn-secondary" data-act="do-alt" data-id="' + esc(row.id) + '">' + esc(row.alt) + "</button>";
	}
	return html;
}

function renderList(route) {
	const row = ui.detailId ? findRow(route, ui.detailId) : null;
	if (row) {
		return '<div class="page"><button class="btn-secondary" data-act="close-detail">返回列表</button><div class="card"><div class="title">' + esc(row.title) + '</div><div class="meta">' + esc(row.status) + "</div>" + fieldHtml(row.fields || []) + detailActions(row) + "</div></div>";
	}
	return '<div class="page"><button class="btn-secondary" data-act="refresh">刷新</button>' + cardsHtml(rowsFor(route), "open-row") + "</div>";
}

function orderCard(order) {
	return {
		id: order.id,
		title: order.code + " " + order.name,
		status: order.status,
		subtitle: order.product,
		fields: [["工单", order.code], ["名称", order.name], ["产品", order.product], ["状态", order.status]]
	};
}

function renderDoc(route) {
	const meta = DOC[route];
	const row = ui.detailId ? findRow(route, ui.detailId) : null;
	if (!row) {
		return '<div class="page"><button class="btn-secondary" data-act="refresh">刷新</button>' + cardsHtml(lists[route], "open-row") + "</div>";
	}
	const lines = row.lines.map(function (item, index) {
		let extra = "";
		if (meta.receipt) {
			extra += '<div class="label">实收数量</div><input class="field" data-line="' + index + '" data-key="receipt" value="' + esc(item.receipt) + '">';
		}
		return '<div class="line"><div class="title">' + esc(item.materialCode + " " + item.materialName) + '</div><div class="meta">单据数量 ' + esc(item.qty) + "</div>" +
			'<div class="label">仓库 ID</div><input class="field" data-line="' + index + '" data-key="warehouseId" value="' + esc(item.warehouseId) + '">' +
			'<div class="label">仓库名称</div><input class="field" data-line="' + index + '" data-key="warehouseName" value="' + esc(item.warehouseName) + '">' +
			'<div class="label">库位 ID</div><input class="field" data-line="' + index + '" data-key="locationId" value="' + esc(item.locationId) + '">' +
			'<div class="label">库位编码</div><input class="field" data-line="' + index + '" data-key="locationCode" value="' + esc(item.locationCode) + '">' +
			'<div class="label">批号</div><input class="field" data-line="' + index + '" data-key="batch" value="' + esc(item.batch) + '">' +
			'<div class="label">序列号（逗号分隔）</div><input class="field" data-line="' + index + '" data-key="serial" value="' + esc(item.serial) + '">' +
			extra + "</div>";
	}).join("");
	return '<div class="page"><div class="card"><button class="btn-secondary" data-act="close-detail">返回列表</button><div class="title">' + esc(row.title) + '</div><div class="meta">' + esc(row.status) + "</div>" +
		'<div class="label">仓库 ID</div><input class="field" data-bind="warehouseId" value="' + esc(row.warehouseId) + '">' +
		'<div class="label">仓库名称</div><input class="field" data-bind="warehouseName" value="' + esc(row.warehouseName) + '">' +
		'<div class="label">' + esc(meta.person) + ' ID</div><input class="field" data-bind="personId" value="' + esc(row.personId) + '">' +
		'<div class="label">' + esc(meta.person) + '</div><input class="field" data-bind="personName" value="' + esc(row.personName) + '">' +
		lines +
		'<button class="btn-primary" data-act="confirm-doc" data-id="' + esc(row.id) + '">' + esc(meta.action) + "</button></div></div>";
}

function renderStock(route) {
	const row = ui.detailId ? findRow(route, ui.detailId) : null;
	if (!row) return '<div class="page"><button class="btn-secondary" data-act="refresh">刷新</button>' + cardsHtml(lists[route], "open-row") + "</div>";
	const lines = row.lines.map(function (item, index) {
		return '<div class="line"><div class="title">' + esc(item.materialCode + " " + item.materialName) + '</div><div class="meta">账面 ' + esc(item.book) + '</div><div class="label">实际数量</div><input class="field" data-line="' + index + '" data-key="actual" value="' + esc(item.actual) + '"><div class="label">备注</div><input class="field" data-line="' + index + '" data-key="remarks" value="' + esc(item.remarks) + '"><button class="btn-primary" data-act="stock-line" data-index="' + index + '">记录实盘</button></div>';
	}).join("");
	return '<div class="page"><div class="card"><button class="btn-secondary" data-act="close-detail">返回列表</button><div class="title">' + esc(row.title) + '</div><div class="meta">' + esc(row.status) + "</div>" + lines + "</div></div>";
}

function renderAlert(route) {
	const row = ui.detailId ? findRow(route, ui.detailId) : null;
	if (!row) return '<div class="page"><button class="btn-secondary" data-act="refresh">刷新</button>' + cardsHtml(lists[route], "open-row") + "</div>";
	const current = ui.choices.alert || "processing";
	const chip = function (value, label) {
		return '<button class="' + (current === value ? "btn-chip btn-chip-on" : "btn-chip") + '" data-act="alert-status" data-value="' + value + '">' + label + "</button>";
	};
	return '<div class="page"><div class="card"><button class="btn-secondary" data-act="close-detail">返回列表</button><div class="title">' + esc(row.title) + '</div>' + fieldHtml(row.fields) +
		'<div class="label">处理状态</div><div class="row">' + chip("processing", "处理中") + chip("resolved", "已解决") + chip("ignored", "已忽略") + "</div>" +
		'<div class="label">处理备注</div><input class="field" data-bind="alertNotes" value="' + esc(row.notes || "") + '">' +
		'<button class="btn-primary" data-act="alert-save" data-id="' + esc(row.id) + '">处理</button></div></div>';
}

function renderQuery(route) {
	const word = ui.query.trim();
	const rows = lists[route].filter(function (row) {
		if (!word) return true;
		return (row.title + row.subtitle).indexOf(word) >= 0;
	});
	const detail = ui.detailId ? findRow(route, ui.detailId) : null;
	if (detail) {
		return '<div class="page"><button class="btn-secondary" data-act="close-detail">返回列表</button><div class="card"><div class="title">' + esc(detail.title) + "</div>" + fieldHtml(detail.fields) + "</div></div>";
	}
	return '<div class="page"><div class="row"><input class="field" id="query-input" placeholder="物料编码、名称或仓库" value="' + esc(ui.query) + '"><button class="btn-chip" data-act="run-query">查询</button></div><button class="btn-secondary" data-act="refresh">刷新</button>' + (rows.length ? cardsHtml(rows, "open-row") : '<div class="empty">没有数据</div>') + "</div>";
}

function renderScan() {
	const order = orders.filter(function (item) { return item.id === ui.scanOrder; })[0];
	let body = '<div class="hint">报工人员 张工</div><button class="btn-primary" data-act="fake-scan">扫码</button>';
	if (ui.scanCode) body += '<div class="hint">扫码内容 ' + esc(ui.scanCode) + "</div>";
	if (ui.scanCode) {
		body += orders.map(function (item) {
			return '<div class="card" data-act="pick-order" data-id="' + esc(item.id) + '"><div class="title">' + esc(item.code + " " + item.name) + '</div><div class="sub">' + esc(item.status) + "</div></div>";
		}).join("");
	}
	if (order) {
		body += '<div class="section">选择工序</div>';
		body += (OPS[order.id] || []).map(function (op) {
			const mark = ui.scanOp === op.id ? "已选" : "点选";
			return '<div class="card" data-act="pick-op" data-id="' + esc(op.id) + '"><div class="title">' + esc(op.code + " " + op.name) + '</div><div class="sub">' + mark + "</div></div>";
		}).join("");
		if (ui.scanOp) {
			body += '<input class="field" id="reported" placeholder="报工数量" value="20"><input class="field" id="qualified" placeholder="合格数量" value="19"><input class="field" id="unqualified" placeholder="不合格数量" value="1"><input class="field" id="hours" placeholder="工时（小时）" value="1.5"><button class="btn-primary" data-act="submit-report">提交报工</button>';
		}
	}
	return '<div class="page">' + body + "</div>";
}

function renderAssign() {
	const order = orders.filter(function (item) { return item.id === ui.assignOrder; })[0];
	if (!order) {
		return '<div class="page"><div class="section">选择工单</div>' + orders.map(function (item) {
			return '<div class="card" data-act="assign-order" data-id="' + item.id + '"><div class="title">' + esc(item.code + " " + item.name) + '</div><div class="sub">' + esc(item.status) + "</div></div>";
		}).join("") + "</div>";
	}
	if (!ui.assignOp) {
		return '<div class="page"><button class="btn-secondary" data-act="assign-back-order">返回工单</button><div class="section">选择工序</div>' + (OPS[order.id] || []).map(function (op) {
			return '<div class="card" data-act="assign-op" data-id="' + op.id + '"><div class="title">' + esc(op.code + " " + op.name) + "</div></div>";
		}).join("") + "</div>";
	}
	const mode = ui.assignMode;
	let people = "";
	if (mode === "worker") {
		people = workers.map(function (worker) {
			const on = ui.pickedWorkers[worker.id];
			return '<div class="card" data-act="toggle-worker" data-id="' + worker.id + '"><div class="title">' + esc(worker.name) + '</div><div class="sub">' + (on ? "已选" : "点选") + "</div></div>";
		}).join("");
	} else {
		people = teams.map(function (team) {
			return '<div class="card" data-act="pick-team" data-id="' + team.id + '"><div class="title">' + esc(team.name) + '</div><div class="sub">' + (ui.assignTeam === team.id ? "已选" : "点选") + "</div></div>";
		}).join("");
	}
	return '<div class="page"><button class="btn-secondary" data-act="assign-back-op">返回工序</button><div class="modes"><button class="' + (mode === "worker" ? "btn-chip btn-chip-on" : "btn-chip") + '" data-act="assign-mode" data-value="worker">指派给人员</button><button class="' + (mode === "team" ? "btn-chip btn-chip-on" : "btn-chip") + '" data-act="assign-mode" data-value="team">指派给小组</button></div>' + people + '<input class="field" id="assign-remarks" placeholder="备注（可空）"><button class="btn-primary" data-act="submit-assign">指派</button></div>';
}

function renderException() {
	const kind = ui.exKind;
	const chip = function (value, label) {
		return '<button class="' + (kind === value ? "btn-chip btn-chip-on" : "btn-chip") + '" data-act="ex-kind" data-value="' + value + '">' + label + "</button>";
	};
	let extra = "";
	const orderCards = '<div class="section">工单</div>' + orders.map(function (item) {
		return '<div class="card" data-act="ex-order" data-id="' + item.id + '"><div class="title">' + esc(item.code + " " + item.name) + '</div><div class="sub">' + (ui.exOrder === item.id ? "已选" : esc(item.status)) + "</div></div>";
	}).join("");
	if (kind === "material-shortage") {
		extra = '<input class="field" id="mat-key" placeholder="物料名称或编码" value=""><button class="btn-secondary" data-act="search-mat">查找物料</button>' + materials.map(function (item) {
			return '<div class="card" data-act="ex-mat" data-id="' + esc(item.code) + '"><div class="title">' + esc(item.code + " " + item.name) + '</div><div class="sub">' + (ui.exMaterial === item.code ? "已选" : "点选") + "</div></div>";
		}).join("") + '<input class="field" id="shortage" placeholder="缺料数量" value="40">';
	} else if (kind === "delivery-delay") {
		extra = '<input class="field" id="delay-reason" placeholder="延期原因" value="来料延迟"><input class="field" id="delay-days" placeholder="延期天数（可空）" value="2">';
	} else {
		extra = '<input class="field" id="problem" placeholder="问题描述" value="外观划伤">';
	}
	return '<div class="page"><div class="modes">' + chip("material-shortage", "缺料") + chip("delivery-delay", "交期") + chip("quality", "质量") + "</div>" + orderCards + extra + '<input class="field" id="ex-remarks" placeholder="备注（可空）"><button class="btn-primary" data-act="submit-ex">提交</button></div>';
}

function renderHub() {
	const rows = [
		["来料检验", pendingQuality("/quality/incoming"), "/quality/incoming"],
		["过程检验", pendingQuality("/quality/process"), "/quality/process"],
		["成品检验", pendingQuality("/quality/finished"), "/quality/finished"],
		["出库检验", pendingQuality("/quality/oqc"), "/quality/oqc"]
	].filter(function (row) { return row[1] > 0; });
	const body = rows.length === 0 ? '<div class="empty">汇总里没有待检项</div>' : rows.map(function (row) {
		return '<div class="card" data-act="open-route" data-route="' + esc(row[2]) + '"><div class="title">' + esc(row[0]) + '</div><div class="meta">待检 ' + row[1] + "</div></div>";
	}).join("");
	return '<div class="page"><button class="btn-secondary" data-act="refresh">刷新</button>' + body + "</div>";
}

function choice(group, value, label) {
	const on = ui.choices[group] === value;
	return '<span class="' + (on ? "choice choice-on" : "choice") + '" data-act="choice" data-group="' + group + '" data-value="' + esc(value) + '">' + esc(label) + "</span>";
}

function renderInspect(route) {
	const row = ui.conductId ? findRow(route, ui.conductId) : null;
	let form = "";
	if (row && row.status === "待检") {
		const steps = (row.steps || []).map(function (name, index) {
			return '<div class="label">' + esc(name) + '</div><div class="choices">' + choice("step-" + index, "pass", "合格") + choice("step-" + index, "fail", "不合格") + "</div>";
		}).join("");
		let oqc = "";
		if (row.kind === "oqc") {
			oqc = '<div class="label">检验结果</div><div class="choices">' + choice("result", "合格", "合格") + choice("result", "不合格", "不合格") + choice("result", "部分合格", "部分合格") + "</div>" +
				'<div class="label">质量状态</div><div class="choices">' + choice("qstatus", "合格", "合格") + choice("qstatus", "不合格", "不合格") + "</div>" +
				'<div class="label">放行结论</div><div class="choices">' + choice("release", "pending", "待判定") + choice("release", "release", "放行") + choice("release", "reject", "拒绝放行") + "</div>" +
				'<div class="label">放行说明</div><input class="field" id="release-note" value="">';
		}
		const reason = row.kind === "oqc" ? "" : '<div class="label">不合格原因</div><input class="field" id="reason" value="">';
		const uuid = row.kind === "oqc" ? "" : '<div class="label">检验人员 UUID</div><input class="field" id="inspector-uuid" value="u-18">';
		form = '<div class="card"><div class="title">执行检验 ' + esc(row.title) + '</div><div class="meta">检验数量 ' + esc(row.qty) + "</div>" +
			'<div class="label">合格数量</div><input class="field" id="ok-qty" value="' + esc(row.qty) + '"><div class="label">不合格数量</div><input class="field" id="bad-qty" value="0">' +
			oqc + '<div class="label">备注</div><input class="field" id="notes" value="">' + reason +
			'<div class="label">检验人员 ID</div><input class="field" id="inspector-id" value="18">' + uuid +
			'<div class="label">附件</div><div class="link-text">添加附件</div>' +
			'<div class="label">整体判定</div><div class="choices">' + choice("overall", "pass", "合格") + choice("overall", "fail", "不合格") + "</div>" +
			steps + '<button class="btn-primary" data-act="submit-inspect" data-id="' + esc(row.id) + '">提交检验</button></div>';
	}
	const list = lists[route].map(function (item) {
		const button = item.status === "待检" ? '<button class="btn-secondary" data-act="open-conduct" data-id="' + esc(item.id) + '">执行检验</button>' : "";
		return '<div class="card"><div class="title">' + esc(item.title) + '</div><div class="meta">' + esc(item.subtitle) + " · " + esc(item.status) + "</div>" + button + "</div>";
	}).join("");
	return '<div class="page"><button class="btn-secondary" data-act="refresh">刷新</button>' + (list || '<div class="empty">暂无检验单</div>') + form + "</div>";
}

function renderSpot() {
	const row = ui.conductId ? findRow("/equipment/spot-checks", ui.conductId) : null;
	let form = "";
	if (row && row.status === "待点检") {
		const steps = row.steps.map(function (name, index) {
			return '<div class="label">' + esc(name) + '</div><div class="choices">' + choice("spot-" + index, "pass", "合格") + choice("spot-" + index, "fail", "不合格") + "</div>";
		}).join("");
		form = '<div class="card"><div class="title">点检 ' + esc(row.title) + "</div>" + steps + '<button class="btn-primary" data-act="submit-spot" data-id="' + esc(row.id) + '">提交点检</button></div>';
	}
	const list = lists["/equipment/spot-checks"].map(function (item) {
		const button = item.status === "待点检" ? '<button class="btn-secondary" data-act="open-conduct" data-id="' + esc(item.id) + '">点检</button>' : "";
		return '<div class="card"><div class="title">' + esc(item.title) + '</div><div class="meta">' + esc(item.status) + "</div><div class=\"meta\">" + esc(item.subtitle) + "</div>" + button + "</div>";
	}).join("");
	return '<div class="page">' + list + form + "</div>";
}

function renderFaults() {
	const list = cardsHtml(lists["/equipment/faults"], "open-row");
	const row = ui.detailId ? findRow("/equipment/faults", ui.detailId) : null;
	if (row) {
		return '<div class="page"><button class="btn-secondary" data-act="close-detail">返回列表</button><div class="card"><div class="title">' + esc(row.title) + "</div>" + fieldHtml(row.fields) + "</div></div>";
	}
	const form = ui.faultOpen ? '<div class="card"><div class="label">设备</div><input class="field" id="fault-eq" value="立式加工中心"><div class="label">故障类型</div><input class="field" id="fault-type" value="漏油"><div class="label">等级</div><input class="field" id="fault-level" value="一般"><div class="label">描述</div><input class="field" id="fault-desc" value="导轨渗油"><button class="btn-primary" data-act="submit-fault">提交报修</button></div>' : '<button class="btn-primary" data-act="open-fault">登记报修</button>';
	return '<div class="page">' + form + list + "</div>";
}

function renderEquipScan() {
	let body = '<button class="btn-primary" data-act="scan-eq">扫码</button>';
	if (ui.equipCode) {
		body += '<div class="hint">扫码内容 ' + esc(ui.equipCode) + '</div><div class="card"><div class="title">立式加工中心</div><div class="meta">运行</div>' + fieldHtml([["设备编码", "EQ-CNC-014"], ["名称", "立式加工中心"], ["状态", "运行"], ["车间", "一车间"], ["产线", "一线"]]) + "</div>";
	}
	return '<div class="page">' + body + "</div>";
}

function renderMoldScan() {
	let body = '<button class="btn-primary" data-act="scan-mold">扫码</button>';
	if (ui.moldCode) {
		body += '<div class="hint">扫码内容 ' + esc(ui.moldCode) + '</div><div class="card"><div class="title">前壳模</div><div class="meta">在库</div>' + fieldHtml([["模具编码", "MD-INJ-021"], ["名称", "前壳模"], ["类型", "注塑"], ["状态", "在库"], ["库位", "模具架 A-3"], ["累计使用", "12000"], ["上次保养", "2026-08-12"]]) + "</div>";
	}
	return '<div class="page">' + body + "</div>";
}

function renderLogin() {
	const orgMsg = ui.message === "没有匹配的组织" || ui.message === "请搜索并选择组织" || ui.message === "请先确定组织";
	let org = '<div class="org-toggle" data-act="toggle-org">' + (ui.orgOpen ? "收起组织搜索" : "搜索组织") + "</div>";
	if (ui.tenantId) org = '<div class="meta">当前组织 ' + esc(ui.tenantId) + "</div>" + org;
	if (orgMsg) org += '<div class="meta">' + esc(ui.message) + "</div>";
	if (ui.orgOpen) {
		org += '<input class="field" id="org-key" placeholder="组织名称或域名" value="' + esc(ui.keyword) + '"><button class="btn-secondary" data-act="search-org">搜索组织</button>';
		org += ui.tenants.map(function (item) {
			return '<div class="list-row" data-act="choose-tenant" data-id="' + esc(item.tenantId) + '"><div class="title">' + esc(item.tenantName) + '</div><div class="muted">' + esc(item.tenantDomain) + "</div></div>";
		}).join("");
	}
	const err = ui.message && !orgMsg ? '<div class="error">' + esc(ui.message) + "</div>" : "";
	return '<div class="login-page"><div class="login-hero"><div class="login-mark">星</div><span class="brand-name">星制造</span><span class="brand-desc">用账号进入生产现场</span></div><div class="card login-card"><div class="login-label login-label-first">用户名</div><input class="field" id="username" placeholder="请输入用户名" value="' + esc(ui.username) + '"><div class="login-label">密码</div><input class="field" id="password" type="password" placeholder="请输入密码" value="' + esc(ui.password) + '">' + err + '<button class="btn-primary" data-act="password-login">登录</button></div><button class="btn-secondary" data-act="wecom">企业微信登录</button><div class="login-org">' + org + "</div></div>";
}

function renderWorkbench() {
	const html = WORKBENCH.map(function (block) {
		let badge = "";
		if (block.badge) {
			const pending = pendingFaultCount();
			const overdue = overdueCount();
			badge = '<div class="badges"><div class="badge-row"><span class="badge-label">待处理故障 ' + pending + "</span>" + (pending > 0 ? '<span class="badge-num">' + pending + "</span>" : "") + '</div><div class="badge-row"><span class="badge-label">逾期保养提醒 ' + overdue + "</span>" + (overdue > 0 ? '<span class="badge-num">' + overdue + "</span>" : "") + "</div></div>";
		}
		const title = block.title ? '<div class="section-title">' + esc(block.title) + "</div>" : "";
		const cells = block.entries.map(function (cell) {
			const icon = GLYPH[cell.icon] || "";
			return '<div class="' + (cell.solo ? "cell solo" : "cell") + '" data-act="open-route" data-route="' + esc(cell.route) + '">' + (icon ? '<span class="icon">' + icon + "</span>" : "") + '<span class="title">' + esc(cell.label) + "</span></div>";
		}).join("");
		return '<div class="scope">' + badge + title + '<div class="grid">' + cells + "</div></div>";
	}).join("");
	return '<div class="page">' + html + "</div>";
}

function renderPage(route) {
	if (route === "/mes/scan") return renderScan();
	if (route === "/mes/assign") return renderAssign();
	if (route === "/exception/report") return renderException();
	if (route === "/quality") return renderHub();
	if (route === "/quality/process" || route === "/quality/incoming" || route === "/quality/finished" || route === "/quality/oqc") return renderInspect(route);
	if (route === "/equipment/scan") return renderEquipScan();
	if (route === "/equipment/spot-checks") return renderSpot();
	if (route === "/equipment/faults") return renderFaults();
	if (route === "/mold/scan") return renderMoldScan();
	if (DOC[route]) {
		if (DOC[route].mode === "doc") return renderDoc(route);
		if (DOC[route].mode === "stock") return renderStock(route);
		if (DOC[route].mode === "alert") return renderAlert(route);
		if (DOC[route].mode === "query") return renderQuery(route);
	}
	return renderList(route);
}

function render() {
	const route = ui.route;
	navTitle.textContent = titleOf(route);
	const showBack = route !== "login" && route !== "workbench";
	backBtn.hidden = !showBack;
	document.getElementById("nav").style.background = route === "login" ? "#F1F1F4" : "#E7D9FD";
	screen.innerHTML = route === "login" ? renderLogin() : route === "workbench" ? renderWorkbench() : renderPage(route);
	screen.querySelectorAll("[data-act]").forEach(function (el) {
		if (el.tagName !== "BUTTON") {
			el.setAttribute("role", "button");
			el.tabIndex = 0;
		}
	});
}

function readInput(id) {
	const el = document.getElementById(id);
	return el ? el.value : "";
}

function syncBinds(route) {
	const row = findRow(route, ui.detailId);
	if (!row) return;
	screen.querySelectorAll("[data-bind]").forEach(function (el) {
		row[el.getAttribute("data-bind")] = el.value;
		if (el.getAttribute("data-bind") === "alertNotes") row.notes = el.value;
	});
	screen.querySelectorAll("[data-line]").forEach(function (el) {
		const item = row.lines[Number(el.getAttribute("data-line"))];
		if (item) item[el.getAttribute("data-key")] = el.value;
	});
}

function onClick(event) {
	const el = event.target.closest("[data-act]");
	if (!el) return;
	const act = el.getAttribute("data-act");
	const route = ui.route;
	if (act === "password-login") {
		ui.username = readInput("username").trim();
		ui.password = readInput("password");
		if (!ui.username) { ui.message = "请输入用户名"; render(); return; }
		if (!ui.password) { ui.message = "请输入密码"; render(); return; }
		ui.message = "";
		ui.loggedIn = true;
		go("workbench");
		return;
	}
	if (act === "wecom") {
		ui.message = ui.tenantId ? "原型不发起企业微信授权" : "请先确定组织";
		render();
		return;
	}
	if (act === "toggle-org") {
		ui.username = readInput("username");
		ui.password = readInput("password");
		ui.orgOpen = !ui.orgOpen;
		render();
		return;
	}
	if (act === "search-org") {
		ui.keyword = readInput("org-key").trim();
		ui.username = readInput("username");
		ui.password = readInput("password");
		const word = ui.keyword.toLowerCase();
		ui.tenants = TENANTS.filter(function (item) {
			if (!word) return true;
			return item.tenantName.toLowerCase().indexOf(word) >= 0 || item.tenantDomain.toLowerCase().indexOf(word) >= 0;
		});
		ui.message = ui.tenants.length === 0 ? "没有匹配的组织" : "";
		render();
		return;
	}
	if (act === "choose-tenant") {
		ui.tenantId = el.getAttribute("data-id");
		ui.message = "";
		render();
		return;
	}
	if (act === "open-route") {
		go(el.getAttribute("data-route"));
		return;
	}
	if (act === "refresh") { toast("已刷新"); render(); return; }
	if (act === "open-row") { ui.detailId = el.getAttribute("data-id"); render(); return; }
	if (act === "close-detail") { ui.detailId = ""; render(); return; }
	if (act === "do-primary" || act === "do-alt") {
		const row = findRow(route, el.getAttribute("data-id"));
		if (row) {
			row.status = act === "do-primary" ? row.done : row.altDone;
			toast(row.status);
		}
		ui.detailId = "";
		render();
		return;
	}
	if (act === "confirm-doc") {
		syncBinds(route);
		const row = findRow(route, el.getAttribute("data-id"));
		if (row) { row.status = DOC[route].done; toast(DOC[route].action); }
		ui.detailId = "";
		render();
		return;
	}
	if (act === "stock-line") {
		syncBinds(route);
		const row = findRow(route, ui.detailId);
		const item = row && row.lines[Number(el.getAttribute("data-index"))];
		if (item && !item.actual) { toast("请填写实际数量"); return; }
		toast("已记录实盘");
		if (row) row.status = "已记录";
		render();
		return;
	}
	if (act === "alert-status") { syncBinds(route); ui.choices.alert = el.getAttribute("data-value"); render(); return; }
	if (act === "alert-save") {
		syncBinds(route);
		const row = findRow(route, el.getAttribute("data-id"));
		const label = { processing: "处理中", resolved: "已解决", ignored: "已忽略" }[ui.choices.alert || "processing"];
		if (row) row.status = label;
		toast("已处理");
		ui.detailId = "";
		render();
		return;
	}
	if (act === "run-query") { ui.query = readInput("query-input"); render(); return; }
	if (act === "fake-scan") { ui.scanCode = "WO-20261004-018"; render(); return; }
	if (act === "pick-order") { ui.scanOrder = el.getAttribute("data-id"); ui.scanOp = ""; render(); return; }
	if (act === "pick-op") { ui.scanOp = el.getAttribute("data-id"); render(); return; }
	if (act === "submit-report") {
		const order = orders.filter(function (item) { return item.id === ui.scanOrder; })[0];
		const op = (OPS[ui.scanOrder] || []).filter(function (item) { return item.id === ui.scanOp; })[0];
		if (!order || !op) return;
		lists["/mes/reporting-history"].unshift({
			id: "rh-" + Date.now(),
			title: order.code + " " + op.code + " " + op.name,
			status: "已提交",
			subtitle: "报工 " + readInput("reported") + " · 合格 " + readInput("qualified") + " · 工时 " + readInput("hours"),
			fields: [["报工数量", readInput("reported")], ["合格数量", readInput("qualified")], ["不合格数量", readInput("unqualified")], ["工时", readInput("hours")], ["报工人员", "张工"]]
		});
		lists["/mes/reporting-approve"].unshift({
			id: "ra-" + Date.now(),
			title: order.code + " " + op.code + " " + op.name,
			status: "待审核",
			subtitle: "张工 · 报工 " + readInput("reported"),
			fields: [["报工数量", readInput("reported")], ["合格数量", readInput("qualified")], ["不合格数量", readInput("unqualified")], ["工时", readInput("hours")]],
			action: "通过",
			alt: "驳回",
			done: "已通过",
			altDone: "已驳回"
		});
		toast("已提交");
		ui.scanOp = "";
		render();
		return;
	}
	if (act === "assign-order") { ui.assignOrder = el.getAttribute("data-id"); render(); return; }
	if (act === "assign-op") { ui.assignOp = el.getAttribute("data-id"); render(); return; }
	if (act === "assign-back-order") { ui.assignOrder = ""; ui.assignOp = ""; render(); return; }
	if (act === "assign-back-op") { ui.assignOp = ""; render(); return; }
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
		if (ui.assignMode === "worker" && picked.length === 0) { toast("请选择人员"); return; }
		if (ui.assignMode === "team" && !ui.assignTeam) { toast("请选择小组"); return; }
		const order = orders.filter(function (item) { return item.id === ui.assignOrder; })[0];
		if (order) order.status = "已派工";
		toast("已指派");
		ui.assignOrder = "";
		ui.assignOp = "";
		render();
		return;
	}
	if (act === "ex-kind") { ui.exKind = el.getAttribute("data-value"); render(); return; }
	if (act === "ex-order") { ui.exOrder = el.getAttribute("data-id"); render(); return; }
	if (act === "ex-mat") { ui.exMaterial = el.getAttribute("data-id"); render(); return; }
	if (act === "search-mat") { toast(materials.length + " 条物料"); return; }
	if (act === "submit-ex") {
		if (!ui.exOrder) { toast("请选择工单"); return; }
		const order = orders.filter(function (item) { return item.id === ui.exOrder; })[0];
		let title = "";
		let subtitle = "";
		let fields = [];
		if (ui.exKind === "material-shortage") {
			if (!ui.exMaterial) { toast("请选择物料"); return; }
			const mat = materials.filter(function (item) { return item.code === ui.exMaterial; })[0];
			title = "缺料 " + order.code;
			subtitle = mat.name + " · 缺 " + readInput("shortage");
			fields = [["工单", order.code], ["物料", mat.name], ["缺料数量", readInput("shortage")], ["状态", "待处理"]];
		} else if (ui.exKind === "delivery-delay") {
			title = "交期 " + order.code;
			subtitle = readInput("delay-reason") + " · " + readInput("delay-days") + " 天";
			fields = [["工单", order.code], ["延期原因", readInput("delay-reason")], ["延期天数", readInput("delay-days")], ["状态", "待处理"]];
		} else {
			title = "质量 " + order.code;
			subtitle = readInput("problem");
			fields = [["工单", order.code], ["问题描述", readInput("problem")], ["状态", "待处理"]];
		}
		lists["/exception"].unshift({ id: "ex-" + Date.now(), title: title, status: "待处理", subtitle: subtitle, fields: fields });
		toast("已提交");
		render();
		return;
	}
	if (act === "open-conduct") { ui.conductId = el.getAttribute("data-id"); ui.choices = {}; render(); return; }
	if (act === "choice") { ui.choices[el.getAttribute("data-group")] = el.getAttribute("data-value"); render(); return; }
	if (act === "submit-inspect") {
		const row = findRow(route, el.getAttribute("data-id"));
		if (row && row.kind !== "oqc" && !ui.choices.overall) { toast("请选择整体判定"); return; }
		if (row) row.status = "已检验";
		ui.conductId = "";
		toast("已提交检验");
		render();
		return;
	}
	if (act === "submit-spot") {
		const row = findRow("/equipment/spot-checks", el.getAttribute("data-id"));
		if (row) row.status = "已点检";
		ui.conductId = "";
		toast("已提交点检");
		render();
		return;
	}
	if (act === "scan-eq") { ui.equipCode = "EQ-CNC-014"; render(); return; }
	if (act === "scan-mold") { ui.moldCode = "MD-INJ-021"; render(); return; }
	if (act === "open-fault") { ui.faultOpen = true; render(); return; }
	if (act === "submit-fault") {
		const no = "FT-20261004-" + String(lists["/equipment/faults"].length + 3).padStart(3, "0");
		lists["/equipment/faults"].unshift({
			id: "ft-" + Date.now(),
			title: no,
			status: "待处理",
			subtitle: readInput("fault-eq") + " · " + readInput("fault-desc"),
			fields: [["报修单", no], ["设备", readInput("fault-eq")], ["故障类型", readInput("fault-type")], ["等级", readInput("fault-level")], ["描述", readInput("fault-desc")], ["状态", "待处理"]]
		});
		ui.faultOpen = false;
		toast("已报修");
		render();
	}
}

function readHash() {
	const raw = decodeURIComponent((location.hash || "#/login").replace(/^#\//, ""));
	const route = raw || "login";
	if (route !== "login" && !ui.loggedIn) {
		ui.route = "login";
		render();
		return;
	}
	ui.route = route;
	render();
}

screen.addEventListener("click", onClick);
backBtn.addEventListener("click", function () {
	if (ui.detailId || ui.conductId || ui.faultOpen) {
		ui.detailId = "";
		ui.conductId = "";
		ui.faultOpen = false;
		render();
		return;
	}
	go("workbench");
});
window.addEventListener("hashchange", readHash);
readHash();
