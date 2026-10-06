# 移动端 P2 方案 B 验证记录

日期：2026-10-06。影响端：riveredge-app-mobile。采用现有 uni-app x 技术栈，复用已安装的 uni-ui x 控件及原生控件，无新增依赖、后端或 PC 修改。

## 修改文件与职责

路径相对移动端工程根目录。

| 文件 | 改动 |
| --- | --- |
| shared/ui/action-button.uvue | 原生按钮统一主次操作、加载与禁用状态；press 事件在忙碌或禁用时不触发 |
| shared/ui/selection-row.uvue | 原生按钮实现选择项；显示选择状态，choose 事件受禁用与忙碌状态保护 |
| shared/ui/date-field.uvue | 原生 picker mode=date；持续标签、可选清空、错误提示，update:modelValue 只提交有效日期 |
| shared/ui/date.uts | 共用日历日期校验与本地今天日期 |
| shared/ui/status-badge.uvue | 封装已安装的 uni-badge-view；显式零值仍显示 |
| features/mold/http.uts | 日期工具移至公共层，保留原导出函数与请求契约 |
| features/mold/mold-repairs/index.uvue | 公共日期、选择与按钮；持续标签、请求期间锁定；紧急程度保留自由文本并限制 32 字符 |
| features/mold/mold-maintenances/index.uvue | 公共日期、模具与方案选择、执行项、按钮；请求期间锁定 |
| features/mold/mold-returns/index.uvue | 公共日期、借出记录选择与按钮；请求期间锁定 |
| features/equipment/components/master-picker.uvue | 复用公共选择项与查询按钮，显示当前选择 |
| shell/workbench/index.uvue | 入口使用原生按钮语义；操作按钮与待办角标复用；保留现有 SVG 图标和今日待办行为 |
| shell/apps/index.uvue | 分组、功能入口使用原生按钮语义；返回操作复用公共按钮 |
| tests/p1-structure.test.cjs | 扩展本批源文件的语法、相对导入、模板标签检查 |
| tests/p2.test.cjs | 日期、操作锁定、紧急程度与请求契约、零值角标回归 |

本批仅迁移上述页面，公共组件供后续页面逐步接入。

## 实际验证

在移动端目录执行：

```powershell
node --test tests/p0.test.cjs tests/p1.test.cjs tests/p1-structure.test.cjs tests/p2.test.cjs
```

结果：34 项通过，0 失败。脚本使用 TypeScript 转译与 VM 桩检查业务行为，并检查模板标签、相对导入；不等价于 UTS 编译或真实渲染。

在 kuaigeyun-mes Git 根目录执行 `git diff --check`：退出码 0。

## 尚未验证

当前未执行 HBuilderX 编译或真机测试。发布前需检查目标平台的按钮布局、焦点与读屏、日期选择取消及清空、禁用交互、长文案滚动，以及零值角标渲染。未提交 Git。

## 第二批：扩展到其他页面

沿用方案 B，修改以下 28 个页面或组件。表内目录相对工程根；除模具领用的状态守卫外，业务脚本仅增加组件导入，操作仍调用原函数。筛选按钮、复杂卡片、登录页保持现有布局。

| 目录 | 修改文件 | 内容 |
| --- | --- | --- |
| features/workshop/ | exception-report、my-work-orders、packing-binding、reporting-approve、scan-report、work-order-assign、work-orders 下的 index.uvue | 查询、返回、提交等主次操作复用公共按钮，保留原标签与禁用条件 |
| features/equipment/ | detail、faults、line-rebinds、maintenance-executions、maintenance-reminders、repairs、route-patrols、scan、spot-check-conduct、spot-checks 下的 index.uvue，以及 components/master-picker.uvue | 查询、扫码、照片、提交等操作复用按钮；点检与巡检使用可选日期字段 |
| features/mold/ | mold-borrows、mold-reminders、mold-scan 下的 index.uvue | 操作按钮；领用的两个日期、模具选择、持续标签和请求期间锁定，防止重复提交 |
| features/quality/ | components/inspection-board.uvue，nonconforming、quality-hub 下的 index.uvue | 查询、执行、阶段导航、提交、处置按钮；共用检验组件覆盖使用它的检验页面 |
| features/warehouse/ | board.uvue | 刷新、分页、编辑、步骤导航与确认按钮；覆盖共用此组件的仓储页面 |
| shell/ | account/edit.uvue、account/password.uvue、tenant/index.uvue | 头像、保存与组织识别确认操作复用按钮 |

新增验证：模具领用非法日期拒绝、可选日期不发送字段、重复请求锁定及结束解锁；设备可选日期模型与禁用条件。结构检查新增本批文件，并检查模板绑定表达式语法。

