# 加载与动效方案 B：第一批

日期：2026-10-06。仅影响移动端；不修改接口、依赖或最低平台版本。

## 文件与行为

| 文件 | 修改 |
| --- | --- |
| shared/ui/load-feedback.uvue | 公共首次加载、刷新、分页和阻塞反馈；首次加载静态占位；原生 loading 动画延迟 160ms 显示；8 秒仍等待时补充说明；结束立即移除提示；重启和销毁清理定时器 |
| shell/workbench/index.uvue | 首次占位、后续更新保留已加载内容；取消重色遮罩，保留按钮操作锁定；失败仍沿用原错误处理 |
| features/workshop/my-work-orders/index.uvue | 区分首次、刷新和分页；分页反馈位于列表底部，保留已加载记录 |
| features/workshop/work-orders/index.uvue | 同上，保持既有查询、分页与请求票号规则 |
| features/warehouse/board.uvue | 共用仓储列表分场景反馈；详情加载保留浅色阻塞层；记录实盘和确认提交接入按钮 busy；移除列表遮罩后补齐加载期间查询、卡片、分页锁定 |
| tests/p1.test.cjs | 工单首次／刷新／分页模式回归 |
| tests/p2.test.cjs | 短请求提示抑制、慢请求提示、重启与销毁清理、仓储分页锁定回归 |
| tests/p1-structure.test.cjs | 新公共组件源码检查 |

原生 loading 文档：https://doc.dcloud.net.cn/uni-app-x/component/loading.html 。没有添加 CSS keyframes 或 animation，也未修改导航转场。

## 验证

移动端目录执行：

```powershell
node --test tests/p0.test.cjs tests/p1.test.cjs tests/p1-structure.test.cjs tests/p2.test.cjs
```

45 项通过，0 失败。Git 根目录 `git diff --check` 通过。上述验证为源码与 VM 行为验证，未执行 HBuilderX 编译和真机渲染；未提交 Git。

真机需确认：原生加载组件兼容性、短请求视觉抑制、刷新内容与滚动位置、分页底部反馈、详情遮挡、提交忙碌反馈，以及计时器在页面离开后的行为。

本批完成公共基础和上述页面接入。其余设备、质量、模具、账号等页面的加载反馈，以及导航转场统一仍待后续批次迁移。

## 第二批：设备与模具

17 个页面或组件接入公共反馈。现有请求 URL、参数、响应处理和过期响应票号机制保留。列表和表单不再使用原深色遮罩，首次显示静态占位，后续刷新保留内容；输入、日期、选择、按钮在加载期间禁用，继续保护未完成的数据。扫码读取保留公共浅色阻塞反馈。

| 目录 | 修改文件与内容 |
| --- | --- |
| features/equipment/ | detail、faults、line-rebinds、maintenance-executions、maintenance-reminders、repairs、route-patrols、scan、spot-check-conduct、spot-checks 下的 index.uvue：公共加载反馈、表单锁定；提交操作沿用 busy 状态显示“提交中” |
| features/equipment/components/master-picker.uvue | 局部查询、绑定方案和扫码反馈；分页反馈在底部；设备变化重置加载表现；保留旧响应丢弃规则 |
| features/mold/ | mold-borrows、mold-maintenances、mold-reminders、mold-repairs、mold-returns、mold-scan 下的 index.uvue：公共加载反馈；保留聚合并行加载状态、选择与提交锁定 |
| features/equipment/faults/index.uvue | 单独跟踪详情读取状态，显示等待反馈，重复详情读取被阻止，失败后解锁，不改变请求契约 |
| tests/p2.test.cjs | 设备日期继续可选，加载和 busy 均保护日期操作；新增详情等待、失败解锁与请求不重复回归 |

执行完整 Node 命令：46 项通过，0 失败。`git diff --check` 通过。未修改后端、PC、依赖或版本门槛，未提交 Git。仍未执行 HBuilderX 编译及真机验证。

本批真机重点：表单在列表／方案／预览加载期间禁用、保留已有记录的刷新、故障详情读取、设备选择器局部与分页反馈、设备切换后旧请求返回、扫码取消、模具并行请求结束时反馈撤销、提交忙碌文案。

后续剩余：质量共用组件和页面、账号与登录初始化、功能分组、生产的报工／指派／异常／装箱／只读记录等页面，以及导航转场策略。本批未修改这些流程的动效。

## 第三批：质量模块

影响移动端 6 个页面：待检验汇总、不合格品处置，以及共享检验组件覆盖的来料、过程、成品、出货检验。

- `features/quality/quality-hub/index.uvue`：首次占位、刷新局部反馈、加载时禁用刷新与进入记录。
- `features/quality/nonconforming/index.uvue`：列表反馈与处置状态分离；处置按钮显示忙碌反馈；等待期间禁止改备注、改处置、返回列表和重复请求；成功后关闭详情并刷新列表，失败后保留详情并解锁。
- `features/quality/components/inspection-board.uvue`：列表首次／刷新反馈，图片上传局部反馈，提交按钮忙碌反馈；输入与既有选择按钮同步锁定；保留离开确认及全部业务校验。
- `tests/p2.test.cjs`：新增旧请求丢弃、刷新等待、输入锁定、处置失败解锁及成功刷新回归。

复用公共组件的 160ms 延迟与 8 秒慢请求提示；不新增 CSS 动画、依赖或后端接口。自定义字段读取沿用已有逻辑，本批未改变其请求处理。

实际执行：`node --test tests/p0.test.cjs tests/p1.test.cjs tests/p1-structure.test.cjs tests/p2.test.cjs`，50 项通过，0 失败；`git diff --check` 通过。未执行 HBuilderX 编译与真机验证，未提交 Git。真机重点：检验上传和提交反馈、输入锁定、处置成功后的列表刷新、短请求闪烁及离开确认。

后续仍有生产报工／指派／异常／装箱／记录、账号／登录初始化／功能分组，以及导航转场策略。
