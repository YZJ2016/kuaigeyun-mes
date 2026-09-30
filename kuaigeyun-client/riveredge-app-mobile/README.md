# riveredge-app-mobile

星制造移动端 uni-app x 蒸汽模式工程。与 `riveredge-app-station` 同级，由本仓 `kuaigeyun-mes` 跟踪，目录下不另建 Git。

用 HBuilderX 打开本目录。`manifest.json` 含 `"uni-app-x"` 且 `"vapor": true`。发行 Web 产物在 `unpackage/dist/build/web`，不提交；部署机复制该目录到 Caddy `/mobile`。版本门槛见 `RELEASE.md`。

本机若要其他接口源，改 shared/api/origin.uts 的 API_ORIGIN，不要把地址提交。origin.local.uts 已被忽略且没有被导入。