再次执行上文完整 Node 命令：36 项通过，0 失败。再次执行 `git diff --check`：退出码 0。仍未执行 HBuilderX 或真机验证，未修改依赖与接口契约，未提交 Git。

## 第三批：登录、账号、公共导航与质量判断

| 文件 | 改动 |
| --- | --- |
| shared/ui/choice-button.uvue（新增） | 紧凑原生选择按钮，横向排列，显示选中标记，禁用时不发送 choose；实际单选和多选规则由调用方保留 |
| shell/login/index.uvue | 登录、企业微信登录、组织搜索、设置复用公共操作按钮；组织列表复用选择项；登录和组织搜索互斥，锁定请求期间的组织选择和相关输入；页面支持纵向滚动 |
| shell/account/index.uvue | 编辑、密码、绑定、解绑和退出操作改用原生按钮，保留原信息布局、条件展示与确认流程；加载或绑定操作期间禁用 |
| shared/ui/home-link.uvue | 返回、首页改为原生按钮；保留 holdHome 事件拦截与 navigateBack 行为 |
| features/quality/components/inspection-board.uvue | 结果、质量状态、放行、整体判断、步骤判断、单选、多选、不适用接入公共选择按钮；附件和照片增删、取消操作复用公共按钮；提交或上传期间锁定选择及附件修改 |
| features/quality/nonconforming/index.uvue | 处置选项复用公共选择按钮，处理期间禁止切换 |
| tests/p1-structure.test.cjs | 纳入新增和本批源文件 |
| tests/p2.test.cjs | 新增紧凑选择禁用、登录互斥、质量单选清空和多选、上传锁定、导航首页拦截、账号确认取消回归 |

实际执行完整 Node 命令：41 项通过，0 失败；`git diff --check` 通过。没有后端、PC、依赖或接口契约修改，未提交 Git。检查仍为源代码与 VM 状态回归，未执行 HBuilderX 编译或真实 UI 渲染。

真机补验重点：登录键盘与滚动、组织长名称、导航标题与两侧按钮、账号操作行和解绑按钮布局、质量选项横向换行和长文案、选择状态、上传期间禁用、检验离开确认。

后续可继续统一生产/设备/仓储的筛选与复杂卡片、异常追踪的类型筛选。我的报工和我的绩效为只读列表，无本批操作按钮可直接迁移。

## 第四批：剩余筛选与业务卡片（源码迁移收尾）

| 文件／目录 | 改动 |
| --- | --- |
| shared/ui/action-card.uvue（新增） | 带默认插槽的公共原生操作卡片，卡片与列表行两种外观，禁用时不触发 press；保留调用方的内容和选择规则 |
| shared/ui/action-button.uvue | 增加默认关闭的 compact 属性，供行内查询和移除操作复用 |
| features/workshop/ | exception-report、exceptions、my-work-orders、work-orders、work-order-assign、packing-binding、scan-report 下的 index.uvue：筛选复用 choice-button，业务卡片复用 action-card，保留原标签、选项值和处理函数 |
| features/equipment/ | faults、repairs、maintenance-reminders 下的 index.uvue：故障类型、级别、维修结果与可操作记录复用公共控件 |
| features/warehouse/board.uvue | 查询、序列号移除复用紧凑操作按钮；库存预警处理状态复用选择按钮；单据卡片复用 action-card |
| features/quality/ | nonconforming、quality-hub 下的 index.uvue：单据卡片复用 action-card |
| features/mold/mold-scan/index.uvue | 扫码结果入口复用列表行式 action-card |
| shell/workbench/index.uvue | 补齐加载或失败状态下设置入口的公共按钮接入，保留原显示条件 |
| tests/p1-structure.test.cjs、tests/p2.test.cjs | 新增组件结构检查、卡片禁用回归，以及全部注册页面和其本地组件的可点击 view/text 遗漏检查 |

实际运行完整 Node 命令：43 项通过，0 失败；`git diff --check` 退出码 0。覆盖检查遍历当前 51 个注册页面及其本地组件，没有剩余以可点击 view/text 实现的操作控件。图片预览继续使用原生 image 交互；账号和工作台等定制布局保留原生 button。只读报工和绩效页面无需新增操作控件。

本轮方案 B 的操作、选择、日期、角标、导航与业务卡片源码迁移完成。没有后端、接口契约或依赖修改，未提交 Git。该结论不代表 UI 已通过平台验收：HBuilderX 编译、真机布局、卡片插槽内容样式、选项换行、禁用反馈与读屏仍未验证。
