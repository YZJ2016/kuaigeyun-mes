# <img src="docs/screenshots/logo/kuaige.png" alt="Logo" height="36" align="absmiddle" /> 星技谷制造


![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=flat-square&logo=typescript)
![Vite](https://img.shields.io/badge/Vite-5-646CFF?style=flat-square&logo=vite)
![Ant Design](https://img.shields.io/badge/Ant%20Design-6-0170FE?style=flat-square&logo=antdesign)
![uni-app x](https://img.shields.io/badge/uni--app%20x-%E8%92%B8%E6%B1%BD%E6%A8%A1%E5%BC%8F-2B9939?style=flat-square)
![Electron](https://img.shields.io/badge/Electron-44-47848F?style=flat-square&logo=electron)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python)
![Pydantic](https://img.shields.io/badge/Pydantic-2-E92063?style=flat-square&logo=pydantic)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?style=flat-square&logo=postgresql)

---

## 15 秒了解星技谷制造

为离散制造企业打造的轻量级 MES：以统一需求模型贯通「销售-研发-计划-执行-质量-设备-仓储」，帮助企业在可控成本下快速上线并持续扩展。

**一句话价值**：用一套可渐进实施的制造系统，替代 Excel + 纸单 + 多系统割裂流程。

**适合谁**

- 10–200 人离散制造企业
- 多品种小批量，按单/按库混合生产
- 需要先跑通核心执行，再逐步扩展全流程协同

**你将获得**

- **更快上线**：插件按需启用，先跑通执行再扩展全流程，降低首期投入
- **更稳交付**：需求贯通计划、工单、采购与出入库，减少断点与交期偏差
- **更控质量**：来料到出货检验与追溯闭环，异常可定位、可复盘

---

## 立即体验与接入

- **在线演示**：[https://kuaigeyun.com](https://kuaigeyun.com)（支持免注册体验，数据可能定期重置）
- **部署入口**：[fast-deploy/deploy.sh](fast-deploy/README.md)（Windows / Linux）
- **完整文档**：[docs/部署指南.md](docs/部署指南.md)

> [!WARNING]
> **仓库范围**：本仓库包含 **后端 API**、**PC Web**（`riveredge-backend` + `riveredge-frontend`）、**移动端**（`kuaigeyun-client/riveredge-app-mobile`，uni-app x 蒸汽模式，同一工程出 Android、iOS、H5、微信小程序）与 **工位壳**（`kuaigeyun-client/riveredge-app-station`，Electron 44）。TV 看板客户端不在本仓。
>
> 星技谷制造仍在**积极开发中**，功能、数据模型与界面可能频繁变更；在线演示与本地部署**仅供预览与评估**，请勿用于正式生产或承载真实业务数据。

> [!CAUTION]
> **建议在独立空白服务器或虚拟机环境中进行安装与验证**，避免与既有业务系统产生端口、数据库或配置冲突。**不建议**在已承载生产业务的服务器上直接试装或试升级。
>
> 若因业务需要必须在生产服务器上部署，**须事先完成完整备份**；未备份即执行上述操作，可能导致**数据不可恢复。**

### 微信沟通反馈群

<img src="docs/screenshots/wechat/wechat.png" alt="星技谷 MES 交流群" width="280" />

扫码加入 **星技谷 MES 交流群**，反馈问题与建议。

> [!IMPORTANT]
> **甄别声明**：网络上个别第三方渠道出现的 MES 收费推广或所谓「官方授权版」，**非星技谷官方提供**，与本项目（星技谷制造）无关联。请用户注意甄别，勿向非官方渠道付费购买。

---

## 为什么选择星技谷制造

- **统一业务主线**：销售预测/销售订单统一进入 `需求`，贯通需求计算、工单/采购、执行与出入库。
- **可渐进上线**：插件化应用按需启用，支持从最小可用到全流程协同的分阶段实施。
- **低运维负担**：默认 PostgreSQL + Taskiq，无 Redis 依赖；部署路径标准化。
- **高配置灵活性**：流程开关、自定义字段、打印与报表能力内建，适配多工厂差异流程。
- **可追溯与可审计**：从需求到执行全链路留痕，便于交付核对、异常定位与持续改进。

---

## 核心能力

### 业务域能力

覆盖 **星制造** 全流程，并与 **主数据**、**星财务**、**星研发** 插件协同。

| 业务域 | 关键能力 |
| --- | --- |
| 销售与 CRM | 客户池、报价/跟进/合同、销售预测、订单与变更、发货通知/退货、销售域看板与报表 |
| 计划与排程 | Demand 统一建模、需求计算（BOM/净需求）、需求变更、排程/滚动排程、甘特与缺料预警 |
| 采购协同 | 采购申请/询价、订单与变更、到货通知/退货、采购看板与执行报表 |
| 生产执行 | 工单、报工、返工、委外、装箱绑定、异常闭环；工位终端（Windows 触屏/移动车间） |
| 质量与追溯 | 来料/过程/成品/OQC、检验方案、8D、SPC、不合格台账、全链路追溯 |
| 仓储物流 | 入出库 Hub、批次/序列号、盘点/调拨、组装拆卸、线边仓/倒冲、条码映射、库存预警 |
| 设备与资材 | 设备点检/巡检/故障/维修/保养；模具/工装借还、维保、校准与备件 |
| 绩效与财务 | 班次排班、工作日历、技能/计件/KPI 汇总；应收应付、发票、对账与成本核算（星财务） |
| 主档与研发 | 工厂/物料/BOM/工艺/图纸/SOP、客户供应商价目；研发项目/NPI 阶段门/变更/FMEA（主数据/星研发） |

### 平台能力

**开源版（本仓库）**

- 多租户 SaaS、RBAC 权限、字段掩码与数据范围
- 插件化应用装配、配置中心、流程开关与单据动作策略
- 审批流、消息模板/提醒规则、编码规则与自定义字段
- 打印模板/打印设备、数据集与 API/应用连接集成
- 各业务域内置看板与报表、上线向导/启动检查、操作与登录审计
- 扫码与二维码（PC、移动 H5、微信小程序、工位终端）

**高级版（私仓 kuaigeyun-pro，可选安装）**

- **星报表**：报表设计器、BI 看板、多源聚合分析
- **星AI**：顶栏智能助手、知识库 RAG、业务单据问答
- **星数采**：工业设备数采与集成（持续迭代）

---

## 插件应用矩阵

插件按需装配；**开源版**随本仓库发布，**高级版**在私仓 [`kuaigeyun-pro`](https://gitee.com/kuaigeyun/kuaigeyun-pro) 维护，经 `./fast-deploy/deploy.sh pro-apps` 或部署向导 **[4] 扩展应用** 安装。

### 开源版（本仓库）

| 插件 | 定位 | 主要范围 |
| --- | --- | --- |
| **星制造** | 全流程制造 MES | 销售、计划、采购、执行、质量、设备、仓储、分析、绩效 |
| **主数据** | 主档中心 | 工厂建模、物料/BOM/工艺、客户/供应商 |
| **星财务** | 管理会计与总账 | 应收应付、收付款、发票库、成本管理、总账（科目/凭证/结账/账表） |
| **星研发** | 研发协同 | 研发项目 / NPI 阶段门、设计变更、知识中心 |

### 行业应用

行业应用按 **免费版（主仓）** 与 **付费版（私仓 kuaigeyun-pro）** 分层发布；应用中心「行业」分类**仅展示已扫描入库的实装应用**，不再展示占位卡片。

| 版本 | 仓库 | 授权 | 示例 |
| --- | --- | --- | --- |
| **行业免费版** | 本仓库 | 无需 License Key | **辐条轮毂总装**（总装调试 / 同心度检测，[@xyt123lyq](https://github.com/xyt123lyq)） |
| **行业付费版** | 私仓 kuaigeyun-pro | 需 License Key | 机械加工、注塑、电子、汽配等行业增值包 |

### 高级版（私仓 kuaigeyun-pro）

| 插件 | 定位 | 主要范围 |
| --- | --- | --- |
| **星AI** | 业务 AI 助手 | 顶栏智能问答、单据查询、知识库 RAG |
| **星报表** | 经营分析 | 报表设计、BI 看板、多源聚合 |
| **星数采** | 工业物联网 | 设备数采与集成（持续迭代中） |

---

## 技术架构

| 终端 | 技术栈 | 源码 |
| --- | --- | --- |
| **PC Web** | React 18 + TypeScript 5 + Vite 5 + Ant Design 6 / Pro Components | 本仓库 `riveredge-frontend` |
| **后端 API** | FastAPI 0.115 + Pydantic 2 + Tortoise ORM 0.21 + PostgreSQL 15 + Taskiq；运行时 Python 3.11 | 本仓库 `riveredge-backend` |
| **移动端 App** | uni-app x 蒸汽模式（`.uvue` / UTS）+ uni-ui x 1.0.5；Android / iOS | 本仓库 `kuaigeyun-client/riveredge-app-mobile` |
| **H5** | 与 App **同一套** uni-app x 工程；HBuilderX 发行 Web 到 `unpackage/dist/build/web`，Caddy 挂 `/mobile` | 同上 |
| **企业微信 / 钉钉 / 飞书** | H5 内嵌工作台；企业微信 OAuth；JS-SDK 扫码签名只接受 `wecom` / `dingtalk` / `feishu` | 本仓库 `kuaigeyun-client/riveredge-app-mobile/shared/channel/h5` |
| **微信小程序** | 同一套 uni-app x 编译到 `mp-weixin`；扫码走小程序 `uni.scanCode` | 本仓库 `kuaigeyun-client/riveredge-app-mobile/shared/channel/mp-weixin` |
| **触屏工位机** | Windows + Electron 44.4.5；薄壳只放主进程，窗口加载服务器工位入口 | 本仓库 `kuaigeyun-client/riveredge-app-station`（本仓跟踪，仓外打包） |
| **TV 看板** | 本仓没有该客户端 | — |

部署与平台：多租户 SaaS、插件化应用、Caddy 反向代理（Web `/`、H5 `/mobile`、API `/api`）。

- 移动端发行与 H5 路径：见 [kuaigeyun-client/riveredge-app-mobile/README.md](kuaigeyun-client/riveredge-app-mobile/README.md)、[RELEASE.md](kuaigeyun-client/riveredge-app-mobile/RELEASE.md)；部署见 [docs/部署指南.md](docs/部署指南.md)（`install-h5` 复制本机已发行的 HBuilderX Web）
- 第三方资源与许可：见 [NOTICE](NOTICE) 与系统内“关于 → 版权声明”

---

## 项目组成矩阵

同一套后端 API 与业务模型，按**使用场景**拆成多种终端形态。企业可按岗位与现场条件组合部署，不必「一刀切」只上 PC 或只上 App。

| 终端 | 形态 | 典型场景 | 为何选用 |
| --- | --- | --- | --- |
| **PC Web** | 浏览器访问 | 计划排程、主数据维护、销售/采购/财务协同、审批、报表与看板设计 | 大屏 + 键鼠，适合复杂表单、多页签并行与办公室长时间操作 |
| **移动端 App** | Android / iOS 安装包（uni-app x） | 工业 PDA 扫码、车间移动报工、仓管收发货、巡检点检 | **不依赖微信与浏览器**；可绑定专用设备；Android 工业 PDA 生态成熟，适合不便安装微信的现场 |
| **移动端 小程序** | 微信小程序（同一套 uni-app x 编译到 `mp-weixin`） | 苹果用户临时访问、轻量查询与报工、外协/访客短时使用 | 免应用商店安装；微信内即可进入 |
| **移动端 办公平台** | 企业微信 / 钉钉 / 飞书 内嵌 H5 | 待办与审批提醒、消息触达、扫码入库/点检、经理移动审单 | 接入组织通讯录与单点登录；**通知推到已在用的办公软件**，降低推广与账号管理成本 |
| **触屏工位机** | Windows Electron 触屏 | 固定工位过站报工、工序扫码确认、线边仓领退料 | 大按钮触屏交互，戴手套也可操作；可固定产线点位，减少员工掏手机 |
| **触屏工位机** | 共享人脸报工模式 | 多班次、多工位共用一台终端，刷脸识别操作员 | 免账号密码输入；适合流水线上**多人轮流、快速过站**的共享场景 |
| **TV 看板** | 本仓未包含该客户端 | 车间大屏、产线 KPI、设备状态、工单进度看板 | 状态一眼可见，无需登录操作 |

**选型建议（可组合）**

| 岗位 / 现场 | 推荐终端 | 说明 |
| --- | --- | --- |
| 计划、物控、办公室文员 | PC Web | 主数据与单据录入的主战场 |
| 仓库 PDA、无微信现场 | 移动端 App（Android） | 独立安装，扫码性能与设备管控更好 |
| 苹果手机一线员工 | 小程序或 iOS 安装包 | 小程序免应用商店；iOS 与 Android 同一套 uni-app x |
| 已全员使用企微/钉钉/飞书 | 办公平台 H5 + 消息提醒 | 少一个新 App，审批与告警跟现有习惯走 |
| 产线固定工序 | 触屏工位机 | 屏幕常亮、触屏优先，减少误操作 |
| 车间入口或班组长区域 | TV 看板 | 状态一眼可见，无需登录操作 |

> **源码说明**：本仓库含 **PC Web、后端 API、移动端**（uni-app x：Android / iOS / H5 / 微信小程序，含企微 / 钉钉 / 飞书的 H5 接入）与 **工位壳**。TV 看板客户端不在本仓。安装包与 H5 静态资源由 HBuilderX 发行或部署脚本复制，不在本仓提交构建产物。

---

## 快速开始

环境要求：Node.js 22+、Python 3.11（`uv.lock` 锁定 `==3.11.*`，工程要求 `>=3.11,<3.12`）、PostgreSQL 15+、Caddy（生产）；默认无需 Redis。移动端用 HBuilderX 发行，不经 npm 编译。

```bash
# Gitee（国内推荐）
git clone https://gitee.com/kuaigeyun/kuaigeyun.git
# GitHub
git clone https://github.com/kuaigeyun/kuaigeyun-mes.git
cd kuaigeyun   # 或 kuaigeyun-mes，取决于 clone 目录名

./fast-deploy/deploy.sh       # 生产模式（8 阶段向导）
./fast-deploy/deploy.sh dev   # 开发模式（Vite 热重载）
```

| 模式 | Web | API |
| --- | --- | --- |
| 生产 | `http://<服务器IP>:8080` | `/api`（经 Caddy 转发） |
| 开发 | `http://<服务器IP>:8100` | `http://<服务器IP>:8200` |

- 部署文档：[docs/部署指南.md](docs/部署指南.md)（含**开发预览**与**备份**警告）
- 脚本速查：[fast-deploy/README.md](fast-deploy/README.md)

---

## 文档导航

- [README](README.md)：产品定位、能力边界、快速启动
- [docs/部署指南.md](docs/部署指南.md)：环境准备、发布流程、运维排查
- [fast-deploy/README.md](fast-deploy/README.md)：部署脚本参数与速查

---

## 联系方式

- 官网：[https://kuaigeyun.com](https://kuaigeyun.com)
- 反馈：Issue 或内部渠道
- 邮箱：[ludingjie@live.cn](mailto:ludingjie@live.cn)
- 微信：`lu_dingjie`

---

## 许可证

见 [LICENSE](LICENSE)。
