# riveredge-app-station

工位机 Electron 壳。Electron **44.4.5**。窗口用 `loadURL` 打开服务器上的工位入口，安装包只含壳，不包含工位业务页面。

入口路径固定为 `/apps/kuaizhizao/production-execution/station`，并带查询参数 `workstationId`。服务器源来自本机，不写进仓库。

## 本机配置

服务器源按下面顺序取值：

- 环境变量 `STATION_SERVER_ORIGIN`，值为 `http` 或 `https` 源（不要带用户名、口令或路径）。已设置时直接打开工位。
- 本机文件 `%APPDATA%\riveredge-app-station\station-shell.json` 的 `serverOrigin`。
- 两者都没有时不退出。全屏打开配置页，由安装人员填写地址。页面先访问工位入口做连通性测试，通过后才把 `serverOrigin` 写入上述本机文件，然后打开工位。

工位 ID 由页面调用 `window.stationShell.setWorkstationId(id)` 写入同一文件的 `workstationId`。`window.stationShell.getWorkstationId()` 只返回该已保存的工位 ID。下次启动时该值进入上述 URL 查询参数。`window.stationShell` 标明这是工位端。

`config.example.json` 只说明字段形状。把地址填进本机文件或环境变量，不要把填好的地址提交进仓库。

## 运行

```bash
npm install
npm start
```

未打包运行不注册开机启动，并清掉开发态已经写入的登录启动项。打包后的工位机仍在当前用户登录后自启。

扫码枪按键盘输入交给页面焦点。壳不解析条码。

工位页加载失败（服务器不可达或已迁移）时不会停在黑窗，壳会回到配置页，可重试或改地址。壳拒绝页面新开窗口，并阻止跳出已配置源的站外导航。

本目录没有 exe 打包脚本。未打包 exe，未跑安装。
