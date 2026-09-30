# <img src="docs/screenshots/logo/kuaige.png" alt="Logo" height="36" align="absmiddle" /> 快格云制造


![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=flat-square&logo=typescript)
![Vite](https://img.shields.io/badge/Vite-5-646CFF?style=flat-square&logo=vite)
![Ant Design](https://img.shields.io/badge/Ant%20Design-6-0170FE?style=flat-square&logo=antdesign)
![Expo](https://img.shields.io/badge/Expo-54-000020?style=flat-square&logo=expo)
![Electron](https://img.shields.io/badge/Electron-33-47848F?style=flat-square&logo=electron)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python)
![Pydantic](https://img.shields.io/badge/Pydantic-2-E92063?style=flat-square&logo=pydantic)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?style=flat-square&logo=postgresql)

---

## 15 秒了解快格云制造

为离散制造企业打造的轻量级 MES：以统一需求模型贯通「销售-研发-计划-执行-质量-设备-仓储」，帮助企业在可控成本下快速上线并持续扩展。

**一句话价值**：用一套可渐进实施的制造系统，替代 Excel + 纸单 + 多系统割裂流程。

**适合谁**

- 10–200 人离散制造企业
- 多品种小批量，按单/按库混合生产
- 需要先跑通核心执行，再逐步扩展全流程协同

**你将获得**

- **更快上线**：插件按需启用，先跑通执行再扩展全流程，降低首期投入
- **更稳交付**：销售预测/订单进入统一需求，贯通计划、工单、采购与出入库，减少断点与交期偏差
- **更控质量**：来料到出货检验与追溯闭环，异常可定位、可复盘
- **更轻运维**：流程开关、自定义字段、打印与报表内建；默认 PostgreSQL + Taskiq，**无需 Redis**
- **更可追溯**：需求到执行全链路留痕，便于核对与复盘

---

## 立即体验与接入

- **在线演示**：[https://kuaigeyun.com](https://kuaigeyun.com)（支持免注册体验，数据可能定期重置）
- **部署入口**：[fast-deploy/deploy.sh](fast-deploy/README.md)（Windows / Linux）
- **完整文档**：[docs/部署指南.md](docs/部署指南.md)

> [!WARNING]
> **开源范围**：本仓库仅公开 **后端 API** 与 **PC Web 前端**（`riveredge-backend` + `riveredge-frontend`）；移动端 App、H5、企微/钉钉/飞书、触屏工位、TV 看板等源码在私仓维护。
>
> 产品仍在**积极开发**，功能与数据模型可能频繁变更；在线演示与本地部署**仅供预览评估**，勿用于正式生产或承载真实业务数据。
>
> **安装与升级**请在独立空白服务器或虚拟机中验证，避免与既有系统端口、数据库或配置冲突；**勿**在已承载生产业务的服务器上直接试装。若必须在生产环境部署，**须先完整备份**，否则可能导致数据不可恢复。

### 微信沟通反馈群

<img src="docs/screenshots/wechat/wechat.png" alt="快格云 MES 交流群" width="280" />

扫码加入 **快格云 MES 交流群**，反馈问题与建议。

> [!CAUTION]
> **渠道甄别**：版权方**未**在小红书、闲鱼等第三方平台销售或授权所谓「官方版」。若出现以 **快格云 / RiverEdge 官方授权** 名义的 MES 收费推广，或暗示与本项目（快格云制造）有关，**均非版权方提供或背书**。
>
> 本仓库开源部分采用 Apache 2.0，他人在**保留版权与 LICENSE、不冒用商标**等前提下可合规再分发（含有偿服务），但这**不代表官方渠道**。付费前请核实销售主体、交付物与开源声明是否完整，谨防冒充官方或夸大私仓未开源能力。

---

## 核心能力

业务覆盖 **快制造** 全流程，并与 **主数据**、**快财务**、**快研发** 等插件协同。


| 业务域     | 能力要点                                         |
| ------- | -------------------------------------------- |
| 销售与 CRM | 客户池、报价/跟进/合同、预测、订单与变更、发货/退货、销售看板             |
| 计划与排程   | 统一需求、需求计算（BOM/净需求）、变更、排程/甘特、缺料预警             |
| 采购协同    | 申请/询价、订单与变更、到货/退货、采购执行与报表                    |
| 生产执行    | 工单、报工、返工、委外、装箱、异常闭环；工位/移动端执行                 |
| 质量与追溯   | 来料/过程/成品/OQC、检验方案、8D、SPC、不合格与全链路追溯           |
| 仓储物流    | 入出库、批次/序列号、盘点/调拨、组装拆卸、线边仓/倒冲、库存预警            |
| 设备与资材   | 点检/巡检/故障/维修/保养；模具工装借还、维保、校准与备件               |
| 绩效      | 班次排班、工作日历、技能/计件/KPI                          |
| 财务（快财务） | 应收应付、收付款、发票、对账、成本与总账                         |
| 主档与研发   | 工厂/物料/BOM/工艺/图纸/SOP；NPI 阶段门、变更、FMEA（主数据/快研发） |


**平台（本仓库开源）**：多租户与 RBAC、插件装配、配置中心、审批与消息、编码与自定义字段、打印与连接器、内置看板报表、上线检查与审计。高级分析 / AI / 数采见下方高级版插件。

---

## 插件应用

插件按需装配。**开源版**随本仓库发布；**高级版 / 行业付费版**在私仓 `[kuaigeyun-pro](https://gitee.com/kuaigeyun/kuaigeyun-pro)`，经 `./fast-deploy/deploy.sh pro-apps` 或部署向导 **[4] 扩展应用** 安装。应用中心仅展示已扫描入库的实装应用。


| 分层       | 插件 / 包        | 说明                                                               |
| -------- | ------------- | ---------------------------------------------------------------- |
| **开源**   | 快制造           | 销售、计划、采购、执行、质量、设备、仓储、分析、绩效                                       |
| **开源**   | 主数据           | 工厂建模、物料/BOM/工艺、客户/供应商                                            |
| **开源**   | 快财务           | 应收应付、发票、成本、总账                                                    |
| **开源**   | 快研发           | 研发项目 / NPI、设计变更、知识中心                                             |
| **行业免费** | 本仓库行业包        | 无需 License；示例：辐条轮毂总装（[@xyt123lyq](https://github.com/xyt123lyq)） |
| **行业付费** | kuaigeyun-pro | 需 License；机械加工、注塑、电子、汽配等增值包                                      |
| **高级版**  | KU-AI         | 顶栏助手、单据问答、知识库 RAG                                                |
| **高级版**  | 快报表           | 报表设计、BI 看板、多源聚合                                                  |
| **高级版**  | 快数采           | 工业设备数采与集成（持续迭代）                                                  |


---

## 终端形态

同一套后端 API 与业务模型，按岗位与现场组合部署。本仓库开源 **PC Web + 后端**；其余终端源码在私仓 `[kuaigeyun-client](https://gitee.com/kuaigeyun/kuaigeyun-client)`。


| 终端               | 技术栈                                         | 源码      | 典型场景                  |
| ---------------- | ------------------------------------------- | ------- | --------------------- |
| **PC Web**       | React 18 + TS + Vite 5 + Ant Design 6       | 本仓库（开源） | 计划、主数据、销售/采购/财务、审批、报表 |
| **后端 API**       | FastAPI + Tortoise + PostgreSQL 15 + Taskiq | 本仓库（开源） | 全终端共用业务与权限            |
| **移动 App**       | Expo 54 + React Native                      | 私仓      | 工业 PDA 扫码、移动报工、收发货、巡检 |
| **H5 / 小程序**     | 与 App 同仓导出；小程序为 web-view 壳                  | 私仓      | 轻量访问、iOS 过渡、外协/访客     |
| **企微 / 钉钉 / 飞书** | 办公平台内嵌 H5 + OAuth / JS-SDK                  | 私仓      | 待办审批、消息触达、移动审单与扫码     |
| **触屏工位**         | Windows Electron；可复用 PC 业务模块                | 私仓      | 固定工位过站、戴手套触屏、可选刷脸共享   |
| **TV 看板**        | Android TV + WebView                        | 私仓      | 车间大屏 KPI，开机直达、免登录     |


**选型建议**：办公室计划/物控 → PC；仓库 PDA / 无微信现场 → App；已用企微钉钉飞书 → 办公 H5；产线固定工序 → 触屏工位；班组巡视 → TV 看板。

部署默认 Caddy 反向代理（Web `/`、H5 `/mobile`、API `/api`）。H5 / 企微配置见 [docs/部署指南.md](docs/部署指南.md)；第三方许可见 [NOTICE](NOTICE)。

---

## 快速开始

环境要求：Node.js 22+、Python 3.12+（运行时由 uv 锁定 3.11）、PostgreSQL 15+、Caddy（生产）；默认无需 Redis。

```bash
# Gitee（国内推荐）
git clone https://gitee.com/kuaigeyun/kuaigeyun.git
# GitHub
git clone https://github.com/kuaigeyun/kuaigeyun-mes.git
cd kuaigeyun   # 或 kuaigeyun-mes，取决于 clone 目录名

./fast-deploy/deploy.sh       # 生产模式（8 阶段向导）
./fast-deploy/deploy.sh dev   # 开发模式（Vite 热重载）
```


| 模式  | Web                   | API                   |
| --- | --------------------- | --------------------- |
| 生产  | `http://<服务器IP>:8080` | `/api`（经 Caddy 转发）    |
| 开发  | `http://<服务器IP>:8100` | `http://<服务器IP>:8200` |


- 部署文档：[docs/部署指南.md](docs/部署指南.md)（含**开发预览**与**备份**警告）
- 脚本速查：[fast-deploy/README.md](fast-deploy/README.md)

---

## 推荐配置

单机部署（PostgreSQL 与后端、Taskiq、Caddy 同机）时的硬件参考；详细说明见 [docs/部署指南.md](docs/部署指南.md#硬件建议)。


| 档位       | 适用场景                 | CPU  | 内存    | 磁盘                       |
| -------- | -------------------- | ---- | ----- | ------------------------ |
| **最低配置** | 开发调试、POC 试用、≤10 并发用户 | 2 核+ | 4 GB+ | 20 GB+（系统 + 库 + 日志）      |
| **推荐配置** | 中小团队生产、日常业务与报表       | 4 核+ | 8 GB+ | 50 GB+ SSD（含数据库、附件与日志余量） |


**软件环境（与快速开始一致）**：Node.js 22+、Python 3.12+（运行时由 uv 锁定 3.11）、PostgreSQL 15+；生产模式需 Caddy。**不需要 Redis。**

> 内存 ≤2 GB 的云主机易在 Taskiq 启动阶段因 swap 变慢，部署脚本可自动创建 swap；更稳妥请按**推荐配置**或启用 [低配模式](fast-deploy/README.md) 说明。

---

## 文档导航

- [README](README.md)：产品定位、核心能力、插件与终端、快速启动、推荐配置
- [docs/部署指南.md](docs/部署指南.md)：环境准备、发布流程、运维排查
- [fast-deploy/README.md](fast-deploy/README.md)：部署脚本参数与速查

---

## 联系方式

- 官网：[https://kuaigeyun.com](https://kuaigeyun.com)
- 反馈：Issue 或内部渠道
- 邮箱：[ludingjie@live.cn](mailto:ludingjie@live.cn)
- 微信：`lu_dingjie`

---

## 支持我们

快格云制造持续开源迭代，离不开社区关注与支持。若项目对你有帮助，欢迎：

- 在 [Gitee](https://gitee.com/kuaigeyun/kuaigeyun) / [GitHub](https://github.com/kuaigeyun/kuaigeyun-mes) 给仓库点一颗 **Star**，方便更多制造同行发现
- 关注更新、提交 Issue / PR，一起把产品打磨得更好
- 有条件时通过捐赠支持持续维护（鸣谢名单见下）

> 你的每一个 Star，都是我们继续更新的动力。

### 捐赠鸣谢

感谢以下朋友对项目的支持（按捐赠时间先后排列）：


| 捐赠人     | 金额（元） |
| ------- | ----- |
| lvlijun | 500   |
| Mike猫空  | 66    |


如需出现在名单中，可通过微信 `lu_dingjie` 或邮箱 [ludingjie@live.cn](mailto:ludingjie@live.cn) 联系，并备注展示名称。名单将不定期更新。

---

## 许可证

见 [LICENSE](LICENSE)。