# 移动端 P1 方案 A 验证记录

影响端：`riveredge-app-mobile`（uni-app x / UTS）。未修改后端、PC 端或接口契约；未增加依赖。当前工作区原有登录、组织入口、渠道与静态原型改动保留，未提交 Git。

## 本批修改文件

以下路径均相对移动端工程根目录。

| 文件 | 改动 |
| --- | --- |
| `shell/workbench/index.uvue` | 扫码报工文案；最近使用与默认入口按当前可用导航过滤 |
| `shell/workbench/load.uts` | 各 scope 并发请求，保留单域失败结果与顺序 |
| `shell/workbench/recent.uts`（新增） | 用户、租户分别存储最近入口，不保存业务单据参数 |
| `shell/registry/index.uts` | 导航成功后记录注册入口 |
| `shared/api/session.uts` | 读取当前会话用户 ID |
| `features/workshop/scan-report/index.uvue` | 手输／粘贴解析、数字校验、持续标签、切单清空、提交摘要 |
| `features/workshop/my-work-orders/index.uvue` | 当前用户工单搜索、状态、分页、详情、返回保留位置 |
| `features/workshop/work-orders/index.uvue` | 全部工单同等查询与详情能力 |
| `features/equipment/selection.uts`（新增） | 设备、方案、路线主数据查询与绑定方案解析 |
| `features/equipment/components/master-picker.uvue`（新增） | 编码／名称查询、分页、设备扫码、绑定方案选择，丢弃设备切换前的响应 |
| `features/equipment/spot-checks/index.uvue` | 设备与点检方案选择，沿用后端人员默认规则 |
| `features/equipment/spot-check-conduct/index.uvue` | 设备详情入口选择点检方案 |
| `features/equipment/route-patrols/index.uvue` | 按名称／编码选择巡检路线，沿用人员默认规则 |
| `features/equipment/faults/index.uvue` | 故障设备选择；详情入口回显设备名称 |
| `features/warehouse/board.uvue` | 按需展开编辑、序列号增删、定位滚动、完整提交摘要 |
| `features/warehouse/payload.uts` | 导出原序列号转换函数供表单复用，字段格式不变 |
| `features/quality/components/inspection-board.uvue` | 执行时隐藏列表；三段进度、缺失项定位、照片预览、离开确认 |
| `features/quality/incoming/index.uvue` | 来料检验系统返回拦截 |
| `features/quality/process-scan/index.uvue` | 制程检验系统返回拦截 |
| `features/quality/finished/index.uvue` | 成品检验系统返回拦截 |
| `features/quality/oqc/index.uvue` | 出货检验系统返回拦截 |
| `tests/p0.test.cjs` | 原 P0 回归补充新增首页依赖桩 |
| `tests/p1.test.cjs`（新增） | P1 状态与请求行为回归 |
| `tests/p1-structure.test.cjs`（新增） | 上述 21 个源文件的语法、导入路径与模板标签检查 |
| `tests/README.md`（新增） | 本验证记录 |

## 可重复运行的检查

先进入独立仓库 `kuaigeyun-mes`。测试使用已安装在 PC 工程的 TypeScript；仅转换并执行真实页面脚本，模拟平台 API 和 Vue 状态边界，不模拟页面渲染。

```powershell
node --test kuaigeyun-client/riveredge-app-mobile/tests/p0.test.cjs kuaigeyun-client/riveredge-app-mobile/tests/p1.test.cjs kuaigeyun-client/riveredge-app-mobile/tests/p1-structure.test.cjs
git diff --check
```

2026-10-05 实际结果：19 条检查通过；`git diff --check` 通过。源语法检查不是 UTS 原生类型检查，也不代表发行构建通过。

## 待 HBuilderX 与真实账号验收

- 编译 Web 与目标 App／小程序；375px、横屏、软键盘、滚动和安全区。
- 手输／扫码工单，选择工序，非法数字及不合格数量超限，切换工单清空，成功摘要与我的报工入口。
- 我的／全部工单筛选、20 条分页、断网重试、详情返回位置；从报工页返回工单页保留查询。
- 切换账号、租户与权限，最近入口只展示该会话当前可用项；单 scope 失败不丢其他入口。
- 当前现场账号对设备、方案、绑定和路线的读取权限；多绑定、无绑定、扫码失败、设备切换中的旧响应。未扩大后端权限。
- 点检人员优先设备配置、再当前操作人；巡检人员默认为当前操作人，与后端既有语义一致。
- 多物料仓储单据展开编辑、序列号增删与提交内容；定位重复物料；领料确认仍不另填实领数量。
- 四类检验的三段切换、必填项定位、照片上传／预览、离开确认、提交中禁离开、系统返回。

未执行正式端构建、真实业务提交、实机视觉检查或 PC／后端测试。本地工程要求 HBuilderX，当前环境未找到可用构建器。
