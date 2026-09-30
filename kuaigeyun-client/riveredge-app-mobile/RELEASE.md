# 发行说明

业务页不按下列门槛分叉。数字来自设计 `docs/03.design/21.mobile-uni-app-x-plan.md` 第 3 节。

- Android 蒸汽模式最低 Android 6.0+（HBuilderX 5.21+）
- iOS 最低 iOS 15+（HBuilderX 5.11+）
- 微信基础库大于 3.7.1

H5 路由在 `manifest.json` 的 `web.router`：`mode` 为 `history`，`base` 为 `/mobile/`。字段名见 [uni-app x manifest](https://doc.dcloud.net.cn/uni-app-x/collocation/manifest.html) 的 Web 配置。

发行 Web 使用本机 HBuilderX。本仓库的 `fast-deploy/launch.dev.sh with-h5` 不编译 uni-app x。
